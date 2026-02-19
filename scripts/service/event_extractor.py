"""
EventExtractor — LLM-based competition event extraction service.

Wraps the GPT-4o-mini call from website.py as a reusable class that accepts
raw post/page content in a unified format and returns structured event dicts
matching the schema defined in prompts.EXTRACTION_PROMPT.
"""

import json
import textwrap
from pathlib import Path

from dotenv import dotenv_values
from openai import AsyncOpenAI

from .prompts import EXTRACTION_PROMPT, MERGE_PROMPT


class EventExtractor:
    """
    LLM-based event extractor backed by OpenAI.

    Parameters
    ----------
    env_file : Path
        .env file containing OPENAI_API_KEY.
    model : str
        OpenAI model to use (default: gpt-4o-mini).
    """

    def __init__(
        self,
        env_file: Path,
        model: str = "gpt-4o-mini",
    ) -> None:
        cfg = dotenv_values(str(env_file))
        self.client = AsyncOpenAI(api_key=cfg.get("OPENAI_API_KEY"))
        self.model = model

    # ── Core extraction ───────────────────────────────────────────────────────

    async def extract(
        self,
        content: str,
        source_url: str,
        platform: str = "website",
        date_posted: str | None = None,
    ) -> tuple[list[dict], dict]:
        """
        Run the extraction prompt over *content* and return
        ``(events, token_summary)``.

        Parameters
        ----------
        content : str
            The raw text / markdown to extract from.
        source_url : str
            URL of the original source (included in the prompt).
        platform : str
            One of 'instagram', 'website', 'facebook', 'others'.
        date_posted : str | None
            ISO 8601 calendar date of the post, forwarded to the model for
            context.
        """

        header_parts = [
            f"Source URL: {source_url}",
            f"Platform: {platform}",
        ]
        if date_posted:
            header_parts.append(f"Date posted: {date_posted}")

        prompt = textwrap.dedent(
            f"""
            {chr(10).join(header_parts)}

            --- BEGIN CONTENT ---
            {content}
            --- END CONTENT ---
        """
        ).strip()

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )

        usage = response.usage
        token_summary = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        }

        raw = response.choices[0].message.content.strip()
        events = json.loads(raw)
        return events, token_summary

    # ── Post helpers ─────────────────────────────────────────────────────────

    async def extract_post(self, post: dict) -> tuple[list[dict], dict]:
        """
        Extract events from a single post dict.
        Supports any platform — expected keys:
            url, platform, caption, media_urls, timestamp (ISO 8601 | None)
        """
        # Build a compact text representation of the post
        lines = []
        if post.get("caption"):
            lines.append(post["caption"])
        if post.get("media_urls"):
            lines.append("\nMedia:")
            for url in post["media_urls"]:
                lines.append(f"  {url}")

        content = "\n".join(lines).strip() or "(no caption)"

        # Derive a calendar date from the ISO timestamp for the model's context
        ts = post.get("timestamp") or ""
        date_posted = ts[:10] or None

        return await self.extract(
            content=content,
            source_url=post.get("url", ""),
            platform=post.get("platform", "others"),
            date_posted=date_posted,
        )

    async def extract_all_posts(self, posts: list[dict]) -> tuple[list[dict], dict]:
        """
        Run extract_post() over every post in *posts* sequentially.

        Returns ``(all_events, cumulative_token_summary)`` where all_events is
        the flat list of every event found across all posts.
        """
        all_events: list[dict] = []
        total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for i, post in enumerate(posts, 1):
            shortcode = post.get("shortcode") or post.get("url", "?")
            print(f"  [llm] {i}/{len(posts)}  {post.get('url', shortcode)}")
            try:
                events, summary = await self.extract_post(post)
                if events:
                    print(f"         → {len(events)} event(s) found")
                    all_events.extend(events)
                else:
                    print("         → no qualifying events")
                for k in total_tokens:
                    total_tokens[k] += summary[k]
            except Exception as exc:
                print(f"         [warn] extraction failed: {exc}")

        return all_events, total_tokens

    async def merge_events(self, events: list[dict]) -> tuple[list[dict], dict]:
        """
        Group a flat list of extracted event records by real-world event identity.

        Sends all records in a single LLM call using MERGE_PROMPT and returns
        ``(merged_events, token_summary)`` where merged_events is a list of
        consolidated event objects each containing a ``posts`` array of the
        original source records that were grouped together.
        """
        if not events:
            empty_tokens = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            return [], empty_tokens

        print(f"\n[merge] Merging {len(events)} extracted record(s) …")

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": MERGE_PROMPT},
                {"role": "user", "content": json.dumps(events, ensure_ascii=False)},
            ],
            temperature=0,
        )

        usage = response.usage
        token_summary = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        }

        raw = response.choices[0].message.content.strip()
        merged = json.loads(raw)

        if not merged:
            print(
                f"[merge] LLM signalled no merging needed — "
                f"keeping original {len(events)} record(s) as-is."
            )
            return events, token_summary

        print(f"[merge] {len(events)} record(s) → {len(merged)} event(s)")
        return merged, token_summary

    # ── Output helpers ────────────────────────────────────────────────────────

    def save_events(self, events: list[dict], output_path: Path | str) -> None:
        """Serialise *events* to *output_path* as pretty-printed JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(events, indent=2, ensure_ascii=False))
        print(f"\n[export] Saved {len(events)} event(s) \u2192 {output_path}")

    def get_stat(self, token_summary: dict) -> None:
        """Print a formatted summary of *token_summary* from an extraction call."""
        print("\n--- Token Usage ---")
        print(f"  Prompt tokens:     {token_summary['prompt_tokens']}")
        print(f"  Completion tokens: {token_summary['completion_tokens']}")
        print(f"  Total tokens:      {token_summary['total_tokens']}")

#!/usr/bin/env python3
"""
CLI for running LLM extraction over posts stored in PostgreSQL.

Reads all unprocessed posts (those with no linked raw_events yet) for a given
gym from the database, runs the LLM extraction pipeline, and writes the
results back to PostgreSQL.

Usage:
    python scripts/parse.py --gym hyperion-climbing
    python scripts/parse.py --gym hyperion-climbing --include-org-posts
    python scripts/parse.py --gym hyperion-climbing --output data/hyperion_events.json

The --output flag is optional and saves a debug JSON copy; the DB is always the
primary destination.

--include-org-posts: also processes posts scraped from the gym's parent
organization account (e.g. @touchstoneclimbing) that haven't yet been parsed
for this gym. The gym's organization is looked up from data/source/gyms.json.

To merge extracted events, run:
    python scripts/merge.py --gym hyperion-climbing
"""

import argparse
import asyncio
import json
from pathlib import Path

from service.db import (
    bulk_insert_raw_events,
    connect,
    ensure_gym,
    get_unprocessed_org_posts,
    get_unprocessed_posts,
)
from service.event_extractor import EventExtractor

_ENV_FILE = Path(__file__).parent.parent / ".env"
_GYMS_FILE = Path(__file__).parent.parent / "data" / "source" / "gyms.json"


def _get_org_slug(gym_slug: str) -> str | None:
    """Return the org slug for *gym_slug* from gyms.json, or None if independent."""
    gyms: list[dict] = json.loads(_GYMS_FILE.read_text())
    for entry in gyms:
        if entry.get("slug") == gym_slug:
            org_name: str | None = entry.get("organization")
            if org_name:
                return org_name.lower().replace(" ", "-")
            return None
    raise SystemExit(
        f"[error] Gym slug '{gym_slug}' not found in gyms.json."
    )


def _get_org_name(gym_slug: str) -> str | None:
    """Return the raw organization name for *gym_slug*, or None if independent."""
    gyms: list[dict] = json.loads(_GYMS_FILE.read_text())
    for entry in gyms:
        if entry.get("slug") == gym_slug:
            return entry.get("organization") or None
    return None


def _get_gym_context(gym_slug: str) -> dict | None:
    """Return {"name": ..., "city": ...} for *gym_slug* from gyms.json, or None."""
    gyms: list[dict] = json.loads(_GYMS_FILE.read_text())
    for entry in gyms:
        if entry.get("slug") == gym_slug:
            name = entry.get("name") or ""
            city = entry.get("city") or ""
            return {"name": name, "city": city}
    return None


async def main(gym: str, output_path: Path | None, include_org_posts: bool) -> None:
    # ── Load unprocessed posts from DB ────────────────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        posts = get_unprocessed_posts(cur, gym)

        org_posts: list[dict] = []
        if include_org_posts:
            org_slug = _get_org_slug(gym)
            org_name = _get_org_name(gym)
            gym_ctx = _get_gym_context(gym)
            gym_name = (gym_ctx or {}).get("name", "")
            if org_name and gym_name and org_name.lower() == gym_name.lower():
                print(
                    f"[parse] '{gym}' is its own organisation ('{org_name}') "
                    f"— skipping org posts to avoid duplicates."
                )
            elif org_slug:
                org_posts = get_unprocessed_org_posts(cur, org_slug, gym_id)
                print(
                    f"[parse] Found {len(org_posts)} unprocessed org post(s) "
                    f"for org '{org_slug}' → gym '{gym}'"
                )
            else:
                print(f"[parse] '{gym}' has no parent organization — skipping org posts.")

        conn.commit()
    finally:
        conn.close()

    # Tag org posts so the extraction loop can apply the gym-context filter.
    # Also tag gym posts that were scraped from an org account (organization_id
    # is set) — those need the same filter even though they live in the gym's
    # own post list (e.g. --profile touchstoneclimbing --gym hyperion-climbing).
    for p in org_posts:
        p["_is_org_post"] = True
    for p in posts:
        if p.get("organization_id") is not None:
            p["_is_org_post"] = True

    # Deduplicate by post id (gym posts take precedence, org posts fill in the rest)
    seen_ids: set[int] = {p["id"] for p in posts}
    posts = posts + [p for p in org_posts if p["id"] not in seen_ids]

    if not posts:
        print(f"[parse] No unprocessed posts found for '{gym}' — nothing to do.")
        return

    print(f"[parse] Found {len(posts)} unprocessed post(s) for '{gym}' (total)")

    # ── LLM extraction + per-post DB insert ───────────────────────────────────
    from service.prompts import build_extraction_prompt
    extractor = EventExtractor(env_file=_ENV_FILE)
    gym_context = _get_gym_context(gym)

    if gym_context and include_org_posts:
        print("\n[parse] ── gym-context filter prompt (appended for org posts) ──")
        print(build_extraction_prompt(gym_context))
        print("[parse] ────────────────────────────────────────────────────────\n")

    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    all_events: list[dict] = []
    total_inserted = 0

    for i, post in enumerate(posts, 1):
        is_org_post = post.get("_is_org_post", False)
        ctx = gym_context if is_org_post else None
        print(f"  [llm] {i}/{len(posts)}  {post.get('url', '?')}{' [org→gym filter]' if is_org_post else ''}")
        try:
            events, summary = await extractor.extract_post(post, gym_context=ctx)
        except Exception as exc:
            print(f"         [warn] extraction failed: {exc}")
            continue

        # Python-side safety net for org posts: drop any event whose location
        # clearly belongs to a different gym.  We accept the event if:
        #   • location is null/empty (LLM couldn't determine it), OR
        #   • location contains the gym name or city (case-insensitive).
        if is_org_post and gym_context:
            gym_name_lower = (gym_context.get("name") or "").lower()
            gym_city_lower = (gym_context.get("city") or "").lower()
            filtered: list[dict] = []
            for ev in events:
                loc = (ev.get("location") or "").lower()
                if not loc or gym_name_lower in loc or gym_city_lower in loc:
                    filtered.append(ev)
                else:
                    print(f"         [filter] dropped '{ev.get('event_name')}' — location '{ev.get('location')}' ≠ target gym")
            if len(filtered) < len(events):
                print(f"         [filter] {len(events) - len(filtered)} event(s) removed by location filter")
            events = filtered

        for k in total_tokens:
            total_tokens[k] += summary[k]

        if events:
            print(f"         → {len(events)} event(s) found")
        else:
            print("         → no qualifying events")
            continue

        all_events.extend(events)

        # Insert this post's events immediately
        url_map: dict[str, int] = (
            {post["url"]: post["id"]} if post.get("url") and post.get("id") else {}
        )
        conn = connect()
        try:
            cur = conn.cursor()
            gym_id = ensure_gym(cur, gym)
            ids = bulk_insert_raw_events(cur, gym_id, events, url_to_post_id=url_map)
            conn.commit()
            total_inserted += len(ids)
            print(f"         → {len(ids)} raw_event(s) inserted (gym_id={gym_id})")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    extractor.get_stat(total_tokens)
    print(f"\n[db] Total raw_event(s) inserted: {total_inserted}")

    # ── Optional debug JSON export ────────────────────────────────────────────
    if output_path:
        extractor.save_events(all_events, output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract competition events from DB posts and store raw_events in PostgreSQL."
    )
    parser.add_argument(
        "--gym",
        required=True,
        help="Gym slug to process (e.g. mosaicboulders)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to save a debug JSON copy of the extracted events.",
    )
    parser.add_argument(
        "--include-org-posts",
        action="store_true",
        help=(
            "Also parse unprocessed posts from the gym's parent organization account "
            "(looked up from data/source/gyms.json). Posts already parsed for this gym "
            "are skipped automatically."
        ),
    )
    args = parser.parse_args()

    asyncio.run(main(args.gym, args.output, args.include_org_posts))

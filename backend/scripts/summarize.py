#!/usr/bin/env python3
"""
Regenerate the summary for a single merged event using all of its linked
raw_events (including the original post captions).

The LLM synthesises a comprehensive, organizer-voiced description that covers
format, categories, prizes, schedule, and other details found across the posts.
The resulting summary is written back to the ``events`` table.  The LLM's
reasoning (``reason``) is printed to the terminal but not stored.

Usage:
    python scripts/summarize.py --gym mosaic-boulders \\
        --event-name "Telegraph Turn-Up 2026"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import dotenv_values
from openai import AsyncOpenAI

from service.db import (
    connect,
    ensure_gym,
    get_event_by_name,
    get_raw_events_for_event,
    update_event_summary,
)
from service.prompts import SUMMARIZE_PROMPT, build_summarize_prompt_input

_ENV_FILE = Path(__file__).parent.parent / ".env"


async def main(gym: str, event_name: str) -> None:
    # ── Look up event ─────────────────────────────────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        event = get_event_by_name(cur, gym_id, event_name)
        if event is None:
            print(
                f'[error] No event named "{event_name}" found for gym "{gym}".\n'
                f"        Check the spelling or use the exact event_name from the events table."
            )
            sys.exit(1)

        raw_events = get_raw_events_for_event(cur, event["id"])
        conn.commit()
    finally:
        conn.close()

    print(f'[summarize] Event: "{event["event_name"]}"  (id={event["id"]})')
    print(f"[summarize] Found {len(raw_events)} linked raw_event(s)")

    if not raw_events:
        print("[summarize] No raw_events linked to this event — nothing to summarize.")
        sys.exit(0)

    # ── Build LLM input ───────────────────────────────────────────────────────
    user_content = build_summarize_prompt_input(event["event_name"], raw_events)

    # ── Call LLM ──────────────────────────────────────────────────────────────
    cfg = dotenv_values(str(_ENV_FILE))
    client = AsyncOpenAI(api_key=cfg.get("OPENAI_API_KEY"))

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SUMMARIZE_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )

    usage = response.usage
    print("--- Token Usage ---")
    print(f"  Prompt tokens:     {usage.prompt_tokens}")
    print(f"  Completion tokens: {usage.completion_tokens}")
    print(f"  Total tokens:      {usage.total_tokens}\n")

    raw = response.choices[0].message.content.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[error] LLM returned invalid JSON: {exc}\n{raw}")
        sys.exit(1)

    new_summary: str = result.get("summary") or ""
    reason: str = result.get("reason") or ""

    if not new_summary:
        print("[error] LLM returned an empty summary — aborting without updating DB.")
        sys.exit(1)

    # ── Print reason (terminal only) ──────────────────────────────────────────
    print(f"[summarize] Reason: {reason}\n")

    # ── Show diff ─────────────────────────────────────────────────────────────
    old_summary = event.get("summary") or "(none)"
    print("── Old summary ──────────────────────────────────────────────────────")
    print(old_summary)
    print("── New summary ──────────────────────────────────────────────────────")
    print(new_summary)
    print("─────────────────────────────────────────────────────────────────────\n")

    # ── Write to DB ───────────────────────────────────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        update_event_summary(cur, event["id"], new_summary)
        conn.commit()
        print(f"[db] Updated summary for event id={event['id']}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Regenerate the summary for a merged event from its raw post captions."
    )
    parser.add_argument(
        "--gym",
        required=True,
        help="Gym slug (e.g. mosaic-boulders)",
    )
    parser.add_argument(
        "--event-name",
        required=True,
        help='Exact (case-insensitive) event_name from the events table, e.g. "Telegraph Turn-Up 2026"',
    )
    args = parser.parse_args()

    asyncio.run(main(args.gym, args.event_name))

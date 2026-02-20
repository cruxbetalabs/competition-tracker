#!/usr/bin/env python3
"""
CLI for running LLM extraction over posts stored in PostgreSQL.

Reads all unprocessed posts (those with no linked raw_events yet) for a given
gym from the database, runs the LLM extraction pipeline, and writes the
results back to PostgreSQL.

Usage:
    python scripts/parse.py --gym mosaicboulders
    python scripts/parse.py --gym mosaicboulders --output data/mosaicboulders_events.json

The --output flag is optional and saves a debug JSON copy; the DB is always the
primary destination.

To merge extracted events, run:
    python scripts/merge.py --gym mosaicboulders
"""

import argparse
import asyncio
from pathlib import Path

from service.db import (
    bulk_insert_raw_events,
    connect,
    ensure_gym,
    get_unprocessed_posts,
)
from service.event_extractor import EventExtractor

_ENV_FILE = Path(__file__).parent.parent / ".env"


async def main(gym: str, output_path: Path | None) -> None:
    # ── Load unprocessed posts from DB ────────────────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        posts = get_unprocessed_posts(cur, gym)
        conn.commit()
    finally:
        conn.close()

    if not posts:
        print(f"[parse] No unprocessed posts found for '{gym}' — nothing to do.")
        return

    print(f"[parse] Found {len(posts)} unprocessed post(s) for '{gym}'")

    # ── LLM extraction + per-post DB insert ───────────────────────────────────
    extractor = EventExtractor(env_file=_ENV_FILE)
    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    all_events: list[dict] = []
    total_inserted = 0

    for i, post in enumerate(posts, 1):
        print(f"  [llm] {i}/{len(posts)}  {post.get('url', '?')}")
        try:
            events, summary = await extractor.extract_post(post)
        except Exception as exc:
            print(f"         [warn] extraction failed: {exc}")
            continue

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
    args = parser.parse_args()

    asyncio.run(main(args.gym, args.output))

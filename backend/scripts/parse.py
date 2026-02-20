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

    # ── LLM extraction ────────────────────────────────────────────────────────
    extractor = EventExtractor(env_file=_ENV_FILE)
    events, token_summary = await extractor.extract_all_posts(posts)
    extractor.get_stat(token_summary)

    # ── Optional debug JSON export ────────────────────────────────────────────
    if output_path:
        extractor.save_events(events, output_path)

    # ── Export to DB (always) ─────────────────────────────────────────────────
    # Build url → post_id map from the posts we just loaded (they carry their DB id).
    url_map: dict[str, int] = {
        p["url"]: p["id"] for p in posts if p.get("url") and p.get("id")
    }

    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        ids = bulk_insert_raw_events(
            cur, gym_id, events, url_to_post_id=url_map, gym=gym
        )
        conn.commit()
        print(
            f"[db] Inserted {len(ids)} raw_event(s) into PostgreSQL  (gym_id={gym_id})"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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

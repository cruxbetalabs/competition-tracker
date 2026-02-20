#!/usr/bin/env python3
"""
CLI for merging unmerged raw_events stored in PostgreSQL.

Reads all unmerged raw_events (event_id IS NULL) for a given gym from
the database, consolidates duplicates/related events via an LLM merge pass, and
writes the resulting merged events back into PostgreSQL.  The raw_events are
updated in-place to reference their new parent event.

Usage:
    python scripts/merge.py --gym mosaicboulders
    python scripts/merge.py --gym mosaicboulders --output data/mosaicboulders_events_merged.json

The --output flag is optional and saves a debug JSON copy; the DB is always the
primary destination.
"""

import argparse
import asyncio
from pathlib import Path

from service.db import (
    connect,
    ensure_gym,
    get_unmerged_raw_events,
    insert_event,
    link_raw_events,
)
from service.event_extractor import EventExtractor

_ENV_FILE = Path(__file__).parent.parent / ".env"


async def main(gym: str, output_path: Path | None) -> None:
    # ── Load unmerged raw_events from DB ──────────────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        raw_events = get_unmerged_raw_events(cur, gym)
        conn.commit()
    finally:
        conn.close()

    if not raw_events:
        print(f"[merge] No unmerged raw_events found for '{gym}' — nothing to do.")
        return

    print(f"[merge] Found {len(raw_events)} unmerged raw_event(s) for '{gym}'")

    # ── LLM merge ─────────────────────────────────────────────────────────────
    extractor = EventExtractor(env_file=_ENV_FILE)
    merged, token_summary = await extractor.merge_events(raw_events)
    extractor.get_stat(token_summary)

    if not merged:
        print("[merge] Nothing to write — raw_events remain unmerged.")
        return

    # ── Optional debug JSON export ────────────────────────────────────────────
    if output_path:
        extractor.save_events(merged, output_path)

    # ── Export to DB (always) ─────────────────────────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        for ev in merged:
            event_id = insert_event(cur, gym_id, ev)
            # Each merged event carries the contributing raw events in "posts".
            # They came from DB, so each dict has an "id" field.
            raw_ids = [
                r["id"] for r in (ev.get("posts") or []) if r.get("id") is not None
            ]
            link_raw_events(cur, event_id, raw_ids)
        conn.commit()
        print(
            f"[db] Inserted {len(merged)} event(s) into PostgreSQL  (gym_id={gym_id})"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge unmerged raw_events from PostgreSQL into consolidated events."
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
        help="Optional path to save a debug JSON copy of the merged events.",
    )
    args = parser.parse_args()

    asyncio.run(main(args.gym, args.output))

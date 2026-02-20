#!/usr/bin/env python3
"""
CLI for manually merging events stored in PostgreSQL.

Folds one or more source records (--from) into a target record (--to),
using the target's event_name as canonical. No LLM is involved.

The --from and --to values are the database ``id`` (primary key) of the
events rows (the merged events table), not raw_events.

Usage:
    # Fold event id 35 into id 32
    python scripts/merge_manual.py --gym bridgesrockgym --to 32 --from 35

    # Multiple merge operations in one run (applied sequentially)
    python scripts/merge_manual.py --gym bridgesrockgym \\
        --to 32 --from 35 \\
        --to 10 --from 11 12

    # Also write a debug JSON copy
    python scripts/merge_manual.py --gym bridgesrockgym --to 32 --from 35 \\
        --output data/bridgesrockgym_events_merged.json
"""

import argparse
import sys
from pathlib import Path

from service.db import (
    connect,
    delete_events,
    ensure_gym,
    get_events_by_ids,
    insert_event,
    link_raw_events,
)
from service.event_extractor import EventExtractor
from service.merge_executor import manual_merge


def parse_ops(args_to: list[int], args_from: list[list[int]]) -> list[dict]:
    """
    Zip paired --to / --from argument groups into operation dicts.

    argparse collects each --to and --from independently; we pair them
    positionally so the i-th --to matches the i-th --from group.
    """
    if len(args_to) != len(args_from):
        print(
            f"[error] Number of --to values ({len(args_to)}) must match "
            f"number of --from groups ({len(args_from)})."
        )
        sys.exit(1)
    return [{"to": t, "from": f} for t, f in zip(args_to, args_from)]


def main(gym: str, output_path: Path | None, ops: list[dict]) -> None:
    # ── Collect all referenced event IDs across every op ─────────────────────
    all_ids: list[int] = []
    for op in ops:
        all_ids.append(op["to"])
        all_ids.extend(op["from"])

    # ── Fetch those events from DB (with their linked raw_events as posts) ────
    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        events = get_events_by_ids(cur, all_ids)
        conn.commit()
    finally:
        conn.close()

    if not events:
        print("[merge_manual] None of the requested event IDs found — nothing to do.")
        return

    found_ids = {e["id"] for e in events}
    missing = [i for i in all_ids if i not in found_ids]
    if missing:
        print(f"[merge_manual] Warning: event IDs not found in DB: {missing}")

    print(f"[merge_manual] Loaded {len(events)} event(s) for manual merge")

    # ── Apply manual merge operations sequentially ────────────────────────────
    for op in ops:
        to_id: int = op["to"]
        from_ids: list[int] = op["from"]
        events = manual_merge(events, from_ids=from_ids, to_id=to_id)

    # ── Optional debug JSON export ────────────────────────────────────────────
    if output_path:
        extractor = EventExtractor(env_file=Path(__file__).parent.parent / ".env")
        extractor.save_events(events, output_path)

    # ── Replace old event rows with merged result ─────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        # Delete originals — raw_events.event_id → NULL via ON DELETE SET NULL
        delete_events(cur, list(found_ids))
        # Insert merged events and re-link their raw_events
        for ev in events:
            event_id = insert_event(cur, gym_id, ev)
            raw_ids = [
                r["id"] for r in (ev.get("posts") or []) if r.get("id") is not None
            ]
            link_raw_events(cur, event_id, raw_ids)
        conn.commit()
        print(
            f"[db] Replaced {len(found_ids)} event(s) → "
            f"{len(events)} merged event(s)  (gym_id={gym_id})"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manually merge events from PostgreSQL by folding source events into a target.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    parser.add_argument(
        "--to",
        type=int,
        action="append",
        default=[],
        metavar="ID",
        help="Database id of the target (destination) event. Repeatable.",
    )
    parser.add_argument(
        "--from",
        type=int,
        nargs="+",
        action="append",
        default=[],
        dest="from_",
        metavar="ID",
        help="Database id(s) of events to fold into --to. Repeatable.",
    )
    args = parser.parse_args()

    if not args.to:
        parser.error("At least one --to / --from pair is required.")

    ops = parse_ops(args.to, args.from_)

    main(args.gym, args.output, ops)

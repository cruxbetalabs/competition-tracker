#!/usr/bin/env python3
"""
Unified merge CLI for competition-tracker.

Two modes, selected automatically by the presence of --to / --from:

──  AUTO MERGE (no --to / --from)  ─────────────────────────────────────────
    Reads all unmerged raw_events (event_id IS NULL) for the given gym from the
    database, consolidates duplicates via an LLM merge pass, and writes the
    resulting merged events back into PostgreSQL.

        python scripts/merge.py --gym mosaic-boulders
        python scripts/merge.py --gym mosaic-boulders --output data/mosaic_merged.json

──  MANUAL MERGE (--to and --from required together)  ──────────────────────
    Folds one or more source events (--from) into a target event (--to) using
    the target's event_name as canonical. No LLM is involved.
    The IDs refer to the ``events`` table (merged events), not raw_events.

        python scripts/merge.py --gym mosaic-boulders --to 32 --from 35
        python scripts/merge.py --gym mosaic-boulders \\
            --to 32 --from 35 \\
            --to 10 --from 11 12

The --output flag is optional in both modes and saves a debug JSON copy; the DB
is always the primary destination.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from service.db import (
    connect,
    delete_events,
    ensure_gym,
    get_events_by_ids,
    get_unmerged_raw_events,
    insert_event,
    link_raw_events,
)
from service.event_extractor import EventExtractor
from service.merge_executor import manual_merge

_ENV_FILE = Path(__file__).parent.parent / ".env"


# ── Manual merge helpers ──────────────────────────────────────────────────────


def _parse_ops(args_to: list[int], args_from: list[list[int]]) -> list[dict]:
    """Zip paired --to / --from argument groups into operation dicts."""
    if len(args_to) != len(args_from):
        print(
            f"[error] Number of --to values ({len(args_to)}) must match "
            f"number of --from groups ({len(args_from)})."
        )
        sys.exit(1)
    return [{"to": t, "from": f} for t, f in zip(args_to, args_from)]


def _run_manual(gym: str, output_path: Path | None, ops: list[dict]) -> None:
    # ── Collect all referenced event IDs ─────────────────────────────────────
    all_ids: list[int] = []
    for op in ops:
        all_ids.append(op["to"])
        all_ids.extend(op["from"])

    # ── Fetch events from DB ──────────────────────────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        ensure_gym(cur, gym)
        events = get_events_by_ids(cur, all_ids)
        conn.commit()
    finally:
        conn.close()

    if not events:
        print("[merge] None of the requested event IDs found — nothing to do.")
        return

    found_ids = {e["id"] for e in events}
    missing = [i for i in all_ids if i not in found_ids]
    if missing:
        print(f"[merge] Warning: event IDs not found in DB: {missing}")

    print(f"[merge] Loaded {len(events)} event(s) for manual merge")

    # ── Apply operations sequentially ─────────────────────────────────────────
    for op in ops:
        events = manual_merge(events, from_ids=op["from"], to_id=op["to"])

    # ── Optional debug JSON export ────────────────────────────────────────────
    if output_path:
        EventExtractor(env_file=_ENV_FILE).save_events(events, output_path)

    # ── Replace old rows with merged result ───────────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        delete_events(cur, list(found_ids))
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


# ── Auto (LLM) merge ──────────────────────────────────────────────────────────


async def _run_auto(gym: str, output_path: Path | None) -> None:
    # ── Load unmerged raw_events from DB ──────────────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        ensure_gym(cur, gym)
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

    # ── Export to DB ──────────────────────────────────────────────────────────
    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        for ev in merged:
            event_id = insert_event(cur, gym_id, ev)
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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Merge events for a gym.\n\n"
            "Without --to / --from: LLM auto-merge of all unmerged raw_events.\n"
            "With --to and --from:  manual fold of specific events table rows."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--gym",
        required=True,
        help="Gym slug to process (e.g. mosaic-boulders)",
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
        help="events.id of the target (destination) event. Repeatable.",
    )
    parser.add_argument(
        "--from",
        type=int,
        nargs="+",
        action="append",
        default=[],
        dest="from_",
        metavar="ID",
        help="events.id(s) to fold into --to. Repeatable.",
    )
    args = parser.parse_args()

    has_to = bool(args.to)
    has_from = bool(args.from_)

    if has_to != has_from:
        parser.error("--to and --from must be used together.")

    if has_to and has_from:
        ops = _parse_ops(args.to, args.from_)
        _run_manual(args.gym, args.output, ops)
    else:
        asyncio.run(_run_auto(args.gym, args.output))

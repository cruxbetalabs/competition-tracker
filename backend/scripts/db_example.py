#!/usr/bin/env python3
"""
db_example.py — connection test, schema smoke-test, and example data insertion.

Demonstrates the full three-table hierarchy:
    gyms → posts (raw scrape) → events (merged) → raw_events (LLM-parsed)

Prerequisites
-------------
    pip install psycopg2-binary

Start the database first:
    docker compose up -d

Usage:
    python scripts/db_example.py
"""

import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).parent))

from service.db import (
    bulk_insert_raw_events,
    ensure_gym,
    insert_event,
    upsert_posts,
)

# ── Connection settings ───────────────────────────────────────────────────────
DSN = (
    "host=localhost port=5432 dbname=competition_tracker user=crux password=crux_local"
)

# ── Example data ──────────────────────────────────────────────────────────────

GYM_SLUG = "example_gym"

# Raw scraped posts (*_posts.json shape)
EXAMPLE_POSTS = [
    {
        "url": "https://www.instagram.com/p/example_announce/",
        "platform": "instagram",
        "caption": "Boulder Bash 2026 is coming! April 1-2 at Example Gym. Register now!",
        "media_urls": ["https://example.com/media/flyer.jpg"],
        "timestamp": "2026-03-01T12:00:00",
    },
    {
        "url": "https://www.instagram.com/p/example_reminder/",
        "platform": "instagram",
        "caption": "Only 3 days left to sign up for Boulder Bash 2026!",
        "media_urls": [],
        "timestamp": "2026-03-29T09:00:00",
    },
]

# Merged event (*_events_merged.json shape) — "posts" are the raw LLM extractions
EXAMPLE_MERGED_EVENT = {
    "event_name": "Example Boulder Bash 2026",
    "event_date": ["2026-04-01", "2026-04-02"],
    "location": "Example Climbing Gym",
    "discipline": "bouldering",
    "type": "announcement",
    "summary": (
        "The Example Boulder Bash 2026 is a two-day bouldering competition "
        "open to all skill levels at Example Climbing Gym on April 1-2. "
        "Registration is free for members and $25 for non-members."
    ),
    "reason": "Same event, different post dates — announcement and reminder merged.",
    "posts": [
        # raw_events — one per source post that was extracted by the LLM
        {
            "event_name": "Example Boulder Bash 2026",
            "event_date": ["2026-04-01", "2026-04-02"],
            "location": "Example Climbing Gym",
            "discipline": "bouldering",
            "type": "announcement",
            "summary": "Boulder Bash 2026 is coming! April 1-2 at Example Gym.",
            "date_posted": "2026-03-01",
            "platform": "instagram",
            "url": "https://www.instagram.com/p/example_announce/",
            "raw_media": ["https://example.com/media/flyer.jpg"],
        },
        {
            "event_name": "Boulder Bash — Last chance to register!",
            "event_date": ["2026-04-01", "2026-04-02"],
            "location": "Example Climbing Gym",
            "discipline": "bouldering",
            "type": "reminder",
            "summary": "Only 3 days left to sign up for Boulder Bash 2026.",
            "date_posted": "2026-03-29",
            "platform": "instagram",
            "url": "https://www.instagram.com/p/example_reminder/",
            "raw_media": [],
        },
    ],
}


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    # ── 1. Connect ────────────────────────────────────────────────────────────
    print("Connecting …")
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT version();")
    print(f"  {cur.fetchone()[0]}\n")

    # ── 2. Verify schema ──────────────────────────────────────────────────────
    print("Checking schema …")
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name"
    )
    tables = {row[0] for row in cur.fetchall()}
    expected = {"gyms", "posts", "events", "raw_events"}
    missing = expected - tables
    if missing:
        raise RuntimeError(
            f"Missing table(s): {missing}. "
            "Make sure the container started with db/schema.sql mounted."
        )
    print(f"  Tables present: {', '.join(sorted(tables))}\n")

    # ── 3. Insert example data ────────────────────────────────────────────────
    print("Inserting example data …")
    try:
        # gym
        gym_id = ensure_gym(cur, GYM_SLUG)
        print(f"  gym       id={gym_id}  slug={GYM_SLUG!r}")

        # posts (raw scraped content)
        url_to_post_id = upsert_posts(cur, gym_id, EXAMPLE_POSTS)
        print(f"  posts     {len(url_to_post_id)} row(s)  url_map={url_to_post_id}")

        # event (merged)
        event_id = insert_event(cur, gym_id, EXAMPLE_MERGED_EVENT)
        print(f"  event     id={event_id}  name={EXAMPLE_MERGED_EVENT['event_name']!r}")

        # raw_events (one per post in the merged event's posts[])
        raw_ids = bulk_insert_raw_events(
            cur,
            gym_id,
            EXAMPLE_MERGED_EVENT["posts"],
            url_to_post_id=url_to_post_id,
            event_id=event_id,
        )
        print(f"  raw_events {len(raw_ids)} row(s)  ids={raw_ids}")

        conn.commit()
        print("  Committed.\n")
    except Exception:
        conn.rollback()
        raise

    # ── 4. Read back ──────────────────────────────────────────────────────────
    print("Reading back …")

    cur.execute(
        """
        SELECT e.id, g.slug, e.event_name, e.event_dates, e.type
        FROM events e JOIN gyms g ON g.id = e.gym_id
        WHERE g.slug = %s ORDER BY e.id
        """,
        (GYM_SLUG,),
    )
    for row in cur.fetchall():
        print(
            f"  event {row[0]}  gym={row[1]}  name={row[2]!r}  "
            f"dates={row[3]}  type={row[4]}"
        )

    cur.execute(
        """
        SELECT re.id, re.type, re.platform, re.url, re.post_id, re.event_id
        FROM raw_events re
        WHERE re.event_id = %s ORDER BY re.id
        """,
        (event_id,),
    )
    for row in cur.fetchall():
        print(
            f"    raw_event {row[0]}  type={row[1]}  platform={row[2]}  "
            f"post_id={row[4]}  event_id={row[5]}"
        )
        print(f"      url={row[3]}")

    cur.execute(
        "SELECT id, platform, url FROM posts WHERE gym_id = %s ORDER BY id",
        (gym_id,),
    )
    for row in cur.fetchall():
        print(f"  post {row[0]}  platform={row[1]}  url={row[2]}")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()

"""
db.py — PostgreSQL insertion helpers for competition-tracker.

Table hierarchy
───────────────
  gyms
    └─ posts            raw scraped content     (*_posts.json)
    └─ events           merged events           (*_events_merged.json)
    └─ raw_events       LLM-parsed events       (*_events.json)

All helpers accept an open psycopg2 cursor and return the inserted row id.
Callers are responsible for commit / rollback.
"""

from __future__ import annotations

import psycopg2

# ── Connection ────────────────────────────────────────────────────────────────
# Matches docker-compose.yml defaults; override via DSN env var if needed.

DSN = (
    "host=localhost port=5432 dbname=competition_tracker user=crux password=crux_local"
)


def connect():
    """Return an autocommit=False psycopg2 connection using DSN."""
    return psycopg2.connect(DSN)


# ── Utilities ─────────────────────────────────────────────────────────────────


def _clean_dates(dates: list | None) -> list[str] | None:
    """Strip None entries; return None when the list is empty."""
    cleaned = [d for d in (dates or []) if d]
    return cleaned or None


# ── gyms ──────────────────────────────────────────────────────────────────────


def ensure_gym(cur, slug: str) -> int:
    """Insert gym if absent; return its id either way."""
    cur.execute(
        """
        INSERT INTO gyms (slug)
        VALUES (%s)
        ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug
        RETURNING id
        """,
        (slug,),
    )
    return cur.fetchone()[0]


# ── posts ─────────────────────────────────────────────────────────────────────


def upsert_post(cur, gym_id: int, post: dict) -> int:
    """
    Insert a raw scraped post; update caption/media on conflict.

    Expected keys (from *_posts.json):
        url, platform, caption, media_urls, timestamp
    """
    cur.execute(
        """
        INSERT INTO posts (gym_id, url, platform, caption, media_urls, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (url) DO UPDATE
            SET caption    = EXCLUDED.caption,
                media_urls = EXCLUDED.media_urls,
                timestamp  = EXCLUDED.timestamp
        RETURNING id
        """,
        (
            gym_id,
            post["url"],
            post.get("platform"),
            post.get("caption"),
            post.get("media_urls") or [],
            post.get("timestamp"),
        ),
    )
    return cur.fetchone()[0]


def upsert_posts(cur, gym_id: int, posts: list[dict]) -> dict[str, int]:
    """
    Bulk-upsert posts; return a {url: post_id} mapping.
    Psycopg2 doesn't support bulk RETURNING with execute_values for upserts
    cleanly, so we fall back to individual calls (posts lists are small).
    """
    url_to_id: dict[str, int] = {}
    for post in posts:
        url = post.get("url")
        if url:
            url_to_id[url] = upsert_post(cur, gym_id, post)
    return url_to_id


# ── events ────────────────────────────────────────────────────────────────────


def insert_event(cur, gym_id: int, event: dict, *, gym: str | None = None) -> int:
    """
    Insert a merged event record; return its id.

    Expected keys (from *_events_merged.json top level):
        event_name, event_date, location, discipline, summary, reason
    """
    cur.execute(
        """
        INSERT INTO events
            (gym_id, gym, event_name, event_dates, location, discipline,
             summary, merge_reason)
        VALUES (%s, %s, %s, %s::date[], %s, %s, %s, %s)
        RETURNING id
        """,
        (
            gym_id,
            gym,
            event["event_name"],
            _clean_dates(event.get("event_date") or event.get("event_dates")),
            event.get("location"),
            event.get("discipline"),
            event.get("summary"),
            event.get("reason") or event.get("merge_reason"),
        ),
    )
    return cur.fetchone()[0]


def get_events_by_ids(cur, ids: list[int]) -> list[dict]:
    """
    Return events rows for the given primary-key IDs, with their linked
    raw_events embedded as a 'posts' list.
    Used by merge_manual.py to target specific merged events by ID.
    """
    if not ids:
        return []

    cur.execute(
        """
        SELECT id, event_name, event_dates, location, discipline,
               summary, merge_reason
        FROM   events
        WHERE  id = ANY(%s)
        ORDER  BY id ASC
        """,
        (ids,),
    )
    event_cols = [
        "id",
        "event_name",
        "event_dates",
        "location",
        "discipline",
        "summary",
        "merge_reason",
    ]
    events = []
    for row in cur.fetchall():
        d = {}
        for c, v in zip(event_cols, row):
            if hasattr(v, "isoformat"):
                d[c] = v.isoformat()
            elif isinstance(v, list):
                d[c] = [x.isoformat() if hasattr(x, "isoformat") else x for x in v]
            else:
                d[c] = v
        events.append(d)

    # Embed linked raw_events as 'posts'
    cur.execute(
        """
        SELECT id, event_id, event_name, event_dates, location, discipline,
               type, summary, reason, date_posted, platform, url, raw_media, post_id
        FROM   raw_events
        WHERE  event_id = ANY(%s)
        ORDER  BY date_posted ASC NULLS LAST, id ASC
        """,
        (ids,),
    )
    raw_cols = [
        "id",
        "event_id",
        "event_name",
        "event_dates",
        "location",
        "discipline",
        "type",
        "summary",
        "reason",
        "date_posted",
        "platform",
        "url",
        "raw_media",
        "post_id",
    ]
    posts_by_event: dict[int, list[dict]] = {}
    for row in cur.fetchall():
        d = {}
        for c, v in zip(raw_cols, row):
            if hasattr(v, "isoformat"):
                d[c] = v.isoformat()
            elif isinstance(v, list):
                d[c] = [x.isoformat() if hasattr(x, "isoformat") else x for x in v]
            else:
                d[c] = v
        posts_by_event.setdefault(d["event_id"], []).append(d)

    for ev in events:
        ev["posts"] = posts_by_event.get(ev["id"], [])

    return events


def delete_events(cur, ids: list[int]) -> None:
    """
    Delete events rows by ID.
    Linked raw_events have their event_id set to NULL automatically
    via the ON DELETE SET NULL foreign key constraint.
    """
    if not ids:
        return
    cur.execute("DELETE FROM events WHERE id = ANY(%s)", (ids,))


# ── raw_events ────────────────────────────────────────────────────────────────


def insert_raw_event(
    cur,
    gym_id: int,
    raw: dict,
    *,
    post_id: int | None = None,
    event_id: int | None = None,
    gym: str | None = None,
) -> int:
    """
    Insert one LLM-extracted event record; return its id.

    Expected keys (from *_events.json or the posts[] array in *_events_merged.json):
        event_name, event_date, location, discipline, type, summary, reason,
        date_posted, platform, url, raw_media
    """
    cur.execute(
        """
        INSERT INTO raw_events
            (gym_id, post_id, event_id, gym,
             event_name, event_dates, location, discipline, type, summary, reason,
             date_posted, platform, url, raw_media)
        VALUES (%s, %s, %s, %s, %s, %s::date[], %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            gym_id,
            post_id,
            event_id,
            gym,
            raw.get("event_name"),
            _clean_dates(raw.get("event_date") or raw.get("event_dates")),
            raw.get("location"),
            raw.get("discipline"),
            raw.get("type"),
            raw.get("summary"),
            raw.get("reason"),
            raw.get("date_posted"),
            raw.get("platform"),
            raw.get("url"),
            raw.get("raw_media") or [],
        ),
    )
    return cur.fetchone()[0]


def bulk_insert_raw_events(
    cur,
    gym_id: int,
    raws: list[dict],
    *,
    url_to_post_id: dict[str, int] | None = None,
    event_id: int | None = None,
    gym: str | None = None,
) -> list[int]:
    """
    Insert multiple raw_event records for one gym.

    Parameters
    ----------
    url_to_post_id : dict, optional
        Maps source URL → posts.id so post_id FK can be set.
    event_id : int, optional
        The merged events.id these all belong to (set during merge load).
    gym : str, optional
        Gym slug (denormalised) stored directly on each row for easy filtering.
    """
    if not raws:
        return []

    url_map = url_to_post_id or {}

    rows = [
        (
            gym_id,
            url_map.get(r.get("url", "")),
            event_id,
            gym,
            r.get("event_name"),
            _clean_dates(r.get("event_date") or r.get("event_dates")),
            r.get("location"),
            r.get("discipline"),
            r.get("type"),
            r.get("summary"),
            r.get("reason"),
            r.get("date_posted"),
            r.get("platform"),
            r.get("url"),
            r.get("raw_media") or [],
        )
        for r in raws
    ]

    # execute_values doesn't support RETURNING natively; insert row by row to
    # collect ids. Raw-event lists are small (< 100), so this is fine.
    ids: list[int] = []
    for row in rows:
        cur.execute(
            """
            INSERT INTO raw_events
                (gym_id, post_id, event_id, gym,
                 event_name, event_dates, location, discipline, type, summary, reason,
                 date_posted, platform, url, raw_media)
            VALUES (%s, %s, %s, %s, %s, %s::date[], %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            row,
        )
        ids.append(cur.fetchone()[0])
    return ids


def link_raw_events(cur, event_id: int, raw_event_ids: list[int]) -> None:
    """
    Set event_id on a list of existing raw_events rows.

    Called by merge.py after inserting a merged event to link the source
    raw_events back to it.
    """
    if not raw_event_ids:
        return
    cur.execute(
        "UPDATE raw_events SET event_id = %s WHERE id = ANY(%s)",
        (event_id, raw_event_ids),
    )


# ── Query helpers ─────────────────────────────────────────────────────────────


def get_unprocessed_posts(cur, gym: str) -> list[dict]:
    """
    Return posts for *gym* (gym slug) that have no raw_events linked yet.

    These are the posts that still need to go through the parse/LLM step.
    """
    cur.execute(
        """
        SELECT p.id, p.url, p.platform, p.caption, p.media_urls, p.timestamp
        FROM   posts p
        JOIN   gyms  g ON g.id = p.gym_id
        WHERE  g.slug = %s
          AND  NOT EXISTS (
                   SELECT 1 FROM raw_events re WHERE re.post_id = p.id
               )
        ORDER  BY p.timestamp ASC NULLS LAST
        """,
        (gym,),
    )
    cols = ["id", "url", "platform", "caption", "media_urls", "timestamp"]
    rows = cur.fetchall()
    return [
        {
            c: (v.isoformat() if hasattr(v, "isoformat") else v)
            for c, v in zip(cols, row)
        }
        for row in rows
    ]


def get_raw_events_by_ids(cur, ids: list[int]) -> list[dict]:
    """
    Return raw_events rows for the given primary-key IDs, regardless of
    whether they have already been merged (event_id may be set or NULL).
    Used by merge_manual.py to target specific records by ID.
    """
    if not ids:
        return []
    cur.execute(
        """
        SELECT id, event_name, event_dates, location, discipline,
               type, summary, reason, date_posted, platform, url, raw_media,
               post_id
        FROM   raw_events
        WHERE  id = ANY(%s)
        ORDER  BY date_posted ASC NULLS LAST, id ASC
        """,
        (ids,),
    )
    cols = [
        "id",
        "event_name",
        "event_dates",
        "location",
        "discipline",
        "type",
        "summary",
        "reason",
        "date_posted",
        "platform",
        "url",
        "raw_media",
        "post_id",
    ]
    rows = cur.fetchall()
    result = []
    for row in rows:
        d = {}
        for c, v in zip(cols, row):
            if hasattr(v, "isoformat"):
                d[c] = v.isoformat()
            elif isinstance(v, list):
                d[c] = [x.isoformat() if hasattr(x, "isoformat") else x for x in v]
            else:
                d[c] = v
        result.append(d)
    return result


def get_unmerged_raw_events(cur, gym: str) -> list[dict]:
    """
    Return raw_events for *gym* (gym slug) that have not been merged yet
    (i.e. event_id IS NULL).

    These are the records that still need to go through the merge step.
    """
    cur.execute(
        """
        SELECT re.id, re.event_name, re.event_dates, re.location, re.discipline,
               re.type, re.summary, re.reason, re.date_posted, re.platform, re.url, re.raw_media,
               re.post_id
        FROM   raw_events re
        JOIN   gyms        g  ON g.id = re.gym_id
        WHERE  g.slug    = %s
          AND  re.event_id IS NULL
        ORDER  BY re.date_posted ASC NULLS LAST, re.id ASC
        """,
        (gym,),
    )
    cols = [
        "id",
        "event_name",
        "event_dates",
        "location",
        "discipline",
        "type",
        "summary",
        "reason",
        "date_posted",
        "platform",
        "url",
        "raw_media",
        "post_id",
    ]
    rows = cur.fetchall()
    result = []
    for row in rows:
        d = {}
        for c, v in zip(cols, row):
            if hasattr(v, "isoformat"):
                d[c] = v.isoformat()
            elif isinstance(v, list):
                d[c] = [x.isoformat() if hasattr(x, "isoformat") else x for x in v]
            else:
                d[c] = v
        result.append(d)
    return result

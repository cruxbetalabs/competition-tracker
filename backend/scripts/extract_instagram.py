#!/usr/bin/env python3
"""
CLI entry point for the Instagram profile scraper.

All scraping logic lives in instagram_crawler.InstagramCrawler.
Posts are scraped and upserted directly into PostgreSQL.

Usage:
    python scripts/extract_instagram.py --gym benchmarkclimbing \\
        --since 2025-05-01 --until 2026-02-16
    python scripts/extract_instagram.py --gym benchmarkclimbing \\
        --since 2025-05-01 --until 2026-02-16 --headless --force-login
"""

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from service.instagram_crawler import InstagramCrawler

ENV_FILE = Path(__file__).parent.parent / ".env"


async def main(
    gym: str,
    since: datetime,
    until: datetime,
    headless: bool,
    force_login: bool,
) -> None:
    if since > until:
        raise ValueError(
            f"--since ({since.date()}) must not be later than --until ({until.date()})"
        )

    crawler = InstagramCrawler(
        env_file=ENV_FILE,
        session_file=Path(__file__).parent / "session.json",
        headless=headless,
    )

    posts = await crawler.scrape(
        gym,
        since,
        until,
        force_relogin=force_login,
    )

    print(f"\n── {len(posts)} posts collected  ({since.date()} → {until.date()}) ──\n")
    for p in posts:
        print(f"  {p['timestamp'][:19]}  {p['url']}")
        if p["caption"]:
            snippet = p["caption"][:120].replace("\n", " ").strip()
            print(f"    ↳ {snippet}{'…' if len(p['caption']) > 120 else ''}")

    # ── Export to DB ──────────────────────────────────────────────────────────
    from service.db import connect, ensure_gym, upsert_posts

    for p in posts:
        p.setdefault("platform", "instagram")

    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        url_map = upsert_posts(cur, gym_id, posts)
        conn.commit()
        print(
            f"[db] Upserted {len(url_map)} post(s) into PostgreSQL  (gym_id={gym_id})"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape an Instagram profile and store raw posts in PostgreSQL."
    )
    parser.add_argument(
        "--gym",
        required=True,
        help="Instagram profile handle / gym slug (e.g. benchmarkclimbing)",
    )
    parser.add_argument(
        "--since",
        required=True,
        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
        help="Start date (inclusive), ISO format: 2025-05-01",
    )
    parser.add_argument(
        "--until",
        default=None,
        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
        help="End date (inclusive), ISO format: 2026-02-16.  Defaults to today.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode (default: visible).",
    )
    parser.add_argument(
        "--force-login",
        action="store_true",
        help="Discard saved session.json and re-authenticate.",
    )
    args = parser.parse_args()

    until = args.until or datetime.now(tz=timezone.utc).replace(
        hour=23, minute=59, second=59, microsecond=0
    )

    asyncio.run(
        main(
            gym=args.gym,
            since=args.since,
            until=until,
            headless=args.headless,
            force_login=args.force_login,
        )
    )

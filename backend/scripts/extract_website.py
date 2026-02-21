#!/usr/bin/env python3
"""
CLI entry point for the website event-page scraper.

Crawls a single URL and stores the resulting post directly in PostgreSQL.

Usage:
    python scripts/extract_website.py \\
        --gym bridgesrockgym \\
        --url https://www.bridgesrockgym.com/events
"""

import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler


async def main(gym: str, url: str) -> None:
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)

    domain = urlparse(url).netloc

    posts = [
        {
            "url": url,
            "platform": "website",
            "author": domain,
            "caption": result.markdown,
            "media_urls": [],
            "timestamp": None,
        }
    ]

    # ── Export to DB ──────────────────────────────────────────────────────────
    sys.path.insert(0, str(Path(__file__).parent))
    from service.db import connect, ensure_gym, upsert_posts

    conn = connect()
    try:
        cur = conn.cursor()
        gym_id = ensure_gym(cur, gym)
        url_map = upsert_posts(cur, posts, gym_id=gym_id)
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
        description="Crawl a website event page and store the raw post in PostgreSQL."
    )
    parser.add_argument(
        "--gym",
        required=True,
        help="Gym slug (e.g. bridgesrockgym)",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL of the events page to crawl.",
    )
    args = parser.parse_args()

    asyncio.run(main(gym=args.gym, url=args.url))

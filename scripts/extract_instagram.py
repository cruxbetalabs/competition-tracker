#!/usr/bin/env python3
"""
CLI entry point for the Instagram profile scraper.

All scraping logic lives in instagram_crawler.InstagramCrawler.
Configure the run by editing the constants below, then run:

  python scripts/instagram.py
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from service.instagram_crawler import InstagramCrawler

# ── Configuration ─────────────────────────────────────────────────────────────
PROFILE = "touchstoneclimbing"
SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 2, 16, tzinfo=timezone.utc)
HEADLESS = False  # set False to watch the browser
FORCE_LOGIN = False  # set True to discard session.json and re-login

data_dir = Path(__file__).parent.parent / "data"
ENV_FILE = Path(__file__).parent.parent / ".env"
# ─────────────────────────────────────────────────────────────────────────────


async def main() -> None:
    if SINCE > UNTIL:
        raise ValueError(
            f"SINCE ({SINCE.date()}) must not be later than UNTIL ({UNTIL.date()})"
        )

    crawler = InstagramCrawler(
        env_file=ENV_FILE,
        session_file=Path(__file__).parent / "session.json",
        headless=HEADLESS,
    )

    posts = await crawler.scrape(
        PROFILE,
        SINCE,
        UNTIL,
        force_relogin=FORCE_LOGIN,  # whether to refetch the credential or not
        # debug=True,
    )

    print(f"\n── {len(posts)} posts collected  ({SINCE.date()} → {UNTIL.date()}) ──\n")
    for p in posts:
        print(f"  {p['timestamp'][:19]}  {p['url']}")
        if p["caption"]:
            snippet = p["caption"][:120].replace("\n", " ").strip()
            print(f"    ↳ {snippet}{'…' if len(p['caption']) > 120 else ''}")

    # ── Export raw posts ──────────────────────────────────────────────────────
    data_dir.mkdir(exist_ok=True)
    posts_file = data_dir / f"{PROFILE}_posts.json"
    posts_file.write_text(json.dumps(posts, indent=2, ensure_ascii=False))
    print(f"\n[export] Saved {len(posts)} raw posts → {posts_file}")


if __name__ == "__main__":
    asyncio.run(main())

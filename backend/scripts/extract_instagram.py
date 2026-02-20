#!/usr/bin/env python3
"""
CLI entry point for the Instagram profile scraper.

All scraping logic lives in instagram_crawler.InstagramCrawler.
Posts are scraped and upserted directly into PostgreSQL.

Usage:
    python scripts/extract_instagram.py \\
        --profile benchmarkberkeley \\
        --gym benchmark-climbing-berkeley \\
        --since 2025-05-01
    python scripts/extract_instagram.py \\
        --profile benchmarkberkeley \\
        --gym benchmark-climbing-berkeley \\
        --since 2025-05-01 --until 2026-02-16 --headless --force-login
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from service.instagram_crawler import InstagramCrawler

ENV_FILE = Path(__file__).parent.parent / ".env"
GYMS_FILE = Path(__file__).parent.parent / "data" / "source" / "gyms.json"


def _load_gym_entry(gym_slug: str) -> dict:
    """Return the gyms.json entry whose slug matches *gym_slug*.

    Raises SystemExit with a clear message if not found.
    """
    gyms: list[dict] = json.loads(GYMS_FILE.read_text())
    for entry in gyms:
        if entry.get("slug") == gym_slug:
            return entry
    available = ", ".join(e["slug"] for e in gyms if e.get("slug"))
    raise SystemExit(
        f"[error] Gym slug '{gym_slug}' not found in gyms.json.\n"
        f"Available slugs: {available}"
    )


def _org_info(gym_entry: dict) -> tuple[str, str]:
    """Return (org_name, org_slug) for the given gym entry.

    When the gym has no parent organization (organization is null),
    the gym itself is treated as its own org — using its name and slug.
    """
    org_name: str | None = gym_entry.get("organization")
    if org_name:
        org_slug = org_name.lower().replace(" ", "-")
    else:
        org_name = gym_entry["name"]
        org_slug = gym_entry["slug"]
    return org_name, org_slug


async def main(
    profile: str,
    gym_slug: str,
    since: datetime,
    until: datetime,
    headless: bool,
    force_login: bool,
) -> None:
    if since > until:
        raise ValueError(
            f"--since ({since.date()}) must not be later than --until ({until.date()})"
        )

    # ── Validate gym slug against gyms.json ───────────────────────────────────
    gym_entry = _load_gym_entry(gym_slug)
    org_name, org_slug = _org_info(gym_entry)

    print(f"[gym] {gym_entry['name']}  (slug={gym_slug})")
    print(f"[org] {org_name}  (slug={org_slug})")

    # ── Scrape ───────────────────────────────────────────────────────────────
    crawler = InstagramCrawler(
        env_file=ENV_FILE,
        session_file=Path(__file__).parent / "session.json",
        headless=headless,
    )

    posts = await crawler.scrape(
        profile,
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
    from service.db import connect, ensure_gym, ensure_organization, upsert_posts

    for p in posts:
        p.setdefault("platform", "instagram")

    conn = connect()
    try:
        cur = conn.cursor()
        organization_id = ensure_organization(cur, org_name, slug=org_slug)
        gym_id = ensure_gym(
            cur,
            gym_slug,
            name=gym_entry["name"],
            city=gym_entry.get("city"),
            organization=org_name,
            organization_slug=org_slug,
        )
        url_map = upsert_posts(cur, posts, gym_id=gym_id, organization_id=organization_id)
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
        "--profile",
        required=True,
        help="Instagram handle to scrape (e.g. benchmarkberkeley)",
    )
    parser.add_argument(
        "--gym",
        required=True,
        help=(
            "Gym slug as defined in data/source/gyms.json "
            "(e.g. benchmark-climbing-berkeley). "
            "Must match an existing slug exactly."
        ),
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
            profile=args.profile,
            gym_slug=args.gym,
            since=args.since,
            until=until,
            headless=args.headless,
            force_login=args.force_login,
        )
    )

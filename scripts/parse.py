#!/usr/bin/env python3
"""
CLI for running LLM extraction + merge over a saved JSON posts file.

Each item in the input JSON array must follow this schema:
    {
        "url":        "<source URL>",
        "platform":   "<'instagram' | 'website' | 'facebook' | 'others'>",
        "caption":    "<text content>",
        "media_urls": ["<image or video URLs>"],
        "timestamp":  "<ISO 8601 datetime | null>"
    }

Usage:
    python scripts/parse.py data/mosaicboulders_posts.json
    python scripts/parse.py data/mosaicboulders_posts.json --output data/mosaicboulders_events.json
"""

import argparse
import asyncio
import json
from pathlib import Path

from service.event_extractor import EventExtractor

_ENV_FILE = Path(__file__).parent.parent / ".env"


async def main(input_path: Path, output_path: Path, merge: bool = True) -> None:
    posts = json.loads(input_path.read_text(encoding="utf-8"))
    print(f"[parse] Loaded {len(posts)} post(s) from {input_path}")

    extractor = EventExtractor(env_file=_ENV_FILE)

    events, extract_tokens = await extractor.extract_all_posts(posts)

    if merge:
        merged, merge_tokens = await extractor.merge_events(events)
        combined_tokens = {
            k: extract_tokens[k] + merge_tokens[k] for k in extract_tokens
        }
    else:
        if not merge:
            print("\n[merge] Skipping merge")
        merged = events
        combined_tokens = extract_tokens

    extractor.save_events(merged, output_path)
    extractor.get_stat(combined_tokens)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract and merge competition events from a JSON posts file."
    )
    parser.add_argument("input", type=Path, help="Path to the JSON posts file")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for events JSON (default: <input_stem>_events.json)",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        default=False,
        help="Skip the merge step and output raw extracted events.",
    )
    args = parser.parse_args()

    stem = args.input.stem.removesuffix("_posts")
    output_path = args.output or args.input.parent / f"{stem}_events.json"

    asyncio.run(main(args.input, output_path, merge=args.merge))

import asyncio
import json
from pathlib import Path
from crawl4ai import AsyncWebCrawler

_DATA_DIR = Path(__file__).parent.parent / "data"


async def main():
    url = "https://www.bridgesrockgym.com/events"
    source_name = "bridgesrockgym"

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)

    posts = [
        {
            "url": url,
            "platform": "website",
            "caption": result.markdown,
            "media_urls": [],
            "timestamp": None,
        }
    ]

    _DATA_DIR.mkdir(exist_ok=True)
    posts_file = _DATA_DIR / f"{source_name}_posts.json"
    posts_file.write_text(json.dumps(posts, indent=2, ensure_ascii=False))
    print(f"[export] Saved raw posts → {posts_file}")


if __name__ == "__main__":
    asyncio.run(main())

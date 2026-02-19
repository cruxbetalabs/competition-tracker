"""
InstagramCrawler — Playwright/Firefox-based Instagram profile scraper.

Responsibilities:
  - Session management  : login once, persist browser state, reload on reuse
  - Profile scraping    : intercept API/GraphQL XHR responses as the page loads
  - Post parsing        : extract shortcode, caption, media URLs, timestamp
  - Date filtering      : collect only posts within [since, until]
"""

import random
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from playwright.async_api import async_playwright, Page, Response

# ── Optional stealth patching ─────────────────────────────────────────────────
try:
    from playwright_stealth import stealth_async as _apply_stealth  # type: ignore
except ImportError:
    raise SystemExit(
        "[error] playwright-stealth is not installed.\n"
        "Install it with: pip install playwright-stealth"
    )


# ── Defaults ──────────────────────────────────────────────────────────────────
_IG_BASE = "https://www.instagram.com"
_LOGIN_URL = f"{_IG_BASE}/accounts/login/"

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# XHR URL fragments that carry post data
_FEED_PATTERNS = (
    "api/v1/feed/user",
    "api/v1/tags",
    "api/v1/clips/user",
    "graphql/query",
    "graphql/async_loader",
)

# Unicode characters that VS Code (and many JSON parsers) flag as unusual
# line terminators when embedded in strings.
_UNUSUAL_LINE_TERMINATORS = str.maketrans(
    {
        "\u2028": "\n",  # LINE SEPARATOR      → regular newline
        "\u2029": "\n",  # PARAGRAPH SEPARATOR → regular newline
        "\u0085": "\n",  # NEXT LINE           → regular newline
        "\u000b": "\n",  # VERTICAL TAB        → regular newline
        "\u000c": "\n",  # FORM FEED           → regular newline
    }
)


def _sanitize(text: str) -> str:
    """Replace unusual Unicode line terminators with plain newlines."""
    return text.translate(_UNUSUAL_LINE_TERMINATORS)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _dismiss_prompts(page: Page) -> None:
    """Dismiss cookie-consent banners and post-login dialogs."""
    for label in (
        r"allow essential and optional cookies",
        r"accept all",
        r"allow all cookies",
        r"only allow essential cookies",
    ):
        try:
            btn = page.get_by_role("button", name=re.compile(label, re.I))
            if await btn.count():
                await btn.first.click()
                await page.wait_for_timeout(random.randint(600, 1_200))
        except Exception:
            pass

    for label in ("Not now", "Not Now", "Skip", "Save Info"):
        try:
            btn = page.get_by_role("button", name=label)
            if await btn.count():
                await btn.first.click()
                await page.wait_for_timeout(random.randint(600, 1_200))
        except Exception:
            pass


def _node_to_post(node: dict) -> dict | None:
    """Convert a raw API post node to a structured dict; returns None on failure."""
    try:
        ts_raw = node.get("taken_at") or node.get("taken_at_timestamp")
        if ts_raw is None:
            return None

        post_dt = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
        shortcode = node.get("code") or node.get("shortcode") or ""

        caption_field = node.get("caption") or {}
        caption = _sanitize(
            caption_field.get("text", "")
            if isinstance(caption_field, dict)
            else str(caption_field)
        )

        media_urls: list[str] = []

        # Single image / video thumbnail
        candidates = (node.get("image_versions2") or {}).get("candidates", [])
        if candidates:
            media_urls.append(candidates[0]["url"])

        # Carousel items
        for item in node.get("carousel_media") or []:
            cc = (item.get("image_versions2") or {}).get("candidates", [])
            if cc:
                media_urls.append(cc[0]["url"])

        # Video
        if node.get("video_url"):
            media_urls.append(node["video_url"])

        # ── Owner resolution ──────────────────────────────────────────────
        # v1 feed use `user.username`; graphql uses `owner.username`
        owner: dict = node.get("user") or node.get("owner") or {}
        author: str = (
            (owner.get("username") or "").strip().lower()
            if isinstance(owner, dict)
            else ""
        )

        return {
            "shortcode": shortcode,
            "url": f"https://www.instagram.com/p/{shortcode}/",
            "timestamp": post_dt.isoformat(),
            "caption": caption,
            "media_urls": media_urls,
            "author": author,
        }
    except Exception as exc:
        print(f"  [warn] _node_to_post error: {exc}")
        return None


def _collect_post_nodes(obj) -> list[dict]:
    """
    Recursively walk a decoded JSON object and return every dict that looks
    like a post node (has taken_at + pk/code/shortcode).
    """
    found: list[dict] = []

    def _walk(o):
        if isinstance(o, dict):
            if ("taken_at" in o or "taken_at_timestamp" in o) and (
                "pk" in o or "code" in o or "shortcode" in o
            ):
                found.append(o)
            for v in o.values():
                _walk(v)
        elif isinstance(o, list):
            for item in o:
                _walk(item)

    _walk(obj)
    return found


# ─────────────────────────────────────────────────────────────────────────────
# Service class
# ─────────────────────────────────────────────────────────────────────────────


class InstagramCrawler:
    """
    Playwright-based Instagram profile scraper.

    Parameters
    ----------
    session_file : Path
        Where to persist browser storage state (cookies + localStorage).
    env_file : Path
        .env file containing INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD.
    headless : bool
        Run Firefox in headless mode. Pass False to watch the browser.
    """

    def __init__(
        self,
        env_file: Path,
        session_file: Path = Path(__file__).parent.parent / "session.json",
        headless: bool = True,
    ) -> None:
        self.session_file = session_file
        self.headless = headless
        cfg = dotenv_values(str(env_file))
        self.username = cfg.get("INSTAGRAM_USERNAME", "").strip()
        self.password = cfg.get("INSTAGRAM_PASSWORD", "").strip()

    # ── Session ───────────────────────────────────────────────────────────────

    def session_exists(self) -> bool:
        return self.session_file.exists() and self.session_file.stat().st_size > 0

    async def login(self) -> None:
        """
        Open Firefox, log in to Instagram, and persist browser state to
        self.session_file. Subsequent scrape() calls reuse this state.
        """
        if not self.username or not self.password:
            raise ValueError(
                "INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD must be set in .env"
            )

        async with async_playwright() as pw:
            browser = await pw.firefox.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                user_agent=_USER_AGENT,
            )
            page = await context.new_page()

            await _apply_stealth(page)

            print("[login] Navigating to Instagram login page …")
            await page.goto(
                _LOGIN_URL + "?hl=en", wait_until="networkidle", timeout=60_000
            )
            await page.wait_for_timeout(random.randint(1_200, 2_500))
            await _dismiss_prompts(page)

            # Guard against redirect to home feed
            if "/accounts/login" not in page.url:
                print(f"[login] Redirected to {page.url!r}, navigating back …")
                await page.goto(
                    _LOGIN_URL + "?hl=en", wait_until="networkidle", timeout=60_000
                )
                await page.wait_for_timeout(random.randint(1_200, 2_500))
                await _dismiss_prompts(page)

            print("[login] Waiting for login form …")
            await page.wait_for_selector(
                'input[name="email"]', state="visible", timeout=30_000
            )

            print("[login] Filling credentials …")
            await page.locator('input[name="email"]').click()
            await page.wait_for_timeout(random.randint(200, 600))
            await page.locator('input[name="email"]').fill(self.username)
            await page.wait_for_timeout(random.randint(300, 700))
            await page.locator('input[name="pass"]').click()
            await page.wait_for_timeout(random.randint(200, 600))
            await page.locator('input[name="pass"]').fill(self.password)
            await page.wait_for_timeout(random.randint(300, 700))
            await page.locator('input[name="pass"]').press("Enter")
            print("[login] Submitted — waiting for redirect …")

            # Wait to leave the plain login page; two_factor counts as progress
            try:
                await page.wait_for_url(
                    lambda url: "/accounts/login" not in url or "two_factor" in url,
                    timeout=30_000,
                )
            except Exception:
                await page.wait_for_timeout(random.randint(2_000, 4_000))

            # ── 2FA handling ──────────────────────────────────────────────────
            if "two_factor" in page.url:
                print("[login] 2FA challenge detected.")
                if not self.headless:
                    # Visible browser — user fills the code manually
                    print(
                        "[login] Enter the 6-digit code in the browser window, then press Confirm."
                    )
                    print("[login] Waiting up to 5 minutes for 2FA completion …")
                    try:
                        await page.wait_for_url(
                            lambda url: "two_factor" not in url,
                            timeout=300_000,  # 5 minutes
                        )
                    except Exception:
                        raise RuntimeError(
                            "[login] 2FA not completed within 5 minutes. "
                            "Please try again."
                        )
                else:
                    # Headless — read code from terminal and submit it
                    import asyncio as _asyncio

                    loop = _asyncio.get_event_loop()
                    code = await loop.run_in_executor(
                        None,
                        lambda: input("[login] Enter your 6-digit 2FA code: ").strip(),
                    )
                    await page.wait_for_selector(
                        'input[placeholder="Security Code"]',
                        state="visible",
                        timeout=10_000,
                    )
                    await page.locator('input[placeholder="Security Code"]').fill(code)
                    await page.wait_for_timeout(random.randint(200, 500))
                    await page.get_by_role("button", name="Confirm").click()
                    print("[login] 2FA code submitted — waiting for redirect …")
                    try:
                        await page.wait_for_url(
                            lambda url: "two_factor" not in url,
                            timeout=30_000,
                        )
                    except Exception:
                        await page.wait_for_timeout(random.randint(4_000, 7_000))

                print("[login] 2FA passed ✓")

            await _dismiss_prompts(page)

            print(f"[login] Saving session → {self.session_file}")
            await context.storage_state(path=str(self.session_file))
            await browser.close()
            print("[login] Done.")

    # ── Scraping ──────────────────────────────────────────────────────────────

    async def scrape(
        self,
        profile: str,
        since: datetime,
        until: datetime,
        *,
        force_relogin: bool = False,
        debug: bool = False,
    ) -> list[dict]:
        """
        Scrape posts from *profile* within [since, until] (both inclusive).

        Parameters
        ----------
        debug : bool
            When True, print the owner fields of every candidate node and
            dump key DOM elements from the profile page for inspection.

        Returns a list of post dicts sorted newest-first:
            {
                "shortcode":      str,
                "url":            str,
                "timestamp":      str (ISO 8601),
                "caption":        str,
                "media_urls":     list[str],
                "author": str,
            }
        """
        if force_relogin or not self.session_exists():
            reason = "force_relogin" if force_relogin else "no saved session"
            print(f"[session] {reason} — logging in.")
            await self.login()

        async with async_playwright() as pw:
            browser = await pw.firefox.launch(headless=self.headless)
            context = await browser.new_context(
                storage_state=str(self.session_file),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                user_agent=_USER_AGENT,
            )
            page = await context.new_page()

            await _apply_stealth(page)

            collected: dict[str, dict] = {}
            oldest_seen: list[datetime] = [until]
            passed_since: list[bool] = [False]

            target_username = profile.lstrip("@").lower()

            async def handle_response(response: Response) -> None:
                url = response.url
                if not any(pat in url for pat in _FEED_PATTERNS):
                    return
                try:
                    if "json" not in response.headers.get("content-type", ""):
                        return
                    data = await response.json()
                    for node in _collect_post_nodes(data):
                        post = _node_to_post(node)
                        if post is None:
                            continue

                        author = post.get("author", "")

                        if debug:
                            print(
                                f"  [debug] node shortcode={post['shortcode']!r:30s} "
                                f"ts={post['timestamp'][:19]}  "
                                f"owner={author!r}  "
                                f"(raw user={node.get('user', {}).get('username')!r}, "
                                f"owner={node.get('owner', {}).get('username')!r})"
                            )

                        # ── Owner filter ──────────────────────────────────────
                        # Skip posts that clearly belong to a different account.
                        # We allow empty author through (older API shapes
                        # sometimes omit the field) so we never silently drop
                        # valid posts.
                        if author and author != target_username:
                            if debug:
                                print(
                                    f"  [debug] SKIP — owner {author!r} "
                                    f"!= target {target_username!r}"
                                )
                            continue

                        post_dt = datetime.fromisoformat(post["timestamp"])
                        if post_dt < oldest_seen[0]:
                            oldest_seen[0] = post_dt
                        if post_dt < since:
                            passed_since[0] = True
                        if since <= post_dt <= until:
                            if post["shortcode"] not in collected:
                                print(
                                    f"  [+] {post['timestamp'][:19]}  "
                                    f"https://instagram.com/p/{post['shortcode']}/"
                                )
                            collected[post["shortcode"]] = post
                        elif debug:
                            reason = (
                                f"too new (> {until.date()})"
                                if post_dt > until
                                else f"too old (< {since.date()})"
                            )
                            print(
                                f"  [debug] OUT-OF-RANGE — {reason}  "
                                f"shortcode={post['shortcode']!r}"
                            )
                except Exception:
                    pass

            page.on("response", handle_response)

            profile_url = f"{_IG_BASE}/{profile}/?hl=en"
            print(f"[scrape] Loading {profile_url}")
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(random.randint(2_500, 5_000))

            if debug:
                # ── DOM inspection ────────────────────────────────────────────
                # Print the key DOM elements that identify the profile so we
                # can verify the page loaded the correct account.
                dom_info: dict = await page.evaluate(
                    """
                    () => {
                        const get = sel => {
                            const el = document.querySelector(sel);
                            return el ? el.innerText || el.getAttribute('content') : null;
                        };
                        return {
                            title:       document.title,
                            h1:          Array.from(document.querySelectorAll('h1'))
                                              .map(e => e.innerText).join(' | '),
                            h2:          Array.from(document.querySelectorAll('h2'))
                                              .map(e => e.innerText).join(' | '),
                            og_title:    get('meta[property="og:title"]'),
                            og_url:      get('meta[property="og:url"]'),
                            profile_pic: get('img[data-testid="user-avatar"]')
                                      || get('header img'),
                            canonical:   get('link[rel="canonical"]'),
                            url:         window.location.href,
                        };
                    }
                """
                )
                print("[debug] DOM snapshot after page load:")
                for k, v in dom_info.items():
                    print(f"  {k:<14}: {v}")

            last_height: int = 0
            stale_scrolls: int = 0
            MAX_STALE = 6

            print("[scrape] Scrolling to load more posts …")
            while not passed_since[0]:
                current_height: int = await page.evaluate(
                    "document.documentElement.scrollHeight"
                )
                if current_height == last_height:
                    stale_scrolls += 1
                    if stale_scrolls >= MAX_STALE:
                        print(
                            "[scrape] No new content after several scrolls — stopping."
                        )
                        break
                else:
                    stale_scrolls = 0
                last_height = current_height

                # Use Playwright's native mouse wheel to generate a real
                # OS-level input event rather than a JS scrollBy call.
                await page.mouse.wheel(0, random.randint(300, 700))
                await page.wait_for_timeout(random.randint(2_000, 5_000))

            await browser.close()

        return sorted(collected.values(), key=lambda p: p["timestamp"], reverse=True)

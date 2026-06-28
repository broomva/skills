#!/usr/bin/env python3
"""x_browser.py — proactive X engagement via Playwright (browser UI automation).

Why this instead of the Twikit approach: Twikit (2.3.3) relies on reverse-
engineering X's `ondemand.s.js` anti-bot file via regex. X rotates that file's
obfuscation periodically, which breaks Twikit with the error
`Couldn't get KEY_BYTE indices`. Happens every few weeks.

Playwright drives a real Chromium instance. No regex against X's internals.
No x-client-transaction bypass. The only thing X can detect is "this looks
like a real human," which is exactly what we want.

Persistent session at ~/.config/x/playwright-profile/ (Chromium user-data-dir).
First run: login in a visible browser (headless=False). Subsequent runs:
session cookies in the profile keep us logged in, so login is skipped.

Usage:
  python3 x_browser.py login            # FIRST TIME ONLY — opens visible browser for manual login
  python3 x_browser.py whoami           # Verify session is still valid
  python3 x_browser.py reply <id> <text>
  python3 x_browser.py post <text>
  python3 x_browser.py search <query>   # Reads recent matches; no API, parses DOM

Safety rails (same as the Twikit version):
  - 30s cooldown between write actions
  - Max 4 writes per process run
  - Explicit exit codes: 4=reply-not-allowed, 5=account-gated, 6=rate-limited, 7=other

Requirements:
  pip install playwright
  playwright install chromium
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

try:
    from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PWTimeout
except ImportError:
    sys.stderr.write("playwright not installed. Run: pip install playwright && playwright install chromium\n")
    sys.exit(2)

PROFILE_DIR = Path.home() / ".config" / "x" / "playwright-profile"
WRITE_COOLDOWN_SECONDS = 30
MAX_WRITES_PER_RUN = 4
X_BASE = "https://x.com"

# Default CDP endpoint — Arc and Chrome both support --remote-debugging-port=9222.
# Override with X_BROWSER_CDP env var to change port or host.
CDP_ENDPOINT = os.environ.get("X_BROWSER_CDP", "http://localhost:9222")

# ───────────── Marketing-shape detector ─────────────
# Refuse-to-send guard: if a reply / quote / post leads with framework-
# proprietary nouns (Life modules, bstack primitives, L3 entity slugs),
# the detector aborts with exit code 8. Override via --allow-marketing-shape
# when the audience is an insider one (Moltbook framework participants,
# named anchors who already use the vocabulary).
#
# The rule comes from ~/.config/moltbook/loop.md §"Marketing-shape vs ideas-
# shape": cold-discovery audiences read proprietary nouns as brand-positioning
# even when the underlying substance is sound. The check is intentionally
# coarse — false-positives are cheap (re-shape the reply); false-negatives
# (marketing-shape escaping into a cold thread) are expensive.
PROPRIETARY_NOUNS_FILE = (
    Path(__file__).resolve().parent.parent / "references" / "proprietary-nouns.txt"
)
EXIT_MARKETING_SHAPE_BLOCKED = 8
MARKETING_SHAPE_LEAD_WINDOW = 12  # first N words inspected
# Per-call CDP-connect retry — Arc/Chrome can be briefly slow on /json/version
# under load; one retry with backoff converts transient timeouts into success
# without changing the steady-state behavior.
CDP_CONNECT_RETRIES = 1
CDP_CONNECT_BACKOFF_S = 2.0

_write_count = 0
_last_write_ts: float = 0.0


def _rate_gate() -> None:
    global _write_count, _last_write_ts
    if _write_count >= MAX_WRITES_PER_RUN:
        sys.stderr.write(f"[x_browser] write cap reached ({MAX_WRITES_PER_RUN}); abort\n")
        sys.exit(3)
    elapsed = time.time() - _last_write_ts
    if _last_write_ts and elapsed < WRITE_COOLDOWN_SECONDS:
        sleep_s = WRITE_COOLDOWN_SECONDS - elapsed
        sys.stderr.write(f"[x_browser] cooldown {sleep_s:.1f}s\n")
        time.sleep(sleep_s)


def _mark_write() -> None:
    global _write_count, _last_write_ts
    _write_count += 1
    _last_write_ts = time.time()


_proprietary_nouns_cache: set[str] | None = None


def _load_proprietary_nouns() -> set[str]:
    """Load the proprietary-nouns list from the references file, cached.

    Format: one word per line, case-insensitive. Lines starting with `#` are
    comments. Empty lines ignored. Hyphens preserved (so multi-word slugs like
    `correction-ratchet` match as one token).
    """
    global _proprietary_nouns_cache
    if _proprietary_nouns_cache is not None:
        return _proprietary_nouns_cache
    nouns: set[str] = set()
    try:
        for raw in PROPRIETARY_NOUNS_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            nouns.add(line.lower())
    except FileNotFoundError:
        # File absent => no detection happens. Surface a warning so the
        # operator notices the silent disablement.
        sys.stderr.write(
            f"[x_browser] WARN: proprietary-nouns file missing at "
            f"{PROPRIETARY_NOUNS_FILE}; marketing-shape detector disabled.\n"
        )
    _proprietary_nouns_cache = nouns
    return nouns


def check_marketing_shape(
    text: str, lead_word_window: int = MARKETING_SHAPE_LEAD_WINDOW
) -> dict[str, Any]:
    """Inspect the first `lead_word_window` tokens of `text` for proprietary nouns.

    Returns a dict with `{is_marketing_shape, matched_nouns, guidance}`.
    `guidance` is a human-readable string when blocked, None otherwise.

    The check is intentionally word-level (not substring) so terms appearing
    later in the reply or inside a URL don't trip the detector. The lead
    window is the audience's first read — that's where shape matters.
    """
    nouns = _load_proprietary_nouns()
    if not nouns:
        return {"is_marketing_shape": False, "matched_nouns": [], "guidance": None}
    tokens = re.findall(r"[A-Za-z0-9-]+", text)[:lead_word_window]
    matched: list[str] = []
    for tok in tokens:
        bare = tok.lower()
        if bare in nouns:
            matched.append(bare)
    if matched:
        return {
            "is_marketing_shape": True,
            "matched_nouns": matched,
            "guidance": (
                f"Marketing-shape detected: proprietary noun(s) {matched} in "
                f"the first {lead_word_window} words of the reply. Lead with "
                "the IDEA in everyday vocabulary; framework names belong in "
                "subsequent tweets or insider conversations. Override with "
                "--allow-marketing-shape if this is an insider audience. See "
                "~/.config/moltbook/loop.md §Marketing-shape vs ideas-shape."
            ),
        }
    return {"is_marketing_shape": False, "matched_nouns": [], "guidance": None}


def _cdp_available() -> bool:
    """Probe the CDP endpoint with a short timeout."""
    try:
        with urllib.request.urlopen(f"{CDP_ENDPOINT}/json/version", timeout=1.5) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001 — connection refused, timeout, etc.
        return False


async def open_context(headless: bool = True) -> tuple[Any, BrowserContext, bool]:
    """Return (playwright, browser context, is_cdp).

    Preferred path: connect to an already-running Arc/Chrome over CDP
    (no automation flags, no bot-detection trip). The user's real session.

    Fallback path (only if CDP unavailable AND headless=True): launch a
    persistent Chromium profile. This is flagged as automated by X and only
    works for sites that do not check `navigator.webdriver`.
    """
    pw = await async_playwright().start()

    if _cdp_available():
        # Retry-once on connect timeout. Arc/Chrome can be briefly slow under
        # tab pressure; rather than fail-loud on transient timeouts, give the
        # browser one short backoff window. Steady-state behavior unchanged.
        browser = None
        last_exc: Exception | None = None
        for attempt in range(CDP_CONNECT_RETRIES + 1):
            try:
                browser = await pw.chromium.connect_over_cdp(CDP_ENDPOINT)
                break
            except Exception as exc:  # noqa: BLE001 — Playwright TimeoutError + transport errors
                last_exc = exc
                if attempt < CDP_CONNECT_RETRIES:
                    sys.stderr.write(
                        f"[x_browser] CDP connect attempt {attempt + 1} failed "
                        f"({type(exc).__name__}); retrying in {CDP_CONNECT_BACKOFF_S}s\n"
                    )
                    await asyncio.sleep(CDP_CONNECT_BACKOFF_S)
        if browser is None:
            await pw.stop()
            raise RuntimeError(
                f"CDP connect failed after {CDP_CONNECT_RETRIES + 1} attempts; "
                f"last error: {last_exc}"
            )
        # A CDP-connected browser exposes its existing contexts. Use the first
        # (typically the default user profile). For Arc, this is the logged-in
        # session the user already has open.
        if browser.contexts:
            ctx = browser.contexts[0]
        else:  # pragma: no cover — should not happen with a running browser
            ctx = await browser.new_context()
        return pw, ctx, True

    # Fallback — launched Chromium. Only useful if the target site doesn't
    # check for automation. X DOES check, so this path is mostly for dev/test.
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    viewport_kw: dict[str, Any] = (
        {"no_viewport": True} if not headless else {"viewport": {"width": 1280, "height": 900}}
    )
    chromium_args: list[str] = []
    if not headless:
        chromium_args.extend(["--window-size=1400,1000", "--window-position=80,80"])
    ctx = await pw.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=headless,
        args=chromium_args,
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/Bogota",
        **viewport_kw,
    )
    return pw, ctx, False


async def close_context(pw: Any, ctx: BrowserContext, is_cdp: bool) -> None:
    """Close the context safely; do NOT close the user's Arc if CDP-connected."""
    try:
        if is_cdp:
            # Disconnect only — never close the user's browser.
            await ctx.browser.close() if False else None  # noqa: E501  intentional no-op
            # playwright's disconnect path for CDP is via pw.stop() below.
        else:
            await ctx.close()
    finally:
        await pw.stop()


async def _find_x_page(ctx: BrowserContext) -> Any | None:
    """Return an existing x.com/twitter.com page, or None."""
    for p in ctx.pages:
        url = p.url or ""
        if "x.com" in url or "twitter.com" in url:
            return p
    return None


async def _acquire_work_page(ctx: BrowserContext, is_cdp: bool) -> tuple[Any, bool]:
    """Get a page to drive. In CDP mode prefer reusing an existing x.com tab
    (cookies carry correctly). In launch mode always create a new page.

    Returns (page, is_new). Callers should close it iff is_new is True.
    """
    if is_cdp:
        existing = await _find_x_page(ctx)
        if existing is not None:
            return existing, False
    page = await ctx.new_page()
    return page, True


async def ensure_logged_in(ctx: BrowserContext) -> tuple[bool, str | None]:
    """Check whether the context is logged into X.

    Prefers inspecting an existing x.com tab when one exists (via CDP the
    session cookies are already loaded there). Only opens a new page as a
    last resort.
    """
    existing = await _find_x_page(ctx)
    if existing is not None:
        try:
            # Give the existing page a short window to render the selector.
            await existing.wait_for_selector(
                'a[data-testid="AppTabBar_Profile_Link"]', timeout=3_000
            )
            href = await existing.get_attribute(
                'a[data-testid="AppTabBar_Profile_Link"]', "href"
            )
            screen = href.lstrip("/") if href else None
            return True, screen
        except PWTimeout:
            pass  # fall through to the fresh-page probe
    # No x.com tab, or existing tab is not rendering the profile link.
    page = await ctx.new_page()
    try:
        await page.goto(f"{X_BASE}/home", wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.wait_for_selector(
                'a[data-testid="AppTabBar_Profile_Link"]', timeout=12_000
            )
        except PWTimeout:
            return False, None
        href = await page.get_attribute('a[data-testid="AppTabBar_Profile_Link"]', "href")
        screen = href.lstrip("/") if href else None
        return True, screen
    finally:
        await page.close()


# ---------- Commands ----------

async def cmd_login() -> int:
    """Verify the CDP-connected browser is logged into X.

    In CDP mode we do NOT launch a new browser; we read the session from the
    user's running Arc/Chrome. If not logged in, print instructions and exit.
    Without CDP, fall back to a visible-browser login flow (rarely useful;
    X flags the Playwright Chromium as automated and blocks sign-in).
    """
    pw, ctx, is_cdp = await open_context(headless=False)
    try:
        if not is_cdp:
            sys.stderr.write(
                "[x_browser] CDP not available at "
                f"{CDP_ENDPOINT}. X flags launched Chromium as automated and "
                "blocks sign-in. Start Arc with --remote-debugging-port=9222 "
                "and log in to x.com there.\n"
            )
            return 1
        page = await ctx.new_page()
        await page.goto(f"{X_BASE}/home", wait_until="domcontentloaded", timeout=30_000)
        ok, screen = await ensure_logged_in(ctx)
        if ok:
            sys.stderr.write(f"[x_browser] CDP session logged in as @{screen}.\n")
            print(json.dumps({"ok": True, "screen_name": screen, "mode": "cdp"}, indent=2))
            await page.close()
            return 0
        sys.stderr.write(
            f"[x_browser] CDP-connected browser is NOT logged into X. "
            f"Open x.com in your Arc/Chrome window and log in manually as "
            f"@broomva_tech. Leave the tab open, then rerun this command.\n"
        )
        print(json.dumps({"ok": False, "reason": "not-logged-in", "mode": "cdp"}, indent=2))
        return 1
    finally:
        await close_context(pw, ctx, is_cdp)


async def cmd_whoami() -> int:
    pw, ctx, is_cdp = await open_context(headless=True)
    try:
        ok, screen = await ensure_logged_in(ctx)
        print(json.dumps({
            "ok": ok,
            "screen_name": screen,
            "mode": "cdp" if is_cdp else "launch",
        }, indent=2))
        return 0 if ok else 1
    finally:
        await close_context(pw, ctx, is_cdp)


async def _do_on_page(
    tweet_id: str | None,
    text: str | None,
    action: str,
    allow_marketing_shape: bool = False,
) -> int:
    """Shared open-context + error-handled page flow for reply/post."""
    # Marketing-shape pre-send check. Block BEFORE opening the browser so the
    # block is cheap and observable. Override path: --allow-marketing-shape
    # (used when audience is an insider who already has the vocabulary).
    if text is not None and not allow_marketing_shape:
        check = check_marketing_shape(text)
        if check["is_marketing_shape"]:
            sys.stderr.write(f"[x_browser] {check['guidance']}\n")
            print(
                json.dumps(
                    {
                        "ok": False,
                        "blocked": "marketing_shape",
                        "matched_nouns": check["matched_nouns"],
                        "guidance": check["guidance"],
                    },
                    indent=2,
                )
            )
            return EXIT_MARKETING_SHAPE_BLOCKED
    _rate_gate()
    pw, ctx, is_cdp = await open_context(headless=False)
    try:
        ok, _ = await ensure_logged_in(ctx)
        if not ok:
            sys.stderr.write(
                "[x_browser] Not logged in. Run: x_browser.py login (CDP mode) "
                "or sign into x.com in your Arc browser.\n"
            )
            return 5
        page, is_new = await _acquire_work_page(ctx, is_cdp)
        try:
            if action == "reply":
                return await _reply_flow(page, tweet_id, text)
            if action == "quote":
                return await _quote_flow(page, tweet_id, text)
            if action == "post":
                return await _post_flow(page, text)
            return 7
        finally:
            # In CDP mode we never close existing tabs (user owns them).
            if is_new:
                try:
                    await page.close()
                except Exception:
                    pass
    finally:
        await close_context(pw, ctx, is_cdp)


def is_cdp_preferred_headed(action: str) -> bool:
    # CDP pages show in the user's real Arc tabs. That's fine. The `headless`
    # kwarg only affects the `launch` fallback path.
    return False


async def _reply_flow(page: Any, tweet_id: str, text: str) -> int:
    await page.goto(f"{X_BASE}/i/status/{tweet_id}", wait_until="domcontentloaded", timeout=30_000)
    try:
        await page.wait_for_selector('article [data-testid="reply"]', timeout=15_000)
        await page.locator('article [data-testid="reply"]').first.click()
    except PWTimeout:
        sys.stderr.write("[x_browser] Could not find reply button — tweet may be deleted or locked.\n")
        return 4
    try:
        await page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=10_000)
        # Two elements may share this test-id (the visible composer + an
        # off-screen one used for accessibility). Target the first visible.
        await page.locator('[data-testid="tweetTextarea_0"]').first.fill(text)
    except PWTimeout:
        sys.stderr.write("[x_browser] Reply composer did not appear.\n")
        return 7
    try:
        await page.wait_for_selector(
            '[data-testid="tweetButton"]:not([aria-disabled="true"])', timeout=10_000
        )
        await page.locator('[data-testid="tweetButton"]').first.click()
    except PWTimeout:
        sys.stderr.write("[x_browser] Tweet submit button stayed disabled — reply may be blocked.\n")
        return 4
    try:
        await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="detached", timeout=15_000)
    except PWTimeout:
        pass
    await page.wait_for_timeout(2_000)
    _mark_write()
    print(json.dumps({"ok": True, "reply_to": tweet_id, "current_url": page.url}, indent=2))
    return 0


async def _quote_flow(page: Any, tweet_id: str, text: str) -> int:
    """Quote-tweet flow: navigate to status, click retweet → Quote, compose, submit.

    Quote-tweet is structurally a *new* tweet with an embedded permalink to the
    quoted source. The X UI exposes it as a sub-action of the retweet button.
    """
    await page.goto(f"{X_BASE}/i/status/{tweet_id}", wait_until="domcontentloaded", timeout=30_000)
    # Find the retweet button on the focal article
    try:
        await page.wait_for_selector('article [data-testid="retweet"]', timeout=15_000)
        await page.locator('article [data-testid="retweet"]').first.click()
    except PWTimeout:
        sys.stderr.write("[x_browser] Could not find retweet button — tweet may be deleted or locked.\n")
        return 4
    # The retweet menu appears with two options: "Repost" and "Quote"
    try:
        # The "Quote" option uses data-testid="unretweetConfirm" in some builds and
        # role="menuitem" with text "Quote" in others. Try both.
        try:
            await page.wait_for_selector('[role="menuitem"]:has-text("Quote")', timeout=5_000)
            await page.locator('[role="menuitem"]:has-text("Quote")').first.click()
        except PWTimeout:
            # Fallback: look for the Quote menu item via aria-label or text content
            await page.wait_for_selector('div[role="menu"] >> text=Quote', timeout=5_000)
            await page.locator('div[role="menu"] >> text=Quote').first.click()
    except PWTimeout:
        sys.stderr.write("[x_browser] Could not find Quote option in retweet menu.\n")
        return 7
    # The composer is the standard tweetTextarea_0
    try:
        await page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=10_000)
        await page.locator('[data-testid="tweetTextarea_0"]').first.fill(text)
    except PWTimeout:
        sys.stderr.write("[x_browser] Quote composer did not appear.\n")
        return 7
    try:
        await page.wait_for_selector(
            '[data-testid="tweetButton"]:not([aria-disabled="true"])', timeout=10_000
        )
        await page.locator('[data-testid="tweetButton"]').first.click()
    except PWTimeout:
        sys.stderr.write("[x_browser] Tweet submit button stayed disabled — quote may be blocked.\n")
        return 4
    try:
        await page.wait_for_selector('[data-testid="tweetTextarea_0"]', state="detached", timeout=15_000)
    except PWTimeout:
        pass
    await page.wait_for_timeout(2_000)
    _mark_write()
    print(json.dumps({"ok": True, "quoted": tweet_id, "current_url": page.url}, indent=2))
    return 0


async def _post_flow(page: Any, text: str) -> int:
    await page.goto(f"{X_BASE}/compose/post", wait_until="domcontentloaded", timeout=30_000)
    try:
        await page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=15_000)
        await page.locator('[data-testid="tweetTextarea_0"]').first.fill(text)
    except PWTimeout:
        sys.stderr.write("[x_browser] Composer did not appear.\n")
        return 7
    try:
        await page.wait_for_selector(
            '[data-testid="tweetButton"]:not([aria-disabled="true"])', timeout=10_000
        )
        await page.locator('[data-testid="tweetButton"]').first.click()
    except PWTimeout:
        sys.stderr.write("[x_browser] Tweet button stayed disabled.\n")
        return 4
    await page.wait_for_timeout(2_000)
    _mark_write()
    print(json.dumps({"ok": True, "current_url": page.url}, indent=2))
    return 0


async def cmd_reply(tweet_id: str, text: str, allow_marketing_shape: bool = False) -> int:
    return await _do_on_page(tweet_id, text, "reply", allow_marketing_shape)


async def cmd_quote(tweet_id: str, text: str, allow_marketing_shape: bool = False) -> int:
    return await _do_on_page(tweet_id, text, "quote", allow_marketing_shape)


async def cmd_post(text: str, allow_marketing_shape: bool = False) -> int:
    return await _do_on_page(None, text, "post", allow_marketing_shape)


MEDIA_DIR = Path("/tmp/x-media")


async def _capture_article_media(
    article: Any, page: Any, tweet_id: str | None, capture_media: bool
) -> dict[str, Any]:
    """Extract media context from an article locator.

    Returns a dict with these keys (all optional — empty when nothing found):
      - screenshot_path: str | None  — absolute path to a clipped article screenshot
      - image_urls: list[str]        — pbs.twimg.com photo URLs (full-resolution)
      - image_alt_texts: list[str]   — alt text per image (X uses alt for descriptions
                                       written by the author; valuable signal)
      - has_video: bool              — whether a <video> element is present
      - quoted_tweet_ids: list[str]  — status IDs of nested (quoted) tweets
      - external_link_urls: list[str] — non-x.com URLs from card previews

    When capture_media is False, only structured fields are returned (no screenshot
    is taken). This keeps the surface backwards-compatible and lets callers opt
    out of the ~100-300ms-per-article screenshot overhead.
    """
    out: dict[str, Any] = {
        "screenshot_path": None,
        "image_urls": [],
        "image_alt_texts": [],
        "has_video": False,
        "quoted_tweet_ids": [],
        "external_link_urls": [],
    }
    # Screenshot — clipped to the article's bounding box. This gives a complete
    # visual artifact that the agent can multimodal-Read, regardless of DOM
    # parsing fragility.
    if capture_media and tweet_id:
        try:
            # CRITICAL: scroll the article into the viewport BEFORE measuring
            # its bounding box. Without this, articles below the fold get a
            # bbox whose y > viewport.height, so page.screenshot(clip=...)
            # captures the WRONG region (the article visible at that y
            # coordinate in the current viewport, not the target article).
            # Symptom: screenshots showed earlier articles than the JSON
            # extraction described, and PNG sizes shrank for each successive
            # article as the captures fell off the visible region.
            try:
                await article.scroll_into_view_if_needed(timeout=3_000)
                # Tiny pause so the scroll settles before measurement
                await page.wait_for_timeout(150)
            except Exception:
                pass
            bbox = await article.bounding_box()
            if bbox and bbox["width"] > 0 and bbox["height"] > 0:
                MEDIA_DIR.mkdir(parents=True, exist_ok=True)
                # Round to ints — Playwright wants exact pixel coords
                clip = {
                    "x": max(0, int(bbox["x"])),
                    "y": max(0, int(bbox["y"])),
                    "width": int(bbox["width"]),
                    "height": int(bbox["height"]),
                }
                shot_path = MEDIA_DIR / f"x-tweet-{tweet_id}.png"
                await page.screenshot(path=str(shot_path), clip=clip)
                out["screenshot_path"] = str(shot_path)
        except Exception as exc:  # noqa: BLE001 — visual capture is best-effort
            sys.stderr.write(f"[x_browser] screenshot failed for {tweet_id}: {exc}\n")

    # Structured image extraction. X serves photos via pbs.twimg.com; the
    # tweetPhoto testid wraps them. Alt text is author-written and often
    # carries substance the body text omits.
    try:
        photo_imgs = await article.locator('[data-testid="tweetPhoto"] img').all()
        for img in photo_imgs:
            src = await img.get_attribute("src")
            alt = await img.get_attribute("alt")
            if src and "pbs.twimg.com" in src:
                # Upgrade to full-resolution: replace &name=small/medium with &name=large
                if "&name=" in src:
                    src = src.split("&name=")[0] + "&name=large"
                out["image_urls"].append(src)
                out["image_alt_texts"].append(alt or "")
    except Exception:
        pass

    # Video presence — actual src URLs are usually blob:// inside the player,
    # so we report presence only. The screenshot covers the poster frame.
    try:
        out["has_video"] = bool(await article.locator("video").count())
    except Exception:
        pass

    # Quoted-tweet detection. X nests a second <article> inside the outer one
    # for quote-tweets. Its status link is the quoted-tweet ID.
    try:
        nested = await article.locator("article").all()
        for n in nested:
            # Pull the status link inside the nested article
            cnt = await n.locator('a[href*="/status/"]').count()
            if cnt:
                href = await n.locator('a[href*="/status/"]').first.get_attribute("href")
                if href and "/status/" in href:
                    qtid = href.split("/status/")[-1].split("?")[0]
                    if qtid and qtid != tweet_id:
                        out["quoted_tweet_ids"].append(qtid)
    except Exception:
        pass

    # External link previews — X surfaces them as card components. We collect
    # any anchor whose href is outside x.com / twitter.com.
    try:
        anchors = await article.locator('a[role="link"][href^="http"]').all()
        seen: set[str] = set()
        for anc in anchors:
            href = await anc.get_attribute("href")
            if not href:
                continue
            if any(host in href for host in ("x.com", "twitter.com", "t.co")):
                # t.co is the X URL shortener — its target is the actual link;
                # X usually expands it visibly. Skip the shortener form to avoid
                # noise; the expanded form will also be present.
                continue
            if href in seen:
                continue
            seen.add(href)
            out["external_link_urls"].append(href)
    except Exception:
        pass

    return out


async def cmd_search(query: str, limit: int, capture_media: bool = True) -> int:
    pw, ctx, is_cdp = await open_context(headless=True)
    try:
        ok, _ = await ensure_logged_in(ctx)
        if not ok:
            sys.stderr.write("[x_browser] Not logged in. Run: x_browser.py login\n")
            return 5
        page = await ctx.new_page()
        try:
            q = query.replace(" ", "%20")
            await page.goto(
                f"{X_BASE}/search?q={q}&src=typed_query&f=live",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            try:
                await page.wait_for_selector('article[data-testid="tweet"]', timeout=15_000)
            except PWTimeout:
                print("[]")
                return 1
            for _ in range(2):
                await page.mouse.wheel(0, 1500)
                await page.wait_for_timeout(800)
            rows: list[dict[str, Any]] = []
            articles = await page.locator('article[data-testid="tweet"]').all()
            for a in articles[:limit]:
                try:
                    # Author = the User-Name block's link, NOT the first /-prefixed
                    # anchor (which on reply chains lands on the REPLIED-TO user).
                    # X marks the author with data-testid="User-Name".
                    try:
                        link = await (
                            a.locator('[data-testid="User-Name"] a[role="link"][href^="/"]')
                            .first.get_attribute("href")
                        )
                    except Exception:
                        link = None
                    if not link:
                        # Fallback to the old selector if the User-Name block is absent
                        # (very old DOM build or partial render).
                        link = await a.locator('a[role="link"][href^="/"]').first.get_attribute("href")
                    handle = link.lstrip("/").split("/")[0] if link else None
                    status_href = await a.locator('a[href*="/status/"]').first.get_attribute("href")
                    tid = status_href.split("/status/")[-1].split("?")[0] if status_href else None
                    text_content = (
                        await a.locator('[data-testid="tweetText"]').first.inner_text()
                    ) if await a.locator('[data-testid="tweetText"]').count() else ""
                    row: dict[str, Any] = {
                        "id": tid,
                        "author": handle,
                        "text": text_content[:240],
                    }
                    # Media capture is gated by --capture-media (default on).
                    # Backwards-compatible: new keys merged in, existing keys
                    # untouched. Callers using `row.get("image_urls", [])`
                    # work whether or not media is captured.
                    media = await _capture_article_media(a, page, tid, capture_media)
                    row.update(media)
                    rows.append(row)
                except Exception as exc:  # noqa: BLE001 — DOM drift possible
                    rows.append({"error": str(exc)})
            print(json.dumps(rows, indent=2))
            return 0 if rows else 1
        finally:
            try:
                await page.close()
            except Exception:
                pass
    finally:
        await close_context(pw, ctx, is_cdp)


# ---------- CLI ----------

def _add_marketing_shape_flag(p: argparse.ArgumentParser) -> None:
    """Add --allow-marketing-shape to a write-subcommand parser.

    Default: detector blocks marketing-shape leads (proprietary nouns in
    first ~12 words). Flag overrides for insider audiences who already use
    the vocabulary (Moltbook framework participants, named anchors).
    """
    p.add_argument(
        "--allow-marketing-shape",
        dest="allow_marketing_shape",
        action="store_true",
        default=False,
        help="Bypass the marketing-shape detector. Use only when the "
        "audience is an insider one (Moltbook framework participants, "
        "named anchors) and the proprietary noun lands as common ground. "
        "See ~/.config/moltbook/loop.md §Marketing-shape vs ideas-shape.",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="One-time: open visible browser for manual login")
    sub.add_parser("whoami", help="Verify the saved session")
    r = sub.add_parser("reply", help="Reply to a tweet by ID (bypasses the 403)")
    r.add_argument("tweet_id")
    r.add_argument("text")
    _add_marketing_shape_flag(r)
    q = sub.add_parser("quote", help="Quote-tweet a tweet by ID with your own framing on top")
    q.add_argument("tweet_id")
    q.add_argument("text")
    _add_marketing_shape_flag(q)
    po = sub.add_parser("post", help="Post a standalone tweet")
    po.add_argument("text")
    _add_marketing_shape_flag(po)
    s = sub.add_parser("search", help="Search recent tweets via the /search page")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument(
        "--no-capture-media",
        dest="capture_media",
        action="store_false",
        default=True,
        help="Skip the per-article screenshot + media extraction "
        "(faster; loses visual context — use only when you have a text-only consumer)",
    )
    # `check-shape` is a no-network utility — runs the marketing-shape detector
    # against a candidate string and exits. Useful for pre-flight in scripts.
    cs = sub.add_parser(
        "check-shape",
        help="Run the marketing-shape detector on a draft reply text; exit 8 if blocked, 0 if ok",
    )
    cs.add_argument("text")
    return p


async def _main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "login":
        return await cmd_login()
    if args.cmd == "whoami":
        return await cmd_whoami()
    if args.cmd == "reply":
        return await cmd_reply(args.tweet_id, args.text, args.allow_marketing_shape)
    if args.cmd == "quote":
        return await cmd_quote(args.tweet_id, args.text, args.allow_marketing_shape)
    if args.cmd == "post":
        return await cmd_post(args.text, args.allow_marketing_shape)
    if args.cmd == "search":
        return await cmd_search(args.query, args.limit, args.capture_media)
    if args.cmd == "check-shape":
        check = check_marketing_shape(args.text)
        print(json.dumps(check, indent=2))
        return EXIT_MARKETING_SHAPE_BLOCKED if check["is_marketing_shape"] else 0
    return 2


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())

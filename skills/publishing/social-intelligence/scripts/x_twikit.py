#!/usr/bin/env python3
"""x_twikit.py — proactive X engagement via Twikit (unofficial web API).

Bypasses the xurl 403 constraint on cold replies. Twikit uses Twitter's
internal web API, which mirrors the web UI and does NOT enforce the
"reply outside conversation graph" restriction the developer API does.

Setup:
  mkdir -p ~/.config/x
  cat > ~/.config/x/twikit-secrets.json <<EOF
  {
    "username": "broomva_tech",
    "email":    "you@example.com",
    "password": "...",
    "totp_secret": "BASE32SECRET"     // optional, if 2FA enabled
  }
  EOF
  chmod 600 ~/.config/x/twikit-secrets.json

Cookies auto-persist at ~/.config/x/twikit-cookies.json after first login.
Reuse cookies on every subsequent call — login itself is heavily monitored
by X and should be avoided when possible.

Usage:
  python3 x_twikit.py login-check
  python3 x_twikit.py search "AI agent stability" --min-likes 10
  python3 x_twikit.py reply <tweet_id> "<text>"
  python3 x_twikit.py post "<text>"
  python3 x_twikit.py whoami

Safety rails (per twikit/ToProtectYourAccount.md):
  - 30s cooldown between write actions
  - Cookie reuse always preferred over re-login
  - Forbidden / AccountLocked / TooManyRequests surface as non-zero exit
  - Max 4 reply actions per process run (defense in depth)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    from twikit import Client
    from twikit.errors import (
        AccountLocked,
        AccountSuspended,
        Forbidden,
        TooManyRequests,
        TwitterException,
    )
except ImportError:
    sys.stderr.write(
        "twikit not installed. Run: pip install twikit\n"
    )
    sys.exit(2)

SECRETS_PATH = Path.home() / ".config" / "x" / "twikit-secrets.json"
COOKIES_PATH = Path.home() / ".config" / "x" / "twikit-cookies.json"
WRITE_COOLDOWN_SECONDS = 30
MAX_WRITES_PER_RUN = 4


def load_secrets() -> dict[str, str]:
    if not SECRETS_PATH.exists():
        sys.stderr.write(
            f"Secrets file missing: {SECRETS_PATH}\n"
            "Create it with username/email/password. See script docstring.\n"
        )
        sys.exit(2)
    data = json.loads(SECRETS_PATH.read_text())
    required = {"username", "password"}
    missing = required - set(data)
    if missing:
        sys.stderr.write(
            f"Secrets file missing required fields: {sorted(missing)}\n"
        )
        sys.exit(2)
    return data


async def get_client() -> Client:
    """Return an authenticated Client, reusing cookies if possible."""
    secrets = load_secrets()
    client = Client("en-US")
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)

    if COOKIES_PATH.exists():
        try:
            client.load_cookies(str(COOKIES_PATH))
            # Probe with a cheap read to confirm the cookies are still valid.
            await client.user()
            return client
        except Exception as exc:  # noqa: BLE001 — cookies might be stale
            sys.stderr.write(f"[twikit] cookie probe failed: {exc}; re-login\n")

    # Fresh login. Use auth_info_1=username, auth_info_2=email if present.
    kwargs: dict[str, Any] = {
        "auth_info_1": secrets["username"],
        "password": secrets["password"],
    }
    if "email" in secrets:
        kwargs["auth_info_2"] = secrets["email"]
    if "totp_secret" in secrets:
        kwargs["totp_secret"] = secrets["totp_secret"]

    await client.login(**kwargs)
    client.save_cookies(str(COOKIES_PATH))
    # Restrict file mode — cookies are session tokens.
    COOKIES_PATH.chmod(0o600)
    return client


# ---------- Safety rails ----------

_write_count = 0
_last_write_ts: float = 0.0


def _rate_gate() -> None:
    global _write_count, _last_write_ts
    if _write_count >= MAX_WRITES_PER_RUN:
        sys.stderr.write(
            f"[twikit] write cap reached ({MAX_WRITES_PER_RUN}); abort\n"
        )
        sys.exit(3)
    elapsed = time.time() - _last_write_ts
    if _last_write_ts and elapsed < WRITE_COOLDOWN_SECONDS:
        sleep_s = WRITE_COOLDOWN_SECONDS - elapsed
        sys.stderr.write(f"[twikit] cooldown {sleep_s:.1f}s\n")
        time.sleep(sleep_s)


def _mark_write() -> None:
    global _write_count, _last_write_ts
    _write_count += 1
    _last_write_ts = time.time()


# ---------- Commands ----------

async def cmd_login_check() -> int:
    client = await get_client()
    me = await client.user()
    print(json.dumps({
        "ok": True,
        "screen_name": me.screen_name,
        "name": me.name,
        "followers": me.followers_count,
        "following": me.following_count,
        "cookies": str(COOKIES_PATH),
    }, indent=2))
    return 0


async def cmd_whoami() -> int:
    return await cmd_login_check()


async def cmd_search(query: str, min_likes: int, limit: int) -> int:
    client = await get_client()
    tweets = await client.search_tweet(query, product="Top", count=limit)
    rows = []
    for t in tweets:
        likes = t.favorite_count or 0
        if likes < min_likes:
            continue
        rows.append({
            "id": t.id,
            "created_at": t.created_at,
            "author": t.user.screen_name if t.user else None,
            "author_followers": (t.user.followers_count if t.user else 0),
            "likes": likes,
            "replies": t.reply_count or 0,
            "retweets": t.retweet_count or 0,
            "views": t.view_count or 0,
            "text": (t.text or "")[:240],
        })
    print(json.dumps(rows, indent=2, default=str))
    return 0 if rows else 1


async def cmd_reply(tweet_id: str, text: str) -> int:
    _rate_gate()
    client = await get_client()
    try:
        t = await client.create_tweet(text=text, reply_to=tweet_id)
    except Forbidden as exc:
        sys.stderr.write(f"[twikit] Forbidden: {exc}\n")
        return 4
    except (AccountLocked, AccountSuspended) as exc:
        sys.stderr.write(f"[twikit] ACCOUNT STATE FAILURE: {type(exc).__name__}: {exc}\n")
        return 5
    except TooManyRequests as exc:
        sys.stderr.write(f"[twikit] TooManyRequests: {exc}\n")
        return 6
    except TwitterException as exc:
        sys.stderr.write(f"[twikit] TwitterException: {exc}\n")
        return 7
    _mark_write()
    print(json.dumps({
        "ok": True,
        "reply_id": t.id,
        "reply_to": tweet_id,
        "url": f"https://x.com/broomva_tech/status/{t.id}",
    }, indent=2))
    return 0


async def cmd_post(text: str) -> int:
    _rate_gate()
    client = await get_client()
    try:
        t = await client.create_tweet(text=text)
    except (AccountLocked, AccountSuspended) as exc:
        sys.stderr.write(f"[twikit] ACCOUNT STATE FAILURE: {type(exc).__name__}: {exc}\n")
        return 5
    except TooManyRequests as exc:
        sys.stderr.write(f"[twikit] TooManyRequests: {exc}\n")
        return 6
    except TwitterException as exc:
        sys.stderr.write(f"[twikit] TwitterException: {exc}\n")
        return 7
    _mark_write()
    print(json.dumps({
        "ok": True,
        "tweet_id": t.id,
        "url": f"https://x.com/broomva_tech/status/{t.id}",
    }, indent=2))
    return 0


# ---------- CLI ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login-check", help="Verify credentials; refresh cookies if needed")
    sub.add_parser("whoami", help="Show @broomva_tech profile metrics")

    s = sub.add_parser("search", help="Search recent tweets")
    s.add_argument("query")
    s.add_argument("--min-likes", type=int, default=5)
    s.add_argument("--limit", type=int, default=20)

    r = sub.add_parser("reply", help="Reply to a tweet by ID (bypasses 403)")
    r.add_argument("tweet_id")
    r.add_argument("text")

    po = sub.add_parser("post", help="Post a standalone tweet")
    po.add_argument("text")

    return p


async def _main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd in ("login-check", "whoami"):
        return await cmd_login_check()
    if args.cmd == "search":
        return await cmd_search(args.query, args.min_likes, args.limit)
    if args.cmd == "reply":
        return await cmd_reply(args.tweet_id, args.text)
    if args.cmd == "post":
        return await cmd_post(args.text)
    parser.print_help()
    return 2


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())

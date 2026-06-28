#!/usr/bin/env python3
"""Prompt library sync CLI.

Pull, push, list, and update prompts from a broomva.tech-compatible prompt API.

Usage:
    python3 prompt-sync.py list [--category CAT] [--tag TAG] [--model MODEL] [--endpoint URL]
    python3 prompt-sync.py pull SLUG [--var KEY=VAL ...] [--endpoint URL] [--raw]
    python3 prompt-sync.py push --title TITLE --category CAT --body BODY [--model MODEL] [--tags T1,T2] [--repo-path PATH]
    python3 prompt-sync.py update SLUG [--body BODY] [--bump-version] [--repo-path PATH]
    python3 prompt-sync.py remote-push --title TITLE --category CAT --body BODY [--token TOKEN] [--endpoint URL]
    python3 prompt-sync.py remote-update SLUG [--body BODY] [--title TITLE] [--token TOKEN] [--endpoint URL]
    python3 prompt-sync.py remote-delete SLUG [--token TOKEN] [--endpoint URL]
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

DEFAULT_ENDPOINT = "https://broomva.tech/api/prompts"


def _get_token(args: argparse.Namespace) -> str:
    token = getattr(args, "token", None) or os.environ.get("BROOMVA_API_TOKEN")
    if not token:
        print("Error: --token or BROOMVA_API_TOKEN env var required", file=sys.stderr)
        sys.exit(1)
    return token


def api_get(url: str) -> dict | list:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "prompt-sync/1.0"})
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        print(f"HTTP {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def api_mutate(url: str, method: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload else None
    req = Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "prompt-sync/1.0",
        },
        method=method,
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.readable() else e.reason
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def cmd_list(args: argparse.Namespace) -> None:
    params = {}
    if args.category:
        params["category"] = args.category
    if args.tag:
        params["tag"] = args.tag
    if args.model:
        params["model"] = args.model

    url = args.endpoint
    if params:
        url += "?" + urlencode(params)

    entries = api_get(url)
    if not entries:
        print("No prompts found.")
        return

    max_title = max(len(e.get("title", "")) for e in entries)
    max_cat = max((len(e.get("category", "") or "") for e in entries), default=0)

    for entry in entries:
        title = entry.get("title", "").ljust(max_title)
        cat = (entry.get("category") or "").ljust(max_cat)
        ver = entry.get("version", "")
        slug = entry.get("slug", "")
        tags = ", ".join(entry.get("tags", [])[:3])
        print(f"  {slug:<35} {cat}  v{ver:<6} {title}  [{tags}]")


def cmd_pull(args: argparse.Namespace) -> None:
    url = f"{args.endpoint}/{args.slug}"
    entry = api_get(url)

    if "error" in entry:
        print(f"Error: {entry['error']}", file=sys.stderr)
        sys.exit(1)

    content = entry.get("content", "")

    if args.var:
        for var_pair in args.var:
            if "=" not in var_pair:
                print(f"Invalid variable format: {var_pair} (expected KEY=VALUE)", file=sys.stderr)
                continue
            key, val = var_pair.split("=", 1)
            content = content.replace(f"{{{{{key}}}}}", val)

    if args.raw:
        print(content)
    else:
        title = entry.get("title", args.slug)
        category = entry.get("category", "")
        version = entry.get("version", "")
        model = entry.get("model", "")
        variables = entry.get("variables", [])

        print(f"# {title}")
        meta_parts = []
        if category:
            meta_parts.append(f"category: {category}")
        if version:
            meta_parts.append(f"version: {version}")
        if model:
            meta_parts.append(f"model: {model}")
        if meta_parts:
            print(f"# {' | '.join(meta_parts)}")

        if variables:
            print("\n## Variables")
            for v in variables:
                default = v.get("default", "")
                print(f"  {{{{{v['name']}}}}} — {v['description']} (default: {default})")

        print(f"\n{content}")


def cmd_push(args: argparse.Namespace) -> None:
    repo_path = Path(args.repo_path).resolve()
    prompts_dir = repo_path / "apps" / "chat" / "content" / "prompts"

    if not prompts_dir.exists():
        prompts_dir = repo_path / "content" / "prompts"

    if not prompts_dir.exists():
        prompts_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^a-z0-9]+", "-", args.title.lower()).strip("-")
    filepath = prompts_dir / f"{slug}.mdx"

    if filepath.exists():
        print(f"Prompt already exists: {filepath}", file=sys.stderr)
        print("Use 'update' command to modify existing prompts.", file=sys.stderr)
        sys.exit(1)

    tags_yaml = ""
    if args.tags:
        tag_list = [t.strip() for t in args.tags.split(",")]
        tags_yaml = "\ntags:\n" + "\n".join(f"  - {t}" for t in tag_list)

    model_yaml = f"\nmodel: {args.model}" if args.model else ""

    frontmatter = f"""---
title: "{args.title}"
summary: ""
date: {date.today().isoformat()}
published: false
category: {args.category}{model_yaml}
version: "1.0"{tags_yaml}
---"""

    filepath.write_text(f"{frontmatter}\n\n{args.body}\n", encoding="utf-8")
    print(f"Created: {filepath}")
    print("Note: published=false — review and set to true when ready.")


def cmd_update(args: argparse.Namespace) -> None:
    repo_path = Path(args.repo_path).resolve()
    prompts_dir = repo_path / "apps" / "chat" / "content" / "prompts"

    if not prompts_dir.exists():
        prompts_dir = repo_path / "content" / "prompts"

    filepath = prompts_dir / f"{args.slug}.mdx"
    if not filepath.exists():
        print(f"Prompt not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    content = filepath.read_text(encoding="utf-8")

    if args.body:
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = f"---{parts[1]}---\n\n{args.body}\n"

    if args.bump_version:
        match = re.search(r'version:\s*"(\d+)\.(\d+)"', content)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            new_version = f"{major}.{minor + 1}"
            content = content.replace(match.group(0), f'version: "{new_version}"')

    today = date.today().isoformat()
    content = re.sub(r"date:\s*\S+", f"date: {today}", content)

    filepath.write_text(content, encoding="utf-8")
    print(f"Updated: {filepath}")


# ─── Remote (API-based) commands ──────────────────────────────────────────────


def cmd_remote_push(args: argparse.Namespace) -> None:
    """Push a new prompt to the remote API."""
    token = _get_token(args)

    payload: dict = {
        "title": args.title,
        "content": args.body,
        "category": args.category,
        "visibility": args.visibility,
    }
    if args.summary:
        payload["summary"] = args.summary
    if args.model:
        payload["model"] = args.model
    if args.version:
        payload["version"] = args.version
    if args.tags:
        payload["tags"] = [t.strip() for t in args.tags.split(",")]

    result = api_mutate(args.endpoint, "POST", token, payload)
    slug = result.get("slug", "")
    print(f"Created: {slug}")
    print(f"  URL: {args.endpoint}/{slug}")


def cmd_remote_update(args: argparse.Namespace) -> None:
    """Update an existing prompt via the remote API."""
    token = _get_token(args)
    url = f"{args.endpoint}/{args.slug}"

    payload: dict = {}
    if args.title:
        payload["title"] = args.title
    if args.body:
        payload["content"] = args.body
    if args.category:
        payload["category"] = args.category
    if args.model:
        payload["model"] = args.model
    if args.tags:
        payload["tags"] = [t.strip() for t in args.tags.split(",")]
    if args.bump_version:
        # Fetch current version first
        entry = api_get(url)
        ver = entry.get("version", "1.0")
        match = re.match(r"(\d+)\.(\d+)", ver)
        if match:
            payload["version"] = f"{match.group(1)}.{int(match.group(2)) + 1}"

    if not payload:
        print("Nothing to update. Provide at least one of: --title, --body, --category, --model, --tags, --bump-version", file=sys.stderr)
        sys.exit(1)

    result = api_mutate(url, "PUT", token, payload)
    print(f"Updated: {args.slug}")
    if "version" in result:
        print(f"  Version: {result['version']}")


def cmd_remote_delete(args: argparse.Namespace) -> None:
    """Soft-delete a prompt via the remote API."""
    token = _get_token(args)
    url = f"{args.endpoint}/{args.slug}"

    result = api_mutate(url, "DELETE", token)
    if result.get("deleted"):
        print(f"Deleted: {args.slug}")
    else:
        print(f"Failed to delete: {args.slug}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prompt library sync CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── Read commands ──
    ls = sub.add_parser("list", help="List available prompts")
    ls.add_argument("--category", help="Filter by category")
    ls.add_argument("--tag", help="Filter by tag")
    ls.add_argument("--model", help="Filter by model")
    ls.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="API endpoint")

    pull = sub.add_parser("pull", help="Pull a prompt by slug")
    pull.add_argument("slug", help="Prompt slug")
    pull.add_argument("--var", action="append", help="Variable substitution KEY=VALUE")
    pull.add_argument("--raw", action="store_true", help="Print raw content only")
    pull.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="API endpoint")

    # ── Local write commands ──
    push = sub.add_parser("push", help="Create a new prompt MDX file locally")
    push.add_argument("--title", required=True, help="Prompt title")
    push.add_argument("--category", required=True, help="Prompt category")
    push.add_argument("--body", required=True, help="Prompt body content")
    push.add_argument("--model", help="Target model")
    push.add_argument("--tags", help="Comma-separated tags")
    push.add_argument("--repo-path", default=".", help="Repository root path")

    update = sub.add_parser("update", help="Update an existing prompt locally")
    update.add_argument("slug", help="Prompt slug")
    update.add_argument("--body", help="New body content")
    update.add_argument("--bump-version", action="store_true", help="Bump minor version")
    update.add_argument("--repo-path", default=".", help="Repository root path")

    # ── Remote write commands (API-based) ──
    rp = sub.add_parser("remote-push", help="Create a prompt via the remote API")
    rp.add_argument("--title", required=True, help="Prompt title")
    rp.add_argument("--category", required=True, help="Prompt category")
    rp.add_argument("--body", required=True, help="Prompt body content")
    rp.add_argument("--summary", help="Short summary")
    rp.add_argument("--model", help="Target model")
    rp.add_argument("--version", help="Version string (default: 1.0)")
    rp.add_argument("--tags", help="Comma-separated tags")
    rp.add_argument("--visibility", default="public", choices=["public", "private"], help="Visibility")
    rp.add_argument("--token", help="API token (or set BROOMVA_API_TOKEN)")
    rp.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="API endpoint")

    ru = sub.add_parser("remote-update", help="Update a prompt via the remote API")
    ru.add_argument("slug", help="Prompt slug")
    ru.add_argument("--title", help="New title")
    ru.add_argument("--body", help="New body content")
    ru.add_argument("--category", help="New category")
    ru.add_argument("--model", help="New model")
    ru.add_argument("--tags", help="New comma-separated tags")
    ru.add_argument("--bump-version", action="store_true", help="Bump minor version")
    ru.add_argument("--token", help="API token (or set BROOMVA_API_TOKEN)")
    ru.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="API endpoint")

    rd = sub.add_parser("remote-delete", help="Delete a prompt via the remote API")
    rd.add_argument("slug", help="Prompt slug")
    rd.add_argument("--token", help="API token (or set BROOMVA_API_TOKEN)")
    rd.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="API endpoint")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "pull": cmd_pull,
        "push": cmd_push,
        "update": cmd_update,
        "remote-push": cmd_remote_push,
        "remote-update": cmd_remote_update,
        "remote-delete": cmd_remote_delete,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()

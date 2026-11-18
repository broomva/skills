#!/usr/bin/env python3
"""Mutation check for reel_loop's gates: delete each gate in a scratch copy and
require the test suite to fail.

A gate whose deletion leaves every test green is not tested, whatever the prose
says. Each mutation names the exact source text it replaces; if that text is no
longer in the script (a rename or refactor), this check FAILS instead of
silently skipping the mutation, so a renamed gate cannot retire its own check.

Run: python3 tests/mutation_check.py      (from skills/video/reel-loop)
Not collected by pytest (no test_ prefix): it runs pytest itself.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]

MUTATIONS = [
    ("approval sha binding",
     'if approval["video_sha256"] != digest:', "if False:"),
    ("approval required",
     'if not approval:\n        return ["no approval', 'if False:\n        return ["no approval'),
    ("YouTube approval platform binding",
     'if approval.get("platform") != "youtube":', "if False:"),
    ("YouTube approval channel binding",
     'elif destination is not None and approved_channel != destination:', "elif False:"),
    ("Instagram optional approval platform binding",
     'if approval.get("platform") is not None and approval["platform"] != "instagram":', "if False:"),
    ("YouTube made_for_kids required",
     'if "made_for_kids" not in youtube or not isinstance(youtube.get("made_for_kids"), bool):', "if False:"),
    ("YouTube privacy defaults private",
     'privacy = youtube.get("privacy_status", "private")', 'privacy = youtube.get("privacy_status", "public")'),
    ("Shorts aspect ratio",
     "elif width > height:", "elif False:"),
    ("Shorts duration",
     'if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not SHORT_MIN_SECONDS <= duration <= SHORT_MAX_SECONDS:',
     "if False:"),
    ("YouTube disclosure forced for synthetic media",
     'contains = youtube.get("contains_synthetic_media") is True or is_ai',
     'contains = youtube.get("contains_synthetic_media") is True'),
    ("YouTube session host is validated",
     "if not _valid_google_session(location):", "if False:"),
    ("YouTube channel check happens before upload",
     'if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict) or items[0].get("id") != channel_id:',
     "if False:"),
    ("YouTube token endpoint pin",
     "if token_uri is not None and token_uri != GOOGLE_TOKEN_URI:", "if False:"),
    ("consent checked for a declared clone",
     'reasons += _consent_errors(card.get("voice_consent"), card_dir, now)', "pass"),
    ("consent file must exist",
     "elif not (card_dir / ref).is_file():", "elif False:"),
    ("consent date must parse",
     'if when is None:\n        errs.append("voice_consent.date must be an ISO date")',
     'if False:\n        errs.append("voice_consent.date must be an ISO date")'),
    ("declared synthetic forces disclosure",
     'is_ai = card.get("is_ai_generated") is True or any(synthetic.values())',
     'is_ai = card.get("is_ai_generated") is True'),
    ("explicit disclosure kept",
     'is_ai = card.get("is_ai_generated") is True or any(synthetic.values())',
     "is_ai = any(synthetic.values())"),
    ("malformed cards blocked",
     "def _type_errors(card) -> list[str]:", "def _type_errors(card) -> list[str]:\n    return []"),
    ("publish sends the gated bytes, not the file as it is now",
     'str(len(data))}, body=data)', 'str(len(data))}, body=video.read_bytes())'),
    ("blocked card makes no API call",
     "    if container is None:\n        return None, reasons, notes\n\n    bearer = {",
     "    bearer = {"),
    ("empty video blocked",
     'if not data:\n        return None, ["video is empty"]', 'if False:\n        return None, ["video is empty"]'),
    ("oversize blocked",
     "if len(data) > REEL_MAX_BYTES:", "if False:"),
    ("container ERROR status fails the publish",
     'if status in ("ERROR", "EXPIRED"):', "if False:"),
    ("HTTP errors carry no server text",
     'failure = f"{where} -> HTTP {exc.code} ({_meta_error_codes(exc.read())})"',
     'failure = f"{where} -> HTTP {exc.code}: {exc.read()[:500].decode(\'utf-8\', \'replace\')}"'),
    ("network errors raise outside except, chaining nothing",
     "except (urllib.error.URLError, OSError) as exc:\n        failure = f\"{where} failed: {type(getattr(exc, 'reason', exc)).__name__}\"\n    if failure:\n        raise PublishError(failure)\n    try:\n        out = json.loads(raw or b\"{}\")",
     "except (urllib.error.URLError, OSError) as exc:\n        raise PublishError(f\"{where} failed: {type(getattr(exc, 'reason', exc)).__name__}\") from None\n    if failure:\n        raise PublishError(failure)\n    try:\n        out = json.loads(raw or b\"{}\")"),
    ("ids must be numeric",
     "if not isinstance(rid, str) or not _ID.fullmatch(rid):", "if not isinstance(rid, str) or not rid:"),
    ("replies carrying an error object fail",
     'if "error" in out:', "if False:"),
    ("no poll starts at or after the deadline",
     "        if clock() >= deadline:", "        if False:"),
    ("CLI prints only the type of an unexpected exception",
     "                except PublishError as exc:\n                    failure = _redact(str(exc), token)\n                except Exception as exc:  # noqa: BLE001 - never print an unexpected exception's text here\n                    failure = f\"unexpected {type(exc).__name__}\"",
     "                except PublishError as exc:\n                    failure = _redact(str(exc), token)\n                except Exception as exc:  # noqa: BLE001 - never print an unexpected exception's text here\n                    failure = str(exc)"),
    ("poll sends the token in a header, not the URL",
     'params={"fields": "status_code"},\n                      headers=bearer,',
     'params={"fields": "status_code", "access_token": token},\n                      headers=bearer,'),
    ("container create sends the token in a header, not the body",
     "params=_form(container), headers=bearer)", 'params={**_form(container), "access_token": token}, headers=bearer)'),
    ("upload success must be boolean true",
     'if sent.get("success") is not True:', 'if not sent.get("success"):'),
    ("polling stops at the deadline",
     "if clock() + poll_every > deadline:", "if False:"),
    ("non-object replies are errors",
     "if not isinstance(out, dict):\n        raise PublishError(f\"{where}",
     "if False:\n        raise PublishError(f\"{where}"),
    ("caption length",
     "if len(caption) > CAPTION_MAX_CHARS:", "if False:"),
    ("ffprobe absent is UNCHECKED, not silent",
     'notes.append("UNCHECKED: ffprobe not on PATH, so codec, fps and duration were not verified")',
     'notes.append("checked: ffprobe not on PATH, so codec, fps and duration were not verified")'),
    ("leave-one-out baseline",
     'others = [x["views"] for x in items if x is not r]', 'others = [x["views"] for x in items]'),
    ("insights settle before judging",
     "if age_h < min_age_hours:", "if False:"),
    ("trial posts excluded from baseline",
     'if q is not p and not q["is_trial"]', "if q is not p"),
    ('funnel whole word keyword', 'r"(?!\\w)", text, re.IGNORECASE)', 'r"", text, re.IGNORECASE)'),
    ('funnel case insensitive', 'text, re.IGNORECASE) is not None', 'text) is not None'),
    ('funnel keyword required', 'not isinstance(text, str) or not keyword_hit(text, keyword)', 'not isinstance(text, str)'),
    ('funnel seven day window', 'if not 0 <= age < REPLY_WINDOW_SECONDS:', 'if False:'),
    ('funnel own comment skipped', 'if author["id"] == ig_user_id or str(author.get("username", "")).lower() == handle:', 'if False:'),
    ('funnel author required', 'continue  # missing author cannot establish that this is not our comment', 'author = {"id": "999"}'),
    ('funnel template approval required', 'if not isinstance(approval, dict) or not all(', 'if False and not all('),
    ('funnel template sha binding', 'if approval["template_sha256"] != digest:', 'if False:'),
    ('funnel dry run sends nothing', '                if go_live:', '                if True:'),
    ('funnel ledger idempotence', 'if cid in seen:', 'if False:'),
    ('funnel reserve before send', 'record({**base, "status": "attempting"})', 'pass'),
    ('funnel reservations fsynced', '            _full_sync(log.fileno())', '            pass'),
    ('funnel concurrent lock', 'fcntl.flock(log, fcntl.LOCK_EX | fcntl.LOCK_NB)', 'pass'),
    ('funnel ledger outside repository', 'if any((parent / ".git").exists() for parent in ledger.parents):', 'if False:'),
    ('funnel pagination bound', 'for page in range(max_pages):', 'for page in range(max_pages + 1):'),
    ('funnel approved bytes retained', '"message": {"text": message}}).encode("utf-8"))', '"message": {"text": template.read_text()}}).encode("utf-8"))'),
    ('funnel output excludes identity', '"keyword_hit": True}', '"keyword_hit": True, "username": author.get("username")}'),
    ('funnel binding covers post, keyword and account', 'if approval["binding_sha256"] != funnel_binding(media_id, keyword, ig_user_id, digest):', 'if False:'),
    ('funnel halts after first unsuccessful send', '                    return result  # the first unsuccessful send stops the run', '                    pass'),
    ('funnel uncertain sends listed for a human', 'result["needs_human"] = sorted({*result["needs_human"], cid})', 'pass'),
    ('funnel uncertain rows stay pending', 'if row["status"] in ("attempting", "uncertain"):', 'if row["status"] == "attempting":'),
    ('funnel 4xx is a definite rejection', 'rejected = re.search(r"-> HTTP 4\\d\\d\\b", str(exc)) is not None', 'rejected = False'),
    ('funnel one reply per commenter', 'if who in authors:', 'if False:'),
    ('funnel commenter dedupe persists', 'authors.add(row["author"])', 'pass'),
    ('funnel ledger rows validated', 'if not _valid_funnel_row(row):', 'if False:'),
    ('funnel account handle required', 'if not isinstance(handle, str) or not re.fullmatch(r"@?[A-Za-z0-9._]{1,30}", handle):', 'if False:'),
    ('funnel go-live needs explicit ledger', 'if a.go_live and a.ledger is None:', 'if False:'),
    ('funnel hidden comments skipped', 'if comment.get("hidden") is True:', 'if False:'),
    ('funnel salt required for a used ledger', 'if not ledger_is_empty:', 'if False:'),
    ('funnel ledger newline completed', 'if content and not content.endswith("\\n"):', 'if False:'),
    ('funnel new ledger directories synced', '        _sync_dir(new_dir.parent)', '        pass'),
    ('youtube tags count the commas', 'for t in tags) + max(0, len(tags) - 1)', 'for t in tags)'),
    ('youtube tags count quotes for spaced tags', 'len(t) + (2 if any(c.isspace() for c in t) else 0)', 'len(t)'),
    ('redirects refused', '    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401, ARG002\n        return None',
     '    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401, ARG002\n        return req'),
    ('opener installs the redirect refusal', 'build_opener(_NoRedirect()).open(req, timeout=timeout)', 'build_opener().open(req, timeout=timeout)'),
    ('google params stay in the query with a body', '        url = f"{url}?{urllib.parse.urlencode(params)}"\n    req = urllib.request.Request(url, data=data',
     '        pass\n    req = urllib.request.Request(url, data=data'),
    ('put goes to the returned session', 'resource, _ = _google_call("upload", "PUT", location,', 'resource, _ = _google_call("upload", "PUT", GOOGLE_UPLOAD,'),
    ('session uri scheme checked', 'return (parsed.scheme == "https" and parsed.hostname', 'return (parsed.scheme in ("https", "http") and parsed.hostname'),
    ('session uri userinfo checked', 'and parsed.username is None and parsed.password is None', 'and True'),
    ('session uri port checked', 'and parsed.port in (None, 443)', 'and True'),
    ('session uri path checked', 'and parsed.path == "/upload/youtube/v3/videos"\n', 'and True\n'),
    ('refresh pinned to the google endpoint', 'parsed, _ = _google_call("refresh token", "POST", GOOGLE_TOKEN_URI,', 'parsed, _ = _google_call("refresh token", "POST", "https://attacker.example/token",'),
    ('refresh uses the refresh grant', 'form = {"grant_type": "refresh_token",', 'form = {"grant_type": "client_credentials",'),
    ('credentials must be regular and owned', 'if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():', 'if False:'),
    ('credentials never follow a symlink', 'os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)', 'os.O_RDONLY'),
    ('explicit credentials win', 'token = environ.get("YT_ACCESS_TOKEN", "") if credentials is None else ""', 'token = environ.get("YT_ACCESS_TOKEN", "")'),
    ('stats failure redacted', 'print(f"STATS FAILED: {_redact_many(str(exc), redactions)}", file=sys.stderr)', 'print(f"STATS FAILED: {exc}", file=sys.stderr)'),
    ('youtube token refusal redacted', 'f"{_redact_many(str(exc), redactions)}", file=sys.stderr)\n                    return 2\n                failure = None', 'f"{exc}", file=sys.stderr)\n                    return 2\n                failure = None'),
    ('stats unexpected prints type only', 'print(f"STATS FAILED: unexpected {type(exc).__name__}", file=sys.stderr)', 'print(f"STATS FAILED: unexpected {exc}", file=sys.stderr)'),
    ('google network error has no upstream text', '        failure = "request failed"', '        failure = f"request failed {exc}"'),
    ('google call unexpected prints type only', 'raise PublishError(f"{step}: unexpected {type(exc).__name__}") from None', 'raise PublishError(f"{step}: unexpected {exc}") from None'),
    ('rotation swaps displayed dimensions', '        width, height = height, width\n', '        pass\n'),
    ('instagram approval cannot name a channel', '        if approval.get("channel_id") is not None:\n', '        if False:\n'),
    ('approval names the visibility', '    if approval and approval.get("privacy_status") != privacy:', '    if False:'),
    ('approval names the audience', '    if approval and approval.get("made_for_kids") is not youtube.get("made_for_kids"):', '    if False:'),
    ('whitespace title refused', 'or not title.strip() or len(title) > 100', 'or not title or len(title) > 100'),
    ('category digits only', 'if category is not None and re.fullmatch(r"[0-9]+", category, re.ASCII) is None:', 'if False:'),
    ('description angle brackets refused', 'len(description.encode("utf-8")) > 5000 or "<" in description or ">" in description', 'len(description.encode("utf-8")) > 5000'),
    ('instagram publisher refuses a youtube card', '    if card.get("platform", "instagram") != "instagram":\n        return None, ["a YouTube card', '    if False:\n        return None, ["a YouTube card'),
    ('youtube publisher refuses an instagram card', '    if card.get("platform", "instagram") != "youtube":\n        return None, ["an Instagram card', '    if False:\n        return None, ["an Instagram card'),
    ('tags: any whitespace counts as quoted', 'len(t) + (2 if any(c.isspace() for c in t) else 0)', 'len(t) + (2 if " " in t else 0)'),
    ('tags: empty and angle brackets refused', 'if tags is not None and any(not t.strip() or "<" in t or ">" in t for t in tags):', 'if False:'),
    ('youtube approval cannot name an instagram account', '        if approval.get("ig_user_id") is not None:\n            reasons.append("approval.ig_user_id names', '        if False:\n            reasons.append("approval.ig_user_id names'),
    ('credentials refuse execute and setuid bits', 'if stat.S_IMODE(st.st_mode) & ~0o600:', 'if st.st_mode & 0o077:'),
    ('session uri needs upload_id, no fragment', 'and not parsed.fragment and _one_upload_id(parse_qs(parsed.query)))', ')'),
    ('upload content length declared', '"X-Upload-Content-Length": str(len(data)), "X-Upload-Content-Type": "video/mp4"}', '"X-Upload-Content-Type": "video/mp4"}'),
    ('metadata is the gated insert body', 'metadata = json.dumps(insert_body, ensure_ascii=False', 'metadata = json.dumps({}, ensure_ascii=False'),
    ('session uri needs exactly one non-empty upload_id', 'return len(ids) == 1 and bool(ids[0].strip())', 'return bool(ids)'),
    ('upload declares its content type', '"Content-Length": str(len(data)), "Content-Type": "video/mp4"}', '"Content-Length": str(len(data))}'),
    ('stats asks for statistics and status of one id', 'params={"part": "statistics,status", "id": video_id},', 'params={"id": video_id},'),
    ('funnel CLI errors exclude upstream text', 'print(f"FUNNEL BLOCKED: {type(exc).__name__}", file=sys.stderr)', 'print(f"FUNNEL BLOCKED: {exc}", file=sys.stderr)'),
]


def run_suite(root: Path) -> int:
    return subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-x", "-p", "no:cacheprovider"],
                          cwd=root, capture_output=True, text=True).returncode


def main() -> int:
    src = (SKILL / "scripts" / "reel_loop.py").read_text(encoding="utf-8")
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "reel-loop"
        shutil.copytree(SKILL, root, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        target = root / "scripts" / "reel_loop.py"
        if run_suite(root) != 0:
            print("FAIL: the unmutated suite does not pass; fix that first")
            return 1
        for label, old, new in MUTATIONS:
            if src.count(old) != 1:
                print(f"FAIL  {label}: anchor found {src.count(old)} times (expected 1); update the mutation")
                failures += 1
                continue
            target.write_text(src.replace(old, new, 1), encoding="utf-8")
            killed = run_suite(root) != 0
            print(f"{'ok  ' if killed else 'FAIL'}  {label}: {'a test fails' if killed else 'every test still passes'}")
            failures += not killed
        target.write_text(src, encoding="utf-8")
    print(f"\n{len(MUTATIONS) - failures}/{len(MUTATIONS)} mutations killed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

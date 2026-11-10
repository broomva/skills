"""Per-host credentials for fleet hosts (BRO-3651; spec: docs/fleet/gcp-host-template.md §3).

Owner direction 2026-11-09: mint what can be minted, copy Linear, log in to Claude, Codex and gh
interactively over ssh when the host is spawned.

| Credential | How it reaches the host                                  | Revocation on shrink                       |
|------------|----------------------------------------------------------|--------------------------------------------|
| Vercel     | minted per host by the owner's minter token (team, 30 d) | DELETE by id; proof: GET by id is 404       |
| Neon       | minted per host, scoped to the preview project only      | DELETE by id; proof: not in the org key list |
| Linear     | the Mac's credentials.toml copied (owner accepted)       | file removed; the key is shared, not revoked |
| Claude, Codex, gh | interactive login over `ssh -t` (own grant per host) | logout on the host, proven logged out      |

Ledger rules (P20 r1):
- A minted id is recorded (state `pending`) before anything else can fail, so no live token is ever
  unrecorded. It becomes `active` only after the scope check and delivery succeed. A record is
  dropped only once the token is proven gone.
- "The host is gone" is concluded only from a definite NOT_FOUND on its GCP instance. An unreachable
  or stopped host blocks; it never counts as revoked.
Values travel only over ssh stdin into 0600 files under 0700 directories (never argv or a log). The
Mac keeps ids, never values, in meta/fleet-hosts/<host>/credentials.json.

No secret is ever exported into a shell or service environment (agentic-vps: no long-lived secret in the
agent's env, where every child process and error dump would see it). A wrapper in ~/.local/bin, ahead of
~/.bun/bin on PATH, loads ~/.config/fleet/<cli>.env into that one CLI process only. Shells export just the
non-secret ids from ~/.config/fleet/ids.env. Measured 2026-11-10: vercel and neonctl both accept the
token this way (VERCEL_TOKEN / NEON_API_KEY per process); neither reads a minted token from its own
config file.
Every step function has the fleet_host signature (h, apply) -> (status, detail).
"""
import json, os, shlex, subprocess, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OK, WOULD, OWNER, BLOCKED, FAIL = 'ok', 'would', 'owner', 'blocked', 'FAIL'

def _template():
    """The host template fleet_host.py uses (same resolution: --template, FLEET_HOST_TEMPLATE, default)."""
    here = Path(__file__).resolve().parent
    for i, a in enumerate(sys.argv):
        if a == '--template' and i + 1 < len(sys.argv):
            return json.loads(Path(sys.argv[i + 1]).read_text())
        if a.startswith('--template='):
            return json.loads(Path(a.split('=', 1)[1]).read_text())
    if os.environ.get('FLEET_HOST_TEMPLATE'):
        return json.loads(Path(os.environ['FLEET_HOST_TEMPLATE']).read_text())
    for p in (here / 'fleet-host/template.json', Path.home() / '.config/fleet-host/template.json'):
        if p.exists():
            return json.loads(p.read_text())
    sys.exit('fleet_host_creds: no host template (see fleet-host/template.example.json)')


C = _template()['credentials']
VERCEL_TEAM = C['vercel']['team']
VERCEL_SCOPE = C['vercel'].get('scope', VERCEL_TEAM)
VERCEL_MINTER = C['vercel']['minter_keychain']   # Keychain service holding the owner's full-account minter token
NEON_ORG = C['neon']['org']
# The preview (non-production) project. A minted key is proven unable to read prod_project before delivery.
NEON_PROJECT = C['neon']['project']
NEON_PROD_PROJECT = C['neon']['prod_project']
NEON_AUTH = Path.home() / '.config/neonctl/credentials.json'
NEON_API = 'https://console.neon.tech/api/v2'
LINEAR_CREDS = Path(os.path.expanduser(C['linear']['source']))
TTL_DAYS = C['vercel']['ttl_days']
ENABLED = set(C.get('enabled', ['vercel', 'neon', 'linear', 'logins']))
# Every host-side command gets these on PATH: Ubuntu's ~/.bashrc returns early for non-interactive
# shells, so `bash -l` alone does not see ~/.bun/bin (P20 r1 BLOCKER 3).
HOST_PATH = 'export PATH="$HOME/.local/bin:$HOME/.bun/bin:/usr/local/bin:$PATH"; '

# Host-side writer: reads {"files": {rel: content}, "remove": [rel], "env_profile": bool} on stdin.
# Paths are relative to $HOME. Nothing is echoed but "ok".
WRITER = r'''
import json, os, sys
d = json.load(sys.stdin); home = os.path.expanduser("~")
for rel, content in d.get("files", {}).items():
    p = os.path.join(home, rel); os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
    os.chmod(os.path.dirname(p), 0o700)
    fd = os.open(p + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write(content)
    os.replace(p + ".tmp", p)
for rel in d.get("remove", []):
    for q in (rel, rel + ".tmp"):
        try: os.remove(os.path.join(home, q))
        except FileNotFoundError: pass
for rel, real in d.get("wrappers", {}).items():
    # ~/.local/bin/<cli>: load only this CLI's token file into its own process, then exec the real CLI.
    p = os.path.join(home, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    name = os.path.basename(rel)
    body = ("#!/bin/sh\n# fleet host wrapper (BRO-3651): the token reaches this process only, never the shell.\n"
            f'f="$HOME/.config/fleet/{name}.env"\n'
            '[ -r "$f" ] && { set -a; . "$f"; set +a; }\n'
            f'exec "$HOME/{real}" "$@"\n')
    with open(p + ".tmp", "w") as f: f.write(body)
    os.chmod(p + ".tmp", 0o755); os.replace(p + ".tmp", p)
if d.get("env_profile"):
    # Non-secret ids only. Above Ubuntu's non-interactive guard in .bashrc, and in .profile.
    line = '[ -r "$HOME/.config/fleet/ids.env" ] && { set -a; . "$HOME/.config/fleet/ids.env"; set +a; }'
    mark = "# fleet host credentials (BRO-3651)"
    for rc, top in ((".bashrc", True), (".profile", False)):
        p = os.path.join(home, rc); t = open(p).read() if os.path.exists(p) else ""
        if line not in t:
            t = (mark + "\n" + line + "\n" + t) if top else (t + "\n" + mark + "\n" + line + "\n")
            with open(p + ".tmp", "w") as f: f.write(t)
            os.replace(p + ".tmp", p)
print("ok")
'''


def _run(cmd, input=None, timeout=60):
    try:
        r = subprocess.run(cmd, input=input, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, type(e).__name__


def ssh(host, script, input_json=None, timeout=60):
    """Run a bash script on the host, or with input_json the python WRITER reading JSON on stdin."""
    if input_json is None:
        return _run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', host, 'bash', '-l', '-s'],
                    input=HOST_PATH + script, timeout=timeout)
    return _run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', host,
                 'python3 -c ' + shlex.quote(script)], input=json.dumps(input_json), timeout=timeout)


def write_files(h, files=None, remove=None, env_profile=False, wrappers=None):
    rc, out = ssh(h.ssh_name, WRITER, {'files': files or {}, 'remove': remove or [], 'env_profile': env_profile,
                                       'wrappers': wrappers or {}})
    return rc == 0 and out.endswith('ok')


def http(method, url, token, body=None):
    """(status, json|None). Status 0 means no answer (network, TLS, timeout). The token goes in a header
    only; errors never include it."""
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
                                          'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, None


# ---- admin tokens on the Mac (read into memory only) --------------------------------------------------

def vercel_admin():
    """The minter token. The Vercel CLI's own login is an OAuth app token, and Vercel refuses to let app
    tokens create tokens (403 "Cannot create tokens for this app", measured 2026-11-09). The owner created
    one full-account token, entered via T3 request_secret, kept only in the Mac Keychain."""
    rc, out = _run(['security', 'find-generic-password', '-s', VERCEL_MINTER, '-w'])
    return out if rc == 0 and out else None


def neon_admin():
    _run(['neonctl', 'me', '-o', 'json'], timeout=60)  # refreshes the CLI's OAuth token when expired
    try:
        return json.loads(NEON_AUTH.read_text())['access_token']
    except (OSError, ValueError, KeyError):
        return None


# ---- the id record (no values) ------------------------------------------------------------------------

def record(h):
    try:
        return json.loads((h.dir / 'credentials.json').read_text())
    except (OSError, ValueError):
        return {}


def set_record(h, kind, value):
    """Write one kind's entry (None deletes it) atomically."""
    full = record(h)
    if value is None:
        full.pop(kind, None)
    else:
        full[kind] = value
    h.dir.mkdir(parents=True, exist_ok=True)
    tmp = h.dir / 'credentials.json.tmp'
    tmp.write_text(json.dumps(full, indent=2) + '\n')
    os.replace(tmp, h.dir / 'credentials.json')


def host_has(h, rel):
    rc, out = ssh(h.ssh_name, f'test -s "$HOME/{rel}" && echo yes || echo no', timeout=30)
    return True if rc == 0 and out == 'yes' else False if rc == 0 and out == 'no' else None


def disk_gone(h):
    """True only when the host's GCP instance is definitely NOT_FOUND (its disk went with it)."""
    if getattr(h, 'kind', None) != 'gcp':
        return False
    try:
        return h.instance_status(fresh=True) is None
    except Exception:  # noqa: BLE001 - an unobservable instance is not a deleted one
        return False


# ---- minted credentials (Vercel, Neon) ------------------------------------------------------------------

class Minted:
    kind = env_rel = admin_hint = wrapper = real = ''
    ids = ''  # non-secret exports for ~/.config/fleet/ids.env

    def admin(self): raise NotImplementedError
    def mint(self, h, admin): raise NotImplementedError        # -> (id, value, meta) or (None, None, why)
    def listed(self, admin, cid): raise NotImplementedError    # -> True / False / None (unknown)
    def delete(self, admin, cid): raise NotImplementedError
    def scope_ok(self, value): return True, ''
    def env(self, value): raise NotImplementedError

    def revoke_proven(self, admin, cid):
        """Delete if still present, then prove absence. True only on proof."""
        if self.listed(admin, cid) is False:
            return True
        self.delete(admin, cid)
        return self.listed(admin, cid) is False


class Vercel(Minted):
    kind, env_rel = 'vercel', '.config/fleet/vercel.env'
    wrapper, real = '.local/bin/vercel', '.bun/bin/vercel'
    admin_hint = (f'no Keychain {VERCEL_MINTER}: owner creates one full-account Vercel token (Account Settings > '
                  f'Tokens, scope {VERCEL_SCOPE}) and enters it via T3 request_secret')

    def admin(self):
        return vercel_admin()

    def mint(self, h, admin):
        expires = int((time.time() + TTL_DAYS * 86400) * 1000)
        status, body = http('POST', f'https://api.vercel.com/v3/user/tokens?teamId={VERCEL_TEAM}', admin,
                            {'name': f'fleet-{h.name}', 'expiresAt': expires})
        if status != 200 or not body or 'bearerToken' not in body:
            return None, None, f'mint failed (HTTP {status})'
        return body['token']['id'], body['bearerToken'], {
            'name': f'fleet-{h.name}', 'team': VERCEL_TEAM,
            'expires': datetime.fromtimestamp(expires / 1000, timezone.utc).isoformat()}

    def listed(self, admin, cid):
        status, _ = http('GET', f'https://api.vercel.com/v5/user/tokens/{cid}', admin)
        return True if status == 200 else False if status == 404 else None

    def delete(self, admin, cid):
        return http('DELETE', f'https://api.vercel.com/v3/user/tokens/{cid}', admin)[0]

    def env(self, value):
        # Not VERCEL_ORG_ID: the CLI then insists on VERCEL_PROJECT_ID too. Lanes pass --scope <team slug>.
        return f'VERCEL_TOKEN={value}\n'


class Neon(Minted):
    kind, env_rel = 'neon', '.config/fleet/neonctl.env'
    wrapper, real = '.local/bin/neonctl', '.bun/bin/neonctl'
    ids = f'NEON_PROJECT_ID={NEON_PROJECT}\nNEON_ORG_ID={NEON_ORG}\n'
    admin_hint = 'Mac has no neonctl login (`neonctl auth`)'

    def admin(self):
        return neon_admin()

    def mint(self, h, admin):
        status, body = http('POST', f'{NEON_API}/organizations/{NEON_ORG}/api_keys', admin,
                            {'key_name': f'fleet-{h.name}', 'project_id': NEON_PROJECT})
        if status not in (200, 201) or not body or 'key' not in body:
            return None, None, f'mint failed (HTTP {status}; org keys need org admin)'
        return body['id'], body['key'], {'name': f'fleet-{h.name}', 'project': NEON_PROJECT, 'org': NEON_ORG}

    def listed(self, admin, cid):
        status, body = http('GET', f'{NEON_API}/organizations/{NEON_ORG}/api_keys', admin)
        if status != 200 or body is None:
            return None
        keys = body if isinstance(body, list) else body.get('api_keys', [])
        return any(k.get('id') == cid for k in keys)

    def delete(self, admin, cid):
        return http('DELETE', f'{NEON_API}/organizations/{NEON_ORG}/api_keys/{cid}', admin)[0]

    def scope_ok(self, value):
        preview = http('GET', f'{NEON_API}/projects/{NEON_PROJECT}', value)[0]
        prod = http('GET', f'{NEON_API}/projects/{NEON_PROD_PROJECT}', value)[0]
        return preview == 200 and prod in (401, 403, 404), f'preview HTTP {preview}, production HTTP {prod}'

    def env(self, value):
        return f'NEON_API_KEY={value}\n'


def s_minted(m):
    def step(h, apply):
        rec = record(h).get(m.kind)
        reachable = h.reachable()
        if rec and rec.get('state') == 'active' and reachable and host_has(h, m.env_rel):
            return OK, f'{rec["name"]} ({rec["id"]}) on host'
        admin = m.admin()
        if not admin:
            return OWNER, m.admin_hint
        if not reachable:
            return WOULD, f'mint {m.kind} credential fleet-{h.name} once the host answers'
        if not apply:
            return WOULD, (f'mint {m.kind} credential fleet-{h.name}, deliver ~/{m.env_rel} 0600'
                           + (f'; first revoke the recorded {rec["id"]} with proof' if rec else ''))
        if rec and not m.revoke_proven(admin, rec['id']):
            return FAIL, f'recorded {m.kind} credential {rec["id"]} not proven revoked; kept on record, re-run'
        if rec:
            set_record(h, m.kind, None)
        cid, value, meta = m.mint(h, admin)
        if cid is None:
            return FAIL, meta
        set_record(h, m.kind, dict(meta, id=cid, state='pending'))  # recorded before anything else can fail
        ok, why = m.scope_ok(value)
        files = {m.env_rel: m.env(value)}
        if m.ids:
            files['.config/fleet/ids.env'] = m.ids
        delivered = ok and write_files(h, files=files, env_profile=True, wrappers={m.wrapper: m.real})
        del value
        if not delivered:
            what = f'scope check failed ({why})' if not ok else 'delivery failed'
            if m.revoke_proven(admin, cid):
                set_record(h, m.kind, None)
                return FAIL, f'{what}; minted {cid} revoked with proof'
            return FAIL, f'{what}; minted {cid} NOT proven revoked, kept on record as pending'
        set_record(h, m.kind, dict(meta, id=cid, state='active'))
        return OK, f'minted {meta["name"]} ({cid})' + (f'; {why}' if why else '')
    return step


def r_minted(m):
    def step(h, apply):
        rec = record(h).get(m.kind)
        if not rec:
            return OK, f'no {m.kind} credential recorded'
        admin = m.admin()
        if not admin:
            return OWNER, f'{m.admin_hint}; or delete {rec.get("name")} by hand and prove it'
        listed = m.listed(admin, rec['id'])
        if listed is None:
            return BLOCKED, f'cannot observe {m.kind} credential {rec["id"]} (API unreachable)'
        reachable = h.reachable()
        file_gone = (not reachable and disk_gone(h)) or (reachable and host_has(h, m.env_rel) is False)
        if listed is False and file_gone:  # already revoked and nothing left on the host
            if apply:
                set_record(h, m.kind, None)
            return OK, f'{rec["name"]} revoked (proven absent); no file left on the host'
        if not reachable and not disk_gone(h):
            return BLOCKED, 'host not reachable and its disk may exist; start it, then re-run'
        if not apply:
            return WOULD, (f'revoke {rec["name"]} ({rec["id"]}) with proof' if listed else
                           f'{rec["name"]} already revoked') + f'; remove ~/{m.env_rel} on the host'
        if not m.revoke_proven(admin, rec['id']):
            return FAIL, f'{rec["id"]} not proven revoked'
        if reachable and not write_files(h, remove=[m.env_rel]):
            return FAIL, f'{rec["id"]} revoked, but ~/{m.env_rel} not removed on the host; re-run'
        set_record(h, m.kind, None)
        return OK, f'revoked {rec["name"]} (proven absent)'
    return step


# ---- Linear (copied; owner accepted the shared key) -----------------------------------------------------

LINEAR_REL = '.config/linear/credentials.toml'


def s_linear(h, apply):
    if h.reachable() and host_has(h, LINEAR_REL):
        return OK, 'Linear credentials present (copied from the Mac; shared key)'
    if not LINEAR_CREDS.exists():
        return BLOCKED, f'no {LINEAR_CREDS} on the Mac'
    if not h.reachable() or not apply:
        return WOULD, f'copy {LINEAR_CREDS} (all its workspaces) to ~/{LINEAR_REL} 0600'
    if not write_files(h, files={LINEAR_REL: LINEAR_CREDS.read_text()}):
        return FAIL, 'copy failed'
    set_record(h, 'linear', {'copied_at': datetime.now(timezone.utc).isoformat(), 'shared_with_mac': True})
    return OK, 'copied'


def r_linear(h, apply):
    if not record(h).get('linear'):
        return OK, 'no Linear copy recorded'
    if not h.reachable():
        if disk_gone(h):
            set_record(h, 'linear', None)
            return OK, 'instance deleted; the copy went with its disk (the shared key stays valid)'
        return BLOCKED, 'host not reachable and its disk may exist; start it, then re-run'
    if not apply:
        return WOULD, 'remove ~/.config/linear/credentials.toml on the host (shared key: not revoked)'
    if not write_files(h, remove=[LINEAR_REL]) or host_has(h, LINEAR_REL) is not False:
        return FAIL, 'remove not proven'
    set_record(h, 'linear', None)
    return OK, 'removed (proven absent)'


# ---- Claude, Codex, gh: interactive logins over ssh -t -----------------------------------------------------

_LOGIN_CMDS = {  # name -> (status check, interactive login, logout)
    'claude': ('claude auth status --json 2>/dev/null | grep -q \'"loggedIn": *true\'', 'claude auth login', 'claude auth logout'),
    'codex': ('codex login status >/dev/null 2>&1', 'codex login --device-auth', 'codex logout'),
    'gh': ('gh auth status -h github.com >/dev/null 2>&1',
           'gh auth login -h github.com -p https -w -s workflow && gh auth setup-git', 'gh auth logout -h github.com </dev/null'),
}
# Template credentials.logins: [{"name": "claude", "account": "who approves it"}] (or bare names). Each is an
# independent grant made on the host, never a copied token: refresh tokens rotate, so a copy breaks a host.
LOGINS = [(n, *_LOGIN_CMDS[n], who) for n, who in
          ((e, 'the account the owner chooses') if isinstance(e, str) else (e['name'], e.get('account', '')) for e in
           _template()['credentials'].get('logins', list(_LOGIN_CMDS)))
          if n in _LOGIN_CMDS]


def logins_missing(h):
    """Names not logged in, or None when the status cannot be read."""
    script = '; '.join(f'if {check}; then echo have:{name}; else echo missing:{name}; fi'
                       for name, check, *_ in LOGINS)
    rc, out = ssh(h.ssh_name, script, timeout=60)
    words = out.split()
    if rc != 0 or len(words) != len(LOGINS):
        return None
    return [w.split(':', 1)[1] for w in words if w.startswith('missing:')]


def s_logins(h, apply):
    if not h.reachable():
        return WOULD, 'interactive logins over ssh -t once the host answers: ' + ', '.join(n for n, *_ in LOGINS)
    missing = logins_missing(h)
    if missing is None:
        return BLOCKED, 'cannot read login status on the host'
    if not missing:
        return OK, 'claude, codex, gh logged in'
    howto = '; '.join(f'`ssh -t {h.ssh_name} {shlex.quote("bash -lc " + shlex.quote(HOST_PATH + cmd))}` as {who}'
                      for name, _, cmd, _, who in LOGINS if name in missing)
    if not apply or not sys.stdin.isatty():
        return OWNER, f'run interactively (needs a terminal): {howto}'
    for name, _, cmd, _, who in LOGINS:
        if name in missing:
            print(f'    -> {name}: log in as {who}', flush=True)
            subprocess.run(['ssh', '-t', h.ssh_name, 'bash', '-lc', shlex.quote(HOST_PATH + cmd)])
    missing = logins_missing(h)
    return (OK, 'logged in') if missing == [] else (OWNER, f'still missing: {missing}; {howto}')


def r_logins(h, apply):
    if not h.reachable():
        if disk_gone(h):
            return OK, 'instance deleted; its local logins went with the disk'
        return BLOCKED, 'host not reachable and its disk may exist; start it, then re-run'
    missing = logins_missing(h)
    if missing is None:
        return BLOCKED, 'cannot read login status on the host'
    present = [n for n, *_ in LOGINS if n not in missing]
    if not present:
        return OK, 'claude, codex, gh logged out (proven)'
    if not apply:
        return WOULD, f'log out on the host: {present}'
    for name, _, _, logout, _ in LOGINS:
        if name in present:
            ssh(h.ssh_name, logout, timeout=60)
    missing = logins_missing(h)
    still = [n for n, *_ in LOGINS if missing is not None and n not in missing]
    if missing is None or still:
        return FAIL, f'logout not proven for {still or "all (status unreadable)"}'
    return OK, 'logged out (proven); server-side grants: see the receipt note'


# Adding a credential = one Minted subclass (or a step pair) plus its name in template credentials.enabled.
# Revocation steps always run for every kind: a record left by an older template is still revoked.
CRED_STEPS = [(n, f) for n, f in [('vercel', s_minted(Vercel())), ('neon', s_minted(Neon())),
                                  ('linear', s_linear), ('logins', s_logins)] if n in ENABLED]
REVOKE_STEPS = [('logins', r_logins), ('vercel', r_minted(Vercel())), ('neon', r_minted(Neon())),
                ('linear', r_linear)]

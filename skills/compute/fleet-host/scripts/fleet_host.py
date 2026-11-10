#!/usr/bin/env python3
"""Grow and shrink the fleet by GCP VMs (BRO-3651; spec: docs/fleet/gcp-host-template.md).

    fleet_host.py [--template T.json] add <name> [--shape S] [--zone Z] [--disk-gb N] [--apply]
    fleet_host.py remove <name> [--drain-timeout 7200] [--push-wip] [--apply]
    fleet_host.py status <name>

Every run without --apply is a dry run: each step observes current state read-only and prints
`ok` (already done), `would` (what --apply would do), `owner` (an owner action, never automated)
or `blocked` (a precondition is missing). Steps are idempotent: --apply runs only the steps whose
check fails, so a re-run after a partial failure continues where it stopped. Billable steps refuse
--apply without meta/fleet-hosts/APPROVAL.json. No step prints a secret value.
"""
import argparse, json, os, re, shlex, subprocess, sys, tempfile, time

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import fleet_host_creds as creds  # noqa: E402  (reads the same template)
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLEET = Path(os.environ.get('FLEET_DIR', Path.home() / '.config/broomva/fleet'))
META = FLEET / 'meta'
REGISTRY = FLEET / 'hosts.json'
SETPOINTS = META / 'setpoints.json'
STATE = META / 'state.json'
CENSUS = META / 'fleet_census.py'
HOSTDIR = META / 'fleet-hosts'
APPROVAL = HOSTDIR / 'APPROVAL.json'
SSH_CONFIG = Path(os.environ.get('FLEET_SSH_CONFIG', Path.home() / '.ssh/config'))
SSH_KEY = Path.home() / '.ssh/fleet_hosts_ed25519'
# Everything deployment-specific comes from the template (scripts/fleet-host/template.json by default;
# --template or FLEET_HOST_TEMPLATE for another fleet or project). No secrets live there.
def _template_path(argv):
    for i, a in enumerate(argv):
        if a == '--template' and i + 1 < len(argv):
            return Path(argv[i + 1])
        if a.startswith('--template='):
            return Path(a.split('=', 1)[1])
    if os.environ.get('FLEET_HOST_TEMPLATE'):
        return Path(os.environ['FLEET_HOST_TEMPLATE'])
    for p in (HERE / 'fleet-host/template.json', Path.home() / '.config/fleet-host/template.json'):
        if p.exists():
            return p
    if {'-h', '--help'} & set(argv):  # help works before any template exists
        return HERE / 'fleet-host/template.example.json'
    sys.exit('fleet_host: no host template. Copy scripts/fleet-host/template.example.json to '
             '~/.config/fleet-host/template.json and fill it in, or pass --template / FLEET_HOST_TEMPLATE.')


TEMPLATE_PATH = _template_path(sys.argv)
T = json.loads(TEMPLATE_PATH.read_text())
G = T['gcp']
PROJECT = os.environ.get('FLEET_GCP_PROJECT', G['project'])
TAILNET_SUFFIX = T['tailnet']['suffix']
TAG = T['tailnet']['tag']
TS_KEYCHAIN = T['tailnet']['oauth_keychain']
REPOS = [f"{r['repo']}:{r['dir']}" for r in T.get('repos', [])]
for _r in REPOS:  # these reach a remote shell as words: allow only plain owner/repo:dir
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+', _r):
        sys.exit(f'fleet_host: template repo spec {_r!r} must be owner/repo with a plain dir name')
LABELS = ','.join(f'{k}={v}' for k, v in G.get('labels', {}).items())
RESERVED = {'mac', 'nuc', 'vps', 'local'}
SHAPES = {k: tuple(v) for k, v in T['shapes'].items()}
SECRETS = ('ts-authkey',)  # only the Tailscale key, needed before ssh works; other credentials go over ssh

OK, WOULD, OWNER, BLOCKED, FAIL = 'ok', 'would', 'owner', 'blocked', 'FAIL'


def run(cmd, input=None, timeout=60):
    """Run argv; return (rc, stdout). stderr is summarized, never echoed (it can carry tokens)."""
    try:
        r = subprocess.run(cmd, input=input, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, type(e).__name__


def gcloud(*args, timeout=90):
    return run(['gcloud', *args, f'--project={PROJECT}', '--quiet'], timeout=timeout)


class Unobservable(Exception):
    """A read failed for a reason other than NOT_FOUND: state is unknown, never assumed absent."""


def gdescribe(*args):
    """Run a gcloud describe/get. Returns stdout, or None only on a definite NOT_FOUND."""
    try:
        r = subprocess.run(['gcloud', *args, f'--project={PROJECT}', '--quiet'], capture_output=True,
                           text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unobservable(type(e).__name__)
    if r.returncode == 0:
        return r.stdout.strip()
    err = r.stderr
    if re.search(r'NOT_FOUND|was not found|does not exist|notFound', err):
        return None
    if 'SERVICE_DISABLED' in err or 'has not been used in project' in err:
        # An API that was never enabled holds no resources of its kind.
        return None
    raise Unobservable(re.sub(r'\s+', ' ', err.strip().splitlines()[-1] if err.strip() else 'error')[:160])


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():  # one dated backup per write, like the other fleet writers
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        (path.parent / f'{path.name}.bak-{stamp}-fleet-host').write_text(path.read_text())
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    with os.fdopen(fd, 'w') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')
    os.replace(tmp, path)


def keychain(service):
    """Admin credential from the Mac Keychain, into memory only. None when absent."""
    rc, out = run(['security', 'find-generic-password', '-s', service, '-w'])
    return out if rc == 0 and out else None


def ssh(host, script, timeout=60):
    return run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', host, 'bash', '-l', '-s'],
               input=script, timeout=timeout)


class Host:
    def __init__(self, a):
        self.name, self.a = a.name, a
        self.instance = f'fleet-{a.name}'
        self.sa = f'fleet-host-{a.name}@{PROJECT}.iam.gserviceaccount.com'
        self.zone = getattr(a, 'zone', None) or self.registry_entry().get('gcp', {}).get('zone', G['zone'])
        self.dir = HOSTDIR / a.name
        self.ssh_name = a.name
        self.kind = self.registry_entry().get('kind') or ('gcp' if a.cmd in ('add', 'remove', 'start', 'stop') else 'ssh')

    def reachable(self):
        """The host answers over ssh (a GCP host must also be RUNNING). Cached per run."""
        if not hasattr(self, '_reachable'):
            if self.kind == 'gcp' and self.instance_status() != 'RUNNING':
                self._reachable = False
            else:
                self._reachable = ssh(self.ssh_name, 'true', timeout=20)[0] == 0
        return self._reachable

    def registry_entry(self):
        return next((h for h in load(REGISTRY, {}).get('hosts', []) if h.get('id') == self.name), {})

    def instance_status(self, fresh=False):
        """RUNNING, TERMINATED, ... or None when absent. Cached per run; steps that change it pass fresh."""
        if fresh or not hasattr(self, '_status'):
            self._status = gdescribe('compute', 'instances', 'describe', self.instance, f'--zone={self.zone}',
                                     '--format=value(status)')
        return self._status


# ---- steps: each returns (status, detail); apply=True performs the change when not done ----------

def s_preflight(h, apply):
    rc, out = gcloud('projects', 'describe', PROJECT, '--format=value(projectNumber)')
    if rc != 0:
        return BLOCKED, f'gcloud cannot read {PROJECT}: owner runs `gcloud auth login {G.get("admin_account", "<admin account>")}`'
    email = run(['git', 'config', 'user.email'])[1]
    if not email or email.endswith('@example.com'):
        return BLOCKED, f'Mac git identity is missing or a placeholder ({email!r})'
    if not h.a.dry and h.a.cmd == 'add' and 'hosts_registry' not in (CENSUS.read_text() if CENSUS.exists() else ''):
        return BLOCKED, ('fleet readers do not read hosts.json yet (spec §4, phase 2); '
                         'a host added now would be invisible to census, gate and governor')
    return OK, f'project {PROJECT} #{out}; git identity {email}'


def s_approval(h, apply):
    ap = load(APPROVAL, None)
    if not ap:
        return BLOCKED, f'no {APPROVAL} (owner approval of spec + monthly spend, decision D1)'
    if h.a.shape not in ap.get('shapes', []):
        return BLOCKED, f'shape {h.a.shape} not in approved shapes {ap.get("shapes")}'
    return OK, f'approved {ap.get("at")} ceiling ${ap.get("monthly_usd_ceiling")}/host/month'


def s_ssh_key(h, apply):
    if SSH_KEY.exists():
        return OK, f'{SSH_KEY} present'
    if not apply:
        return WOULD, f'create Mac-only key {SSH_KEY} (ed25519, no passphrase, 0600)'
    rc, _ = run(['ssh-keygen', '-t', 'ed25519', '-N', '', '-C', 'fleet-hosts (BRO-3651)', '-f', str(SSH_KEY)])
    return (OK, 'created') if rc == 0 else (FAIL, 'ssh-keygen failed')


SA_ROLES = tuple(G['sa_roles'])


def sa_exists(h):
    """From the account list, the authoritative view: a deleted account is soft-deleted for 30 days and
    `describe` on it answers 403 "denied (or it may not exist)", not NOT_FOUND (measured 2026-11-10)."""
    rc, out = gcloud('iam', 'service-accounts', 'list', f'--filter=email={h.sa}', '--format=value(email)')
    if rc != 0:
        raise Unobservable('service-accounts list failed')
    return h.sa in out.split()


def sa_roles(h):
    """Project roles bound to the host's service account (a failed read is unknown, never 'none')."""
    rc, out = gcloud('projects', 'get-iam-policy', PROJECT, '--flatten=bindings[].members',
                     f'--filter=bindings.members:serviceAccount:{h.sa}', '--format=value(bindings.role)')
    if rc != 0:
        raise Unobservable('get-iam-policy failed')
    return set(out.split())


def s_service_account(h, apply):
    exists = sa_exists(h)
    missing = [r for r in SA_ROLES if r not in sa_roles(h)] if exists else list(SA_ROLES)
    if exists and not missing:
        return OK, f'{h.sa} with {", ".join(SA_ROLES)}'
    if not apply:
        return WOULD, (f'create {h.sa} (no key file); ' if not exists else '') + f'bind {missing}'
    if not exists and gcloud('iam', 'service-accounts', 'create', f'fleet-host-{h.name}',
                             f'--display-name=fleet host {h.name} (BRO-3651)')[0] != 0:
        return FAIL, 'service account create failed'
    for role in missing:
        gcloud('projects', 'add-iam-policy-binding', PROJECT, f'--member=serviceAccount:{h.sa}',
               f'--role={role}', '--condition=None', '--format=none')
    still = [r for r in SA_ROLES if r not in sa_roles(h)]
    return (OK, 'created and bound') if not still else (FAIL, f'roles not bound: {still}')


APIS = tuple(G['apis'])
NET, SUBNET, REGION_CIDR = G['network'], G['subnet'], G['cidr']


def s_apis(h, apply):
    rc, out = gcloud('services', 'list', '--enabled', '--format=value(config.name)')
    if rc != 0:
        return BLOCKED, 'cannot list enabled APIs'
    missing = [a for a in APIS if a not in out.split()]
    if not missing:
        return OK, 'compute, iap, secretmanager, aiplatform enabled'
    if not apply:
        return WOULD, (f'enable {missing}. Note: enabling Compute auto-creates the `default` VPC with '
                       'default-allow-ssh from 0.0.0.0/0; fleet hosts never use it (step network)')
    rc, _ = gcloud('services', 'enable', *missing, timeout=600)
    return (OK, 'enabled') if rc == 0 else (FAIL, 'enable failed')


def fleet_rules():
    rc, out = gcloud('compute', 'firewall-rules', 'list', f'--filter=network~/{NET}$',
                     '--format=json(name,sourceRanges,direction,disabled)')
    if rc != 0:
        raise Unobservable('firewall-rules list failed')
    return json.loads(out or '[]')


def s_network(h, apply):
    """Dedicated custom-mode VPC: no default rules, so nothing public can reach a fleet host. Network,
    subnet and the IAP rule are each checked on their own, so a partial create re-converges."""
    region = h.zone.rsplit('-', 1)[0]
    has_net = gdescribe('compute', 'networks', 'describe', NET, '--format=value(name)') is not None
    has_sub = has_net and gdescribe('compute', 'networks', 'subnets', 'describe', SUBNET, f'--region={region}',
                                    '--format=value(name)') is not None
    rules = fleet_rules() if has_net else []
    public = [r['name'] for r in rules if r.get('direction') == 'INGRESS' and not r.get('disabled')
              and r.get('sourceRanges') != ['35.235.240.0/20']]
    if public:
        return BLOCKED, f'{NET} has ingress rules beyond IAP: {public} (spec §2)'
    has_iap = any(r['name'] == 'fleet-allow-iap-ssh' for r in rules)
    todo = [x for x, ok in ((f'VPC {NET} (custom mode)', has_net),
                            (f'subnet {SUBNET} {REGION_CIDR} (private Google access)', has_sub),
                            ('firewall fleet-allow-iap-ssh: tcp:22 from 35.235.240.0/20 only', has_iap)) if not ok]
    if not todo:
        return OK, f'{NET}: subnet {SUBNET}; only ingress is IAP tcp:22'
    if not apply:
        return WOULD, 'create ' + '; '.join(todo)
    if not has_net:
        gcloud('compute', 'networks', 'create', NET, '--subnet-mode=custom', timeout=300)
    if not has_sub:
        gcloud('compute', 'networks', 'subnets', 'create', SUBNET, f'--network={NET}', f'--region={region}',
               f'--range={REGION_CIDR}', '--enable-private-ip-google-access', timeout=300)
    if not has_iap:
        gcloud('compute', 'firewall-rules', 'create', 'fleet-allow-iap-ssh', f'--network={NET}',
               '--direction=INGRESS', '--allow=tcp:22', '--source-ranges=35.235.240.0/20', '--target-tags=fleet-iap')
    status, detail = s_network(h, False)
    return (OK, 'created; ' + detail) if status == OK else (FAIL, 'network re-check: ' + detail)


def secret_exists(h, cred):
    return gdescribe('secrets', 'describe', f'fleet-{h.name}-{cred}', '--format=value(name)') is not None


def put_secret(h, cred, value):
    """Store a value in Secret Manager via stdin; readable only by this host's service account."""
    sid = f'fleet-{h.name}-{cred}'
    if not secret_exists(h, cred) and gcloud('secrets', 'create', sid, '--replication-policy=automatic',
                                             f'--labels=fleet-host={h.name}')[0] != 0:
        return False
    rc, _ = run(['gcloud', 'secrets', 'versions', 'add', sid, '--data-file=-', f'--project={PROJECT}', '--quiet'],
                input=value)
    rc2, _ = gcloud('secrets', 'add-iam-policy-binding', sid, f'--member=serviceAccount:{h.sa}',
                    '--role=roles/secretmanager.secretAccessor', '--format=none')
    return rc == 0 and rc2 == 0


def secret_usable(h, cred, max_age_s):
    """The latest version is ENABLED, younger than max_age_s, and the host's SA can read the secret."""
    sid = f'fleet-{h.name}-{cred}'
    out = gdescribe('secrets', 'versions', 'describe', 'latest', f'--secret={sid}', '--format=json(state,createTime)')
    if not out:
        return False
    v = json.loads(out)
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(v['createTime'].replace('Z', '+00:00'))).total_seconds()
    except (KeyError, ValueError):
        return False
    rc, pol = gcloud('secrets', 'get-iam-policy', sid, '--format=json')
    if rc != 0:
        raise Unobservable('secret get-iam-policy failed')
    bound = f'serviceAccount:{h.sa}' in pol
    return v.get('state') == 'ENABLED' and age < max_age_s and bound


def tailscale_api(method, path, body=None):
    """Tailscale API with the OAuth client from the Keychain (devices:core, auth_keys; tag-limited).
    Returns (status, json). Raises Unobservable when the API cannot be reached at all."""
    import urllib.request, urllib.parse, urllib.error
    raw = keychain(TS_KEYCHAIN)  # "client_id:client_secret"
    if not raw or ':' not in raw:
        raise Unobservable(f'Keychain {TS_KEYCHAIN} missing')
    cid, csec = raw.split(':', 1)
    try:
        tok = json.load(urllib.request.urlopen(urllib.request.Request(
            'https://api.tailscale.com/api/v2/oauth/token',
            data=urllib.parse.urlencode({'client_id': cid, 'client_secret': csec}).encode()), timeout=30))['access_token']
        req = urllib.request.Request(f'https://api.tailscale.com/api/v2{path}', method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
            return r.status, (json.loads(data) if data else {})
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as e:
        raise Unobservable(f'tailscale API: {type(e).__name__}')


def ts_device(h):
    """The host's tailnet device from the API (authoritative), or None when it definitely does not exist."""
    status, body = tailscale_api('GET', '/tailnet/-/devices')
    if status != 200 or body is None:
        raise Unobservable(f'tailscale device list HTTP {status}')
    return next((d for d in body.get('devices', []) if d.get('hostname') == h.name), None)


def s_tailscale_key(h, apply):
    if not keychain(TS_KEYCHAIN):
        return OWNER, (f'Keychain {TS_KEYCHAIN} missing: owner creates a Tailscale OAuth client '
                       f'(devices:core, auth_keys; tag {TAG}) and enters it via T3 request_secret')
    if ts_device(h):
        return OK, f'{h.name} is already a tailnet node'
    if secret_exists(h, 'ts-authkey') and secret_usable(h, 'ts-authkey', 50 * 60):
        return OK, f'single-use auth key staged in fleet-{h.name}-ts-authkey (fresh, readable by {h.sa})'
    if not apply:
        return WOULD, f'mint single-use pre-authorized key ({TAG}, 1 h) and stage it in Secret Manager'
    status, key = tailscale_api('POST', '/tailnet/-/keys', {
        'capabilities': {'devices': {'create': {'reusable': False, 'ephemeral': False, 'preauthorized': True,
                                                'tags': [TAG]}}},
        'expirySeconds': 3600, 'description': f'fleet {h.name}'})
    if status != 200 or not key:
        return FAIL, f'mint failed (HTTP {status})'
    ok = put_secret(h, 'ts-authkey', key['key'])
    kid = key['id']
    del key
    if not ok:
        tailscale_api('DELETE', f'/tailnet/-/keys/{kid}')  # an unstaged key is useless: revoke it now
        return FAIL, 'staging in Secret Manager failed; minted key revoked'
    return OK, f'staged key {kid}'


def s_instance(h, apply):
    st = h.instance_status()
    if st:
        return OK, f'{h.instance} {st} in {h.zone}'
    vcpu, mem = SHAPES[h.a.shape]
    if not apply:
        return WOULD, (f'create {h.instance}: {h.a.shape} ({vcpu} vCPU/{mem} GB), {h.a.disk_gb} GB {G["disk_type"]}, '
                       f'{G["image_family"]}, on-demand, SA {h.sa}, tags fleet-host,fleet-iap, '
                       f'labels {LABELS},fleet-host={h.name}, network {NET} (IAP-only ingress); startup-script + metadata')
    slots = max(1, min(vcpu // 4, (mem - 6) // 5))
    name = run(['git', 'config', 'user.name'])[1]
    email = run(['git', 'config', 'user.email'])[1]
    with tempfile.TemporaryDirectory() as td:  # metadata values, none secret
        md = {'fleet-host-name': h.name, 'fleet-tailscale-tag': TAG, 'fleet-heavy-slots': str(slots), 'fleet-git-name': name,
              'fleet-git-email': email, 'fleet-ssh-pubkey': (SSH_KEY.with_suffix('.pub')).read_text().strip()}
        files = {'startup-script': HERE / 'fleet-host/startup.sh',
                 'fleet-heavy-run': HERE / 'fleet-host/heavy-run.py',
                 'fleet-idle-stop': HERE / 'fleet-host/idle-stop.sh'}
        for k, v in md.items():
            (Path(td) / k).write_text(v)
            files[k] = Path(td) / k
        rc, _ = gcloud('compute', 'instances', 'create', h.instance, f'--zone={h.zone}',
                       f'--machine-type={h.a.shape}', '--provisioning-model=STANDARD',
                       f'--image-family={G["image_family"]}', f'--image-project={G["image_project"]}',
                       f'--boot-disk-size={h.a.disk_gb}GB', f'--boot-disk-type={G["disk_type"]}',
                       f'--service-account={h.sa}', '--scopes=cloud-platform',
                       f'--network={NET}', f'--subnet={SUBNET}', '--tags=fleet-host,fleet-iap', f'--labels={LABELS},fleet-host={h.name}',
                       '--metadata-from-file=' + ','.join(f'{k}={v}' for k, v in files.items()),
                       timeout=300)
    return (OK, 'created') if rc == 0 and h.instance_status(fresh=True) else (FAIL, 'instance create failed')


def s_ssh_alias(h, apply):
    text = SSH_CONFIG.read_text() if SSH_CONFIG.exists() else ''
    if f'# >>> fleet-host {h.name} ' in text:
        return OK, f'ssh alias {h.name} present'
    block = (f'\n# >>> fleet-host {h.name} (BRO-3651, managed by scripts/fleet_host.py)\n'
             f'Host {h.name}\n    HostName {h.name}.{TAILNET_SUFFIX}\n    User agent\n    IdentitiesOnly yes\n'
             f'    IdentityFile {SSH_KEY}\n    ServerAliveInterval 30\n    ServerAliveCountMax 4\n'
             f'# <<< fleet-host {h.name}\n')
    if not apply:
        return WOULD, 'append ssh alias:' + block.replace('\n', '\n      ')
    with open(SSH_CONFIG, 'a') as f:
        f.write(block)
    return OK, 'appended'


def no_host(h):
    """Host-side steps need a running instance; without one they only say what they will check."""
    return h.instance_status() != 'RUNNING'


def s_ready(h, apply):
    if no_host(h):
        return WOULD, 'poll /var/lib/fleet/ready.json over ssh until the startup script finishes'
    rc, out = ssh(h.name, 'cat /var/lib/fleet/ready.json', timeout=30)
    if rc != 0 or not out:
        return BLOCKED, 'host not reachable over the tailnet yet, or startup not finished (re-run)'
    tools = json.loads(out).get('tools', {})
    missing = [t for t, ok in tools.items() if not ok]
    if missing:
        return FAIL, f'missing tools: {missing}'
    # The single-use join key is spent once the host answers over the tailnet: destroy its secret.
    if secret_exists(h, 'ts-authkey'):
        if not apply:
            return WOULD, f'toolchain complete; delete the spent fleet-{h.name}-ts-authkey secret'
        gcloud('secrets', 'delete', f'fleet-{h.name}-ts-authkey')
        if secret_exists(h, 'ts-authkey'):
            return FAIL, 'spent tailscale key secret not deleted'
    return OK, 'toolchain complete; spent join key secret gone'


def mac_t3_version():
    """The Mac's T3 runtime version; hosts pin it so the linked-environment protocol matches."""
    try:  # the version the Mac's background service runs (service-state.json), else the only installed one
        v = json.loads((Path.home() / '.t3/runtime/service-state.json').read_text()).get('activeVersion')
        if v:
            return v
    except (OSError, ValueError, AttributeError):
        pass
    versions = sorted(p.name for p in (Path.home() / '.t3/runtime/versions').glob('*') if p.is_dir())
    return versions[0] if len(versions) == 1 else None


T3_INSTALL = r'''set -eu
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"
V="$1"; shift  # remaining args: owner/repo:dir specs from the template
# 1. Runtime + user service at the Mac's version. Verified on gcp-1 2026-11-10: `npx t3@V service install`
#    downloads ~/.t3/runtime/versions/V and starts t3code.service, but creates no launcher (and
#    `npx t3@V update V` is a no-op: the npx copy already is V). So link the launcher ourselves.
R="$HOME/.t3/runtime/versions/$V/t3"
if [ ! -x "$R" ] || ! systemctl --user is-active -q t3code.service; then
  npx -y "t3@$V" service install
fi
mkdir -p "$HOME/.local/bin"; ln -sfn "$R" "$HOME/.local/bin/t3"
# 2. Linked environments on (the Mac links to this host).
python3 - <<'PY'
import json, os
p = os.path.expanduser('~/.t3/userdata/settings.json')
d = json.load(open(p)) if os.path.exists(p) else {}
if d.get('linkedEnvironmentsEnabled') is not True:
    d['linkedEnvironmentsEnabled'] = True
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(d, open(p + '.tmp', 'w'), indent=2); os.replace(p + '.tmp', p)
    print('settings: linkedEnvironmentsEnabled=true')
PY
t3 service restart >/dev/null 2>&1 || true
# 3. Repositories and T3 projects, once gh is logged in (the logins step); until then they stay pending.
if gh auth status -h github.com >/dev/null 2>&1; then
  for spec in "$@"; do
    repo="${spec%%:*}"; dir="$HOME/${spec##*:}"
    [ -d "$dir/.git" ] || gh repo clone "$repo" "$dir" -- --filter=blob:none
    t3 project add "$dir" >/dev/null 2>&1 || true
  done
  echo repos:ok
else
  echo repos:pending-gh-login
fi
sleep 2
t3 --version | tail -1
systemctl --user is-active t3code.service
'''


def s_t3(h, apply):
    want = mac_t3_version()
    rc, out = (1, '') if no_host(h) else ssh(
        h.name, 'export PATH="$HOME/.local/bin:$PATH"; '
                # repos still owed: gh is logged in but a template checkout is missing (re-run clones them)
                + ''.join(f'gh auth status -h github.com >/dev/null 2>&1 && [ ! -d "$HOME/{r.split(":", 1)[1]}/.git" ] '
                          f'&& echo repo-missing; ' for r in REPOS)
                + 't3 --version 2>/dev/null | tail -1; systemctl --user is-active t3code.service', timeout=30)
    lines = out.split()  # `t3 --version` prints "t3 v<version>"
    if rc == 0 and want and lines and lines[-1] == 'active' and f'v{want}' in lines and 'repo-missing' not in lines:
        return OK, f't3 {want}, t3code.service active'
    if not want:
        return BLOCKED, 'cannot determine the Mac T3 version (~/.t3/runtime/service-state.json)'
    if not apply or no_host(h):
        return WOULD, (f'install t3 {want} (npm `t3`, the Mac version) as agent, `t3 service install`, '
                       f'linkedEnvironmentsEnabled=true, clone {", ".join(r.split(":")[0] for r in REPOS)}, `t3 project add`')
    rc, out = run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', h.name, 'bash', '-l', '-s', '--', want, *REPOS],
                  input=T3_INSTALL, timeout=1800)
    tail = out.splitlines()[-3:] if out else []
    if rc == 0 and tail and tail[-1] == 'active':
        return OK, f'installed: {" ".join(tail)}'
    return FAIL, f'install failed (rc {rc}): {" | ".join(tail)}'

def t3_cli():
    v = mac_t3_version()
    p = Path.home() / f'.t3/runtime/versions/{v}/t3' if v else None
    return str(p) if p and p.exists() else None


def linked_ids():
    """Environment ids the Mac currently links (live `t3 environment list --json`)."""
    cli = t3_cli()
    if not cli:
        raise Unobservable('Mac T3 runtime CLI not found')
    rc, out = run([cli, 'environment', 'list', '--json'], timeout=60)
    if rc != 0:
        raise Unobservable('t3 environment list failed')
    return set(re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', out))


def s_t3_link(h, apply):
    env = h.registry_entry().get('environment_id')
    if env and env in linked_ids():
        return OK, f'linked environmentId {env}'
    return OWNER, (f'agent calls t3_environment_link (hint "{h.name}", access full-access, decision D3), then '
                   f'records its environmentId in {REGISTRY}; never a pairing code in chat')


def s_snapshot(h, apply):
    """agentic-vps hard rule 1: a rollback point exists. One snapshot of the provisioned disk."""
    snap = f'fleet-{h.name}-provisioned'
    if gdescribe('compute', 'snapshots', 'describe', snap, '--format=value(name)') is not None:
        return OK, f'snapshot {snap} present'
    if no_host(h) or not apply:
        return WOULD, f'snapshot the provisioned boot disk as {snap} (incremental; deleted on remove)'
    rc, _ = gcloud('compute', 'disks', 'snapshot', h.instance, f'--zone={h.zone}', f'--snapshot-names={snap}',
                   f'--labels={LABELS},fleet-host={h.name}', timeout=900)
    return (OK, f'created {snap}') if rc == 0 else (FAIL, 'snapshot failed')


VERIFY = Path.home() / '.claude/skills/agentic-vps/scripts/verify.py'


def external_ip(h):
    return gdescribe('compute', 'instances', 'describe', h.instance, f'--zone={h.zone}',
                     '--format=value(networkInterfaces[0].accessConfigs[0].natIP)')


def s_agentic_verify(h, apply):
    """The agentic-vps gate: non-root agent with sudo, slice caps, Tailscale up, public :22 closed (probed
    from the Mac at the VM's external IP), no long-lived secret in the agent env, Claude bypassPermissions.
    It makes live probes, so it runs only with --apply (a dry run says what it would check)."""
    if no_host(h) or not apply:
        return WOULD, 'run agentic-vps verify.py; every required gate must pass'
    if not VERIFY.exists():
        return BLOCKED, f'{VERIFY} not installed'
    ip = external_ip(h)
    rc, out = run([sys.executable, '-I', str(VERIFY), '--host', h.name] + (['--public-ip', ip] if ip else []),
                  timeout=300)
    failed = [l.split()[1] for l in out.splitlines() if l.startswith('[FAIL]')]
    if rc == 0:
        return OK, f'agentic-vps required gates PASS (public {ip} :22 closed)'
    if not ip and failed == ['public_ssh_closed']:
        # verify.py cannot probe without an address; a VM with no external IP has no public :22 at all.
        return OK, 'agentic-vps required gates PASS; no external IP, so no public :22 to probe'
    return FAIL, 'agentic-vps gates failed: ' + ', '.join(failed or ['verify.py error'])


def s_setpoint(h, apply):
    sp = load(SETPOINTS, {})
    key = f'host.{h.name}.max_live'
    if key in sp.get('setpoints', {}):
        return OK, f'{key}={sp["setpoints"][key]["value"]}'
    entry = {'value': T['fleet']['max_live'], 'min': 0, 'max': T['fleet']['max_live_max'], 'max_step': 1, 'min_interval_h': 2, 'rule': 'host_load',
             'host': h.name, 'held': False, 'actuator': 'dispatch_gate.py + placements',
             'why': 'GCP host (BRO-3651): heavy capacity, not model concurrency; starts at 1.'}
    if not apply:
        return WOULD, f'insert setpoints.{key} = {json.dumps(entry)}'
    sp['setpoints'][key] = entry
    atomic_json(SETPOINTS, sp)
    return OK, 'inserted'


def s_hold(h, apply):
    holds = load(STATE, {}).get('remote_host_holds', {})
    if h.name in holds:
        return OK, f'remote_host_holds.{h.name} active={holds[h.name].get("active")}'
    if not apply:
        return WOULD, f'state.json remote_host_holds.{h.name} = held (Meta releases after the drill)'
    st = load(STATE, {})
    st.setdefault('remote_host_holds', {})[h.name] = {
        'active': True, 'at': datetime.now(timezone.utc).isoformat(), 'why': 'new GCP host (BRO-3651); Meta releases'}
    atomic_json(STATE, st)
    return OK, 'held'


def s_register(h, apply):
    if h.registry_entry():
        return OK, f'{REGISTRY} has {h.name}'
    vcpu, mem = SHAPES[h.a.shape]
    entry = {'id': h.name, 'kind': 'gcp', 'state': 'active',
             'transport': ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', h.name, 'bash', '-l', '-s'],
             'environment_id': None, 't3_db': '/home/agent/.t3/userdata/statev2.sqlite',
             'gcp': {'project': PROJECT, 'zone': h.zone, 'instance': h.instance, 'service_account': h.sa,
                     'shape': h.a.shape},
             'heavy_slots': max(1, min(vcpu // 4, (mem - 6) // 5)), 'roles': T['fleet']['roles'],
             'added_at': datetime.now(timezone.utc).isoformat(), 'ticket': 'BRO-3651'}
    if not apply:
        return WOULD, f'register in {REGISTRY}: {json.dumps(entry)}'
    reg = load(REGISTRY, {'hosts': []})
    reg['hosts'].append(entry)
    atomic_json(REGISTRY, reg)
    return OK, 'registered'


# ---- remove ----------------------------------------------------------------------------------------

def r_drain_hold(h, apply):
    e, sp = h.registry_entry(), load(SETPOINTS, {}).get('setpoints', {})
    cap = sp.get(f'host.{h.name}.max_live', {}).get('value')
    if (not e or e.get('state') == 'draining') and cap in (None, 0):
        return OK, 'no new placements (draining, cap 0)'
    if not apply:
        return WOULD, f'registry state=draining, host.{h.name}.max_live {cap}->0, governor hold active'
    if e:
        reg = load(REGISTRY, {'hosts': []})
        for x in reg['hosts']:
            if x.get('id') == h.name:
                x['state'] = 'draining'
        atomic_json(REGISTRY, reg)
    full = load(SETPOINTS, {})
    if f'host.{h.name}.max_live' in full.get('setpoints', {}):
        full['setpoints'][f'host.{h.name}.max_live']['value'] = 0
        atomic_json(SETPOINTS, full)
    st = load(STATE, {})
    st.setdefault('remote_host_holds', {})[h.name] = {
        'active': True, 'at': datetime.now(timezone.utc).isoformat(), 'why': 'draining (fleet_host.py remove)'}
    atomic_json(STATE, st)
    return OK, 'held'


ACTIVE_RUNS = ("select count(*) from orchestration_v2_projection_runs "
               "where status in ('running','starting','preparing','queued','waiting')")


WIP_SCAN = r'''for d in "$@" ~/.t3/worktrees/*/*; do
  [ -e "$d/.git" ] || continue
  git -C "$d" status --porcelain 2>/dev/null | grep -q . && echo "dirty:$d"
  # commits no remote has, on any local branch (incl. ones with no upstream) or on a detached HEAD
  git -C "$d" log HEAD --branches --not --remotes --oneline 2>/dev/null | grep -q . && echo "unpushed:$d"
done; echo scan-ok'''

# Commit any dirty tree and push every local-only branch to wip/<host>/<branch>; print what was pushed.
# Fails closed: any git error exits non-zero, and a re-scan must come back clean.
WIP_PUSH = r'''set -eu
host="$1"; shift  # remaining args: the template's repo checkouts
email=$(git config --global user.email || true)
email=${email:-fleet-$host@users.noreply.github.com}
for d in "$@" ~/.t3/worktrees/*/*; do
  [ -e "$d/.git" ] || continue
  wt=$(basename "$d")
  if git -C "$d" status --porcelain | grep -q .; then
    git -C "$d" add -A
    git -C "$d" -c user.name="fleet-host $host" -c user.email="$email" \
      commit -q --no-verify -m "wip($host): unfinished work saved on host removal (BRO-3651)"
  fi
  # Every local-only tip: each branch, plus a detached HEAD. The ref name carries the worktree and the
  # commit, so two worktrees never collide and a retry pushes the same ref again (a no-op), never a
  # non-fast-forward.
  tips=$(git -C "$d" for-each-ref --format='%(refname:short)' refs/heads)
  git -C "$d" symbolic-ref -q HEAD >/dev/null || tips="$tips HEAD"
  for b in $tips; do
    if git -C "$d" log "$b" --not --remotes --oneline | grep -q .; then
      sha=$(git -C "$d" rev-parse --short=10 "$b")
      name=$( [ "$b" = HEAD ] && echo detached || echo "$b" )
      ref="wip/$host/$wt/$name-$sha"
      git -C "$d" push -q origin "$b:refs/heads/$ref"
      git -C "$d" fetch -q origin "refs/heads/$ref:refs/remotes/origin/$ref"  # so the re-scan sees it pushed
      echo "pushed:$d:$b -> $ref"
    fi
  done
done'''


REPO_DIRS = [f"$HOME/{r.split(':', 1)[1]}" for r in REPOS]


def scan_wip(h):
    rc, out = run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', h.name, 'bash', '-l', '-s', '--',
                   *REPO_DIRS], input=WIP_SCAN, timeout=120)
    if rc != 0 or not out.endswith('scan-ok'):
        raise Unobservable('unfinished-work scan failed')
    return [w for w in out.split() if w != 'scan-ok']


def r_drain(h, apply):
    """Never kill accepted work: wait for active runs, then find unfinished work. With --push-wip it is
    committed and pushed to wip/<host>/<branch> (fail closed); without it removal stops."""
    if h.instance_status() is None:
        return OK, 'instance absent; nothing to drain'
    q = f'sqlite3 "file:$HOME/.t3/userdata/statev2.sqlite?mode=ro" "{ACTIVE_RUNS}"'
    rc, out = ssh(h.name, q, timeout=30)
    if rc != 0 or not out.strip().isdigit():
        return BLOCKED, 'cannot read the host T3 DB (stopped? run `fleet_host.py start`); never drain blind'
    runs = int(out)
    if runs and not apply:
        return WOULD, f'wait up to {h.a.drain_timeout}s for {runs} active runs to finish/checkpoint; never kills'
    deadline = time.time() + h.a.drain_timeout
    while runs and time.time() < deadline:
        time.sleep(60)
        rc, out = ssh(h.name, q, timeout=30)
        runs = int(out) if rc == 0 and out.strip().isdigit() else runs
    if runs:
        return BLOCKED, f'still draining after {h.a.drain_timeout}s ({runs} runs); re-run remove later'
    dirty = scan_wip(h)  # after the runs finished, so their last commits are included
    if not dirty:
        return OK, 'no active runs; no dirty trees or local-only commits'
    if not h.a.push_wip:
        return BLOCKED, f'unfinished work {dirty[:6]}: re-run with --push-wip (pushes wip/{h.name}/<branch>)'
    if not apply:
        return WOULD, f'commit dirty trees and push local-only branches to wip/{h.name}/*: {dirty[:6]}'
    rc, out = run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', h.name, 'bash', '-l', '-s', '--', h.name, *REPO_DIRS],
                  input=creds.HOST_PATH + WIP_PUSH, timeout=900)
    if rc != 0:
        return FAIL, 'wip push failed; nothing deleted'
    left = scan_wip(h)
    if left:
        return FAIL, f'still unfinished after push: {left[:6]}'
    pushed = [l for l in out.splitlines() if l.startswith('pushed:')]
    with open(h.dir / 'wip-pushed.txt', 'a') as f:
        f.write('\n'.join(pushed) + '\n')
    return OK, f'pushed {len(pushed)} wip refs (listed in {h.dir}/wip-pushed.txt; file draft PRs from them)'


def r_archive_unlink(h, apply):
    env = h.registry_entry().get('environment_id')
    if not env or env not in linked_ids():
        return OK, 'not linked (checked live with `t3 environment list`)'
    return OWNER, (f'agent archives settled threads on environment {env} (the full-access link permits it), '
                   f'then t3_environment_unlink / `t3 environment unlink {env}` on the Mac; re-run remove')


def r_tailscale(h, apply):
    dev = ts_device(h)
    if not dev:
        return OK, 'no tailnet node (tailscale API)'
    if not apply:
        return WOULD, f'delete tailnet device {dev.get("hostname")} ({dev.get("id")}) via API, prove it is gone'
    status, _ = tailscale_api('DELETE', f'/device/{dev["id"]}')
    if ts_device(h):
        return FAIL, f'device still listed after DELETE (HTTP {status})'
    return OK, f'deleted {dev["id"]} (no longer listed)'


def r_instance(h, apply):
    if not h.instance_status():
        return OK, 'instance and boot disk absent'
    if not apply:
        return WOULD, f'delete {h.instance} --delete-disks=all'
    rc, _ = gcloud('compute', 'instances', 'delete', h.instance, f'--zone={h.zone}', '--delete-disks=all', timeout=300)
    return (OK, 'deleted') if rc == 0 and not h.instance_status(fresh=True) else (FAIL, 'delete failed')


def fleet_secret_names(h):
    rc, out = gcloud('secrets', 'list', f'--filter=labels.fleet-host={h.name}', '--format=value(name)')
    if rc != 0:
        raise Unobservable('secrets list failed')
    return [n.rsplit('/', 1)[-1] for n in out.split()]


def r_secrets(h, apply):
    names = fleet_secret_names(h)
    if not names:
        return OK, 'no fleet secrets'
    if not apply:
        return WOULD, f'delete secrets {names}'
    for n in names:
        gcloud('secrets', 'delete', n)
    left = fleet_secret_names(h)
    return (OK, f'deleted {len(names)} (none left)') if not left else (FAIL, f'still present: {left}')


def r_snapshots(h, apply):
    rc, out = gcloud('compute', 'snapshots', 'list', f'--filter=labels.fleet-host={h.name}', '--format=value(name)')
    if rc != 0:
        raise Unobservable('snapshots list failed')
    names = out.split()
    if not names:
        return OK, 'no fleet snapshots'
    if not apply:
        return WOULD, f'delete snapshots {names}'
    gcloud('compute', 'snapshots', 'delete', *names, timeout=600)
    rc, out = gcloud('compute', 'snapshots', 'list', f'--filter=labels.fleet-host={h.name}', '--format=value(name)')
    return (OK, f'deleted {names}') if rc == 0 and not out.split() else (FAIL, 'snapshots still present')


def r_wake(h, apply):
    """A stopped host is started for removal: drain, archive and logout all need it running."""
    st = h.instance_status()
    if st in (None, 'RUNNING'):
        return OK, f'instance {st or "absent"}'
    if not apply:
        return WOULD, f'start {h.instance} ({st}) so it can be drained and its logins revoked'
    return start_instance(h)


def start_instance(h):
    if gcloud('compute', 'instances', 'start', h.instance, f'--zone={h.zone}', timeout=300)[0] != 0:
        return FAIL, 'start failed'
    h.instance_status(fresh=True)
    for _ in range(30):
        if ssh(h.name, 'true', timeout=20)[0] == 0:
            h.__dict__.pop('_reachable', None)
            return OK, 'started; answers over the tailnet'
        time.sleep(10)
    return BLOCKED, 'started, but not reachable over the tailnet yet; re-run'


def r_service_account(h, apply):
    if not sa_exists(h):
        return OK, 'service account absent (not in the account list)'
    if not apply:
        return WOULD, f'remove IAM bindings and delete {h.sa}'
    for role in SA_ROLES:
        gcloud('projects', 'remove-iam-policy-binding', PROJECT, f'--member=serviceAccount:{h.sa}',
               f'--role={role}', '--condition=None', '--format=none')
    gcloud('iam', 'service-accounts', 'delete', h.sa)
    return (OK, 'deleted (no longer in the account list)') if not sa_exists(h) else (FAIL, 'service account still present')


def r_deregister(h, apply):
    reg, sp, st = load(REGISTRY, {'hosts': []}), load(SETPOINTS, {}), load(STATE, {})
    text = SSH_CONFIG.read_text() if SSH_CONFIG.exists() else ''
    left = [x for x, present in (('registry', bool(h.registry_entry())),
                                 ('setpoint', f'host.{h.name}.max_live' in sp.get('setpoints', {})),
                                 ('hold', h.name in st.get('remote_host_holds', {})),
                                 ('ssh-alias', f'# >>> fleet-host {h.name} ' in text)) if present]
    if not left:
        return OK, 'deregistered'
    if not apply:
        return WOULD, f'remove {left}'
    if 'registry' in left:
        reg['hosts'] = [x for x in reg['hosts'] if x.get('id') != h.name]
        atomic_json(REGISTRY, reg)
    if 'setpoint' in left:
        del sp['setpoints'][f'host.{h.name}.max_live']
        atomic_json(SETPOINTS, sp)
    if 'hold' in left:
        del st['remote_host_holds'][h.name]
        atomic_json(STATE, st)
    if 'ssh-alias' in left:
        SSH_CONFIG.write_text(re.sub(rf'\n?# >>> fleet-host {re.escape(h.name)} .*?# <<< fleet-host {re.escape(h.name)}\n',
                                     '', text, flags=re.S))
    return OK, 'deregistered'


ADD = [('preflight', s_preflight, False), ('approval', s_approval, False), ('apis', s_apis, True),
       ('network', s_network, True), ('ssh-key', s_ssh_key, False), ('service-account', s_service_account, True),
       ('tailscale-key', s_tailscale_key, False), ('instance', s_instance, True),
       ('ssh-alias', s_ssh_alias, False), ('ready', s_ready, False),
       ('snapshot', s_snapshot, True),  # provisioned and secret-free: the rollback point (agentic-vps rule 1)
       *[(f'cred:{n}', f, False) for n, f in creds.CRED_STEPS], ('t3', s_t3, False),
       ('agentic-verify', s_agentic_verify, False), ('t3-link', s_t3_link, False),
       ('setpoint', s_setpoint, False), ('governor-hold', s_hold, False), ('register', s_register, False)]
REMOVE = [('preflight', s_preflight, False), ('wake', r_wake, True), ('hold', r_drain_hold, False),
          ('drain', r_drain, False), ('archive+unlink', r_archive_unlink, False),
          *[(f'revoke:{n}', f, False) for n, f in creds.REVOKE_STEPS],
          ('tailscale-node', r_tailscale, False), ('instance', r_instance, False),
          ('snapshots', r_snapshots, False), ('secrets', r_secrets, False),
          ('service-account', r_service_account, False), ('deregister', r_deregister, False)]

CREDS = [(f'cred:{n}', f, False) for n, f in creds.CRED_STEPS]


def x_start(h, apply):
    st = h.instance_status()
    if st is None:
        return BLOCKED, f'{h.instance} does not exist'
    if st == 'RUNNING':
        return OK, 'running'
    return start_instance(h) if apply else (WOULD, f'start {h.instance} ({st})')


IDLE_CHECK = (f'sqlite3 "file:$HOME/.t3/userdata/statev2.sqlite?mode=ro" "{ACTIVE_RUNS}"; '
              'for l in /var/lib/fleet/heavy/slot-*.lock; do [ -e "$l" ] || continue; '
              'flock -n "$l" true || echo busy; done')


def x_stop(h, apply):
    st = h.instance_status()
    if st in (None, 'TERMINATED', 'STOPPED'):
        return OK, f'instance {st or "absent"}'
    rc, out = ssh(h.name, IDLE_CHECK, timeout=30)
    lines = out.split()
    if rc != 0 or not lines or not lines[0].isdigit():
        return BLOCKED, 'cannot confirm the host is idle; not stopping'
    if int(lines[0]) or 'busy' in lines:
        return BLOCKED, f'{lines[0]} active runs, heavy slots busy: {"busy" in lines}; not stopping'
    if not apply:
        return WOULD, f'stop {h.instance} (disk kept; only the disk bills while stopped)'
    rc, _ = gcloud('compute', 'instances', 'stop', h.instance, f'--zone={h.zone}', timeout=300)
    return (OK, 'stopped') if rc == 0 and h.instance_status(fresh=True) == 'TERMINATED' else (FAIL, 'stop failed')


START = [('start', x_start, True)]
STOP = [('stop', x_stop, False)]
REVOKE_CREDS = [(f'revoke:{n}', f, False) for n, f in creds.REVOKE_STEPS]


def duration(v):
    m = re.fullmatch(r'(\d+)([smh]?)', str(v).strip())
    if not m:
        raise argparse.ArgumentTypeError('use seconds, or e.g. 90m / 2h')
    return int(m.group(1)) * {'': 1, 's': 1, 'm': 60, 'h': 3600}[m.group(2)]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--template', help=f'host template JSON (default {TEMPLATE_PATH}). Read from sys.argv at import, '
                   'so it applies to command-line runs; a caller of main() sets FLEET_HOST_TEMPLATE instead')
    sub = p.add_subparsers(dest='cmd', required=True)
    tp = argparse.ArgumentParser(add_help=False)
    tp.add_argument('--template', help=argparse.SUPPRESS)  # accepted after the subcommand too (read at import)
    _add_parser = sub.add_parser
    sub.add_parser = lambda *a_, **k: _add_parser(*a_, parents=[tp], **k)
    a = sub.add_parser('add')
    a.add_argument('name')
    a.add_argument('--shape', default=G['shape'], choices=sorted(SHAPES))
    a.add_argument('--zone', default=G['zone'])
    a.add_argument('--disk-gb', type=int, default=G['disk_gb'])
    a.add_argument('--apply', action='store_true')
    r = sub.add_parser('remove')
    r.add_argument('name')
    r.add_argument('--drain-timeout', type=duration, default=7200, help='seconds, or 90m / 2h')
    r.add_argument('--push-wip', action='store_true')
    r.add_argument('--apply', action='store_true')
    s = sub.add_parser('status')
    s.add_argument('name')
    for cmd in ('start', 'stop'):
        c = sub.add_parser(cmd, help=f'{cmd} a GCP fleet host (stop refuses while runs or heavy jobs are active)')
        c.add_argument('name')
        c.add_argument('--apply', action='store_true')
    for cmd, what in (('creds', 'mint/copy credentials and run logins on a reachable host'),
                      ('revoke-creds', 'revoke and prove every credential recorded for a host')):
        c = sub.add_parser(cmd, help=what)
        c.add_argument('name', help='ssh alias of the host (a fleet host or any ssh-reachable host)')
        c.add_argument('--apply', action='store_true')
    args = p.parse_args(argv)
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,20}', args.name) or args.name in RESERVED:
        p.error(f'host name must match [a-z][a-z0-9-]{{1,20}} and not be one of {sorted(RESERVED)}')
    args.dry = not getattr(args, 'apply', False)
    args.shape = getattr(args, 'shape', None) or Host(args).registry_entry().get('gcp', {}).get('shape', G['shape'])
    h = Host(args)
    steps = {'remove': REMOVE, 'creds': CREDS, 'revoke-creds': REVOKE_CREDS, 'start': START, 'stop': STOP}.get(args.cmd, ADD)
    mode = 'DRY RUN (no changes; pass --apply)' if args.dry else 'APPLY'
    print(f'fleet_host {args.cmd} {args.name} — {mode} — project {PROJECT}, zone {h.zone}, shape {args.shape}')
    journal, approved = [], args.cmd != 'add' or s_approval(h, False)[0] == OK
    stop = False
    for name, fn, billable in steps:
        if stop:
            print(f'  [skip   ] {name}')
            continue
        do = not args.dry and args.cmd != 'status' and (approved or not billable)
        try:
            status, detail = fn(h, do)
        except Unobservable as e:
            status, detail = BLOCKED, f'state unknown (read failed: {e})'
        except Exception as e:  # noqa: BLE001 - a step error is reported, never a traceback with values
            status, detail = FAIL, f'{type(e).__name__}'
        if billable and not args.dry and not approved and status == WOULD:
            status, detail = BLOCKED, 'billable step without owner approval: ' + detail
        print(f'  [{status:7}] {name}: {detail}')
        journal.append({'step': name, 'status': status, 'detail': detail,
                        'at': datetime.now(timezone.utc).isoformat()})
        if not args.dry and status in (FAIL, BLOCKED, OWNER):  # an owner step gates everything after it
            stop = True  # later steps depend on this one; re-run resumes here
    if not args.dry:
        h.dir.mkdir(parents=True, exist_ok=True)
        with open(h.dir / 'journal.jsonl', 'a') as f:
            for j in journal:
                f.write(json.dumps({'cmd': args.cmd, **j}) + '\n')
        if args.cmd == 'remove':
            out = h.dir / f'remove-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'
            out.write_text(json.dumps({'host': args.name, 'steps': journal}, indent=2) + '\n')
            print(f'receipt: {out}')
    pending = [j['step'] for j in journal if j['status'] not in (OK,)]
    print(f'summary: {len(journal) - len(pending)}/{len(journal)} done; pending: {pending or "none"}')
    return 0 if not pending else (0 if args.dry else 3)


if __name__ == '__main__':
    sys.exit(main())

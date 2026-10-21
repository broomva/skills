"""Antigravity ACP profile registry and account selection (never swaps global auth)."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

import pm_antigravity_quota


# ACP 1.3.0 darwin-arm64: initialize verified offline, no sessionCapabilities.fork.
# Upgrade requires repeating that contract probe before adding a release here.
VERIFIED_RUNTIME = (
    'cb1f0725183ed922079ed6cd1d2422b4d8be44c5fb60be3e9a43d8d04f99a18e',
    'b04b00662c1821b953a409d43626b86d1229130eeb2078b4e1304c06199aa481')


def runtime_fingerprint(binary):
    path = Path(binary)
    values = []
    for candidate in (path, path.parent / 'localharness_external'):
        with candidate.open('rb') as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
            values.append(digest.hexdigest())
    return tuple(values)


class AntigravityError(RuntimeError):
    pass


def root():
    return Path(os.environ.get('PROVIDER_MANAGER_ANTIGRAVITY_ROOT',
                               '~/.local/share/broomva/antigravity')).expanduser()


def fingerprint(profile):
    token = json.loads((Path(profile) / 'antigravity-acp/acp_token.json').read_text())
    identity = {k: token.get(k) for k in ('client_id', 'client_secret', 'refresh_token', 'project_id')}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


@contextlib.contextmanager
def registry():
    base = root()
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (base / 'registry.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = base / 'registry.json'
        try:
            state = json.loads(path.read_text()) if path.exists() else {
                'version': 1, 'accounts': {}, 'selected': {}, 'pins': {}, 'lastSwitch': {}}
        except (ValueError, OSError) as exc:
            raise AntigravityError('Unreadable Antigravity registry; selection refused') from exc
        if (state.get('version') != 1 or any(not isinstance(state.get(k), dict)
                for k in ('accounts', 'selected', 'pins', 'lastSwitch'))):
            raise AntigravityError('Invalid Antigravity registry')
        yield state
        fd, temporary = tempfile.mkstemp(dir=base, prefix='.registry-')
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def validate_profile(entry):
    from pm_antigravity_launch import child_environment, LaunchError
    try:
        child_environment(entry, {})
    except LaunchError as exc:
        raise AntigravityError('Invalid isolated Google ACP profile') from exc


def register(email, profile, binary):
    profile, binary = str(Path(profile).expanduser().resolve()), str(Path(binary).expanduser().resolve())
    if not Path(binary).is_file() or not os.access(binary, os.X_OK):
        raise AntigravityError('Official ACP executable must exist and be executable')
    validate_profile({'profile': profile, 'binary': binary})
    runtime = runtime_fingerprint(binary)
    if runtime != VERIFIED_RUNTIME:
        raise AntigravityError('ACP release has no verified session isolation contract')
    stamp = fingerprint(profile)
    result = pm_antigravity_quota.probe(profile, email)
    if result.get('email') != email or result.get('status') != 'ok':
        raise AntigravityError('Profile identity and quota must verify before registration')
    if stamp != fingerprint(profile):
        raise AntigravityError('Profile changed during verification')
    with registry() as state:
        existing = state['accounts'].get(email)
        if existing and (existing['profile'] != profile or existing['fingerprint'] != stamp):
            raise AntigravityError('Registered profile is immutable; use a new account generation')
        if any(a['profile'] == profile and key != email for key, a in state['accounts'].items()):
            raise AntigravityError('Profile already belongs to another account')
        state['accounts'][email] = {'profile': profile, 'binary': binary,
                                    'fingerprint': stamp, 'runtimeFingerprint': list(runtime), 'usage': result}
        for family in ('gemini', 'third_party', 'all'):
            state['selected'].setdefault(family, email)
    return {'email': email, 'profile': profile, 'status': 'registered'}


def _refresh(state, force=False):
    now = time.time()
    for email, entry in state['accounts'].items():
        usage = entry.get('usage', {})
        try:
            if fingerprint(entry['profile']) != entry['fingerprint']:
                entry['usage'] = {'email': email, 'status': 'profile_changed', 'numbersAt': None, 'windows': []}
                continue
            if force or now - usage.get('checkedAt', usage.get('numbersAt') or 0) >= 300:
                result = pm_antigravity_quota.probe(entry['profile'], email)
                result['checkedAt'] = now
                if fingerprint(entry['profile']) != entry['fingerprint']:
                    result = {'email': email, 'status': 'profile_changed', 'numbersAt': None, 'windows': []}
                entry['usage'] = result
        except (OSError, ValueError):
            entry['usage'] = {'email': email, 'status': 'unavailable', 'numbersAt': None, 'windows': []}


def accounts(force=False, refresh=False):
    with registry() as state:
        if refresh:
            _refresh(state, force)
        return [dict(email=email, profile=a['profile'], usage=a.get('usage'),
                     selectedFor=[f for f, selected in state['selected'].items() if selected == email])
                for email, a in state['accounts'].items()]


def model_family(model):
    name = (model or '').lower()
    if 'gemini' in name:
        return 'gemini'
    if 'claude' in name or 'gpt' in name:
        return 'third_party'
    return 'all'


def utilization(entry, family, now):
    usage = entry.get('usage', {})
    if usage.get('status') != 'ok' or not usage.get('numbersAt') or now - usage['numbersAt'] > 1800:
        return None
    families = ('gemini', 'third_party') if family == 'all' else (family,)
    used = []
    for target in families:
        windows = [w for w in usage.get('windows', []) if (w.get('family') == target or
                       target == 'third_party' and w.get('family') in ('claude', 'gpt'))
                   and not w.get('disabled')]
        if not windows or any(w.get('disabled') or not isinstance(w.get('usedPercent'), (int, float))
                              or isinstance(w.get('usedPercent'), bool)
                              or not 0 <= w['usedPercent'] <= 100 for w in windows):
            return None
        used.extend(w['usedPercent'] for w in windows)
    return max(used)


def _select(state, family, dry_run=False):
    now = time.time()
    active = state['selected'].get(family)
    entries = state['accounts']
    current = utilization(entries.get(active, {}), family, now)
    result = {'action': 'unchanged', 'active': active, 'family': family}
    if current is None:
        return dict(result, reason='active_telemetry_unknown')
    if current < 90:
        return dict(result, reason='below_threshold')
    if now - state['lastSwitch'].get(family, 0) < 1800:
        return dict(result, reason='cooldown')
    candidates = [(utilization(entry, family, now), email) for email, entry in entries.items() if email != active]
    candidates = [(used, email) for used, email in candidates
                  if used is not None and used <= 70 and current - used >= 25]
    if not candidates:
        return dict(result, reason='no_healthy_standby')
    _, target = min(candidates)
    if not dry_run:
        state['selected'][family] = target
        state['lastSwitch'][family] = now
    return dict(result, action='would_switch' if dry_run else 'switched', previous=active,
                active=active if dry_run else target, target=target, reason='quota_threshold')


def automatic_enabled():
    config = Path.home() / '.config/broomva/provider-manager.json'
    try:
        data = json.loads(config.read_text()) if config.exists() else {}
        return data.get('autoBalance', True) is True
    except (ValueError, OSError, AttributeError):
        return False


def balance(dry_run=False, model=None, force=False, automatic=False):
    with registry() as state:
        _refresh(state, force)
        return _select(state, model_family(model), dry_run or automatic and not automatic_enabled())


def switch(email, model=None):
    with registry() as state:
        if email not in state['accounts']:
            raise AntigravityError('Unknown Antigravity account')
        _refresh(state)
        family = model_family(model)
        if utilization(state['accounts'][email], family, time.time()) is None:
            raise AntigravityError('Target quota/identity is unreadable')
        state['selected'][family] = email
        state['lastSwitch'][family] = time.time()
        return {'active': email, 'family': family}


def pin_session(session_key, model=None, require_existing=False):
    if not isinstance(session_key, str) or not session_key.strip():
        raise AntigravityError('A stable session key is required')
    with registry() as state:
        pinned = state['pins'].get(session_key)
        if pinned:
            entry = state['accounts'].get(pinned)
            if not entry or fingerprint(entry['profile']) != entry['fingerprint']:
                raise AntigravityError('Pinned account profile changed; resume refused')
            if tuple(entry.get('runtimeFingerprint', ())) != runtime_fingerprint(entry['binary']):
                raise AntigravityError('Pinned ACP runtime changed; resume refused')
            return dict(entry, email=pinned)
        if require_existing:
            raise AntigravityError("Existing session has no account pin; explicit mapping required")
        _refresh(state)
        family = model_family(model)
        _select(state, family, dry_run=not automatic_enabled())
        selected = state['selected'].get(family)
        entry = state['accounts'].get(selected, {})
        if utilization(entry, family, time.time()) is None:
            raise AntigravityError('No verified account for new session')
        if tuple(entry.get('runtimeFingerprint', ())) != runtime_fingerprint(entry['binary']):
            raise AntigravityError('Registered ACP runtime changed; launch refused')
        validate_profile(entry)
        state['pins'][session_key] = selected
        return dict(entry, email=selected)


def install_launcher():
    import shlex
    import sys
    directory = root() / 'bin'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / 'antigravity-acp'
    source = Path(__file__).resolve().with_name('pm_antigravity_launch.py')
    content = '#!/bin/sh\nexec %s %s "$@"\n' % (shlex.quote(sys.executable), shlex.quote(str(source)))
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o700)
    os.replace(temporary, path)
    return {'launcher': str(path)}

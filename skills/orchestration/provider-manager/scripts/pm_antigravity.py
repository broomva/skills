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
    try:
        token = json.loads((Path(profile) / 'antigravity-acp/acp_token.json').read_text())
        identity = {k: token.get(k) for k in ('client_id', 'client_secret', 'refresh_token', 'project_id')}
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    except (ValueError, TypeError, AttributeError) as exc:
        raise AntigravityError('Native profile credentials are unreadable') from exc


def generation_id(email, profile, stamp):
    return hashlib.sha256(json.dumps([email, profile, stamp]).encode()).hexdigest()


def _migrate(state):
    if not isinstance(state, dict) or any(not isinstance(state.get(k), dict)
            for k in ('accounts', 'selected', 'pins', 'lastSwitch')):
        raise AntigravityError('Invalid Antigravity registry')
    if state.get('version') == 1:
        generations = {}
        for email, entry in state['accounts'].items():
            if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str)
                    for k in ('profile', 'fingerprint', 'binary')):
                raise AntigravityError('Invalid legacy Antigravity account')
            identity = generation_id(email, entry['profile'], entry['fingerprint'])
            entry.update(email=email, generation=identity)
            generations[identity] = entry
        pins = {}
        for key, email in state['pins'].items():
            if not isinstance(email, str) or email not in state['accounts']:
                raise AntigravityError('Legacy session pin has no known account')
            pins[key] = state['accounts'][email]['generation']
        state.update(version=2, generations=generations, pins=pins)
    if state.get('version') != 2 or not isinstance(state.get('generations'), dict):
        raise AntigravityError('Invalid Antigravity registry version')
    for identity, entry in state['generations'].items():
        if (not isinstance(entry, dict) or entry.get('generation') != identity or
                not all(isinstance(entry.get(k), str) and entry[k]
                        for k in ('email', 'profile', 'fingerprint', 'binary')) or
                generation_id(entry['email'], entry['profile'], entry['fingerprint']) != identity):
            raise AntigravityError('Invalid immutable Antigravity generation')
    for email, entry in state['accounts'].items():
        if not isinstance(entry, dict):
            raise AntigravityError('Invalid Antigravity account')
        identity = entry.get('generation')
        historic = state['generations'].get(identity) if isinstance(identity, str) else None
        if not isinstance(historic, dict) or historic != entry or historic.get('email') != email:
            raise AntigravityError('Latest account does not match its generation')
        # Keep the latest-account view and canonical generation in sync within the lock.
        state['accounts'][email] = historic
    if any(not isinstance(identity, str) or identity not in state['generations']
           for identity in state['pins'].values()):
        raise AntigravityError('Session pin has no known generation')
    if any(not isinstance(email, str) or email not in state['accounts']
           for email in state['selected'].values()):
        raise AntigravityError('Selected account is unknown')
    return state


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
                'version': 2, 'accounts': {}, 'generations': {}, 'selected': {}, 'pins': {}, 'lastSwitch': {}}
        except (ValueError, OSError) as exc:
            raise AntigravityError('Unreadable Antigravity registry; selection refused') from exc
        state = _migrate(state)
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
    identity = generation_id(email, profile, stamp)
    with registry() as state:
        for old in state['generations'].values():
            if old['profile'] == profile and (old['email'] != email or old['fingerprint'] != stamp):
                raise AntigravityError('Registered profile is immutable; authenticate into a fresh profile')
            if old['profile'] != profile and old['fingerprint'] == stamp:
                raise AntigravityError('One native grant cannot be registered in multiple profiles')
        result = pm_antigravity_quota.probe(profile, email)
        if result.get('email') != email or result.get('status') != 'ok':
            raise AntigravityError('Profile identity and quota must verify before registration')
        if stamp != fingerprint(profile):
            raise AntigravityError('Profile changed during verification')
        if identity not in state['generations']:
            entry = {'email': email, 'generation': identity, 'profile': profile, 'binary': binary,
                     'fingerprint': stamp, 'runtimeFingerprint': list(runtime), 'usage': result}
            state['generations'][identity] = entry
            state['accounts'][email] = entry
        else:
            # Idempotent registration of a retained generation never rolls the latest one back.
            state['generations'][identity]['usage'] = result
        for family in ('gemini', 'third_party', 'all'):
            state['selected'].setdefault(family, email)
    return {'email': email, 'profile': profile, 'generation': identity, 'status': 'registered'}


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
        except (OSError, ValueError, AntigravityError):
            entry['usage'] = {'email': email, 'status': 'unavailable', 'numbersAt': None, 'windows': []}


def accounts(force=False, refresh=False):
    with registry() as state:
        if refresh:
            _refresh(state, force)
        return [dict(email=email, profile=a['profile'], generation=a['generation'], usage=a.get('usage'),
                     selectedFor=[f for f, selected in state['selected'].items() if selected == email])
                for email, a in state['accounts'].items()]


def model_family(model):
    name = (model or '').lower()
    if 'gemini' in name:
        return 'gemini'
    if name == 'third_party' or 'claude' in name or 'gpt' in name:
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
        families = (model_family(model),) if model is not None else ('all', 'gemini', 'third_party')
        if any(utilization(state['accounts'][email], family, time.time()) is None for family in families):
            raise AntigravityError('Target quota/identity is unreadable')
        for family in families:
            state['selected'][family] = email
            state['lastSwitch'][family] = time.time()
        return {'active': email, 'family': families[0], 'families': list(families)}


def pin_session(session_key, model=None, require_existing=False):
    if not isinstance(session_key, str) or not session_key.strip():
        raise AntigravityError('A stable session key is required')
    with registry() as state:
        pinned = state['pins'].get(session_key)
        if pinned:
            entry = state['generations'].get(pinned)
            if not entry or fingerprint(entry['profile']) != entry['fingerprint']:
                raise AntigravityError('Pinned account profile changed; resume refused')
            if tuple(entry.get('runtimeFingerprint', ())) != runtime_fingerprint(entry['binary']):
                raise AntigravityError('Pinned ACP runtime changed; resume refused')
            return dict(entry)
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
        state['pins'][session_key] = entry['generation']
        return dict(entry)


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

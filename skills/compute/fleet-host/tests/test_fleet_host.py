#!/usr/bin/env python3
"""Local-state tests for scripts/fleet_host.py (BRO-3651). No gcloud, ssh or network calls."""
import argparse, importlib.util, json, os, tempfile, unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
# The same file runs beside the scripts (broomva/workspace scripts/) or in a skill's tests/ dir.
SCRIPTS = HERE if (HERE / 'fleet_host.py').exists() else HERE.parent / 'scripts'
_T = SCRIPTS / 'fleet-host/template.json'
os.environ.setdefault('FLEET_HOST_TEMPLATE', str(_T if _T.exists() else SCRIPTS / 'fleet-host/template.example.json'))


def load_module(tmp):
    os.environ['FLEET_DIR'] = str(tmp / 'fleet')
    os.environ['FLEET_SSH_CONFIG'] = str(tmp / 'ssh_config')
    os.environ['FLEET_KNOWN_HOSTS'] = str(tmp / 'known_hosts')  # never the real ~/.ssh/known_hosts
    spec = importlib.util.spec_from_file_location('fleet_host', SCRIPTS / 'fleet_host.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    # Never the operator's real fleet key: a CI runner has none, and a test must not read one (skills#311).
    key = tmp / 'fleet_hosts_ed25519'
    key.write_text('test private key, never used\n')
    key.with_suffix('.pub').write_text('ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestOnlyKey fleet-test\n')
    m.SSH_KEY = key
    return m


class LocalStateRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.m = load_module(self.tmp)
        (self.tmp / 'fleet/meta').mkdir(parents=True)
        self.m.SETPOINTS.write_text(json.dumps({'setpoints': {'host.nuc.max_live': {'value': 3}}}))
        self.m.STATE.write_text(json.dumps({'remote_host_holds': {'nuc': {'active': False}}, 'other': 1}))
        (self.tmp / 'ssh_config').write_text('Host other\n  HostName example\n')
        args = argparse.Namespace(name='gcp-1', zone='us-central1-a', shape='e2-standard-8', disk_gb=200,
                                  drain_timeout=1, push_wip=False, dry=False, cmd='add')
        self.h = self.m.Host(args)

    def test_add_then_remove_restores_local_state(self):
        before = {p: p.read_text() for p in (self.m.SETPOINTS, self.m.STATE, self.tmp / 'ssh_config')}
        for step in (self.m.s_setpoint, self.m.s_hold, self.m.s_register, self.m.s_ssh_alias):
            self.assertEqual(step(self.h, True)[0], self.m.OK)
            self.assertEqual(step(self.h, False)[0], self.m.OK, 'second run must be a no-op')
        sp = json.loads(self.m.SETPOINTS.read_text())['setpoints']
        self.assertEqual(sp['host.gcp-1.max_live']['value'], 1)
        self.assertTrue(json.loads(self.m.STATE.read_text())['remote_host_holds']['gcp-1']['active'])
        self.assertEqual(self.h.registry_entry()['heavy_slots'], 2)
        with mock.patch.object(self.m.Host, 'instance_status', return_value=None):
            self.assertEqual(self.m.r_drain_hold(self.h, True)[0], self.m.OK)
            self.assertEqual(json.loads(self.m.SETPOINTS.read_text())['setpoints']['host.gcp-1.max_live']['value'], 0)
            self.assertEqual(self.m.r_deregister(self.h, True)[0], self.m.OK)
            self.assertEqual(self.m.r_deregister(self.h, False)[0], self.m.OK)
        for p, text in before.items():
            self.assertEqual(json.loads(p.read_text()) if p.suffix == '.json' else p.read_text(),
                             json.loads(text) if p.suffix == '.json' else text, p.name)
        self.assertEqual(json.loads(self.m.REGISTRY.read_text())['hosts'], [])

    def test_dry_run_writes_nothing(self):
        before = {p: p.read_text() for p in (self.m.SETPOINTS, self.m.STATE, self.tmp / 'ssh_config')}
        for step in (self.m.s_setpoint, self.m.s_hold, self.m.s_register, self.m.s_ssh_alias):
            self.assertEqual(step(self.h, False)[0], self.m.WOULD)
        for p, text in before.items():
            self.assertEqual(p.read_text(), text)
        self.assertFalse(self.m.REGISTRY.exists())

    def test_unobservable_is_not_absent(self):
        r = mock.Mock(returncode=1, stdout='', stderr='ERROR: PERMISSION_DENIED: caller lacks permission')
        with mock.patch.object(self.m.subprocess, 'run', return_value=r):
            with self.assertRaises(self.m.Unobservable):
                self.m.gdescribe('compute', 'instances', 'describe', 'x')
        r.stderr = 'ERROR: (gcloud) NOT_FOUND: instance x was not found'
        with mock.patch.object(self.m.subprocess, 'run', return_value=r):
            self.assertIsNone(self.m.gdescribe('compute', 'instances', 'describe', 'x'))

    def test_reserved_names_rejected(self):
        for bad in ('nuc', 'mac', 'Gcp', 'x', 'a' * 30):
            with self.assertRaises(SystemExit):
                with mock.patch('sys.stderr'):
                    self.m.main(['status', bad])


class FakeMinted:
    """A minted-credential double: `live` is the provider's truth, `listed_ok` False makes it unobservable."""
    def __init__(self, m, scope=True, delete_works=True):
        self.m, self.live, self.scope, self.delete_works, self.listed_ok = m, set(), scope, delete_works, True

    def patch(self, c):
        m = self.m
        return [mock.patch.object(type(m), 'admin', lambda _s: 'admin'),
                mock.patch.object(type(m), 'mint', lambda _s, h, a: (self.live.add('id1') or ('id1', 'VALUE', {'name': 'fleet-gcp-1'}))),
                mock.patch.object(type(m), 'listed', lambda _s, a, cid: (cid in self.live) if self.listed_ok else None),
                mock.patch.object(type(m), 'delete', lambda _s, a, cid: self.delete_works and self.live.discard(cid)),
                mock.patch.object(type(m), 'scope_ok', lambda _s, v: (self.scope, 'prod 200' if not self.scope else ''))]


class Credentials(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.m = load_module(self.tmp)
        self.c = self.m.creds
        args = argparse.Namespace(name='gcp-1', zone='us-central1-a', shape='e2-standard-8', disk_gb=200,
                                  drain_timeout=1, push_wip=False, dry=False, cmd='creds')
        self.h = self.m.Host(args)
        self.h._reachable = True

    def run_step(self, fake, step, deliver_ok=True, host_has=False):
        patches = fake.patch(self.c) + [mock.patch.object(self.c, 'write_files', return_value=deliver_ok),
                                        mock.patch.object(self.c, 'host_has', return_value=host_has)]
        for p_ in patches:
            p_.start()
        try:
            return step(self.h, True)
        finally:
            for p_ in patches:
                p_.stop()

    def test_writer_wrappers_keep_the_token_out_of_the_shell(self):
        home = self.tmp / 'home'
        (home / '.bun/bin').mkdir(parents=True)
        real = home / '.bun/bin/neonctl'
        real.write_text('#!/bin/sh\necho "key=${NEON_API_KEY:+set}"\n')
        real.chmod(0o755)
        payload = json.dumps({'files': {'.config/fleet/neonctl.env': 'NEON_API_KEY=v\n',
                                        '.config/fleet/ids.env': 'NEON_PROJECT_ID=p\n'},
                              'env_profile': True, 'wrappers': {'.local/bin/neonctl': '.bun/bin/neonctl'}})
        env = {**os.environ, 'HOME': str(home)}
        sp = __import__('subprocess')
        for _ in range(2):
            self.assertEqual(sp.run(['python3', '-c', self.c.WRITER], input=payload, text=True,
                                    capture_output=True, env=env).stdout.strip(), 'ok')
        f = home / '.config/fleet/neonctl.env'
        self.assertEqual(oct(f.stat().st_mode & 0o777), '0o600')
        self.assertEqual((home / '.bashrc').read_text().count('fleet host credentials'), 1)
        self.assertEqual(sp.run([str(home / '.local/bin/neonctl')], env=env, capture_output=True, text=True).stdout.strip(), 'key=set')
        shell = sp.run(['bash', '-lc', 'echo "${NEON_API_KEY:-unset} $NEON_PROJECT_ID"'], env=env,
                       capture_output=True, text=True).stdout.strip()
        self.assertEqual(shell, 'unset p')

    def test_minted_id_is_recorded_before_delivery_and_dropped_only_on_proof(self):
        fake = FakeMinted(self.c.Vercel())
        status, _ = self.run_step(fake, self.c.s_minted(self.c.Vercel()), deliver_ok=False)
        self.assertEqual(status, self.c.FAIL)
        self.assertEqual(fake.live, set())                       # revoked
        self.assertNotIn('vercel', self.c.record(self.h))       # and only then forgotten

    def test_unprovable_revoke_keeps_the_record(self):
        fake = FakeMinted(self.c.Vercel(), delete_works=False)
        status, detail = self.run_step(fake, self.c.s_minted(self.c.Vercel()), deliver_ok=False)
        self.assertEqual(status, self.c.FAIL)
        self.assertEqual(self.c.record(self.h)['vercel']['state'], 'pending', detail)
        self.assertEqual(fake.live, {'id1'})

    def test_over_scoped_neon_key_is_revoked_not_delivered(self):
        fake = FakeMinted(self.c.Neon(), scope=False)
        with mock.patch.object(self.c, 'write_files') as wf:
            for p_ in fake.patch(self.c):
                p_.start()
            try:
                status, _ = self.c.s_minted(self.c.Neon())(self.h, True)
            finally:
                mock.patch.stopall()
        self.assertEqual(status, self.c.FAIL)
        wf.assert_not_called()
        self.assertEqual(fake.live, set())

    def test_success_marks_active(self):
        fake = FakeMinted(self.c.Neon())
        status, _ = self.run_step(fake, self.c.s_minted(self.c.Neon()))
        self.assertEqual(status, self.c.OK)
        self.assertEqual(self.c.record(self.h)['neon']['state'], 'active')

    def test_revoke_requires_proof(self):
        self.c.set_record(self.h, 'vercel', {'id': 'id1', 'name': 'fleet-gcp-1', 'state': 'active'})
        fake = FakeMinted(self.c.Vercel(), delete_works=False)
        fake.live.add('id1')
        status, _ = self.run_step(fake, self.c.r_minted(self.c.Vercel()))
        self.assertEqual(status, self.c.FAIL)
        self.assertIn('vercel', self.c.record(self.h))
        fake.listed_ok = False
        status, _ = self.run_step(fake, self.c.r_minted(self.c.Vercel()))
        self.assertEqual(status, self.c.BLOCKED)                # unobservable is never "revoked"

    def test_unreachable_host_with_a_disk_blocks_revocation(self):
        self.c.set_record(self.h, 'linear', {'copied_at': 'x'})
        self.h.reachable = lambda: False  # never a real ssh from a test
        with mock.patch.object(self.c, 'disk_gone', return_value=False):
            self.assertEqual(self.c.r_linear(self.h, True)[0], self.c.BLOCKED)
            self.assertEqual(self.c.r_logins(self.h, True)[0], self.c.BLOCKED)
        self.assertIn('linear', self.c.record(self.h))
        with mock.patch.object(self.c, 'disk_gone', return_value=True):
            self.assertEqual(self.c.r_linear(self.h, True)[0], self.c.OK)


class RemoveSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.m = load_module(self.tmp)
        args = argparse.Namespace(name='gcp-1', zone='z', shape='e2-standard-8', disk_gb=200,
                                  drain_timeout=1, push_wip=False, dry=False, cmd='remove')
        self.h = self.m.Host(args)
        self.h._status = 'RUNNING'

    def test_unfinished_work_blocks_without_push_wip(self):
        with mock.patch.object(self.m, 'ssh', return_value=(0, '0')), \
             mock.patch.object(self.m, 'run', return_value=(0, 'unpushed:/home/agent/app\nscan-ok')):
            self.assertEqual(self.m.r_drain(self.h, True)[0], self.m.BLOCKED)

    def test_failed_scan_is_not_clean(self):
        with mock.patch.object(self.m, 'ssh', return_value=(0, '0')), \
             mock.patch.object(self.m, 'run', return_value=(255, '')):
            with self.assertRaises(self.m.Unobservable):
                self.m.r_drain(self.h, True)

    def test_push_wip_must_leave_nothing_behind(self):
        self.h.a.push_wip = True
        runs = [(0, 'dirty:/home/agent/app\nscan-ok'), (0, 'pushed:/home/agent/app:main -> wip/gcp-1/app/main-x'),
                (0, 'dirty:/home/agent/app\nscan-ok')]   # scan, push, re-scan still dirty
        with mock.patch.object(self.m, 'ssh', return_value=(0, '0')), \
             mock.patch.object(self.m, 'run', side_effect=runs):
            self.assertEqual(self.m.r_drain(self.h, True)[0], self.m.FAIL)

    def test_owner_step_stops_apply(self):
        calls = []
        steps = [('a', lambda h, ap: (self.m.OWNER, 'needs owner'), False),
                 ('b', lambda h, ap: calls.append('b') or (self.m.OK, ''), False)]
        with mock.patch.object(self.m, 'REMOVE', steps), mock.patch('sys.stdout'):
            self.m.main(['remove', 'gcp-1', '--apply'])
        self.assertEqual(calls, [])

    def test_durations(self):
        self.assertEqual(self.m.duration('2h'), 7200)
        self.assertEqual(self.m.duration('90m'), 5400)
        self.assertEqual(self.m.duration('45'), 45)

class WipRescueOnRealRepos(unittest.TestCase):
    """WIP_SCAN / WIP_PUSH on real git repos: dirty tree, branch with no upstream, detached-HEAD worktree."""
    def test_everything_unfinished_is_pushed_and_rescan_is_clean(self):
        import subprocess as sp
        m = load_module(Path(tempfile.mkdtemp()))
        home = Path(tempfile.mkdtemp())
        env = {**os.environ, 'HOME': str(home), 'GIT_CONFIG_GLOBAL': str(home / 'gitconfig'),
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TEMPLATE_DIR': ''}
        (home / 'gitconfig').write_text('[core]\n\thooksPath = /dev/null\n')
        def git(*a, cwd=None):
            sp.run(['git', '-c', 'user.email=t@e.st', '-c', 'user.name=t', *a], cwd=cwd, env=env, check=True,
                   capture_output=True)
        git('init', '-q', '--bare', str(home / 'origin.git'))
        git('clone', '-q', str(home / 'origin.git'), str(home / 'broomva'))
        repo = home / 'broomva'
        (repo / 'a').write_text('a')
        git('add', 'a', cwd=repo); git('commit', '-qm', 'init', cwd=repo); git('push', '-q', 'origin', 'HEAD:main', cwd=repo)
        git('checkout', '-qb', 'no-upstream', cwd=repo)
        (repo / 'b').write_text('b')
        git('add', 'b', cwd=repo); git('commit', '-qm', 'feat', cwd=repo)
        (repo / 'b').write_text('dirty')
        wt = home / '.t3/worktrees/proj/wt1'
        git('worktree', 'add', '-q', '--detach', str(wt), 'HEAD', cwd=repo)
        (wt / 'd').write_text('d')
        git('add', 'd', cwd=wt); git('commit', '-qm', 'detached', cwd=wt)
        wt2 = home / '.t3/worktrees/proj/wt2'                 # a second detached worktree, different commit
        git('worktree', 'add', '-q', '--detach', str(wt2), 'origin/main', cwd=repo)
        (wt2 / 'e').write_text('e')
        git('add', 'e', cwd=wt2); git('commit', '-qm', 'detached-2', cwd=wt2)

        def sh(script, *args):
            r = sp.run(['bash', '-s', '--', *args], input=script, capture_output=True, text=True, env=env)
            return r.returncode, r.stdout
        before = sh(m.WIP_SCAN, str(repo))[1].split()
        self.assertIn(f'unpushed:{wt}', before)          # detached HEAD is seen
        self.assertIn(f'dirty:{repo}', before)
        rc, out = sh(m.WIP_PUSH, 'gcp-1', str(repo))
        self.assertEqual(rc, 0, out)
        self.assertEqual(sh(m.WIP_SCAN, str(repo))[1].split(), ['scan-ok'])
        rc, again = sh(m.WIP_PUSH, 'gcp-1', str(repo))
        self.assertEqual((rc, again.strip()), (0, ''))    # a retry is a no-op
        # With every branch pushed, a new commit on a detached HEAD alone must still be found.
        (wt / 'f').write_text('f')
        git('add', 'f', cwd=wt); git('commit', '-qm', 'later', cwd=wt)
        self.assertEqual(sh(m.WIP_SCAN, str(repo))[1].split(), [f'unpushed:{wt}', 'scan-ok'])

class LoginFreeHost(unittest.TestCase):
    """BRO-3666: the host is usable before any login (Gemini on Vertex, T3, link, registry); logins come last."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.m = load_module(self.tmp)
        args = argparse.Namespace(name='gcp-1', zone='z', shape='e2-standard-8', disk_gb=200,
                                  drain_timeout=1, push_wip=False, dry=False, cmd='add')
        self.h = self.m.Host(args)
        self.h._status = 'RUNNING'

    def test_logins_are_last_and_gate_nothing(self):
        names = [n for n, *_ in self.m.ADD]
        self.assertEqual(names[-1], 'cred:logins')
        for before in ('llm:vertex', 't3', 'agentic-verify', 't3-link', 'register'):
            self.assertLess(names.index(before), names.index('cred:logins'), before)
        # ssh trust and the re-applied startup script come before anything runs on the host
        self.assertLess(names.index('host-key'), names.index('converge'))
        self.assertLess(names.index('converge'), names.index('ready'))
        self.assertLess(names.index('snapshot'), names.index('cred:vercel'))  # rollback point stays secret-free

    def test_t3_settings_add_the_vertex_provider_and_keep_the_rest(self):
        import subprocess as sp
        script = self.m.T3_INSTALL
        block = script[script.index('GV_MODELS="$GV"'):script.index("PY\n", script.index('GV_MODELS="$GV"')) + 3]
        home = Path(tempfile.mkdtemp())
        settings = home / '.t3/userdata/settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({'keep': 1, 'providerInstances': {'codex': {'enabled': True}}}))
        env = {'HOME': str(home), 'PATH': os.environ['PATH']}
        models = ','.join(self.m.VERTEX['models'])
        for _ in range(2):  # idempotent
            sp.run(['bash', '-c', 'GV="$1"; ' + block, 'bash', models], env=env, check=True, capture_output=True)
        d = json.loads(settings.read_text())
        self.assertEqual(d['keep'], 1)
        self.assertTrue(d['linkedEnvironmentsEnabled'])
        self.assertIn('codex', d['providerInstances'])
        gv = d['providerInstances']['gemini-vertex']
        self.assertEqual(gv['config']['customModels'], self.m.VERTEX['models'])
        self.assertEqual(gv['config']['commandPath'], self.m.GV_HOME + '/bin/gemini-vertex-acp')
        # the s_t3 check agrees with what the install wrote, and notices a stale model list
        check = lambda: sp.run(['bash', '-c', self.m.GV_CHECK], env=env, capture_output=True, text=True).stdout
        self.assertNotIn('gv-missing', check())
        gv['config']['customModels'] = ['old-model']
        settings.write_text(json.dumps(d))
        self.assertIn('gv-missing', check())

    def test_host_key_pins_only_the_console_key(self):
        host = self.m.ssh_host(self.h)
        console = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIConsoleKey'
        other = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOtherKey'
        self.m.KNOWN_HOSTS.write_text(f'{host} ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOldVmKey\nelse.example {other}\n')
        real_run = self.m.run
        def fake_run(cmd, **k):
            if cmd[0] == 'ssh-keyscan':
                return 0, f'{host} {self.answering}\n'
            if cmd[0] == 'ssh':
                return 255, ''  # the pinned key does not answer (a re-created VM); never a real ssh in a test
            return real_run(cmd, **k)
        with mock.patch.object(self.m, 'console_host_keys', return_value={console}), \
             mock.patch.object(self.m, 'run', side_effect=fake_run):
            self.answering = other  # an impostor on the tailnet name
            self.assertEqual(self.m.s_host_key(self.h, True)[0], self.m.FAIL)
            self.answering = console
            self.assertEqual(self.m.s_host_key(self.h, False)[0], self.m.WOULD)
            self.assertIn('OldVmKey', self.m.KNOWN_HOSTS.read_text())  # dry run changed nothing
            self.assertEqual(self.m.s_host_key(self.h, True)[0], self.m.OK)
            self.assertEqual(self.m.pinned_host_keys(self.h), {console})
            self.assertIn(f'else.example {other}', self.m.KNOWN_HOSTS.read_text())  # other hosts untouched
            self.assertEqual(self.m.s_host_key(self.h, True)[1], f'{host} pinned to its console key')
        with mock.patch.object(self.m.Host, 'instance_status', return_value=None):
            self.assertEqual(self.m.r_deregister(self.h, True)[0], self.m.OK)
        self.assertEqual(self.m.pinned_host_keys(self.h), set())

    def test_converge_reports_only_stale_keys(self):
        want = self.m.instance_metadata(self.h)
        with mock.patch.object(self.m, 'deployed_metadata', return_value=dict(want)):
            self.assertEqual(self.m.s_converge(self.h, False)[0], self.m.OK)
        old = dict(want, **{'startup-script': '#!/bin/bash\necho old\n'})
        old.pop('fleet-gemini-cli-version', None)
        with mock.patch.object(self.m, 'deployed_metadata', return_value=old):
            st, detail = self.m.s_converge(self.h, False)
        self.assertEqual(st, self.m.WOULD)
        self.assertIn('startup-script', detail)
        self.assertIn('fleet-gemini-cli-version', detail)
        self.assertNotIn('fleet-host-name', detail)

    def test_t3_link_pairs_without_leaking_the_token_and_records_the_id(self):
        url = f'https://{self.m.ssh_host(self.h)}:4443'
        token = 'SeCrEtPaIrInG42'
        pair_out = f'Pairing with x\n\nPairing URL: {url}/pair#token={token}\nToken: {token}\n'
        env = '11111111-2222-3333-4444-555555555555'
        listed = [[{'environmentId': 'aaaaaaaa-0000-0000-0000-000000000000', 'urls': ['https://other:4444']}],
                  [{'environmentId': env, 'urls': [url]}]]
        calls = []
        def fake_run(cmd, **k):
            calls.append(cmd)
            return (0, '') if cmd[1:3] == ['environment', 'link'] else (1, '')
        with mock.patch.object(self.m, 'ssh', return_value=(0, pair_out)), \
             mock.patch.object(self.m, 'run', side_effect=fake_run), \
             mock.patch.object(self.m, 't3_cli', return_value='/t3'), \
             mock.patch.object(self.m, 'linked_envs', side_effect=[listed[0], listed[0], listed[1], listed[1]]), \
             mock.patch('sys.stdout') as out:
            self.assertEqual(self.m.s_t3_link(self.h, False)[0], self.m.WOULD)  # a dry run never pairs
            self.assertEqual(calls, [])
            st, detail = self.m.s_t3_link(self.h, True)
            self.assertEqual(st, self.m.OK)
            self.assertNotIn(token, detail)
            self.assertNotIn(token, str(out.mock_calls))
            self.assertEqual(calls, [['/t3', 'environment', 'link', url, '--pairing-code', token, '--access', 'full-access']])
            self.assertEqual(self.m.host_env_id(self.h), env)
            # re-run: found by its recorded id, no new pairing
            self.assertEqual(self.m.s_t3_link(self.h, True), (self.m.OK, f'linked environmentId {env}'))
            self.assertEqual(len(calls), 1)
        # a failed link reports, never echoes the token
        self.m.atomic_json(self.h.dir / 't3-link.json', {})
        with mock.patch.object(self.m, 'ssh', return_value=(0, pair_out)), \
             mock.patch.object(self.m, 'run', return_value=(1, f'error {token}')), \
             mock.patch.object(self.m, 't3_cli', return_value='/t3'), \
             mock.patch.object(self.m, 'linked_envs', return_value=[]), mock.patch.object(self.m.time, 'sleep'):
            st, detail = self.m.s_t3_link(self.h, True)
        self.assertEqual(st, self.m.FAIL)
        self.assertNotIn(token, detail)

    def test_t3_step_reinstalls_when_the_vertex_provider_is_missing(self):
        v = '0.1.5-test'
        with mock.patch.object(self.m, 'mac_t3_version', return_value=v):
            with mock.patch.object(self.m, 'ssh', return_value=(0, f't3 v{v} active')):
                self.assertEqual(self.m.s_t3(self.h, False)[0], self.m.OK)
            for missing in ('gv-missing', 'scratch-missing', 'repo-missing'):
                with mock.patch.object(self.m, 'ssh', return_value=(0, f'{missing} t3 v{v} active')):
                    self.assertEqual(self.m.s_t3(self.h, False)[0], self.m.WOULD, missing)

    def test_converge_apply_paths(self):
        """P20 #1252 r1: converge never runs the startup script twice at once, and a booting host blocks."""
        m, h = self.m, self.h
        pub = Path(tempfile.mkdtemp()) / 'k'
        pub.with_suffix('.pub').write_text('ssh-ed25519 AAAA test')
        stale = lambda: dict(m.instance_metadata(h), **{'startup-script': 'old'})
        def run_conv(ssh_side, status='RUNNING', reach=True):
            h.__dict__.pop('_reachable', None)
            with mock.patch.object(m, 'SSH_KEY', pub), mock.patch.object(m, 'deployed_metadata', side_effect=lambda _h: stale()), \
                 mock.patch.object(m, 'gcloud', return_value=(0, '')), \
                 mock.patch.object(m.Host, 'instance_status', return_value=status), \
                 mock.patch.object(m.Host, 'reachable', return_value=reach), \
                 mock.patch.object(m, 'ssh', side_effect=ssh_side) as s:
                return m.s_converge(h, True), s.call_args_list
        (st, _), calls = run_conv([(0, 'inactive'), (0, '')])
        self.assertEqual(st, m.OK)
        self.assertIn('google_metadata_script_runner', calls[-1][0][1])
        (st, _), _ = run_conv([(0, 'inactive'), (1, '')])
        self.assertEqual(st, m.FAIL)
        (st, _), calls = run_conv([(0, 'activating')])
        self.assertEqual(st, m.BLOCKED)  # a boot-time run is in progress: never a second one
        self.assertEqual(len(calls), 1)
        (st, _), calls = run_conv([], reach=False)
        self.assertEqual(st, m.BLOCKED)
        (st, _), calls = run_conv([], status='TERMINATED')
        self.assertEqual(st, m.OK)  # applies at next boot
        with mock.patch.object(m, 'SSH_KEY', pub.with_name('absent')), \
             mock.patch.object(m.Host, 'instance_status', return_value='RUNNING'):
            self.assertEqual(m.s_converge(h, False)[0], m.BLOCKED)  # missing pubkey: blocked, not a crash

    def test_vertex_off_clears_its_metadata(self):
        with mock.patch.object(self.m, 'VERTEX', {'enabled': False, 'location': 'global', 'gemini_cli': '0.66.0'}):
            md = self.m.instance_metadata(self.h)
        self.assertEqual((md['fleet-vertex-location'], md['fleet-gemini-cli-version']), ('', ''))

    def test_unreachable_is_not_cached(self):
        answers = iter([(255, ''), (0, '')])
        with mock.patch.object(self.m, 'ssh', side_effect=lambda *a, **k: next(answers)), \
             mock.patch.object(self.m.Host, 'instance_status', return_value='RUNNING'):
            self.assertFalse(self.h.reachable())
            self.assertTrue(self.h.reachable())   # booted since: asked again, not the cached no
            self.assertTrue(self.h.reachable())   # a yes is cached (no third ssh call)

    def test_link_matches_the_exact_host_only(self):
        tail = self.m.TAILNET_SUFFIX
        envs = [{'environmentId': 'other', 'urls': [f'https://test-gcp-1.{tail}:4443']},
                {'environmentId': 'mine', 'urls': [f'https://gcp-1.{tail}:4443']}]
        self.assertEqual(self.m.env_for_host(envs, self.h), ['mine'])
        self.assertEqual(self.m.env_for_host(envs[:1], self.h), [])

    def test_ready_requires_gemini_vertex_when_enabled(self):
        if not self.m.VERTEX.get('enabled'):
            self.skipTest('template has Vertex off')
        tools = {'git': True}
        with mock.patch.object(self.m, 'ssh', return_value=(0, json.dumps({'tools': tools}))):
            self.assertEqual(self.m.s_ready(self.h, False)[0], self.m.FAIL)  # absent is missing
        tools['gemini-vertex'] = True
        with mock.patch.object(self.m, 'ssh', return_value=(0, json.dumps({'tools': tools}))), \
             mock.patch.object(self.m, 'secret_exists', return_value=False):
            self.assertEqual(self.m.s_ready(self.h, False)[0], self.m.OK)

    def test_woken_host_is_verified_by_its_pinned_key_without_the_console(self):
        host = self.m.ssh_host(self.h)
        self.m.KNOWN_HOSTS.write_text(f'{host} ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPinned\n')
        real_run = self.m.run
        calls = []
        def fake_run(cmd, **k):
            calls.append(cmd[0])
            return (0, '') if cmd[0] == 'ssh' else real_run(cmd, **k)
        with mock.patch.object(self.m, 'run', side_effect=fake_run), \
             mock.patch.object(self.m, 'console_host_keys', side_effect=AssertionError('console not needed')):
            self.assertEqual(self.m.s_host_key(self.h, True), (self.m.OK, f'{host} answers with its pinned key'))
        ssh_call = [c for c in calls if c == 'ssh']
        self.assertEqual(len(ssh_call), 1)
        argv = self.m.strict_ssh(self.h)  # bound to the inspected entry: no config, no global file, its alias
        for opt in ('StrictHostKeyChecking=yes', f'UserKnownHostsFile={self.m.KNOWN_HOSTS}',
                    'GlobalKnownHostsFile=/dev/null', f'HostKeyAlias={host}'):
            self.assertIn(opt, argv)
        self.assertEqual(argv[argv.index('-F') + 1], '/dev/null')

    def test_host_key_append_survives_a_file_without_trailing_newline(self):
        host = self.m.ssh_host(self.h)
        key = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIConsoleKey'
        self.m.KNOWN_HOSTS.write_text('else.example ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOther')  # no newline
        real_run = self.m.run
        fake = lambda cmd, **k: ((0, f'{host} {key}\n') if cmd[0] == 'ssh-keyscan' else (255, '') if cmd[0] == 'ssh'
                                 else real_run(cmd, **k))
        with mock.patch.object(self.m, 'console_host_keys', return_value={key}), \
             mock.patch.object(self.m, 'run', side_effect=fake):
            self.assertEqual(self.m.s_host_key(self.h, True)[0], self.m.OK)
        lines = self.m.KNOWN_HOSTS.read_text().splitlines()
        self.assertEqual(lines, ['else.example ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOther', f'{host} {key}'])

    def test_scratch_check_reads_t3s_project_table(self):
        import sqlite3, subprocess as sp
        home = Path(tempfile.mkdtemp())
        (home / '.t3/userdata').mkdir(parents=True)
        db = sqlite3.connect(home / '.t3/userdata/statev2.sqlite')
        db.execute('create table projection_projects (project_id text, workspace_root text, deleted_at text)')
        db.commit()
        check = lambda: sp.run(['bash', '-c', self.m.SCRATCH_CHECK], env={'HOME': str(home), 'PATH': os.environ['PATH']},
                               capture_output=True, text=True).stdout
        (home / 'scratch/.git').mkdir(parents=True)
        self.assertIn('scratch-missing', check())   # the directory alone is not a T3 project
        db.execute('insert into projection_projects values (?, ?, ?)', ('p', f'{home}/scratch', None)); db.commit()
        self.assertNotIn('scratch-missing', check())
        db.execute('update projection_projects set deleted_at = ?', ('x',)); db.commit()
        self.assertIn('scratch-missing', check())   # a deleted project is missing

    def test_vertex_off_removes_the_t3_provider(self):
        import subprocess as sp
        script = self.m.T3_INSTALL
        block = script[script.index('GV_MODELS="$GV"'):script.index("PY\n", script.index('GV_MODELS="$GV"')) + 3]
        home = Path(tempfile.mkdtemp())
        settings = home / '.t3/userdata/settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({'providerInstances': {'codex': {}, 'gemini-vertex': {'config': {}}}}))
        sp.run(['bash', '-c', 'GV="$1"; ' + block, 'bash', '-'], env={'HOME': str(home), 'PATH': os.environ['PATH']},
               check=True, capture_output=True)
        self.assertEqual(list(json.loads(settings.read_text())['providerInstances']), ['codex'])

    def test_ssh_key_derives_a_missing_pub_and_never_makes_a_new_key(self):
        import subprocess as sp
        key = Path(tempfile.mkdtemp()) / 'k'
        sp.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
        original = key.with_suffix('.pub').read_text().split()[:2]
        key.with_suffix('.pub').unlink()
        with mock.patch.object(self.m, 'SSH_KEY', key):
            self.assertEqual(self.m.s_ssh_key(self.h, False)[0], self.m.WOULD)
            self.assertEqual(self.m.s_ssh_key(self.h, True)[0], self.m.OK)
            self.assertEqual(key.with_suffix('.pub').read_text().split()[:2], original)
            self.assertEqual(self.m.s_ssh_key(self.h, True), (self.m.OK, f'{key} present'))

    def test_awake_bounds_and_start_holds_the_host(self):
        import argparse as ap
        for bad in ('-1', '241', 'x'):
            with self.assertRaises((ap.ArgumentTypeError, ValueError)):
                self.m.awake_minutes(bad)
        self.assertEqual(self.m.awake_minutes('240'), 240)
        self.h.a.awake = 60
        with mock.patch.object(self.m.Host, 'instance_status', return_value='RUNNING'), \
             mock.patch.object(self.m.Host, 'reachable', return_value=True), \
             mock.patch.object(self.m, 'hold_awake', return_value=True) as hold:
            self.assertEqual(self.m.x_start(self.h, True)[0], self.m.OK)
            hold.assert_called_once_with(self.h, 60)
            hold.reset_mock()
            self.assertEqual(self.m.x_start(self.h, False)[0], self.m.OK)
            hold.assert_not_called()  # a dry run changes nothing
        for reach, held in ((False, True), (True, False)):  # never claim a hold that was not set
            with mock.patch.object(self.m.Host, 'instance_status', return_value='RUNNING'), \
                 mock.patch.object(self.m.Host, 'reachable', return_value=reach), \
                 mock.patch.object(self.m, 'hold_awake', return_value=held):
                self.assertNotIn('held awake', self.m.x_start(self.h, True)[1], (reach, held))

    def test_login_code_always_closes_the_spent_session(self):
        c = self.m.creds
        f = Path(tempfile.mkdtemp()) / 'code'
        self.h.a.tool, self.h.a.code_file = 'claude', str(f)
        self.assertEqual(self.m.x_login_code(self.h, True)[0], self.m.BLOCKED)  # no file
        f.write_text('abc#state')
        self.assertEqual(self.m.x_login_code(self.h, False)[0], self.m.WOULD)
        # a slow token exchange: missing at first, logged in on a later poll, and the session is closed after
        with mock.patch.object(c, 'send_login_code', return_value=True), \
             mock.patch.object(c, 'logins_missing', side_effect=[['claude'], ['claude'], []]) as lm, \
             mock.patch.object(c, 'end_login_sessions') as end, mock.patch.object(self.m.time, 'sleep'):
            self.assertEqual(self.m.x_login_code(self.h, True)[0], self.m.OK)
            self.assertEqual(lm.call_count, 3)
            end.assert_called_once_with(self.h, ['claude'])
        for sent, missing, want in ((True, [], self.m.OK), (True, ['claude'], self.m.FAIL), (False, ['claude'], self.m.FAIL)):
            with mock.patch.object(c, 'send_login_code', return_value=sent), \
                 mock.patch.object(c, 'logins_missing', return_value=missing), \
                 mock.patch.object(c, 'end_login_sessions') as end, mock.patch.object(self.m.time, 'sleep'):
                self.assertEqual(self.m.x_login_code(self.h, True)[0], want, (sent, missing))
                end.assert_called_once_with(self.h, ['claude'])  # spent either way: next relay starts fresh

    def test_logins_close_the_sessions_of_tools_already_logged_in(self):
        c = self.m.creds
        self.h._reachable = True
        with mock.patch.object(c, 'logins_missing', return_value=['claude']), \
             mock.patch.object(c, 'end_login_sessions') as end, \
             mock.patch.object(c, 'relay_logins', return_value=['claude: open X']), \
             mock.patch.object(c.sys.stdin, 'isatty', return_value=False):
            st, _ = c.s_logins(self.h, True)
        self.assertEqual(st, c.OWNER)
        self.assertEqual(sorted(end.call_args[0][1]), ['codex', 'gh'])

    def test_relay_sessions_are_bounded_and_never_reuse_a_finished_login(self):
        c = self.m.creds
        scripts = []
        with mock.patch.object(c, 'ssh', side_effect=lambda h, sc, *a, **k: scripts.append(sc) or (0, '   CUNO-5F1GE')):
            c.relay_logins(self.h, ['codex'])
        self.assertIn(f'timeout {c.LOGIN_MAX_S} bash -lc', scripts[0])  # no login outlives its code
        self.assertIn('[ "$cmd" = sleep ]', scripts[0])                 # a finished login is restarted
        self.assertNotIn('sleep 1200', scripts[0])

    def test_login_relay_reads_each_code_and_never_runs_without_a_pane(self):
        c = self.m.creds
        panes = {'login-gh': '! First copy your one-time code: 9738-B569\nPress Enter to open https://github.com/login/device',
                 'login-codex': '2. Enter this one-time code (expires in 15 minutes)\n   CUNO-5F1GE\n',
                 'login-claude': 'If the browser didn\'t open, visit: https://claude.com/cai/oauth/authorize?code=true&state=abc\nPaste code here'}
        def fake_ssh(host, script, input_json=None, timeout=60):
            sess = next(k for k in panes if f's={k};' in script)
            self.assertIn('awake-until', script)            # the relay holds the host awake
            self.assertIn('c=0 ;; esac', script)             # an absent session never breaks the age expression
            return 0, panes[sess]
        with mock.patch.object(c, 'ssh', side_effect=fake_ssh):
            asks = c.relay_logins(self.h, ['gh', 'codex', 'claude'])
        self.assertIn('enter 9738-B569', asks[0])
        self.assertIn('enter CUNO-5F1GE', asks[1])
        self.assertIn('open https://claude.com/cai/oauth/authorize?code=true&state=abc', asks[2])
        self.assertIn('login-code', asks[2])
        with mock.patch.object(c, 'ssh', return_value=(0, 'Welcome, nothing to read yet')):
            self.assertIsNone(c.relay_logins(self.h, ['codex']))
        with mock.patch.object(c, 'ssh', return_value=(1, '')):
            self.assertIsNone(c.relay_logins(self.h, ['gh']))

    def test_login_code_travels_on_stdin_only(self):
        c = self.m.creds
        code = 'uUpoSecretCode#state'
        with mock.patch.object(c, '_run', return_value=(0, '')) as r:
            self.assertTrue(c.send_login_code(self.h, 'claude', code))
        argv, kw = r.call_args[0][0], r.call_args[1]
        self.assertNotIn(code, ' '.join(argv))
        self.assertEqual(kw['input'], code + '\n')
        with mock.patch.object(c, '_run') as r:
            self.assertFalse(c.send_login_code(self.h, 'claude', 'has space'))
            self.assertFalse(c.send_login_code(self.h, 'unknown-tool', 'x'))
            r.assert_not_called()

    def test_vertex_probe_needs_apply_and_checks_the_answer(self):
        with mock.patch.object(self.m, 'ssh', return_value=(0, 'ok')) as s:
            self.assertEqual(self.m.s_llm_vertex(self.h, False)[0], self.m.WOULD)
            s.assert_not_called()  # a billed call never runs in a dry run
            self.assertEqual(self.m.s_llm_vertex(self.h, True)[0], self.m.OK)
        with mock.patch.object(self.m, 'ssh', return_value=(0, 'Error: permission denied')):
            self.assertEqual(self.m.s_llm_vertex(self.h, True)[0], self.m.FAIL)


class TemplateDriven(unittest.TestCase):
    """A second fleet is a second template: project, network, labels and credentials all follow it."""
    def test_alternate_template(self):
        t = json.loads((Path(os.environ['FLEET_HOST_TEMPLATE'])).read_text())
        t['gcp'].update(project='other-proj', network='other-net', labels={'fleet': 'other'})
        t['credentials']['enabled'] = ['neon', 'logins']
        t['repos'] = [{'repo': 'acme/app', 'dir': 'app'}]
        f = Path(tempfile.mkdtemp()) / 't.json'
        f.write_text(json.dumps(t))
        importlib_ = __import__('importlib')
        try:
            with mock.patch.dict(os.environ, {'FLEET_HOST_TEMPLATE': str(f)}):
                m = load_module(Path(tempfile.mkdtemp()))
                creds = importlib_.reload(m.creds)
                got_steps = [n for n, _ in creds.CRED_STEPS]
                got_revoke = len(creds.REVOKE_STEPS)
        finally:
            importlib_.reload(m.creds)  # back to the shipped template for every later test
        self.assertEqual((m.PROJECT, m.NET, m.LABELS, m.REPOS), ('other-proj', 'other-net', 'fleet=other', ['acme/app:app']))
        self.assertEqual(got_steps, ['neon', 'logins'])
        self.assertEqual(got_revoke, 4)  # revocation always covers every kind

    def test_shipped_template_is_complete(self):
        t = json.loads((Path(os.environ['FLEET_HOST_TEMPLATE'])).read_text())
        for path in (('gcp', 'project'), ('gcp', 'network'), ('tailnet', 'tag'), ('credentials', 'neon', 'project'),
                     ('credentials', 'vercel', 'team'), ('fleet', 'max_live')):
            node = t
            for k in path:
                node = node[k]
            self.assertTrue(node, path)
        self.assertNotIn(t['credentials']['neon']['project'], (t['credentials']['neon']['prod_project'],))

class TemplateEdgeCases(unittest.TestCase):
    """P20 r4: a minimal template works; bad input fails clearly, never deep inside a step."""
    def run_cli(self, template, *argv, home=None):
        import subprocess as sp
        env = {**os.environ, 'FLEET_DIR': tempfile.mkdtemp(), 'FLEET_SSH_CONFIG': os.devnull,
               'FLEET_KNOWN_HOSTS': os.devnull}
        if template is None:
            env.pop('FLEET_HOST_TEMPLATE', None)
            env['HOME'] = home or tempfile.mkdtemp()
        else:
            f = Path(tempfile.mkdtemp()) / 't.json'
            f.write_text(json.dumps(template))
            env['FLEET_HOST_TEMPLATE'] = str(f)
        code = ('import sys; sys.path.insert(0, %r); sys.argv = ["fleet_host.py"] + %r; import fleet_host' % (str(SCRIPTS), list(argv)))
        return sp.run(['python3', '-I', '-c', code], env=env, capture_output=True, text=True)

    def base(self):
        return json.loads(Path(os.environ['FLEET_HOST_TEMPLATE']).read_text())

    def test_logins_only_template_imports(self):
        t = self.base()
        t['credentials'] = {'enabled': ['logins'], 'logins': ['gh']}
        r = self.run_cli(t)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_enabled_provider_without_its_block_fails_clearly(self):
        t = self.base()
        t['credentials'] = {'enabled': ['neon', 'logins'], 'logins': ['gh']}
        r = self.run_cli(t)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('credentials.neon is enabled but missing', r.stderr)

    def test_repo_spec_with_shell_metacharacters_is_refused(self):
        t = self.base()
        t['repos'] = [{'repo': 'acme/app', 'dir': 'app; rm -rf ~'}]
        r = self.run_cli(t)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('plain dir name', r.stderr)

    def test_vertex_values_must_be_plain_names(self):
        t = self.base()
        t.setdefault('llm', {})['vertex'] = {'enabled': True, 'location': 'global', 'gemini_cli': '0.66.0',
                                             'models': ['ok-model', 'bad; rm -rf ~'], 'probe_model': 'ok-model'}
        r = self.run_cli(t)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('llm.vertex.models must be a plain name', r.stderr)
        t['llm']['vertex']['models'] = ['ok-model']
        t['llm']['vertex']['probe_model'] = 'missing'
        r = self.run_cli(t)
        self.assertIn('probe_model must be one of', r.stderr)
        t['llm']['vertex']['enabled'] = False  # a template without Vertex still works
        self.assertEqual(self.run_cli(t).returncode, 0)
        t['llm']['vertex'].update(enabled=True, probe_model='ok-model', gemini_cli='v0.66.0')
        self.assertIn('gemini_cli must be a plain version', self.run_cli(t).stderr)  # startup.sh would skip it
        t['llm']['vertex'].update(gemini_cli='0.66.0', location='US-Central1')
        self.assertIn('location must be lowercase', self.run_cli(t).stderr)

    def test_help_needs_no_template(self):
        r = self.run_cli(None, '--help')
        self.assertEqual(r.returncode, 0, r.stderr)

if __name__ == '__main__':
    unittest.main()

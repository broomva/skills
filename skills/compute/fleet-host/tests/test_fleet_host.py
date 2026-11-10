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
    spec = importlib.util.spec_from_file_location('fleet_host', SCRIPTS / 'fleet_host.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
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
        self.h._reachable = False
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

if __name__ == '__main__':
    unittest.main()

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.environ.get('PM_IMPL_DIR', str(Path(__file__).resolve().parents[1] / 'scripts')))
import pm_antigravity as ag


def usage(gemini=95, third=95, age=0, status='ok'):
    return {'email': 'a', 'status': status, 'numbersAt': time.time() - age,
            'checkedAt': time.time(), 'windows': [
                {'family': 'gemini', 'usedPercent': gemini},
                {'family': 'third_party', 'usedPercent': third}]}


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, PROVIDER_MANAGER_ANTIGRAVITY_ROOT=self.temp.name)
        self.env.start()
        self.addCleanup(self.env.stop)
        runtime = patch.object(ag, 'runtime_fingerprint', return_value=('binary', 'harness'))
        runtime.start()
        self.addCleanup(runtime.stop)
        enabled = patch.object(ag, 'automatic_enabled', return_value=True)
        enabled.start()
        self.addCleanup(enabled.stop)
        validation = patch.object(ag, 'validate_profile')
        validation.start()
        self.addCleanup(validation.stop)
        self.profiles = {}
        with ag.registry() as state:
            for email, used in [('a', usage()), ('b', usage(10, 10))]:
                profile = Path(self.temp.name) / email
                (profile / 'antigravity-acp').mkdir(parents=True)
                (profile / 'antigravity-acp/acp_token.json').write_text('{}')
                state['accounts'][email] = {'profile': str(profile), 'binary': '/bin/true',
                    'fingerprint': ag.fingerprint(profile), 'runtimeFingerprint': ['binary', 'harness'], 'usage': used}
                self.profiles[email] = profile
            state['selected'] = dict.fromkeys(['all', 'gemini', 'third_party'], 'a')

    def test_new_threads_balance_and_resume_keeps_original_account(self):
        with ag.registry() as state:
            state['accounts']['a']['usage'] = usage(50, 50)
        self.assertEqual(ag.pin_session('original', 'gemini')['email'], 'a')
        with ag.registry() as state:
            state['accounts']['a']['usage'] = usage()
        self.assertEqual(ag.pin_session('new', 'gemini')['email'], 'b')
        self.assertEqual(ag.pin_session('original', 'gemini')['email'], 'a')
        self.assertEqual(ag.pin_session('new', 'gemini')['email'], 'b')

    def test_existing_unknown_thread_refuses_new_selection(self):
        with self.assertRaises(ag.AntigravityError):
            ag.pin_session('preexisting', require_existing=True)

    def test_changed_grant_refuses_resume(self):
        ag.pin_session('pinned')
        (self.profiles['b'] / 'antigravity-acp/acp_token.json').write_text('{"refresh_token":"changed"}')
        with self.assertRaises(ag.AntigravityError):
            ag.pin_session('pinned')

    def test_unknown_stale_disabled_and_nonfinite_never_candidates(self):
        for bad in [usage(None), usage(age=1900), usage(status='unavailable'), usage(float('nan')),
                    usage(True)]:
            self.assertIsNone(ag.utilization({'usage': bad}, 'gemini', time.time()))
        bad = usage(1, 1)
        bad['windows'][0]['disabled'] = True
        self.assertIsNone(ag.utilization({'usage': bad}, 'gemini', time.time()))

    def test_unreadable_active_is_not_exhausted(self):
        with ag.registry() as state:
            state['accounts']['a']['usage'] = usage(status='throttled')
        self.assertEqual(ag.balance()['reason'], 'active_telemetry_unknown')

    def test_family_limits_are_independent_and_unknown_requires_both(self):
        with ag.registry() as state:
            state['accounts']['b']['usage'] = usage(10, None)
        self.assertEqual(ag.balance(model='gemini')['action'], 'switched')
        self.assertEqual(ag.balance(model='claude')['reason'], 'no_healthy_standby')
        self.assertEqual(ag.balance()['reason'], 'no_healthy_standby')

    def test_cooldown_and_dry_run_preserve_selection(self):
        self.assertEqual(ag.balance(dry_run=True)['action'], 'would_switch')
        with ag.registry() as state:
            self.assertEqual(state['selected']['all'], 'a')
            state['lastSwitch']['all'] = time.time()
        self.assertEqual(ag.balance()['reason'], 'cooldown')

    def test_corrupt_registry_fails_closed(self):
        (Path(self.temp.name) / 'registry.json').write_text('broken')
        with self.assertRaises(ag.AntigravityError):
            ag.pin_session('x')

    def test_fallback_third_party_and_disabled_inapplicable_bucket(self):
        reading = usage(5, 10)
        reading['windows'][1]['family'] = 'claude'
        self.assertEqual(ag.utilization({'usage': reading}, 'third_party', time.time()), 10)
        reading['windows'].append({'family': 'gemini', 'usedPercent': None, 'disabled': True})
        self.assertEqual(ag.utilization({'usage': reading}, 'gemini', time.time()), 5)

    def test_automatic_disabled_preserves_selection(self):
        with patch.object(ag, 'automatic_enabled', return_value=False):
            self.assertEqual(ag.balance(automatic=True)['action'], 'would_switch')
            self.assertEqual(ag.pin_session('observe')['email'], 'a')

    def test_token_format_changes_do_not_change_grant_identity(self):
        before = ag.fingerprint(self.profiles['a'])
        (self.profiles['a'] / 'antigravity-acp/acp_token.json').write_text('{"scopes": []}')
        self.assertEqual(ag.fingerprint(self.profiles['a']), before)

    def test_invalid_profile_does_not_publish_pin(self):
        with patch.object(ag, 'validate_profile', side_effect=ag.AntigravityError('invalid')):
            with self.assertRaises(ag.AntigravityError):
                ag.pin_session('invalid')
        with ag.registry() as state:
            self.assertNotIn('invalid', state['pins'])

    def test_registration_rejects_unverified_runtime_before_touching_grant(self):
        with patch.object(ag.pm_antigravity_quota, 'probe') as probe:
            with self.assertRaisesRegex(ag.AntigravityError, 'no verified'):
                ag.register('new', self.profiles['a'], '/usr/bin/true')
            probe.assert_not_called()
        with ag.registry() as state:
            self.assertNotIn('new', state['accounts'])

    def test_runtime_upgrade_cannot_move_an_existing_session(self):
        ag.pin_session('old-runtime')
        with patch.object(ag, 'runtime_fingerprint', return_value=('upgraded', 'harness')):
            with self.assertRaisesRegex(ag.AntigravityError, 'runtime changed'):
                ag.pin_session('old-runtime')

    def test_private_registry_mode(self):
        self.assertEqual((Path(self.temp.name) / 'registry.json').stat().st_mode & 0o777, 0o600)


class RuntimeHashTests(unittest.TestCase):
    def test_binary_and_harness_content_are_both_bound(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'agy'
            binary.write_bytes(b'vendor')
            harness = Path(directory) / 'localharness_external'
            harness.write_bytes(b'harness')
            expected = tuple(hashlib.sha256(value).hexdigest() for value in (b'vendor', b'harness'))
            self.assertEqual(ag.runtime_fingerprint(binary), expected)
            harness.write_bytes(b'upgraded')
            self.assertNotEqual(ag.runtime_fingerprint(binary), expected)


if __name__ == '__main__':
    unittest.main()

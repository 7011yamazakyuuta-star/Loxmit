import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from document_worker import worker_environment
from security_status import SecurityStatus, check_linux, check_mac, crypt_covered, windows_state


class SecurityStatusTests(unittest.TestCase):
    def test_windows_requires_both_complete_encryption_and_active_protection(self):
        good = dict(protection_code=0, conversion_code=0, protection=1, conversion=1)
        self.assertEqual(windows_state(good), 'protected')
        for changed in (dict(conversion=2), dict(conversion=3), dict(conversion=4),
                        dict(conversion=5), dict(protection=2), dict(protection_code=5),
                        dict(conversion_code=5)):
            self.assertEqual(windows_state(dict(good, **changed)), 'unknown')
        self.assertEqual(windows_state(dict(good, protection=0)), 'unprotected')
        self.assertEqual(windows_state({}), 'unknown')

    def test_linux_requires_every_storage_branch_covered(self):
        disk = {'type': 'disk'}
        crypt = {'type': 'crypt', 'children': [disk]}
        self.assertTrue(crypt_covered({'type': 'lvm', 'children': [crypt]}))
        self.assertFalse(crypt_covered({'type': 'lvm', 'children': [crypt, disk]}))
        self.assertFalse(crypt_covered(disk))
        self.assertFalse(crypt_covered({}))

    def test_linux_unknown_mounts_are_not_assumed_protected(self):
        for filesystem in ('overlay', 'btrfs', 'nfs', 'zfs'):
            with patch('security_status.run_probe', return_value=json.dumps({'filesystems': [
                    {'fstype': filesystem, 'source': '/dev/mapper/test'}]}).encode()) as query:
                self.assertEqual(check_linux(Path('.')), 'unknown')
                self.assertEqual(query.call_count, 1)
        with patch('security_status.run_probe', side_effect=[
                b'{"filesystems":[{"fstype":"ext4","source":"/dev/mapper/test"}]}',
                b'{"blockdevices":[{"type":"crypt"}]}']):
            self.assertEqual(check_linux(Path('.')), 'protected')

    def test_mac_does_not_apply_startup_status_to_external_volume(self):
        with patch('security_status.Path.is_dir', return_value=False), patch('security_status.run_probe') as query:
            self.assertEqual(check_mac(Path('.')), 'unknown')
            query.assert_not_called()
        with patch('security_status.Path.is_dir', return_value=True), patch('security_status.Path.stat') as stat:
            stat.return_value.st_dev = 1
            for raw, expected in [(b'FileVault is On.\n', 'protected'), (b'FileVault is Off.\n', 'unprotected'),
                                  (b'Encryption in progress: 50%', 'unknown')]:
                with patch('security_status.run_probe', return_value=raw):
                    self.assertEqual(check_mac(Path('.')), expected)

    def test_probes_are_explicit_cached_and_fail_unknown_without_private_errors(self):
        status = SecurityStatus('.')
        with patch('security_status.sys.platform', 'win32'), patch('security_status.check_windows', side_effect=OSError('private-path')) as query:
            self.assertEqual(status.snapshot()['storage']['state'], 'unchecked')
            query.assert_not_called()
            self.assertEqual(status.check()['storage']['state'], 'unknown')
            self.assertEqual(status.check()['storage']['state'], 'unknown')
            self.assertEqual(query.call_count, 1)
            self.assertNotIn('private-path', json.dumps(status.snapshot()))
        with status.lock, self.assertRaises(ValueError):
            status.check()

    def test_worker_inheritance_excludes_secrets_and_loader_hooks(self):
        source = {'TOKEN': 'private', 'AWS_SECRET_ACCESS_KEY': 'private', 'GITHUB_TOKEN': 'private',
                  'HTTP_PROXY': 'private', 'PYTHONPATH': 'unsafe', 'PYTHONSTARTUP': 'unsafe',
                  'LD_PRELOAD': 'unsafe', 'DYLD_INSERT_LIBRARIES': 'unsafe', 'PATH': 'unsafe',
                  'HOME': 'private', 'SYSTEMROOT': os.environ.get('SystemRoot', 'system'),
                  '_PYI_ARCHIVE_FILE': 'runtime', '_PYI_PARENT_PROCESS_LEVEL': '1'}
        with patch.dict(os.environ, source), tempfile.TemporaryDirectory() as work:
            env = worker_environment(work)
            self.assertNotIn('private', env.values())
            self.assertNotIn('unsafe', env.values())
            self.assertEqual(env['HOME'], work)
            self.assertEqual(env['TMPDIR'], work)
            self.assertEqual(env['_PYI_ARCHIVE_FILE'], 'runtime')

    def test_read_only_command_timeout_and_nonzero_exit(self):
        from security_status import run_probe
        with patch('security_status.subprocess.run', side_effect=subprocess.TimeoutExpired('probe', 12)):
            with self.assertRaises(subprocess.TimeoutExpired):
                run_probe(['synthetic'])

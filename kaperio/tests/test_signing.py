import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.signing import add_arguments, notarize, sign_engine_files, sign_windows, validate_options


def options(*values):
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    return parser.parse_args(values)


class SigningTests(unittest.TestCase):
    def test_disabled_by_default_and_platform_and_identity_validated(self):
        for platform in ('win32', 'linux', 'darwin'):
            validate_options(options(), platform)
        for args, platform in [(options('--notary-profile', 'profile'), 'darwin'),
                               (options('--macos-identity', '-', '--macos-team-id', 'ABCDEFGHIJ'), 'darwin'),
                               (options('--windows-certificate', 'bad'), 'win32'),
                               (options('--windows-certificate', 'a'*40, '--timestamp-url', 'https://user:secret@example.test'), 'win32'),
                               (options('--windows-certificate', 'a'*40, '--timestamp-url', 'https://example.test'), 'linux')]:
            with self.assertRaises(ValueError):
                validate_options(args, platform)

    def test_windows_signs_sha256_and_verifies_with_timestamp_no_key_password(self):
        args = options('--windows-certificate', 'a'*40, '--timestamp-url', 'https://example.test')
        with patch('scripts.signing.shutil.which', return_value='signtool'), patch('scripts.signing.run') as run:
            evidence = sign_windows(Path('bundle'), args)
        calls = [c.args[0] for c in run.call_args_list]
        self.assertIn('/fd', calls[0]); self.assertIn('SHA256', calls[0]); self.assertNotIn('/p', calls[0])
        self.assertEqual(calls[1][1:5], ['verify', '/pa', '/all', '/tw'])
        self.assertTrue(evidence['developer_signed'])
        self.assertEqual(evidence['signature_scope'], 'Loxmit.exe')

    def test_windows_verification_failure_is_not_success(self):
        args = options('--windows-certificate', 'a'*40, '--timestamp-url', 'https://example.test')
        with patch('scripts.signing.shutil.which', return_value='signtool'), patch('scripts.signing.run', side_effect=[None, subprocess.CalledProcessError(2, 'verify')]):
            with self.assertRaises(subprocess.CalledProcessError):
                sign_windows(Path('bundle'), args)

    def test_native_engine_signed_before_archive_and_non_code_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            binary, notice = Path(directory)/'hashcat', Path(directory)/'license.txt'
            binary.write_bytes(b'\xcf\xfa\xed\xfe' + b'fixture')
            notice.write_text('upstream notice')
            with patch('scripts.signing.run') as run:
                self.assertEqual(sign_engine_files([binary, notice], 'identity', 'ABCDEFGHIJ'), 1)
            self.assertEqual(run.call_count, 2)
            self.assertIn('--timestamp', run.call_args_list[0].args[0])
            self.assertIn('--test-requirement', run.call_args_list[1].args[0])
            self.assertEqual(notice.read_text(), 'upstream notice')

    def test_notarization_rejects_nonaccepted_response_before_stapling(self):
        for status in ('Invalid', 'In Progress', None):
            with patch('scripts.signing.run', return_value=SimpleNamespace(stdout=json.dumps({'status':status}).encode())) as run:
                with self.assertRaises(ValueError):
                    notarize(Path('app'), Path('archive'), 'profile', 'ABCDEFGHIJ')
                self.assertEqual(run.call_count, 1)

    def test_notarization_requires_stapling_signature_and_gatekeeper_checks(self):
        accepted = SimpleNamespace(stdout=b'{"status":"Accepted","id":"synthetic-id"}')
        with patch('scripts.signing.run', return_value=accepted) as run:
            result = notarize(Path('app'), Path('archive'), 'profile', 'ABCDEFGHIJ')
        self.assertTrue(result['notarized'])
        commands = [c.args[0] for c in run.call_args_list]
        self.assertEqual(len(commands), 5)
        self.assertIn('--keychain-profile', commands[0])
        self.assertEqual(commands[1][1:3], ['stapler', 'staple'])
        self.assertEqual(commands[2][1:3], ['stapler', 'validate'])
        self.assertIn('--assess', commands[4])

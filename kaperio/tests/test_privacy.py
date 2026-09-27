import io
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from document_worker import DocumentWorker, check_workspace
from recovery import read_password_result, run_stage, validate_plan


class PrivacyTests(unittest.TestCase):
    def test_nested_workspace_size_and_entry_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / 'helper'
            nested.mkdir()
            (nested / 'one').write_bytes(b'1' * 20)
            (nested / 'two').write_bytes(b'2' * 20)
            check_workspace(root, limit=40, max_entries=3)
            with self.assertRaisesRegex(ValueError, 'size limit'):
                check_workspace(root, limit=39)
            with self.assertRaisesRegex(ValueError, 'file count'):
                check_workspace(root, max_entries=2)

    def test_result_is_bounded_and_errors_do_not_echo_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'found.hex'
            self.assertIsNone(read_password_result(path))
            for raw, expected in ((b'', None), (b'\n', b''), (b'546573743432\n', b'Test42')):
                path.write_bytes(raw)
                self.assertEqual(read_password_result(path), expected)
            for raw in (b'private-not-hex', b'\xff', b'0' * 65537):
                path.write_bytes(raw)
                with self.assertRaises(ValueError) as caught:
                    read_password_result(path)
                self.assertNotIn('private', str(caught.exception))

    def test_result_removed_on_success_invalid_data_and_process_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            found = folder / 'found.hex'
            plan = validate_plan({'min': 4, 'max': 4})
            for mode in ('success', 'invalid', 'timeout', 'spawn_error'):
                with self.subTest(mode=mode):
                    def start(*args, **kwargs):
                        found.write_bytes(b'546573743432\n' if mode != 'invalid' else b'private-not-hex')
                        if mode == 'spawn_error':
                            raise OSError('synthetic spawn failure')
                        process = Mock(stdout=io.BytesIO())
                        process.poll.return_value = 0
                        process.wait.side_effect = subprocess.TimeoutExpired('synthetic', 15) if mode == 'timeout' else None
                        process.wait.return_value = 0
                        return process
                    with patch('recovery.subprocess.Popen', side_effect=start):
                        if mode == 'success':
                            result = run_stage(folder / 'hashcat', folder, 10400, plan, threading.Event(), lambda **_: None)
                            self.assertEqual(result['password'], b'Test42')
                        else:
                            with self.assertRaises((OSError, ValueError, subprocess.TimeoutExpired)):
                                run_stage(folder / 'hashcat', folder, 10400, plan, threading.Event(), lambda **_: None)
                    self.assertFalse(found.exists())

    def test_worker_temp_files_and_relative_outputs_stay_private(self):
        import sys
        fixture = Path(__file__).with_name('worker_fixture.py')
        with tempfile.TemporaryDirectory() as directory:
            worker = DocumentWorker(directory)
            try:
                with patch('document_worker.worker_command', return_value=[sys.executable, str(fixture), 'private_temp']), patch.dict(os.environ, {'LOXMIT_TEST_PRIVATE_TOKEN': 'synthetic-secret'}):
                    result = worker.run('inspect', {'source': 'unused'})
                self.assertTrue(result['private'])
                self.assertFalse(list(Path(directory).iterdir()))
            finally:
                worker.close()

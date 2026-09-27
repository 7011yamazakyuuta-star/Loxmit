import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app import Library
from gpu_check import engine_identity, run_compute, synthetic_input

DEVICE = {'id': 1, 'name': 'Synthetic GPU', 'backend': 'OpenCL', 'type': 'GPU'}


class GPUCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / 'hashcat.exe'
        self.engine.write_bytes(b'not an executable')

    def test_fixture_is_generated_locally_and_contains_known_candidate(self):
        expected = synthetic_input(self.root)
        self.assertIn(bytes.fromhex(expected).decode(), (self.root / 'test.words').read_text())
        self.assertTrue((self.root / 'test.hash').read_text().startswith('$pdf$1*2*40*'))
        self.assertEqual((self.root / 'test.hash').read_text().split('*')[5], '16')

    def fake_process(self, behavior):
        popen = subprocess.Popen
        def spawn(command, **kwargs):
            self.command = command
            if behavior in ('pass', 'wrong'):
                words = Path(command[6]).read_text().splitlines()
                expected = (words[-1] if behavior == 'pass' else 'wrong').encode().hex()
                Path(command[-1]).write_text(expected + '\n')
            code = 'import time; time.sleep(60)' if behavior == 'hang' else 'pass'
            kwargs['env'] = None
            return popen([sys.executable, '-c', code], **kwargs)
        return spawn

    def test_result_must_match_and_test_data_is_always_removed(self):
        for behavior, state in [('pass', 'passed'), ('wrong', 'error'), ('empty', 'error')]:
            with patch('gpu_check.subprocess.Popen', side_effect=self.fake_process(behavior)):
                result = run_compute(self.engine, self.root, DEVICE, threading.Event())
            self.assertEqual(result['state'], state)
            self.assertEqual(result['compute_tested'], state == 'passed')
            self.assertIn('--hwmon-temp-abort=75', self.command)
            self.assertIn('--potfile-disable', self.command)
            self.assertNotIn('--force', self.command)
            self.assertNotIn('--self-test-disable', self.command)
            self.assertFalse(list(self.root.glob('.gpucheck-*')))

    def test_timeout_cancel_and_spawn_failure_clean_up(self):
        with patch('gpu_check.subprocess.Popen', side_effect=self.fake_process('hang')):
            result = run_compute(self.engine, self.root, DEVICE, threading.Event(), timeout=.1)
        self.assertEqual(result['state'], 'timeout')
        stop = threading.Event()
        stop.set()
        self.assertEqual(run_compute(self.engine, self.root, DEVICE, stop)['state'], 'cancelled')
        with patch('gpu_check.subprocess.Popen', side_effect=OSError('synthetic')):
            self.assertEqual(run_compute(self.engine, self.root, DEVICE, threading.Event())['state'], 'error')
        self.assertFalse(list(self.root.glob('.gpucheck-*')))

    def test_consent_gpu_identity_busy_and_cancellation(self):
        library = Library(self.root / 'library')
        self.addCleanup(library.close)
        library.hashcat = self.engine
        setup = library.setup
        setup.report = {'backend': {'status': 'recognized', 'devices': [DEVICE]}, 'hardware': {'devices': []}}
        setup.diagnosed_identity = engine_identity(self.engine)
        for request in ({}, {'consent': False, 'device': 1}, {'consent': True, 'device': True},
                        {'consent': True, 'device': 2}, {'consent': True, 'device': 1, 'path': 'user.pdf'}):
            with self.assertRaises(ValueError):
                setup.start_compute(request)
        def run(engine, root, device, stop):
            stop.wait(5)
            return {'state': 'cancelled', 'compute_tested': False}
        with patch('environment_setup.run_compute', side_effect=run):
            setup.start_compute({'consent': True, 'device': 1})
            self.assertTrue(library.settings_snapshot()['settings_locked'])
            with self.assertRaises(ValueError):
                setup.diagnose()
            with self.assertRaises(ValueError):
                library.save_settings({'hashcat': ''})
            setup.cancel_compute()
            setup.compute_thread.join(5)
        self.assertFalse(setup.busy)
        self.assertEqual(setup.compute['state'], 'cancelled')
        self.engine.write_bytes(b'changed executable')
        with self.assertRaises(ValueError):
            setup.start_compute({'consent': True, 'device': 1})


if __name__ == '__main__':
    unittest.main()

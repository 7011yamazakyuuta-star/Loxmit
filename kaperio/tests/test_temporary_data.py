import errno
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import Library
from temporary_data import MARKER, atomic_json, cleanup_stale, identity, private_workspace


class TemporaryDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def abandoned(self, purpose='document'):
        process = subprocess.Popen([sys.executable, '-c',
            'from pathlib import Path; import sys,time; from temporary_data import private_workspace; '
            'ctx=private_workspace(Path(sys.argv[1]),sys.argv[2]); p=ctx.__enter__(); '
            '(p/"output.bin").write_bytes(b"synthetic"*1024); print(p.name,flush=True); time.sleep(60)',
            str(self.root), purpose], stdout=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            name = process.stdout.readline().strip()
            self.assertTrue(name.startswith('.' + purpose + '-'))
        finally:
            process.kill()
            process.wait(timeout=5)
            process.stdout.close()
        return self.root / name

    def test_hard_kill_cleanup_preserves_documents_and_checkpoints(self):
        job = self.root / ('a' * 32)
        job.mkdir()
        for name in ('source.pdf', 'unlocked.pdf', 'execution.json', 'hashcat.restore', 'candidates.txt'):
            (job / name).write_bytes(b'preserve')
        (self.root / '.document-legacy').mkdir()
        self.abandoned()
        self.abandoned('upload')
        result = cleanup_stale(self.root)
        self.assertEqual(result['removed'], 2)
        self.assertGreater(result['bytes'], 16000)
        self.assertEqual(len(list(job.iterdir())), 5)
        self.assertTrue((self.root / '.document-legacy').exists())
        self.assertEqual(cleanup_stale(self.root)['removed'], 0)

    def test_live_owner_or_child_protects_related_uploads(self):
        stale = self.abandoned('upload')
        with private_workspace(self.root, 'document'):
            self.assertEqual(cleanup_stale(self.root)['removed'], 0)
            self.assertTrue(stale.exists())
        path = self.abandoned()
        marker = json.loads((path / MARKER).read_text())
        marker['children'] = [identity(os.getpid())]
        atomic_json(path / MARKER, marker)
        self.assertEqual(cleanup_stale(self.root)['removed'], 0)
        self.assertTrue(stale.exists())

    def test_unconfirmed_spawn_or_tampered_marker_is_not_deleted(self):
        path = self.abandoned()
        marker = json.loads((path / MARKER).read_text())
        marker['spawn_pending'] = True
        atomic_json(path / MARKER, marker)
        self.assertEqual(cleanup_stale(self.root)['skipped'], 1)
        marker.update(spawn_pending=False, name='../outside')
        atomic_json(path / MARKER, marker)
        self.assertEqual(cleanup_stale(self.root)['removed'], 0)
        self.assertTrue(path.exists())

    def test_link_and_permission_failure_are_nonfatal(self):
        path = self.abandoned()
        with patch('temporary_data.safe_tree', side_effect=PermissionError()):
            self.assertEqual(cleanup_stale(self.root)['skipped'], 1)
        target = self.root / 'precious.txt'
        target.write_text('preserve')
        try:
            (path / 'link').symlink_to(target)
        except OSError:
            self.skipTest('Symlink privilege unavailable')
        self.assertEqual(cleanup_stale(self.root)['removed'], 0)
        self.assertEqual(target.read_text(), 'preserve')

    def test_temporary_data_removed_after_success_and_exception(self):
        with private_workspace(self.root, 'gpucheck') as path:
            (path / 'fixture').write_bytes(b'x')
        self.assertFalse(path.exists())
        with self.assertRaises(RuntimeError):
            with private_workspace(self.root, 'upload') as path:
                raise RuntimeError('synthetic')
        self.assertFalse(path.exists())

    def test_disk_full_preserves_last_committed_json(self):
        path = self.root / 'job.json'
        atomic_json(path, {'state': 'paused'})
        with patch('temporary_data.os.fsync', side_effect=OSError(errno.ENOSPC, 'synthetic disk full')):
            with self.assertRaises(OSError):
                atomic_json(path, {'state': 'recovering'})
        self.assertEqual(json.loads(path.read_text()), {'state': 'paused'})
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_large_validation_defaults_to_disposable_fixtures(self):
        import large_documents
        generated = []
        def prepare(path):
            generated.append(path)
            (path / 'large-synthetic.pdf').write_bytes(b'synthetic')
            return []
        arguments = ['large_documents.py', '--executable', 'not-run.exe', '--report', str(self.root / 'report.json')]
        with patch.object(sys, 'argv', arguments), patch.object(large_documents, 'prepare', side_effect=prepare):
            with patch.object(large_documents, 'run_suite') as suite:
                large_documents.main()
                self.assertFalse(generated[-1].exists())
                suite.assert_called_once()
            with patch.object(large_documents, 'run_suite', side_effect=RuntimeError('synthetic failure')):
                with self.assertRaises(RuntimeError):
                    large_documents.main()
                self.assertFalse(generated[-1].exists())

    def test_interrupted_job_is_persisted_once_without_discarding_plan(self):
        jid = 'b' * 32
        folder = self.root / jid
        folder.mkdir()
        atomic_json(folder / 'job.json', {'id': jid, 'state': 'recovering', 'plan': {'strategy': 'hints'},
                                        'elapsed': 4, 'activity_started': 10, 'updated': 15})
        (folder / 'execution.json').write_text('checkpoint')
        library = Library(self.root)
        try:
            self.assertEqual(library.startup['interrupted'], 1)
            job = json.loads((folder / 'job.json').read_text())
            self.assertEqual(job['state'], 'paused')
            self.assertEqual(job['elapsed'], 9)
            self.assertEqual(job['plan'], {'strategy': 'hints'})
            self.assertEqual((folder / 'execution.json').read_text(), 'checkpoint')
        finally:
            library.close()
        library = Library(self.root)
        try:
            self.assertEqual(library.startup['interrupted'], 0)
        finally:
            library.close()


if __name__ == '__main__':
    unittest.main()

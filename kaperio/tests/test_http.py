import http.client
import json
import socket
import tempfile
import threading
import unittest
from types import SimpleNamespace
from pathlib import Path
from local_server import LocalHTTPServer
from unittest.mock import patch

from app import Handler, Library, MAX_UPLOAD, MAX_UPLOAD_MB


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.library=Library(self.tmp.name)
        self.server=LocalHTTPServer(('127.0.0.1',0),Handler)
        self.server.library=self.library
        self.server.token='test-capability'
        self.server.tls=False
        self.server.authority=f'127.0.0.1:{self.server.server_port}'
        self.server.origin='http://'+self.server.authority
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.library.close();self.tmp.cleanup()

    def request(self,method,path,body=None,headers=None):
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        client.request(method,path,body=body,headers=headers or {})
        response=client.getresponse();data=response.read();status=response.status;client.close()
        return status,data

    def test_authentication_origin_and_paths(self):
        self.assertEqual(self.request('GET','/api/jobs')[0],403)
        self.assertEqual(self.request('GET','/launch?token=wrong')[0],403)
        self.assertEqual(self.request('GET','/launch?token=test-capability')[0],303)
        headers={'Cookie':'kaperio_session=test-capability'}
        self.assertEqual(self.request('GET','/api/jobs',headers=headers)[0],200)
        status, license_text = self.request('GET','/api/licenses',headers=headers)
        self.assertEqual(status,200)
        self.assertIn(b'Copyright (c) 2026 Lucide',license_text)
        self.assertIn(b'MIT License',license_text)
        self.assertEqual(self.request('GET','/../app.py',headers=headers)[0],404)
        self.assertEqual(self.request('POST','/api/settings','{}',headers)[0],403)
        headers.update({'X-Kaperio':'1','Origin':'https://other.example'})
        self.assertEqual(self.request('POST','/api/settings','{}',headers)[0],403)
        headers.pop('Origin');headers['Host']='other.example'
        self.assertEqual(self.request('GET','/api/jobs',headers=headers)[0],403)

    def test_invalid_import(self):
        headers={'Cookie':'kaperio_session=test-capability','X-Kaperio':'1','X-Filename':'test.pdf'}
        self.assertEqual(self.request('POST','/api/import',b'not a pdf',headers)[0],400)
        self.assertEqual(self.library.snapshot(),[])

    def test_security_checks_require_auth_origin_and_do_not_run_on_read(self):
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1'}
        with patch.object(self.library.security, 'check', return_value={'storage': {'state': 'unknown'}}) as check:
            self.assertEqual(self.request('GET', '/api/security')[0], 403)
            self.assertEqual(self.request('POST', '/api/security/check', '{}')[0], 403)
            status, raw = self.request('GET', '/api/security', headers=headers)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)['storage']['state'], 'unchecked')
            check.assert_not_called()
            self.assertEqual(self.request('POST', '/api/security/check', '{}', dict(headers, Origin='https://other.example'))[0], 403)
            check.assert_not_called()
            self.assertEqual(self.request('POST', '/api/security/check', '{}', headers)[0], 200)
            self.assertEqual(check.call_count, 1)

    def test_import_limit_accepts_old_limit_plus_one_and_exactly_200mb(self):
        self.assertEqual(MAX_UPLOAD, 200 * 1024 * 1024)
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1', 'X-Filename': 'limit.pdf'}
        for size in (100 * 1024 * 1024 + 1, MAX_UPLOAD):
            with self.subTest(size=size), tempfile.TemporaryFile() as source:
                source.truncate(size)
                source.seek(0)
                def inspect(path, extension, _):
                    self.assertEqual(extension, '.pdf')
                    self.assertEqual(path.stat().st_size, size)
                    return {'format': 'pdf', 'extension': '.pdf', 'empty_password': False}
                # Only parsing is stubbed; HTTP transfer, disk staging and hashing are real.
                with patch.object(self.library.documents, 'inspect_file', side_effect=inspect) as inspector, patch.object(self.library, 'import_pdf', side_effect=AssertionError('HTTP must stream')):
                    status, body = self.request('POST', '/api/import', source, dict(headers, **{'Content-Length': str(size)}))
                    self.assertEqual(status, 200)
                    job_id = json.loads(body)['id']
                    self.assertEqual(self.library.jobs[job_id]['size'], size)
                    inspector.assert_called_once()
                    self.library.remove(job_id)
        self.assertEqual(self.library.snapshot(), [])

    def test_oversized_upload_rejected_before_reading_body(self):
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1'}
        for route, size, message in (('/api/import', MAX_UPLOAD + 1, '200MB'),
                                     ('/api/settings', 16 * 1024 * 1024 + 1, '16MB')):
            with self.subTest(route=route), patch.object(self.library, 'import_stream') as importer:
                status, body = self.request('POST', route, headers=dict(headers, **{'Content-Length': str(size)}))
                self.assertEqual(status, 413)
                self.assertIn(message, json.loads(body)['error'])
                importer.assert_not_called()

    def test_interrupted_and_stalled_uploads_leave_no_partial_files(self):
        for stalled in (False, True):
            with self.subTest(stalled=stalled), patch('app.UPLOAD_TIMEOUT', .2):
                client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
                try:
                    client.request('POST', '/api/import', b'cut', {
                        'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1',
                        'X-Filename': 'cut.pdf', 'Content-Length': '100'})
                    if not stalled:
                        client.sock.shutdown(socket.SHUT_WR)
                    response = client.getresponse()
                    self.assertEqual(response.status, 408 if stalled else 400)
                    response.read()
                finally:
                    client.close()
                self.assertEqual(self.library.snapshot(), [])
                self.assertFalse(list(Path(self.tmp.name).glob('.upload-*')))
                self.assertFalse(self.library.import_lock.locked())

    def test_import_disk_space_busy_and_framing_guards(self):
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1',
                   'X-Filename': 'test.pdf', 'Content-Length': '100'}
        with patch('app.shutil.disk_usage', return_value=SimpleNamespace(free=0)):
            self.assertEqual(self.request('POST', '/api/import', headers=headers)[0], 507)
        with self.library.import_lock:
            self.assertEqual(self.request('POST', '/api/import', headers=headers)[0], 409)
            self.assertEqual(self.request('GET', '/api/jobs', headers=headers)[0], 200)
        invalid = dict(headers, **{'Transfer-Encoding': 'chunked'})
        self.assertEqual(self.request('POST', '/api/import', headers=invalid)[0], 400)
        self.assertFalse(list(Path(self.tmp.name).glob('.upload-*')))
        self.assertEqual(self.library.snapshot(), [])

    def test_upload_limit_matches_browser_and_label(self):
        headers = {'Cookie': 'loxmit_session=test-capability'}
        script = self.request('GET', '/app.js', headers=headers)[1].decode('utf-8')
        page = self.request('GET', '/', headers=headers)[1].decode('utf-8')
        self.assertIn(f'const MAX_UPLOAD_MB = {MAX_UPLOAD_MB};', script)
        self.assertIn('file.size>MAX_UPLOAD_MB*1024*1024', script)
        self.assertIn(f'最大{MAX_UPLOAD_MB}MB', page)

    def test_loxmit_brand_and_authentication(self):
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1'}
        self.assertEqual(self.request('GET', '/api/jobs', headers=headers)[0], 200)
        self.assertEqual(self.request('POST', '/api/settings', '{}', headers)[0], 200)
        for asset in ('/', '/app.js', '/icon-64.png', '/favicon.ico'):
            status, body = self.request('GET', asset, headers=headers)
            self.assertEqual(status, 200, asset)
            self.assertGreater(len(body), 100)
        self.assertIn(b'Loxmit', self.request('GET', '/', headers=headers)[1])
        headers['Origin'] = 'https://other.example'
        self.assertEqual(self.request('POST', '/api/settings', '{}', headers)[0], 403)

    def test_guided_estimate_requires_auth_and_does_not_store_hints(self):
        data = json.dumps({'strategy': 'guided', 'words': 'PrivateHint', 'numbers': '2024'})
        self.assertEqual(self.request('POST', '/api/recovery/estimate', data)[0], 403)
        headers = {'Cookie': 'kaperio_session=test-capability', 'X-Kaperio': '1'}
        status, body = self.request('POST', '/api/recovery/estimate', data, headers)
        self.assertEqual(status, 200)
        self.assertNotIn(b'PrivateHint', body)
        self.assertGreater(int(json.loads(body)['candidates']), 1)
        self.assertFalse(list(Path(self.tmp.name).glob('**/candidates.hex')))

    def test_external_settings_without_hashcat(self):
        headers={'Cookie':'kaperio_session=test-capability','X-Kaperio':'1'}
        self.assertEqual(self.request('POST','/api/settings',json.dumps({'hashcat':'','zip2john':''}),headers)[0],200)
        self.assertIsNone(self.library.hashcat)
        self.assertIsNone(self.library.zip2john)
        self.assertEqual(self.request('POST','/api/settings',json.dumps({'zip2john':'not-existing.exe'}),headers)[0],400)

    def test_automatic_estimate_is_private_and_does_not_start_recovery(self):
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1'}
        data = json.dumps({'strategy': 'automatic', 'words': 'PrivateMemory', 'prefix': 'PrivateStart'})
        status, body = self.request('POST', '/api/recovery/estimate', data, headers)
        self.assertEqual(status, 200)
        self.assertNotIn(b'PrivateMemory', body)
        self.assertNotIn(b'PrivateStart', body)
        result = json.loads(body)
        self.assertLessEqual(int(result['candidates']), 10000000)
        self.assertTrue(result['notes'])
        self.assertFalse(list(Path(self.tmp.name).glob('**/candidates.hex')))
        self.assertFalse(self.library.stops)

    def test_first_run_has_no_documents_and_settings_status_is_explicit(self):
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1'}
        self.library.hashcat = self.library.zip2john = None
        status, body = self.request('GET', '/api/settings', headers=headers)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertFalse(data['hashcat_configured'])
        self.assertFalse(data['zip2john_configured'])
        self.assertFalse(data['settings_locked'])
        self.assertEqual(json.loads(self.request('GET', '/api/jobs', headers=headers)[1]), {'jobs': []})

    def test_detect_is_authenticated_read_only_and_does_not_execute(self):
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1'}
        self.assertEqual(self.request('POST', '/api/settings/detect', '{}')[0], 403)
        fake = Path(self.tmp.name) / 'hashcat.exe'
        with patch.object(self.library, 'discover_hashcat', return_value=fake), patch('app.discover_zip2john', return_value=None), patch('app.subprocess.run') as run:
            status, body = self.request('POST', '/api/settings/detect', '{}', headers)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['hashcat'], str(fake))
            run.assert_not_called()
        self.assertFalse((Path(self.tmp.name) / 'settings.json').exists())
        self.assertEqual(self.library.snapshot(), [])
        headers['Origin'] = 'https://other.example'
        self.assertEqual(self.request('POST', '/api/settings/detect', '{}', headers)[0], 403)

    def test_settings_errors_identify_field_and_preserve_previous_settings(self):
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1'}
        candidate = Path(self.tmp.name) / 'hashcat.exe'
        candidate.touch()
        status, body = self.request('POST', '/api/settings', json.dumps({'hashcat': '"' + str(candidate) + '"'}), headers)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['hashcat_configured'])
        original = (Path(self.tmp.name) / 'settings.json').read_bytes()
        status, body = self.request('POST', '/api/settings', json.dumps({'hashcat': '', 'zip2john': 'missing.exe'}), headers)
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)['field'], 'zip2john')
        self.assertEqual((Path(self.tmp.name) / 'settings.json').read_bytes(), original)
        self.assertEqual(self.library.hashcat, candidate.resolve())
        self.library.jobs['busy-test'] = {'state': 'recovering'}
        self.assertEqual(self.request('POST', '/api/diagnostics', '{}', headers)[0], 400)
        self.assertEqual(self.request('POST', '/api/settings', '{}', headers)[0], 400)
        self.library.jobs.clear()

    def test_cleared_engine_stays_cleared_after_restart(self):
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1'}
        self.request('POST', '/api/settings', json.dumps({'hashcat': '', 'zip2john': ''}), headers)
        candidate = Path(self.tmp.name) / 'hashcat.exe'
        candidate.touch()
        with patch.dict('os.environ', {'LOXMIT_HASHCAT': str(candidate)}):
            restored = Library(self.tmp.name)
            try:
                self.assertIsNone(restored.hashcat)
                self.assertIsNone(restored.zip2john)
                self.assertEqual(restored.discover_hashcat(configured=False), candidate.resolve())
            finally:
                restored.close()

    def test_gpu_diagnostics_use_the_saved_executable(self):
        from subprocess import CompletedProcess
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1'}
        candidate = Path(self.tmp.name) / 'hashcat.exe'
        candidate.touch()
        self.library.save_settings({'hashcat': str(candidate)})
        with patch('app.subprocess.run', return_value=CompletedProcess([], 0, b'device fixture', b'')) as run:
            status, body = self.request('POST', '/api/diagnostics', '{}', headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['code'], 0)
        self.assertEqual(run.call_args.args[0], [str(candidate.resolve()), '-I'])

    def test_setup_auth_consent_and_read_only_catalog(self):
        headers = {'Cookie': 'loxmit_session=test-capability', 'X-Loxmit': '1'}
        for route in ('/api/setup', '/setup.js'):
            self.assertEqual(self.request('GET', route)[0], 403)
            self.assertEqual(self.request('GET', route, headers=headers)[0], 200)
        with patch('environment_setup.download_component') as download, patch('environment_setup.hardware_inventory') as inventory:
            self.assertEqual(self.request('POST', '/api/setup/install', '{}', headers)[0], 400)
            self.assertEqual(self.request('POST', '/api/setup/diagnose', '{}')[0], 403)
            self.assertEqual(self.request('POST', '/api/setup/dismiss', '{}', headers)[0], 200)
            self.assertTrue(json.loads(self.request('GET', '/api/setup', headers=headers)[1])['guide_seen'])
            bad_origin = dict(headers, Origin='https://other.test')
            self.assertEqual(self.request('POST', '/api/setup/install', '{}', bad_origin)[0], 403)
            with patch('app.ipaddress.ip_address', return_value=SimpleNamespace(is_loopback=False)):
                self.assertEqual(self.request('POST', '/api/setup/install', '{}', headers)[0], 400)
            download.assert_not_called(); inventory.assert_not_called()

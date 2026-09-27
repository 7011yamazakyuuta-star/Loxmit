"""Opt-in frozen-app GPU check. Synthetic data only; no user library is opened."""
import argparse
import http.client
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import psutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--hashcat', type=Path, required=True)
    parser.add_argument('--device', type=int, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='loxmit-hardware-') as temporary:
        root = Path(temporary)
        process = subprocess.Popen([str(args.executable.resolve()), '--no-browser', '--port', '0', '--data', str(root)],
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        request = None
        try:
            deadline = time.monotonic() + 30
            while not (root / 'launch.json').exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Test app failed to start')
                time.sleep(.1)
            launch = json.loads((root / 'launch.json').read_text())
            url = urlsplit(launch['url'])
            token = parse_qs(url.query)['token'][0]
            def request(route, data=None):
                connection = http.client.HTTPConnection(url.hostname, url.port, timeout=55)
                try:
                    connection.request('POST' if data is not None else 'GET', route,
                                       body=json.dumps(data) if data is not None else None,
                                       headers={'Cookie': 'loxmit_session=' + token, 'X-Loxmit': '1'})
                    response = connection.getresponse()
                    result = json.loads(response.read())
                    if response.status != 200:
                        raise RuntimeError(result)
                    return result
                finally:
                    connection.close()
            request('/api/settings', {'hashcat': str(args.hashcat.resolve())})
            request('/api/setup/diagnose', {})
            request('/api/setup/compute', {'consent': True, 'device': args.device})
            deadline = time.monotonic() + 140
            while True:
                result = request('/api/setup')['compute']
                if result['state'] not in ('running', 'cancelling'):
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError('GPU test exceeded supervisor deadline')
                time.sleep(.2)
            result['scratch_removed'] = not list(root.glob('.gpucheck-*'))
            result['version'] = request('/api/settings')['version']
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result), flush=True)
            if result['state'] != 'passed' or not result['scratch_removed']:
                raise RuntimeError('GPU correctness check did not pass')
        finally:
            if request:
                try:
                    request('/api/setup/compute-cancel', {})
                    request('/api/shutdown', {})
                except (OSError, RuntimeError):
                    pass
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                children = psutil.Process(process.pid).children(recursive=True)
                for child in reversed(children):
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                process.kill()
                process.wait(timeout=5)
                psutil.wait_procs(children, timeout=5)


if __name__ == '__main__':
    main()

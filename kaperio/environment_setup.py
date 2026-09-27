"""Opt-in, pinned user-local components. Never installs drivers or runs installers."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from runtime import APP_DIR, engine_environment
from gpu_check import engine_identity, run_compute

CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
CATALOG_REVISION = '2026-09-25.2'
CATALOG = {
    'hashcat': {
        'name': 'Hashcat', 'version': '7.1.2', 'size': 19682772,
        'url': 'https://hashcat.net/files/hashcat-7.1.2.7z',
        'sha256': '80db0316387794ce9d14ed376da75b8a7742972485b45db790f5f8260307ff98',
        'license': 'MIT・同梱部品の各ライセンス',
        'license_url': 'https://github.com/hashcat/hashcat/blob/v7.1.2/docs/license.txt',
        'folder': 'hashcat-7.1.2',
    },
    'nvrtc': {
        'name': 'NVIDIA NVRTC', 'version': '12.9.86', 'size': 76408187,
        'url': 'https://files.pythonhosted.org/packages/52/de/823919be3b9d0ccbf1f784035423c5f18f4267fb0123558d58b813c6ec86/nvidia_cuda_nvrtc_cu12-12.9.86-py3-none-win_amd64.whl',
        'sha256': '72972ebdcf504d69462d3bcd67e7b81edd25d0fb85a2c46d3ea3517666636349',
        'license': 'NVIDIA CUDA EULA',
        'license_url': 'https://docs.nvidia.com/cuda/archive/12.9.1/eula/index.html',
        'folder': 'nvrtc-12.9.86',
    },
}
NVRTC_DLLS = {'nvrtc64_120_0.dll', 'nvrtc-builtins64_129.dll'}
ACTIVE = {'downloading', 'verifying', 'extracting', 'configuring', 'cancelling'}


class Cancelled(Exception):
    pass


def windows_x64():
    return platform.system() == 'Windows' and platform.machine().lower() in ('amd64', 'x86_64')


def native_pack():
    """Only trust build resources, never a manifest from a user-selected directory."""
    if windows_x64():
        return None
    try:
        folder = APP_DIR / 'component_pack'
        data = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        system, machine = platform.system(), platform.machine().lower()
        if (system, machine) not in {('Darwin', 'arm64'), ('Darwin', 'x86_64'), ('Linux', 'x86_64')}:
            return None
        if system == 'Darwin' and int(platform.mac_ver()[0].split('.')[0]) < 15:
            return None
        if (data['schema'] != 1 or data['version'] != '7.1.2'
                or data['system'] != system or data['machine'] != machine
                or data['source_commit'] != 'c75f446c44cd3f0742035a1394416c39bee5ea8f'
                or not re.fullmatch('[0-9a-f]{64}', data['sha256'])
                or not 0 < data['size'] <= 256 * 1024 * 1024
                or (folder / 'hashcat.zip').stat().st_size != data['size']):
            return None
        return {**CATALOG['hashcat'], 'size': data['size'], 'sha256': data['sha256'],
                'url': 'https://github.com/hashcat/hashcat/tree/' + data['source_commit'],
                'archive': folder / 'hashcat.zip', 'delivery': 'bundled', 'executable': 'hashcat'}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def unpack_native(item, stage, stop, progress):
    archive = item['archive']
    digest, received = hashlib.sha256(), 0
    with archive.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            if stop.is_set():
                raise Cancelled()
            digest.update(chunk)
            received += len(chunk)
            progress(received, item['size'])
    if received != item['size'] or digest.hexdigest() != item['sha256']:
        raise ValueError('同梱HashcatのSHA-256検証に失敗しました。')
    total, names = 0, set()
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            mode = member.external_attr >> 16
            if (not safe_member(member.filename, item['folder']) or member.filename in names
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError('同梱Hashcatの構成が不正です。')
            names.add(member.filename)
            total += member.file_size
            if total > 512 * 1024 * 1024:
                raise ValueError('展開サイズが上限を超えました。')
        for member in source.infolist():
            if stop.is_set():
                raise Cancelled()
            path = stage.joinpath(*PurePosixPath(member.filename).parts)
            if member.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as stream, path.open('xb') as output:
                while chunk := stream.read(1024 * 1024):
                    if stop.is_set():
                        raise Cancelled()
                    output.write(chunk)
            path.chmod(0o700 if path.name == 'hashcat' else 0o600)
    target = stage / item['folder']
    for name in ('hashcat', 'docs/license.txt', 'modules/module_10400.so', 'OpenCL/inc_vendor.h'):
        if not (target / name).is_file():
            raise ValueError('必要なHashcatの部品がありません。')
    return target


def system_tar():
    path = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/tar.exe'
    return path if windows_x64() and path.is_file() else None


def run_readonly(command, timeout=35, env=None, cwd=None):
    # Capture into a temporary file so a broken executable cannot fill RAM.
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, timeout=timeout,
                                creationflags=CREATE_FLAGS, env=env, cwd=cwd)
        output.seek(0)
        return result.returncode, output.read(256 * 1024).decode('utf-8-sig', errors='replace')


def hardware_inventory():
    devices = []
    try:
        if platform.system() == 'Windows':
            shell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            code, text = run_readonly([str(shell), '-NoProfile', '-NonInteractive', '-Command',
                '[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); Get-CimInstance Win32_VideoController | Select-Object Name,AdapterCompatibility,DriverVersion | ConvertTo-Json -Compress'])
            if code:
                raise ValueError('Inventory failed')
            rows = json.loads(text or '[]')
            for row in rows if isinstance(rows, list) else [rows]:
                devices.append({'name': str(row.get('Name') or 'Display adapter'),
                                'vendor': str(row.get('AdapterCompatibility') or ''),
                                'driver': str(row.get('DriverVersion') or '')})
        elif platform.system() == 'Darwin':
            code, text = run_readonly(['/usr/sbin/system_profiler', 'SPDisplaysDataType', '-json'])
            if code:
                raise ValueError('Inventory failed')
            for row in json.loads(text).get('SPDisplaysDataType', []):
                devices.append({'name': str(row.get('sppci_model') or row.get('_name') or 'GPU'),
                                'vendor': str(row.get('spdisplays_vendor') or ''), 'driver': ''})
        elif platform.system() == 'Linux':
            pci = Path('/sys/bus/pci/devices')
            if not pci.is_dir():
                raise ValueError('PCI inventory unavailable')
            for path in pci.iterdir():
                if (path / 'class').read_text().strip().startswith('0x03'):
                    vendor = (path / 'vendor').read_text().strip()
                    vendor = {'0x10de': 'NVIDIA', '0x1002': 'AMD', '0x8086': 'Intel'}.get(vendor, vendor)
                    devices.append({'name': vendor + ' GPU ' + (path / 'device').read_text().strip(),
                                    'vendor': vendor, 'driver': ''})
        else:
            raise ValueError('Unsupported inventory')
        return {'status': 'detected' if devices else 'not_reported', 'devices': devices}
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return {'status': 'unknown', 'devices': []}


def parse_backend(text, code):
    backend, current, devices = '', None, []
    for line in text.splitlines():
        heading = re.match(r'^(CUDA|HIP|OpenCL|Metal) (?:Info|API|Platform)', line)
        if heading:
            backend, current = heading[1], None
        match = re.search(r'Backend Device ID #([0-9]+)', line)
        if match:
            current = {'id': int(match[1]), 'backend': backend,
                       'type': 'GPU' if backend in ('CUDA', 'HIP', 'Metal') else '', 'name': ''}
            devices.append(current)
        field = re.match(r'\s+(Name|Type)\.+:\s*(.+)', line)
        if current is not None and field:
            current[field[1].lower()] = field[2].strip()
    devices = [d for d in devices if d['name']]
    gpu = [d for d in devices if 'GPU' in d['type']]
    return {'status': 'recognized' if gpu and code == 0 else 'cpu_only' if devices and code == 0 else 'unavailable',
            'devices': devices, 'code': code, 'compute_tested': False,
            'nvrtc_missing': 'Failed to initialize NVIDIA RTC library' in text,
            'text': text}


class PinnedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlsplit
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if new.scheme != 'https' or new.hostname != old.hostname or new.port not in (None, 443) or new.username or new.password:
            raise ValueError('配布元以外への転送を拒否しました。')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_component(item, target, stop, progress):
    opener = urllib.request.build_opener(PinnedRedirect())
    digest, received, started = hashlib.sha256(), 0, time.monotonic()
    request = urllib.request.Request(item['url'], headers={'User-Agent': 'Loxmit-Setup/1'})
    with opener.open(request, timeout=20) as response, target.open('xb') as output:
        length = response.headers.get('Content-Length')
        if length and int(length) != item['size']:
            raise ValueError('配布物のサイズが一致しません。')
        while True:
            if stop.is_set():
                raise Cancelled()
            if time.monotonic() - started > 600:
                raise ValueError('ダウンロードがタイムアウトしました。')
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            received += len(chunk)
            if received > item['size']:
                raise ValueError('配布物が予定サイズを超えています。')
            digest.update(chunk)
            output.write(chunk)
            progress(received, item['size'])
    if received != item['size'] or digest.hexdigest() != item['sha256']:
        raise ValueError('SHA-256検証に失敗しました。導入していません。')


def safe_member(name, root=None):
    path = PurePosixPath(name)
    if '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts:
        return False
    if root and (not path.parts or path.parts[0] != root):
        return False
    for part in path.parts:
        if part.endswith((' ', '.')) or re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', part):
            return False
    return bool(path.parts)


def unpack_hashcat(archive, stage, stop):
    tar = system_tar()
    if not tar:
        raise ValueError('Windows標準の展開機能がありません。手動設定をご利用ください。')
    code, listing = run_readonly([str(tar), '-tf', str(archive)], timeout=45)
    names = listing.splitlines()
    if code or not names or any(not safe_member(n, 'hashcat-7.1.2') for n in names):
        raise ValueError('配布物の展開先を検証できませんでした。')
    if stop.is_set():
        raise Cancelled()
    code, _ = run_readonly([str(tar), '-xf', str(archive), '-C', str(stage)], timeout=90)
    target = stage / 'hashcat-7.1.2'
    if code or not (target / 'hashcat.exe').is_file() or not (target / 'docs/license.txt').is_file():
        raise ValueError('Hashcatの展開に失敗しました。')
    total = 0
    for path in target.rglob('*'):
        info = path.lstat()
        if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('リンクを含む配布物は導入できません。')
        total += info.st_size
        if total > 512 * 1024 * 1024:
            raise ValueError('展開サイズが上限を超えました。')
    return target


def unpack_nvrtc(archive, stage, stop):
    target = stage / CATALOG['nvrtc']['folder']
    (target / 'bin').mkdir(parents=True)
    (target / 'licenses').mkdir()
    found, notices, total = set(), 0, 0
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            name = PurePosixPath(item.filename).name
            is_notice = 'license' in name.lower() and not item.is_dir()
            if name not in NVRTC_DLLS and not is_notice:
                continue
            if not safe_member(item.filename) or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('NVRTC配布物のパスが不正です。')
            total += item.file_size
            if total > 512 * 1024 * 1024 or name in found:
                raise ValueError('NVRTC配布物の構成が不正です。')
            if is_notice:
                notices += 1
                destination = target / 'licenses' / f'NVIDIA-{notices}.txt'
            else:
                found.add(name)
                destination = target / 'bin' / name
            with source.open(item) as stream, destination.open('xb') as output:
                while chunk := stream.read(1024 * 1024):
                    if stop.is_set():
                        raise Cancelled()
                    output.write(chunk)
    if found != NVRTC_DLLS or not notices:
        raise ValueError('必要なNVRTCライブラリまたはライセンスがありません。')
    return target


class SetupManager:
    def __init__(self, library):
        self.library = library
        self.root = library.root / 'tools'
        self.stop = threading.Event()
        self.thread = None
        self.diagnosing = False
        self.report = None
        self.diagnosed_engine = None
        self.diagnosed_identity = None
        self.compute = {'state': 'idle', 'compute_tested': False}
        self.compute_stop = threading.Event()
        self.compute_thread = None
        self.status = {'phase': 'idle', 'message': '', 'received': 0, 'total': 0}

    def item(self, key):
        return (native_pack() if key == 'hashcat' else None) or CATALOG[key]

    @property
    def busy(self):
        return self.status['phase'] in ACTIVE or self.diagnosing or self.compute['state'] in {'running', 'cancelling'}

    def receipt_path(self, key):
        return self.root / CATALOG[key]['folder'] / 'loxmit-receipt.json'

    def installed(self, key):
        try:
            receipt = json.loads(self.receipt_path(key).read_text(encoding='utf-8'))
            target = self.receipt_path(key).parent
            if target.resolve().parent != self.root.resolve():
                return False
            item = self.item(key)
            expected = [item.get('executable', 'hashcat.exe')] if key == 'hashcat' else ['bin/' + n for n in NVRTC_DLLS]
            return receipt['sha256'] == item['sha256'] and all((target / n).is_file() for n in expected)
        except (OSError, ValueError, KeyError):
            return False

    def snapshot(self):
        with self.library.lock:
            try:
                seen = json.loads((self.library.root / 'setup-state.json').read_text())['guide_seen'] is True
            except (OSError, ValueError, KeyError):
                seen = False
            configured = bool(self.library.hashcat and self.library.hashcat.is_file())
            pack = native_pack()
            supported = windows_x64() or pack is not None
            components = []
            for key in CATALOG:
                item = self.item(key)
                installed = self.installed(key)
                eligible = supported and not self.busy
                reason = ''
                if not supported:
                    reason = 'この環境に対応する同梱部品がありません。macOS 15以降・Linux x64の配布版、または既存のHashcatを使用してください。'
                elif key == 'hashcat':
                    if configured:
                        eligible, reason = False, '設定済みのHashcatを使用します。追加ダウンロードは不要です。'
                    elif not pack and not system_tar():
                        eligible, reason = False, 'Windows標準の展開機能が見つかりません。'
                elif not windows_x64():
                    eligible, reason = False, 'NVRTCの自動追加はWindows x64のみです。macOSでは不要です。ドライバーは変更しません。'
                elif installed:
                    eligible, reason = False, '導入済みです。'
                elif not self.report or self.diagnosed_engine != str(self.library.hashcat):
                    eligible, reason = False, '先にHashcatを設定し、GPU診断を実行してください。'
                elif not configured or not self.report['backend'].get('nvrtc_missing'):
                    eligible, reason = False, '診断ではNVRTCの追加が必要と判定されていません。'
                elif not any('nvidia' in (d['name'] + d['vendor']).lower() for d in self.report['hardware']['devices']):
                    eligible, reason = False, 'NVIDIA GPUを確認できませんでした。'
                components.append({**{k: item[k] for k in ('name', 'version', 'size', 'license', 'license_url')},
                                   'id': key, 'installed': installed, 'eligible': eligible, 'reason': reason,
                                   'delivery': item.get('delivery', 'download')})
            return {'catalog_revision': CATALOG_REVISION, 'guide_seen': seen,
                    'platform': platform.system(), 'automatic_supported': supported,
                    'destination': str(self.root), 'components': components,
                    'operation': dict(self.status), 'diagnosing': self.diagnosing,
                    'compute': dict(self.compute) if self.diagnosed_identity == engine_identity(self.library.hashcat) else {'state': 'idle', 'compute_tested': False},
                    'compute_eligible': bool(self.report and self.report['backend'].get('status') == 'recognized'
                                             and self.diagnosed_identity and self.diagnosed_identity == engine_identity(self.library.hashcat)),
                    'report': self.report, 'locked': self.library.settings_snapshot()['settings_locked']}

    def dismiss(self):
        path = self.library.root / 'setup-state.json'
        with self.library.lock:
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps({'guide_seen': True}), encoding='utf-8')
            temp.replace(path)

    def diagnose(self):
        with self.library.lock:
            if self.busy or self.library.settings_snapshot()['settings_locked']:
                raise ValueError('探索・導入が終わってから診断してください。')
            self.diagnosing = True
            engine = self.library.hashcat
            self.compute = {'state': 'idle', 'compute_tested': False}
            identity = engine_identity(engine)
        try:
            hardware = hardware_inventory()
            backend = {'status': 'missing', 'devices': [], 'compute_tested': False, 'nvrtc_missing': False, 'text': ''}
            if engine:
                try:
                    code, text = run_readonly([str(engine), '-I'], timeout=45, env=engine_environment(self.library.root), cwd=engine.parent)
                    backend = parse_backend(text, code)
                except (OSError, subprocess.TimeoutExpired):
                    backend['status'] = 'error'
            with self.library.lock:
                self.report = {'hardware': hardware, 'backend': backend, 'checked_at': time.time()}
                self.diagnosed_engine = str(engine)
                self.diagnosed_identity = identity
        finally:
            self.diagnosing = False
        return self.snapshot()

    def start_compute(self, data):
        with self.library.lock:
            if self.busy or self.library.settings_snapshot()['settings_locked']:
                raise ValueError('探索・診断・導入の終了を待ってください。')
            if (set(data) != {'consent', 'device'} or data['consent'] is not True
                    or type(data['device']) is not int):
                raise ValueError('GPUを選び、計算テストの実行を許可してください。')
            if not self.snapshot()['compute_eligible']:
                raise ValueError('先にGPUの認識状態を再診断してください。')
            device = next((d for d in self.report['backend']['devices']
                           if d['id'] == data['device'] and 'GPU' in d['type']), None)
            if not device:
                raise ValueError('診断で確認できたGPUを選択してください。')
            self.compute_stop.clear()
            self.compute = {'state': 'running', 'compute_tested': False, 'device': dict(device),
                            'message': '計算テスト中（準備を含め最大120秒）'}
            self.compute_thread = threading.Thread(target=self._compute, args=(self.library.hashcat, dict(device)), daemon=True)
            self.compute_thread.start()

    def _compute(self, engine, device):
        try:
            result = run_compute(engine, self.library.root, device, self.compute_stop)
        except Exception:
            result = {'state': 'error', 'compute_tested': False, 'message': '計算テストを完了できませんでした。'}
        with self.library.lock:
            self.compute = result

    def cancel_compute(self):
        with self.library.lock:
            if self.compute['state'] in {'running', 'cancelling'}:
                self.compute_stop.set()
                self.compute.update(state='cancelling', message='計算テストを中止しています。')

    def start(self, data):
        with self.library.lock:
            if self.busy or self.library.settings_snapshot()['settings_locked']:
                raise ValueError('探索・診断・導入の終了を待ってください。')
            if set(data) != {'component', 'consent', 'catalog_revision'} or data['consent'] is not True or data['catalog_revision'] != CATALOG_REVISION:
                raise ValueError('表示された部品と利用条件を確認し、同意してください。')
            key = data['component']
            component = next((c for c in self.snapshot()['components'] if c['id'] == key), None)
            if not component or not component['eligible']:
                raise ValueError(component['reason'] if component else 'この部品は導入できません。')
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.root.is_symlink() or self.root.resolve().parent != self.library.root:
                raise ValueError('部品の保存先が不正です。')
            self.stop.clear()
            self.status = {'phase': 'downloading', 'component': key, 'received': 0, 'total': self.item(key)['size'], 'message': '導入を開始します。'}
            self.thread = threading.Thread(target=self._install, args=(key, time.time()), daemon=True)
            self.thread.start()

    def cancel(self):
        with self.library.lock:
            if self.status['phase'] in ACTIVE:
                self.stop.set()
                self.status.update(phase='cancelling', message='中止しています。')

    def _update(self, **fields):
        with self.library.lock:
            if self.stop.is_set():
                raise Cancelled()
            self.status.update(fields)

    def _install(self, key, accepted_at):
        item = self.item(key)
        try:
            target = self.root / item['folder']
            if not self.installed(key):
                if target.exists():
                    raise ValueError('同名の保存先が既にあります。既存ファイルは変更しません。')
                if shutil.disk_usage(self.root).free < item['size'] + 640 * 1024 * 1024:
                    raise ValueError('導入用の空き容量が不足しています。')
                with tempfile.TemporaryDirectory(prefix='.install-', dir=self.root) as folder:
                    stage = Path(folder)
                    archive = stage / 'download.bin'
                    if item.get('delivery') == 'bundled':
                        self._update(phase='extracting', message='同梱部品を検証・展開中')
                        extracted = unpack_native(item, stage, self.stop, lambda done, total: self._update(received=done, total=total))
                        code, version = run_readonly([str(extracted / 'hashcat'), '--version'], cwd=extracted)
                        if code or version.strip() != 'v' + item['version']:
                            raise ValueError('この環境では同梱Hashcatを実行できません。既存のHashcatを手動設定してください。')
                    else:
                        download_component(item, archive, self.stop, lambda done, total: self._update(received=done, total=total, message='ダウンロード中'))
                        self._update(phase='verifying', message='SHA-256検証完了')
                        self._update(phase='extracting', message='必要な部品を展開中')
                        extracted = unpack_hashcat(archive, stage, self.stop) if key == 'hashcat' else unpack_nvrtc(archive, stage, self.stop)
                    self._update(phase='configuring', message='設定中')
                    receipt = {k: item[k] for k in ('version', 'sha256', 'url', 'license_url')}
                    receipt.update(component=key, accepted_at=accepted_at, catalog_revision=CATALOG_REVISION)
                    (extracted / 'loxmit-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
                    with self.library.lock:
                        if self.stop.is_set():
                            raise Cancelled()
                        extracted.rename(target)
            with self.library.lock:
                if key == 'hashcat':
                    self.library.save_settings({'hashcat': str(target / item.get('executable', 'hashcat.exe'))}, _setup=True)
                self.report = None
                self.compute = {'state': 'idle', 'compute_tested': False}
                self.diagnosed_identity = None
                self.status.update(phase='complete', message='導入済みです。GPU診断で認識状態を確認してください。')
        except Cancelled:
            with self.library.lock:
                self.status.update(phase='cancelled', message='導入を中止しました。')
        except Exception as error:
            with self.library.lock:
                message = str(error) if isinstance(error, ValueError) else '導入できませんでした。通信・保存先・空き容量を確認して再試行してください。'
                self.status.update(phase='error', message=message)

    def close(self):
        self.cancel_compute()
        if self.compute_thread:
            self.compute_thread.join(timeout=15)
        self.cancel()
        if self.thread:
            self.thread.join(timeout=100)

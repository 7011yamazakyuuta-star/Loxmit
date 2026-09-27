"""Read-only, conservative storage checks; never enable encryption or request keys."""
from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HELP = {
    'win32': 'https://learn.microsoft.com/windows/security/operating-system-security/data-protection/bitlocker/',
    'darwin': 'https://support.apple.com/guide/mac-help/protect-data-on-your-mac-with-filevault-mh11785/mac',
    'linux': 'https://documentation.ubuntu.com/security/security-features/storage/encryption-full-disk/',
}


def run_probe(command, *, extra_env=None):
    # No shell, elevation, recovery-key queries, or raw command output in the API.
    env = dict(os.environ, LC_ALL='C', LANG='C', **(extra_env or {}))
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=12, env=env,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode or len(result.stdout) > 256 * 1024:
        raise ValueError('Storage query unavailable')
    return result.stdout


def windows_volume(root):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    for name in ('GetVolumePathNameW', 'GetVolumeNameForVolumeMountPointW'):
        function = getattr(kernel, name)
        function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        function.restype = ctypes.c_int
    mount, volume = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(1024)
    if not kernel.GetVolumePathNameW(str(root), mount, len(mount)):
        raise OSError('Volume mapping unavailable')
    if not kernel.GetVolumeNameForVolumeMountPointW(mount.value, volume, len(volume)):
        raise OSError('Volume identity unavailable')
    return volume.value


def windows_state(data):
    if not isinstance(data, dict):
        return 'unknown'
    if data.get('protection_code') != 0 or data.get('conversion_code') != 0:
        return 'unknown'
    if data.get('protection') == 1 and data.get('conversion') == 1:
        return 'protected'
    if data.get('protection') == 0:
        return 'unprotected'
    return 'unknown'


def check_windows(root):
    volume = windows_volume(root)
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = r"""
$ErrorActionPreference = 'Stop'
$v = @(Get-CimInstance -Namespace 'root/CIMV2/Security/MicrosoftVolumeEncryption' -ClassName Win32_EncryptableVolume | Where-Object { $_.DeviceID -eq $env:LOXMIT_CHECK_VOLUME })
if ($v.Count -ne 1) { exit 2 }
$p = Invoke-CimMethod -InputObject $v[0] -MethodName GetProtectionStatus
$c = Invoke-CimMethod -InputObject $v[0] -MethodName GetConversionStatus
@{ protection_code = $p.ReturnValue; conversion_code = $c.ReturnValue; protection = $p.ProtectionStatus; conversion = $c.ConversionStatus } | ConvertTo-Json -Compress
"""
    raw = run_probe([str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
                    extra_env={'LOXMIT_CHECK_VOLUME': volume})
    return windows_state(json.loads(raw.decode('utf-8-sig')))


def check_mac(root):
    # FileVault status applies to startup data, not arbitrary external volumes.
    data = Path('/System/Volumes/Data')
    if not data.is_dir() or root.stat().st_dev != data.stat().st_dev:
        return 'unknown'
    status = run_probe(['/usr/bin/fdesetup', 'status']).decode('utf-8').strip()
    return {'FileVault is On.': 'protected', 'FileVault is Off.': 'unprotected'}.get(status, 'unknown')


def crypt_covered(node):
    if not isinstance(node, dict):
        return False
    if node.get('type') == 'crypt':
        return True
    parents = node.get('children', [])
    return bool(parents) and all(crypt_covered(parent) for parent in parents)


def check_linux(root):
    raw = run_probe(['/usr/bin/findmnt', '--json', '--target', str(root), '--output', 'SOURCE,FSTYPE'])
    mounts = json.loads(raw)['filesystems']
    if len(mounts) != 1 or mounts[0].get('fstype') not in {'ext4', 'xfs'}:
        return 'unknown'
    source = mounts[0].get('source', '')
    if not re.fullmatch(r'/dev/[A-Za-z0-9/_+.-]+', source):
        return 'unknown'
    raw = run_probe(['/usr/bin/lsblk', '--json', '--inverse', '--paths', '--output', 'NAME,TYPE', source])
    devices = json.loads(raw)['blockdevices']
    if len(devices) != 1:
        return 'unknown'
    return 'protected' if crypt_covered(devices[0]) else 'not_detected'


class SecurityStatus:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.Lock()
        self.result = None
        self.updated = 0

    def snapshot(self):
        return {'storage': self.result or {'state': 'unchecked'},
                'checked_at': self.updated or None,
                'method': {'win32': 'BitLocker', 'darwin': 'FileVault', 'linux': 'dm-crypt'}.get(sys.platform, 'OS'),
                'help_url': HELP.get(sys.platform, HELP['linux']),
                'application_encryption': False, 'full_sandbox': False}

    def check(self):
        if not self.lock.acquire(blocking=False):
            raise ValueError('保存先の保護状態を確認中です。')
        try:
            if self.result is not None and time.time() - self.updated < 30:
                return self.snapshot()
            try:
                probe = {'win32': check_windows, 'darwin': check_mac, 'linux': check_linux}.get(sys.platform)
                state = probe(self.root) if probe else 'unknown'
            except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, subprocess.SubprocessError):
                state = 'unknown'
            self.result = {'state': state}
            self.updated = time.time()
            return self.snapshot()
        finally:
            self.lock.release()

"""Opt-in native signing. Private keys stay in the developer's OS key store."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

MACHO = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
         b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
         b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}


def add_arguments(parser, *, engine=False):
    parser.add_argument('--macos-identity', help='Developer ID Application identity in Keychain')
    parser.add_argument('--macos-team-id', help='Expected Apple Team ID (10 characters)')
    if not engine:
        parser.add_argument('--notary-profile', help='Existing notarytool Keychain profile; no password argument')
        parser.add_argument('--windows-certificate', help='SHA1 thumbprint in CurrentUser/My (not the file digest)')
        parser.add_argument('--timestamp-url', help='RFC3161 timestamp service supplied by the certificate provider')
        parser.add_argument('--signtool', help='Absolute path to Windows SDK signtool.exe')


def validate_options(args, platform):
    mac = bool(args.macos_identity or args.macos_team_id or getattr(args, 'notary_profile', None))
    win = bool(getattr(args, 'windows_certificate', None) or getattr(args, 'timestamp_url', None)
               or getattr(args, 'signtool', None))
    if mac:
        if platform != 'darwin' or not args.macos_identity or not re.fullmatch(r'[A-Z0-9]{10}', args.macos_team_id or ''):
            raise ValueError('macOS signing requires a native Mac, identity and expected Team ID')
        if not args.macos_identity.startswith('Developer ID Application: '):
            raise ValueError('Use a Developer ID Application identity; ad-hoc signing is not distribution signing')
    if win:
        if platform != 'win32' or not re.fullmatch(r'[a-fA-F0-9]{40}', args.windows_certificate or ''):
            raise ValueError('Windows signing requires a native Windows host and a certificate thumbprint')
        url = urlsplit(args.timestamp_url or '')
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.fragment:
            raise ValueError('Specify a public RFC3161 timestamp URL without credentials')
        if args.signtool and not Path(args.signtool).is_absolute():
            raise ValueError('signtool must be an absolute path')


def run(command, *, timeout=180):
    return subprocess.run(list(map(str, command)), check=True, timeout=timeout,
                          stdin=subprocess.DEVNULL, capture_output=True)


def verify_mac(path, team):
    requirement = ('anchor apple generic and certificate leaf[subject.OU] = "' + team + '"'
                   ' and certificate 1[field.1.2.840.113635.100.6.2.6] exists'
                   ' and certificate leaf[field.1.2.840.113635.100.6.1.13] exists')
    run(['/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2',
         '--test-requirement', requirement, path])


def sign_engine_files(files, identity, team):
    count = 0
    for path in files:
        if path.is_symlink():
            raise ValueError('Engine inputs cannot be symlinks')
        with path.open('rb') as source:
            magic = source.read(4)
        if magic in MACHO:
            run(['/usr/bin/codesign', '--force', '--sign', identity, '--options', 'runtime', '--timestamp', path])
            verify_mac(path, team)
            count += 1
    if not count:
        raise ValueError('No native engine binaries were signed')
    return count


def sign_windows(bundle, args):
    tool = args.signtool or shutil.which('signtool')
    if not tool:
        raise ValueError('Install the Windows SDK signing tools or supply --signtool')
    executable = bundle / 'Loxmit.exe'
    run([tool, 'sign', '/sha1', args.windows_certificate, '/s', 'My', '/fd', 'SHA256',
         '/tr', args.timestamp_url, '/td', 'SHA256', '/d', 'Loxmit', executable])
    # /tw warns on absent timestamps; all nonzero exit codes (including warnings) fail.
    run([tool, 'verify', '/pa', '/all', '/tw', executable])
    return {'developer_signed': True, 'signature_scope': 'Loxmit.exe', 'notarized': False}


def notarize(bundle, archive, profile, team):
    result = run(['/usr/bin/xcrun', 'notarytool', 'submit', archive, '--keychain-profile', profile,
                  '--wait', '--timeout', '20m', '--output-format', 'json'], timeout=1260)
    receipt = json.loads(result.stdout)
    if receipt.get('status') != 'Accepted':
        raise ValueError('Apple did not accept the notarization submission')
    run(['/usr/bin/xcrun', 'stapler', 'staple', bundle])
    run(['/usr/bin/xcrun', 'stapler', 'validate', bundle])
    verify_mac(bundle, team)
    run(['/usr/sbin/spctl', '--assess', '--type', 'execute', '--verbose=2', bundle])
    return {'notarized': True, 'notarization_id': receipt.get('id')}

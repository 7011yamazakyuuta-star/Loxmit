"""Build on the target OS, smoke-test separately, then package the exact bundle."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime import APP_NAME, VERSION
from scripts.signing import add_arguments, notarize, sign_windows, validate_options, verify_mac

RUNTIME = ['cffi', 'charset-normalizer', 'cryptography', 'lxml', 'msoffcrypto-tool',
           'olefile', 'pillow', 'pycparser', 'pycryptodomex', 'pypdf', 'pypdfium2',
           'python-docx', 'pyzipper', 'reportlab', 'typing_extensions', 'psutil']


def collect_licenses(destination):
    destination.mkdir(parents=True, exist_ok=True)
    inventory = {}
    for name in RUNTIME:
        dist = metadata.distribution(name)
        notices = [f for f in dist.files or [] if any(key in str(f).lower()
                   for key in ('license', 'copying', 'notice')) and dist.locate_file(f).is_file()]
        if not notices:
            raise RuntimeError('Missing upstream notices for ' + name)
        inventory[name] = dist.version
        for index, file in enumerate(notices):
            target = destination / (name + '-' + str(index) + '-' + file.name + '.txt')
            shutil.copyfile(dist.locate_file(file), target)
    python_license = next((p for p in [Path(sys.base_prefix) / 'LICENSE.txt',
                          Path(sys.base_prefix) / 'LICENSE',
                          Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt'] if p.exists()), None)
    if python_license is None:
        raise RuntimeError('Python license missing from build runtime')
    shutil.copyfile(python_license, destination / 'Python.txt')
    inventory['Python'] = platform.python_version()
    (destination / 'versions.txt').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    return inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-only', action='store_true')
    add_arguments(parser)
    args = parser.parse_args()
    validate_options(args, sys.platform)
    output = ROOT / 'dist'
    build = ROOT / 'build'
    bundle = output / (APP_NAME + '.app' if sys.platform == 'darwin' else APP_NAME)
    if args.macos_identity:
        manifest = json.loads((ROOT / 'component_pack/manifest.json').read_text(encoding='utf-8'))
        if manifest.get('signing_team') != args.macos_team_id or not manifest.get('signed_binaries'):
            raise RuntimeError('Rebuild the native engine pack with the same Developer ID before signing the app')
    if not args.package_only:
        licenses = build / 'runtime-licenses'
        collect_licenses(licenses)
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
                   '--name', APP_NAME, '--distpath', str(output), '--workpath', str(build / 'pyinstaller'),
                   '--specpath', str(build), '--paths', str(ROOT), '--noupx',
                   '--collect-data', 'docx', '--collect-all', 'pypdfium2', '--collect-all', 'pypdfium2_raw',
                   '--collect-submodules', 'Cryptodome', '--hidden-import', 'olefile']
        for source, target in [('static', 'static'), ('licenses', 'licenses'),
                               ('vendor/office2john.py', 'vendor'), ('office_render.ps1', '.'),
                               ('LICENSE', '.'), ('THIRD_PARTY.md', '.')]:
            command += ['--add-data', str(ROOT / source) + ':' + target]
        command += ['--add-data', str(licenses) + ':licenses/runtime']
        if sys.platform in ('darwin', 'linux'):
            from environment_setup import native_pack
            if native_pack() is None:
                raise RuntimeError('Build the pinned native engine pack before packaging this platform')
            command += ['--add-data', str(ROOT / 'component_pack') + ':component_pack']
        if sys.platform in ('win32', 'darwin'):
            icon = 'favicon.ico' if sys.platform == 'win32' else 'icon.icns'
            command += ['--windowed', '--icon', str(ROOT / 'static' / icon)]
        if sys.platform == 'darwin':
            command += ['--osx-bundle-identifier', 'org.loxmit.desktop']
            if args.macos_identity:
                command += ['--codesign-identity', args.macos_identity]
        command += [str(ROOT / 'desktop.py')]
        subprocess.run(command, cwd=ROOT, check=True)
    if not bundle.is_dir():
        raise RuntimeError('Build output not found')
    evidence = {'developer_signed': False, 'signature_scope': 'none', 'notarized': False}
    if args.windows_certificate:
        evidence.update(sign_windows(bundle, args))
    if args.macos_identity:
        embedded = bundle / 'Contents/Resources/component_pack/hashcat.zip'
        with embedded.open('rb') as stream:
            embedded_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
        if embedded_hash != manifest['sha256']:
            raise RuntimeError('The bundle does not contain the expected signed engine pack')
        verify_mac(bundle, args.macos_team_id)
        evidence.update(developer_signed=True, signature_scope='app-bundle-and-engine-pack',
                        signing_team=args.macos_team_id)
    package_name = APP_NAME + '-' + VERSION + '-' + platform.system().lower() + '-' + platform.machine().lower()
    releases = output / 'releases'
    releases.mkdir(exist_ok=True)
    # Failed signing/notarization must not leave a new distributable in releases/.
    build.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='package-', dir=build) as directory:
        target = Path(directory) / package_name
        if sys.platform == 'darwin':
            staged = Path(str(target) + '.zip')
            def archive_mac():
                subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(bundle), str(staged)], check=True)
            archive_mac()
            if args.notary_profile:
                evidence.update(notarize(bundle, staged, args.notary_profile, args.macos_team_id))
                staged.unlink()
                archive_mac()  # Include the stapled ticket, not the pre-notarization archive.
        else:
            staged = Path(shutil.make_archive(str(target), 'zip' if sys.platform == 'win32' else 'gztar',
                                             root_dir=output, base_dir=APP_NAME))
        archive = releases / staged.name
        staged.replace(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + '.sha256').write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
    evidence.update(archive=archive.name, sha256=digest, system=platform.platform(), architecture=platform.machine())
    archive.with_name(archive.name + '.security.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence))


if __name__ == '__main__':
    main()

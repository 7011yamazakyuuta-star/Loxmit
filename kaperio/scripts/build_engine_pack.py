"""Build a consent-activated native engine pack from one pinned upstream commit."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import zipfile
from pathlib import Path
from signing import add_arguments, sign_engine_files, validate_options

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'c75f446c44cd3f0742035a1394416c39bee5ea8f'
VERSION = '7.1.2'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    add_arguments(parser, engine=True)
    args = parser.parse_args()
    validate_options(args, sys.platform)
    source = args.source.resolve()
    system, machine = platform.system(), platform.machine().lower()
    if (system, machine) not in {('Darwin', 'arm64'), ('Darwin', 'x86_64'), ('Linux', 'x86_64')}:
        raise SystemExit('This pack supports macOS arm64/x86_64 and Linux x86_64 only')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    clean = subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip()
    if commit != UPSTREAM or clean:
        raise SystemExit('Expected a clean checkout of the pinned upstream commit')
    subprocess.run(['make', '-j', '4'], cwd=source, check=True)
    version = subprocess.check_output([str(source / 'hashcat'), '--version'], cwd=source, text=True).strip()
    if version != 'v' + VERSION:
        raise SystemExit('Unexpected engine version: ' + version)
    # These read-only queries also load the document/archive modules without a GPU.
    for mode in ('10400', '10500', '10600', '10700', '9500', '9600', '13600', '17200'):
        subprocess.run([str(source / 'hashcat'), '--hash-info', '-m', mode], cwd=source,
                       check=True, stdout=subprocess.DEVNULL)
    output = ROOT / 'component_pack'
    output.mkdir(exist_ok=True)
    archive = output / 'hashcat.zip'
    folders = ('OpenCL', 'modules', 'bridges', 'charsets', 'layouts', 'masks', 'rules', 'tunings', 'docs', 'deps')
    files = [source / 'hashcat', source / 'hashcat.hcstat2']
    for name in folders:
        files.extend(p for p in (source / name).rglob('*') if p.is_file())
    if not (source / 'docs/license.txt').is_file() or not (source / 'modules/module_10400.so').is_file():
        raise SystemExit('Missing engine modules or upstream notices')
    signed_count = sign_engine_files(files, args.macos_identity, args.macos_team_id) if args.macos_identity else 0
    if signed_count:
        for mode in ('10400', '10500', '10600', '10700', '9500', '9600', '13600', '17200'):
            subprocess.run([str(source / 'hashcat'), '--hash-info', '-m', mode], cwd=source,
                           check=True, stdout=subprocess.DEVNULL)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as pack:
        for path in sorted(files):
            if path.is_symlink():
                raise SystemExit('Unexpected upstream symlink: ' + str(path))
            relative = path.relative_to(source).as_posix()
            if '/.git/' in '/' + relative or path.suffix in ('.o', '.a'):
                continue
            item = zipfile.ZipInfo('hashcat-' + VERSION + '/' + relative, (2025, 8, 23, 0, 0, 0))
            item.create_system = 3
            item.external_attr = (0o100755 if relative == 'hashcat' else 0o100644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            pack.writestr(item, path.read_bytes())
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = {'schema': 1, 'version': VERSION, 'system': system, 'machine': machine,
                'source_commit': UPSTREAM, 'size': archive.stat().st_size,
                'sha256': digest,
                'minimum_os': '15.0' if system == 'Darwin' else 'glibc 2.35',
                'module_queries_passed': 8, 'gpu_compute_tested': False,
                'signing_team': args.macos_team_id if signed_count else None,
                'signed_binaries': signed_count}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()

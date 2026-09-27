"""Opt-in, bounded correctness check using only an ephemeral synthetic PDF."""
from __future__ import annotations

import io
import os
import secrets
import shutil
import subprocess
import time

from document_worker import check_workspace, end_process
from runtime import engine_environment
from temporary_data import private_workspace, prepare_child, record_child

TIMEOUT = 120
LOG_LIMIT = 8 * 1024 * 1024


def engine_identity(engine):
    if not engine:
        return None
    try:
        info = engine.stat()
        return (str(engine.resolve()), info.st_size, info.st_mtime_ns)
    except OSError:
        return None


def synthetic_input(work):
    from pypdf import PdfReader, PdfWriter
    from pdf_tools import extract_hash
    from reportlab.pdfgen import canvas
    password = 'LoxmitTest' + secrets.token_hex(8)
    plain = io.BytesIO()
    page = canvas.Canvas(plain, pagesize=(72, 72))
    page.drawString(5, 36, 'Loxmit test')
    page.showPage()
    page.save()
    # ReportLab supplies the 16-byte file ID required by Hashcat's legacy PDF mode.
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(plain.getvalue())))
    try:
        writer.encrypt(password, algorithm='RC4-40')
        source = io.BytesIO()
        writer.write(source)
    finally:
        writer.close()
    source.seek(0)
    digest, mode = extract_hash(PdfReader(source))
    assert mode == 10400
    (work / 'test.hash').write_text(digest + '\n', encoding='ascii')
    (work / 'test.words').write_text('LoxmitWrongCandidate\n' + password + '\n', encoding='ascii')
    return password.encode('ascii').hex()


def run_compute(engine, root, device, stop, *, timeout=TIMEOUT):
    started = time.monotonic()
    result = {'state': 'error', 'device': dict(device), 'mode': 10400, 'compute_tested': False}
    try:
        if shutil.disk_usage(root).free < 64 * 1024 * 1024:
            raise ValueError('診断用の空き容量が不足しています。')
        with private_workspace(root, 'gpucheck') as work:
            expected = synthetic_input(work)
            command = [str(engine), '-m', '10400', '-a', '0', str(work / 'test.hash'),
                       str(work / 'test.words'), '-d', str(device['id']), '-D', '2', '-w', '1',
                       '--runtime=10', '--hwmon-temp-abort=75', '--potfile-disable',
                       '--restore-disable', '--logfile-disable', '--outfile-format=3',
                       '--session', 'loxmit-check-' + work.name[-32:],
                       '--outfile', str(work / 'found.hex')]
            with (work / 'engine.log').open('wb') as log:
                if stop.is_set():
                    raise InterruptedError()
                prepare_child(work)
                process = subprocess.Popen(command, cwd=engine.parent, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT,
                                           env=engine_environment(root), close_fds=True,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                           start_new_session=os.name != 'nt')
                try:
                    record_child(work, process.pid)
                    while process.poll() is None:
                        if stop.wait(.05):
                            raise InterruptedError()
                        if time.monotonic() - started >= timeout:
                            raise TimeoutError()
                        check_workspace(work, limit=LOG_LIMIT, max_entries=20)
                    if stop.is_set():
                        raise InterruptedError()
                    check_workspace(work, limit=LOG_LIMIT, max_entries=20)
                    result['code'] = process.returncode
                    found = work / 'found.hex'
                    if (process.returncode == 0 and found.is_file() and found.stat().st_size <= 1024
                            and found.read_text(encoding='ascii').strip() == expected):
                        result.update(state='passed', compute_tested=True,
                                      message='テスト用PDFの照合に成功しました。')
                    else:
                        result['message'] = '計算結果を確認できませんでした。部品・ドライバーの状態を確認してください。'
                        log.flush()
                        with (work / 'engine.log').open('rb') as source:
                            diagnostic = source.read(16384).decode('utf-8', errors='replace')
                        result['details'] = '\n'.join(line for line in diagnostic.splitlines()
                                                      if '$pdf$' not in line and 'Candidates.' not in line)[-4000:].replace(str(work), '[test]')
                finally:
                    end_process(process, [])
    except InterruptedError:
        result.update(state='cancelled', message='計算テストを中止しました。')
    except TimeoutError:
        result.update(state='timeout', message='準備を含む120秒の上限に達しました。初回のコンパイルに時間がかかる場合があります。')
    except Exception as error:
        result['message'] = str(error) if isinstance(error, ValueError) else '計算テストを実行できませんでした。'
    result.update(seconds=round(time.monotonic() - started, 2), checked_at=time.time())
    return result

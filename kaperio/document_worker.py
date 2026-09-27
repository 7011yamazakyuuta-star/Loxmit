"""Isolated, cancellable document operations with bounded resource supervision."""
from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import psutil

MEMORY_LIMIT = 2 * 1024**3
OUTPUT_LIMIT = 1024**3
RESULT_LIMIT = 16 * 1024**2
REQUEST_LIMIT = 64 * 1024
TASK_TIMEOUT = 120
EXPORT_TIMEOUT = 300


def check_workspace(work, limit=OUTPUT_LIMIT, max_entries=10000):
    pending, size, count = [work], 0, 0
    while pending:
        try:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    count += 1
                    if count > max_entries:
                        raise ValueError('Temporary file count exceeds the limit.')
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                        raise ValueError('Temporary file links are not supported.')
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(entry.path)
                    elif stat.S_ISREG(info.st_mode):
                        size += info.st_size
                    else:
                        raise ValueError('Unexpected temporary file type.')
                    if size > limit:
                        raise ValueError('Temporary output exceeds the size limit.')
        except FileNotFoundError:
            continue


def write_json(path, value):
    raw = json.dumps(value, ensure_ascii=True).encode('ascii')
    if len(raw) > RESULT_LIMIT:
        raise ValueError('Document result exceeds the metadata limit.')
    temp = path.with_suffix('.tmp')
    temp.write_bytes(raw)
    # Windows readers briefly deny replacement; never publish a partial JSON record.
    deadline = time.monotonic() + 1
    while True:
        try:
            temp.replace(path)
            break
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.01)


def read_json(path):
    with path.open('rb') as stream:
        raw = stream.read(RESULT_LIMIT + 1)
    if len(raw) > RESULT_LIMIT:
        raise ValueError('Document result exceeds the metadata limit.')
    return json.loads(raw)


def worker_main():
    from document_limits import apply_limits, input_stream
    request = json.loads(input_stream().read(REQUEST_LIMIT + 1))
    work = Path(request['work'])
    try:
        apply_limits(request['memory'], request['timeout'], OUTPUT_LIMIT)
        # Native helpers and Python libraries share the supervised private workspace.
        tempfile.tempdir = str(work)
        for name in ('TMP', 'TEMP', 'TMPDIR'):
            os.environ[name] = str(work)
        from formats import inspect_file, unlock_file, contents, get_hash
        from pdf_tools import preview_png, export_pdf
        operation, args = request['operation'], request['args']
        source = Path(args['source'])
        output = work / ('output' + args.get('suffix', '.bin'))
        result = None
        if operation == 'inspect':
            result = inspect_file(source, args['extension'], args.get('zip2john'))
        elif operation == 'unlock':
            password = bytes.fromhex(args['password_hex']) if 'password_hex' in args else args['password']
            pages = unlock_file(source, password, output, args['info'])
            result = {'pages': pages, 'contents': contents(output, args['info'])
                      if args['info']['format'] != 'pdf' else []}
        elif operation == 'hash':
            result = get_hash(source, args['info'], Path(args['hashcat']), args.get('zip2john'))
        elif operation == 'preview':
            output.write_bytes(preview_png(source, args['page']))
        elif operation == 'export':
            export_pdf(source, output, args['kind'], args['dpi'], args['gray'],
                       lambda n, total: write_json(work / 'progress.json', [n, total]), lambda: False)
        else:
            raise ValueError('Unknown document operation.')
        write_json(work / 'result.json', {'ok': True, 'result': result})
    except MemoryError:
        write_json(work / 'result.json', {'ok': False, 'error': '文書処理がメモリー上限に達しました。'})
    except Exception as exc:
        write_json(work / 'result.json', {'ok': False, 'error': str(exc)[:1000]})


def worker_command():
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--document-worker']
    return [sys.executable, str(Path(__file__).resolve())]


def worker_environment(work):
    # Inheritance reduction, not an OS sandbox: the same user can still read files.
    allowed = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'LANG', 'LC_ALL', 'LC_CTYPE',
               '_PYI_ARCHIVE_FILE', '_PYI_APPLICATION_HOME_DIR', '_PYI_PARENT_PROCESS_LEVEL',
               '_PYI_SPLASH_IPC'}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    if os.name == 'nt':
        system = Path(os.environ['SystemRoot'])
        env['PATH'] = os.pathsep.join(map(str, (system / 'System32', system)))
    else:
        env['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
    # PyInstaller needs its own library directory, not arbitrary preload/search hooks.
    if getattr(sys, 'frozen', False) and sys.platform.startswith('linux'):
        env['LD_LIBRARY_PATH'] = str(Path(sys._MEIPASS))
    env.update({name: str(work) for name in ('TMP', 'TEMP', 'TMPDIR', 'HOME', 'USERPROFILE')})
    env['PYTHONNOUSERSITE'] = '1'
    return env


def end_process(process, children):
    try:
        current = psutil.Process(process.pid).children(recursive=True)
        children = list({p.pid: p for p in children + current}.values())
    except psutil.NoSuchProcess:
        pass
    if os.name != 'nt':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for child in reversed(children):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)
    psutil.wait_procs(children, timeout=3)


class DocumentWorker:
    def __init__(self, root, *, memory=MEMORY_LIMIT, timeout=TASK_TIMEOUT):
        self.root = Path(root)
        self.memory = memory
        self.timeout = timeout
        self.slot = threading.BoundedSemaphore(1)
        self.closed = threading.Event()

    def close(self):
        self.closed.set()
        # The supervisor polls cancellation even if a native parser is stuck.
        with self.slot:
            pass

    def run(self, operation, args, *, target=None, cancelled=lambda: False,
            progress=None, timeout=None, preview=False):
        timeout = self.timeout if timeout is None else timeout
        started = time.monotonic()

        def check():
            if self.closed.is_set() or cancelled():
                raise InterruptedError('文書処理を中止しました。')
            if time.monotonic() - started >= timeout:
                raise ValueError('文書処理が時間上限に達しました。ファイルを分割してお試しください。')

        check()
        while not self.slot.acquire(timeout=.05):
            check()
            if preview:
                raise ValueError('文書を処理中です。プレビューは完了後に表示できます。')
        try:
            check()
            with tempfile.TemporaryDirectory(prefix='.document-', dir=self.root) as temporary:
                work = Path(temporary)
                request = json.dumps({'work': str(work), 'operation': operation, 'args': args,
                                      'memory': self.memory, 'timeout': timeout}).encode('utf-8')
                if len(request) > REQUEST_LIMIT:
                    raise ValueError('文書処理の入力が上限を超えています。')
                flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                env = worker_environment(work)
                process = subprocess.Popen(worker_command(), stdin=subprocess.PIPE,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           creationflags=flags, start_new_session=os.name != 'nt',
                                           cwd=work, env=env, close_fds=True)
                children, last_progress = [], None
                def send_request():
                    try:
                        process.stdin.write(request)
                        process.stdin.close()
                    except (OSError, ValueError):
                        pass
                sender = threading.Thread(target=send_request, daemon=True)
                try:
                    # Passwords travel over an anonymous pipe, never argv or a request file.
                    sender.start()
                    observed = psutil.Process(process.pid)
                    while process.poll() is None:
                        check()
                        try:
                            live = observed.children(recursive=True)
                            children = list({p.pid: p for p in children + live}.values())
                            rss = observed.memory_info().rss
                            for child in live:
                                try:
                                    rss += child.memory_info().rss
                                except psutil.NoSuchProcess:
                                    pass
                            if rss > self.memory:
                                raise ValueError('文書処理がメモリー上限に達しました。')
                        except psutil.NoSuchProcess:
                            pass
                        check_workspace(work)
                        if progress and (work / 'progress.json').exists():
                            current = read_json(work / 'progress.json')
                            if current != last_progress:
                                progress(*current)
                                last_progress = current
                        time.sleep(.05)
                    check()
                    check_workspace(work)
                    if process.returncode or not (work / 'result.json').exists():
                        raise ValueError('文書処理が終了しました。破損、または処理上限超過の可能性があります。')
                    result = read_json(work / 'result.json')
                    if not result['ok']:
                        raise ValueError(result['error'])
                    if progress and (work / 'progress.json').exists():
                        current = read_json(work / 'progress.json')
                        if current != last_progress:
                            progress(*current)
                    output = work / ('output' + args.get('suffix', '.bin'))
                    if target or preview:
                        if output.stat().st_size > (32 * 1024**2 if preview else OUTPUT_LIMIT):
                            raise ValueError('書き出しサイズが上限を超えました。')
                        check()
                        if preview:
                            return output.read_bytes()
                        output.replace(target)
                    return result['result']
                finally:
                    end_process(process, children)
                    sender.join(timeout=3)
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
        finally:
            self.slot.release()

    def inspect_file(self, source, extension, zip2john=None, cancelled=lambda: False):
        return self.run('inspect', {'source': str(source), 'extension': extension,
                                   'zip2john': str(zip2john) if zip2john else None}, cancelled=cancelled)

    def unlock_file(self, source, password, target, info, cancelled=lambda: False):
        args = {'source': str(source), 'info': info, 'suffix': info['extension']}
        args.update({'password_hex': password.hex()} if isinstance(password, bytes) else {'password': password})
        return self.run('unlock', args, target=target, cancelled=cancelled)

    def get_hash(self, source, info, hashcat, zip2john=None, cancelled=lambda: False):
        return self.run('hash', {'source': str(source), 'info': info, 'hashcat': str(hashcat),
                                'zip2john': str(zip2john) if zip2john else None}, cancelled=cancelled)

    def preview_png(self, source, page):
        return self.run('preview', {'source': str(source), 'page': page, 'suffix': '.png'}, preview=True)

    def export_pdf(self, source, target, kind, dpi, gray, progress, cancelled):
        return self.run('export', {'source': str(source), 'kind': kind, 'dpi': dpi, 'gray': gray,
                                  'suffix': target.suffix}, target=target, progress=progress,
                        cancelled=cancelled, timeout=EXPORT_TIMEOUT)


if __name__ == '__main__':
    worker_main()

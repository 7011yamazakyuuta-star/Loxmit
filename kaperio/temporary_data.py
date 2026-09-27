"""Conservative cleanup of app-owned scratch data, never document libraries."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path

import psutil

MARKER = '.loxmit-temporary.json'
PURPOSES = {'upload', 'document', 'gpucheck'}


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def identity(pid):
    process = psutil.Process(pid)
    return {'pid': pid, 'created': process.create_time()}


def alive(record):
    if (not isinstance(record, dict) or type(record.get('pid')) is not int
            or record['pid'] <= 0 or type(record.get('created')) not in (int, float)):
        raise ValueError('Invalid process identity')
    try:
        return psutil.Process(record['pid']).create_time() == record['created']
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


def safe_tree(path):
    """Refuse links, junctions, special files and unexpectedly large inventories."""
    pending, size, count = [Path(path)], 0, 0
    while pending:
        item = pending.pop()
        info = item.lstat()
        count += 1
        if count > 20000 or stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Unsafe temporary tree')
        if stat.S_ISDIR(info.st_mode):
            pending.extend(item.iterdir())
        elif stat.S_ISREG(info.st_mode):
            size += info.st_size
        else:
            raise ValueError('Unexpected temporary file')
    return size


def prepare_child(work):
    path = work / MARKER
    value = json.loads(path.read_text(encoding='utf-8'))
    # A crash between spawn and recording its PID must not authorize deletion.
    value['spawn_pending'] = True
    atomic_json(path, value)


def record_child(work, pid):
    path = work / MARKER
    value = json.loads(path.read_text(encoding='utf-8'))
    try:
        value['children'].append(identity(pid))
    except psutil.NoSuchProcess:
        pass
    value['spawn_pending'] = False
    atomic_json(path, value)


@contextmanager
def private_workspace(root, purpose):
    if purpose not in PURPOSES:
        raise ValueError('Unknown scratch purpose')
    root = Path(root).resolve()
    path = root / ('.' + purpose + '-' + uuid.uuid4().hex)
    path.mkdir(mode=0o700)
    try:
        atomic_json(path / MARKER, {'schema': 1, 'name': path.name, 'purpose': purpose,
                                  'owner': identity(os.getpid()), 'children': [], 'spawn_pending': False})
        yield path
    finally:
        try:
            safe_tree(path)
            shutil.rmtree(path)
        except (OSError, ValueError):
            # Keep the marker for the next startup; do not mask the operation error.
            pass


def cleanup_stale(root):
    """Caller must hold the library instance lock. Unknown data is left untouched."""
    root = Path(root).resolve()
    result = {'removed': 0, 'bytes': 0, 'skipped': 0}
    candidates, in_use = [], False
    for path in root.iterdir():
        if not re.fullmatch(r'\.(upload|document|gpucheck)-[0-9a-f]{32}', path.name):
            continue
        try:
            if path.is_symlink() or path.resolve().parent != root:
                raise ValueError('Invalid temporary path')
            size = safe_tree(path)
            marker = path / MARKER
            if marker.stat().st_size > 16384:
                raise ValueError('Invalid marker size')
            value = json.loads(marker.read_text(encoding='utf-8'))
            if (value.get('schema') != 1 or value.get('name') != path.name
                    or value.get('purpose') not in PURPOSES
                    or not path.name.startswith('.' + value['purpose'] + '-')
                    or value.get('spawn_pending') is not False
                    or not isinstance(value.get('children'), list)):
                raise ValueError('Invalid marker')
            if alive(value['owner']) or any(alive(child) for child in value['children']):
                in_use = True
            candidates.append((path, size))
        except (OSError, ValueError, KeyError, TypeError):
            result['skipped'] += 1
            # An unconfirmed child may still hold an upload in another workspace.
            in_use = True
    if in_use:
        result['skipped'] += len(candidates)
        return result
    for path, size in candidates:
        try:
            safe_tree(path)
            shutil.rmtree(path)
            result['removed'] += 1
            result['bytes'] += size
        except (OSError, ValueError):
            result['skipped'] += 1
    return result

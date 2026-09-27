"""Synthetic process failures for supervisor regression tests; not a runtime action."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

request = json.load(sys.stdin)
root = Path(request['work'])
mode = sys.argv[1]
if mode == 'private_temp':
    with tempfile.TemporaryDirectory() as directory:
        nested = Path(directory)
        (nested / 'synthetic-secret').write_text('private fixture')
        Path('relative-output').write_text('private fixture')
        # macOS /var and /private/var can name the same directory.
        private = nested.resolve().is_relative_to(root.resolve()) and Path.cwd().samefile(root)
        private = private and 'LOXMIT_TEST_PRIVATE_TOKEN' not in os.environ
        (root / 'result.json').write_text(json.dumps({'ok': True, 'result': {'private': private}}))
    sys.exit(0)
if mode == 'os_limit':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from document_limits import apply_limits
    apply_limits(128 * 1024 * 1024, 10, 1024 * 1024)
    try:
        allocation = bytearray(256 * 1024 * 1024)
        message = 'allocation unexpectedly succeeded'
    except MemoryError:
        message = 'OS memory limit enforced'
    (root / 'result.json').write_text(json.dumps({'ok': False, 'error': message}))
    sys.exit(0)
if mode == 'crash':
    (root / 'output.pdf').write_bytes(b'incomplete')
    os._exit(23)
if mode == 'tree':
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
    Path(request['args']['source']).write_text(json.dumps([os.getpid(), child.pid]))
if mode == 'memory':
    allocation = bytearray(32 * 1024 * 1024)
time.sleep(20)

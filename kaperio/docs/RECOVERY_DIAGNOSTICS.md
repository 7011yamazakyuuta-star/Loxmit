# Recovery, diagnostics and temporary data

## Startup recovery

- In-progress job states become paused, locked or ready on restart, depending on
  the saved plan and output. The corrected state is atomically persisted.
- Settings and job JSON use a unique temporary file, flush/fsync and replacement.
  A failed write preserves the previous committed file. This is not a guarantee
  against every filesystem or hardware failure; there is no transactional database.
- After the single-instance lock is acquired, only new `.upload-`, `.document-`
  and `.gpucheck-` directories with a matching versioned marker are eligible for
  cleanup. Owners and recorded worker PIDs are bound to process creation times.
- A live owner/worker, unconfirmed spawn, link/junction, malformed marker or
  access failure prevents cleanup. Related uploads are retained together with
  worker scratch data. Unmarked legacy directories are never auto-deleted.
- Original/imported documents, unlocked outputs, hints, candidates and resume
  checkpoints are not part of this cleanup. No recovery automatically restarts.
- The settings storage section reports interrupted jobs and cleanup counts.
  Process identity checks are conservative crash recovery, not an adversarial
  filesystem sandbox or guaranteed containment of every orphaned descendant.
  Same-user processes can still access files and network. Full OS sandboxing
  and app-wide storage encryption remain unimplemented.

## GPU computation check

- Explicit local authenticated POST only; opening the app/catalog does not run it.
- Uses a generated PDF with a known random test password and two candidates.
  Neither the API nor the test accepts a user document, hash, command or wordlist.
- GPU ID must come from the current engine's successful enumeration. A changed
  executable identity requires another diagnosis. CPU-only devices are rejected.
- Hashcat mode 10400, workload 1, 10-second runtime and 120-second outer deadline
  including compilation. Abort temperature 75 C where telemetry is available.
  Hashcat's normal self-test remains enabled; no `--force` or safety bypass.
- Only an exact answer and successful process exit qualify as passed. Failure,
  timeout and cancellation are distinct. Log output is bounded; test hashes and
  candidate lines are excluded from the displayed diagnostic excerpt.
- Potfile, restore and Hashcat log are disabled. Scratch files are removed after
  completion, failure or cancellation. Driver/compiler caches outside the private
  workspace may remain and are not indiscriminately deleted.
- This is a correctness smoke test for one PDF mode, not sustained stability,
  a benchmark, support for all formats, or a guarantee of password recovery.

Official option and format references (checked 2026-09-27):
[Hashcat 7.1.2 options](https://hashcat.net/wiki/doku.php?id=hashcat) and
[mode 10400 parser](https://github.com/hashcat/hashcat/blob/v7.1.2/src/modules/module_10400.c).

## Storage policy for development

- Unit tests use temporary directories. Browser acceptance removes its synthetic
  library after stopping the test server; only the latest named screenshots remain
  in `.test-results/browser`. `KAPERIO_KEEP_TEST_DATA=1` explicitly retains fixtures.
- Large-document tests default to temporary fixtures unless an existing fixture
  directory is explicitly supplied. JSON measurement reports are retained.
- Published release archives and duplicate expanded builds can be removed locally
  after verification. Keep the active installation and one rollback bundle.
  Do not apply development cleanup to the user's application library or Downloads.

## Local evidence

2026-09-27 Windows / Hashcat 7.1.2 / NVIDIA GeForce RTX 4060 Laptop GPU:
OpenCL computation check passed with an exact answer in 5.03 seconds including
preparation, and its scratch directory was removed. This duration is not a speed
benchmark. CUDA, Intel GPU, macOS and Linux hardware computation are not measured
by this record. Hosted tests use synthetic process fixtures, not physical GPUs.

The local alpha.12 frozen EXE also passed the authenticated HTTP diagnostic flow
in 2.59 seconds and left no GPU scratch directory. Windows regression: 122 tests,
121 passed and one explicit symlink-privilege skip; 26 frozen acceptance groups;
56 browser groups including opt-in/cancel/result and 320/390/768/1440px GPU UI.
Browser synthetic libraries were removed after the runs; screenshots are retained.

Optional physical-GPU validation (not run automatically in CI):

```powershell
.venv/Scripts/python.exe tests/gpu_hardware.py --executable dist/Loxmit/Loxmit.exe --hashcat <absolute-hashcat-path> --device 1 --report .test-results/gpu.json
```

Fault tests cover hard-killed temporary owners, live owners/children, unconfirmed
spawn, invalid markers, permission failure, interrupted job persistence and disk
full during JSON commit. Actual power loss, OS sleep/resume and adversarial
same-user filesystem races are not claimed as verified.

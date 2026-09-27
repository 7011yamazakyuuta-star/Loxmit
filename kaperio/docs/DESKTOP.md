# Loxmit Desktop 0.4.0-alpha.11

Storage protection checks and signing preparation are described in
[SECURITY_READINESS.md](SECURITY_READINESS.md) and [SIGNING.md](SIGNING.md).
Certificates have not been provisioned: ordinary CI builds remain unsigned
(macOS uses ad-hoc signatures) and unnotarized. Each new native archive has a
`.security.json` sidecar stating the requested build's verified signing scope;
this sidecar is informational, not an independent cryptographic attestation.

Document operations now use disposable, resource-limited workers. See
[hardening boundaries](HARDENING.md); earlier native validation is not a result
for this version. Consult the release's linked CI run for the exact build.

Formerly Kaperio. The public repository is now `7011yamazakyuuta-star/Loxmit`.
Internal source directories, legacy launchers and Hashcat session identifiers
remain compatible to preserve existing data and checkpoints. See `design-qa.md` for the v0.4 validation boundary;
earlier native-runner results do not automatically validate a new release.

## Downloads

Native bundles are published on [GitHub Releases](https://github.com/7011yamazakyuuta-star/Loxmit/releases).
An operating-system build is only published after its frozen executable smoke test passes.
The source ZIP is independent of the native bundles. No app store is required.

| Platform | Package | Launch | Status boundary |
|---|---|---|---|
| Windows x86-64 | ZIP | `Loxmit.exe` | Local Windows testing; GPU tested separately |
| macOS 15+ Apple Silicon | ZIP containing `.app` | `Loxmit.app` | Native hosted build/smoke, not physical GPU validation |
| macOS 15+ Intel | ZIP containing `.app` | `Loxmit.app` | Native hosted build/smoke, not physical GPU validation |
| Linux x86-64 | tar.gz | `Loxmit/Loxmit` | Requires Ubuntu 22.04 build; glibc >= 2.35, not every distro |

These are portable application bundles, not a single standalone executable and not installers.
Keep all files together. The app starts a local HTTP service and opens the default browser.
Python and application libraries are included; the browser, GPU driver, zip2john,
and Office/LibreOffice are not included. Known-password decryption does not require Hashcat.
Windows x86-64 can optionally download Hashcat and, when diagnosed as missing,
NVIDIA NVRTC through the consent-based [setup guide](SETUP.md). Drivers are never
installed or changed. macOS/Linux native bundles include a pinned-source native
Hashcat pack, activated only after consent without extra downloads or development
tools. This is not an upstream official macOS binary package. See `SETUP.md`.
PDF raster export and image-based Word export work without Office. Office-to-PDF needs
an installed Microsoft Office (Windows) or LibreOffice (all supported desktop systems).

Windows executables are unsigned. macOS bundles have only build-tool ad-hoc signing,
not an Apple Developer ID signature and not notarization. OS reputation/Gatekeeper
warnings are expected. Do not disable security software or system-wide security checks.
For managed machines follow the administrator's policy. Signing requires the owner's
certificates/account and is outside this alpha release.

## Local data

Each imported file may be up to 200 MiB (209,715,200 bytes), shown as 200MB in
the interface. This is a per-file limit, not a library total. Parsing and conversion
can require more memory than the input file size.
Uploads and downloads use 1 MiB chunks. One import runs at a time, without blocking
the library status lock during transfer or inspection. Uploads require space for the
input plus a 64 MiB reserve; conversion outputs can require substantially more.
Interrupted or timed-out transfers remove their temporary staging directory.
See `LARGE_FILES.md` for the measured workloads and remaining limits.

- Windows: `%LOCALAPPDATA%/Loxmit`
- macOS: `~/Library/Application Support/Loxmit`
- Linux: `$XDG_DATA_HOME/loxmit`, or `~/.local/share/loxmit`
- Override with `--data DIRECTORY`; source launches retain `outputs/kaperio`.

The application retains imported copies, recovery inputs, checkpoints, and plaintext outputs.
Protect this directory. It is never included in release bundles. If the old Kaperio
directory exists and the new Loxmit directory does not, it is reused in place.
Nothing is automatically moved or deleted. Renaming Hiraku does not
automatically move or delete old user data; use `--data` explicitly to reuse an old library.
The original documents are not modified. Use the app's power button to stop its service.

After opening a protected document, its password is visible in a prominent result
field by default. Copy is an explicit action, with success or failure feedback;
the eye control optionally hides the value. Hiding it does not disable copying.
The result remains transient: no password persistence is added, and restarting
the service clears the in-memory password even when an unlocked file is retained.

New libraries start with zero files. Demo documents and browser test fixtures are
not bundled or imported at startup. Development/test libraries are never selected
by shipped launchers. Use the same data directory when launching from a shortcut
and when launching the executable directly.

Settings now separate availability, engine discovery/manual paths, GPU query and
library location. Auto-detection only checks environment/PATH and nearby tool
directories; it does not scan the disk, download tools, execute them or save changes.
Manual paths are validated before saving. A GPU query of an edited path explicitly
saves it first. A successful device query is not a performance or recovery test.

## Hashcat and optimization

The official latest stable release verified on 2026-09-24 is
[Hashcat 7.1.2](https://github.com/hashcat/hashcat/releases/tag/v7.1.2), published 2025-08-23.
The official `hashcat-7.1.2.7z` SHA-256 is
`80db0316387794ce9d14ed376da75b8a7742972485b45db790f5f8260307ff98`.
Set the executable in Settings, or use `LOXMIT_HASHCAT` (`KAPERIO_HASHCAT` remains supported). Use a native executable and
the complete upstream installation for your OS, not another OS's binary.
On macOS Hashcat support still depends on the OS/GPU/backend supported by upstream.

Loxmit uses upstream kernels unchanged. Auto mode requests `-O` for supported PDF
modes only when every candidate in the stage is at most 16 UTF-8 bytes.
No candidate is silently removed to improve speed.
PDF R6 mixed lists split when at least 65,536 base words fit the optimized bound;
short words use the optimized kernel and long words retain the pure kernel.
Smaller lists and other modes stay in one process to avoid extra startup costs.
The pure option allows comparison. Office and ZIP retain their normal kernels.
Hashcat performs its own device-specific autotuning on each run; Loxmit does not
hardcode device acceleration, loop counts, or clock speeds. Higher workload settings
remain user-selectable and may affect responsiveness. No profile is fastest on every GPU.
Default workload 1 and temperature abort at 80 C remain in place. No `--force`,
overclocking, driver replacement, or thermal-protection bypass is used.

`tests/benchmark.py` compares pure CLI, identically configured optimized CLI, and the
Kaperio runner using equal candidate sets. Each profile runs three times in rotated
order, using the same device, mode, workload, and thermal limit. Initial samples are
discarded. Thermal warnings are retained. This distinguishes upstream optimization
benefits from application overhead; it does not prove superiority over tuned Hashcat.

## Recovery methods

- Automatic interview (default): optional remembered words/numbers, unknown or bounded
  length, unknown or selected character classes, and certain ASCII prefix/suffix.
  Exact memories come first, followed by ASCII case/substitution variants, pairs of
  words, numeric/symbol additions, and small bounded ASCII masks. Unknown character
  classes try numeric, lowercase, alphanumeric, and printable ASCII subsets in order.
  No external service or language model receives hints. Draft answers are separate
  per file in browser memory; reloading clears unsent drafts.
  Maximum 64 words (127 UTF-8 bytes each), 32 numeric tokens (16 bytes each),
  100,000 generated words and 10,000,000 total planned attempts. Generated-word
  truncation and length exclusions are explicitly reported. Overlapping mask
  stages can repeat candidates; counts are attempts, not unique passwords.
  Numeric additions cover supplied tokens, suffixes 0-99 (also 00-09), prefixes
  0-9, and `!`, `_`, `-`. Word pairs also include a space separator.
  The preview lists the actual subsets before starting. A known long length with
  no useful clues can produce no feasible subset and asks for more clues instead
  of pretending that a full long-password search is practical. Time limits still
  apply across all stages; this is prioritized recovery, not complete coverage.
- Exact dictionary: preserve each UTF-8 candidate, including literal `$HEX[...]` strings.
- Mask: known prefix/suffix, ASCII character classes, total length 1-127.
- Dictionary rules: original/lower/upper/capitalized/toggled ASCII case, each with
  no suffix or a single trailing digit. 55 rule applications per base word;
  duplicates mean the displayed count is an upper bound, not unique passwords.
- Suffix hybrid (`-a 6`): base dictionary plus a 1-127 character mask.
- Prefix hybrid (`-a 7`): a 1-127 character mask plus the base dictionary.
- Guided: deterministic local hints, ordered exact / ASCII case and substitutions /
  supplied numeric tokens and symbols / optional word pairs and deletion/transposition.
  Maximum 64 hints (48 UTF-8 bytes each), 32 tokens (16 bytes), and 100,000 unique
  generated words. Overflow is rejected, not truncated. No probabilistic success
  rate or AI model is claimed. Inputs are not sent to external services.

All use upstream Hashcat engines, time/temperature limits, pause/cancel and checkpoint
handling. Rules are generated from a small built-in set, not executed as shell code.
Combined candidates must be at most 127 UTF-8 bytes; optimized PDF kernels are requested
only when the maximum after rules/masks is at most 16 bytes. ASCII case rules are not
Unicode linguistic case folding. Recovery still depends on the actual password being
inside the selected candidate set. No method decrypts a strong password instantly.
Manual plans exceeding 2^63-1 attempts are rejected before launch. The 127-byte
application ceiling is not a promise that every engine supports that length:
Hashcat 7.1.2 PDF modes [10400](https://github.com/hashcat/hashcat/blob/v7.1.2/src/modules/module_10400.c)
and [10500](https://github.com/hashcat/hashcat/blob/v7.1.2/src/modules/module_10500.c)
declare a 32-byte maximum. Automatic plans exclude over-limit variants with a
notice; manual plans reject them. Other runtime kernel length limits stop a stage
with an explicit error instead of reporting silently rejected candidates as searched.
Japanese words use UTF-8 and may occupy several bytes per character; generated ASCII
masks do not enumerate Japanese characters. Long complete phrases remain eligible.

`tests/interview_integration.py --hashcat /absolute/path/to/hashcat` performs opt-in
GPU checks on generated PDFs, including long hints, a long prefix with one unknown
character, and a 127-byte phrase. It never opens documents from the user's library.

Completed stages are atomically checkpointed locally. The active stage uses its own
Hashcat restore file. Resume verifies a digest of the source hash, plan, candidate
list and executable path/size/mtime. A legacy root restore file remains supported.
Progress across stages is candidate-weighted; amplification/duplicate rules can make
it an upper-bound estimate, not a count of unique passwords. A new time budget applies
on each explicit resume. Generated candidates are removed after successful recovery.

Optional workload auto measurement uses the actual attack and all its candidates;
it does not replace the canonical search with a sample. It runs workloads 1,2,3,3,2,1
for up to 12 wall seconds each, discarding the first 3 seconds of speed samples.
It requires >= 1,000,000 candidates and >= 120 seconds remaining to start.
Trial results that find the password or exhaust the stage are honored immediately.
Otherwise the full stage is searched again, so some candidates repeat. Trial time
counts against the overall limit. Pause/cancel and temperature abort remain active.
At least four post-warmup samples per trial, two usable trials per workload, <=20%
repeat variation, no throttling warning and temperature below min(limit-5,75 C) are
required. A >=10% speed gain is required to raise load; within 5% of the best score,
prefer the lower load. Missing thermal telemetry falls back to workload 1.
Measurements are local to a stage/job, not a portable GPU profile or a universal
fastest guarantee. Tuning itself does not install drivers or backends. Optional
component activation is a separate consent-based setup operation.

## Build and verify

Run these commands from `kaperio` on the target OS in a clean Python 3.13 environment.
CI uses 3.13.15, whose native builds are available on all four targets. Local Windows
development also tests 3.12.14. Runtime versions are listed inside each artifact.
Intel macOS builds cryptography 50.0.1 with `OPENSSL_STATIC=1` and the Homebrew
OpenSSL prefix to isolate it from Python's OpenSSL. Upstream Intel wheels are not
available for this version. This extra build step follows
[cryptography's macOS instructions](https://cryptography.io/en/latest/installation/#building-cryptography-on-macos).

```text
python -m pip install -r requirements-dev.txt -c requirements-tested.txt pyinstaller==6.22.3
python -m unittest discover -s tests -p "test_*.py" -v
```

On macOS 15+ or Linux x86-64, prepare the native pack before the desktop build.
Developer builds need a compiler and the pinned upstream checkout; end users do not.
From the `kaperio` directory:

```text
git clone https://github.com/hashcat/hashcat.git ../.upstream-hashcat
git -C ../.upstream-hashcat checkout c75f446c44cd3f0742035a1394416c39bee5ea8f
python scripts/build_engine_pack.py --source ../.upstream-hashcat
```

Then build and test (omit `--native-setup` on Windows):

```text
python scripts/build_desktop.py
python tests/frozen_smoke.py PATH_TO_BUILT_EXECUTABLE --native-setup
```

PyInstaller is not a cross-compiler. The GitHub Actions matrix builds on native runners.
The smoke test launches the packaged executable from an unrelated working directory and
checks authentication, notices, PDF preview, four PDF export formats, the frozen Office
hash helper, byte-preserving DOCX/XLSX/PPTX unlock, ZIP unlock, single instance, and deletion.
Hosted runners do not prove GPU performance, Office automation, or desktop-browser behavior.

Bundles include the exact installed runtime package license/notice files, PDFium native
notices, the Python license, and an inventory. See `licenses/runtime` inside the bundle
and Settings > licenses. The macOS/Linux Hashcat pack retains upstream notices and
dependency sources alongside its runtime files. Other external tools are not included.

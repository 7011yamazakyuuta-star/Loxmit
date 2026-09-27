# Optional setup and GPU diagnostics

Loxmit 0.4.0-alpha.8 includes a dismissible first-run tutorial, GPU diagnostics and
explicitly consented component downloads. Closing the tutorial never blocks
known-password opening or export. Reopen it using the help icon or Settings.
No demo document is added. The tutorial-seen flag is local to the library.

## Scope

- Windows x86-64 automatic downloads use Windows' existing
  system `tar.exe` for the pinned official Hashcat 7z archive. No extra extractor,
  package manager, administrator elevation or installer executable is downloaded.
- macOS 15+ arm64/x86-64 and Linux x86-64 native bundles include a compressed
  Hashcat pack built from upstream 7.1.2 commit
  `c75f446c44cd3f0742035a1394416c39bee5ea8f` on the matching CI runner.
  Consent activates it into the private library; no extra download, Homebrew,
  compiler, system package manager or elevation is needed. Linux is built on
  Ubuntu 22.04 (glibc 2.35). Other architectures/distributions are not validated.
  Windows and source ZIPs do not contain this native pack.
- Drivers, CUDA Toolkit as a whole, Visual Studio, John, Office and LibreOffice
  are never installed or updated. System PATH, registry and GPU settings are not
  modified. Already-configured Hashcat is retained, not upgraded automatically.
- Windows Hashcat comes from the upstream binary archive, with its kernels, modules,
  configuration and complete license notices. Official stable version checked
  on 2026-09-25: 7.1.2, https://hashcat.net/hashcat/.
- Optional NVIDIA component: NVRTC 12.9.86 from NVIDIA's Windows wheel on PyPI,
  76,408,187 download bytes. Only `nvrtc64_120_0.dll`,
  `nvrtc-builtins64_129.dll` and license files are retained. The larger CUDA
  redistribution archive and development headers/static libraries are not used.
  No Python installation or pip invocation is needed by the desktop user.

NVIDIA's [Windows guide](https://docs.nvidia.com/cuda/archive/12.9.1/cuda-installation-guide-microsoft-windows/index.html)
lists its NVRTC wheel, and the [version metadata](https://pypi.org/pypi/nvidia-cuda-nvrtc-cu12/12.9.86/json)
provides the pinned URL, size and SHA-256. NVIDIA's
[version-specific EULA](https://docs.nvidia.com/cuda/archive/12.9.1/eula/index.html)
remains applicable; the components do not become MIT-licensed Loxmit code.
Consent is requested separately for each component, with no checked defaults.
Downloaded component notices remain alongside that component.

## Boundaries

Opening the guide/catalog makes no external request and runs no executable.
An explicit diagnostic action queries OS display adapters and, when configured,
Hashcat `-I`. It does not inspect documents, benchmark, run recovery or modify a
driver. OS detection, backend device enumeration and untested computation are
separate states. An absent inventory result is not proof that no GPU is fitted.
CPU-only and failed backend results are not reported as GPU-ready.

alpha.12 adds a separate opt-in GPU computation check after enumeration. It uses
only a generated synthetic PDF, selects one enumerated GPU, verifies the exact
answer, and removes its scratch data. It is not a throughput benchmark or proof
of support for every format. See [limits and cleanup](RECOVERY_DIAGNOSTICS.md).

NVRTC is offered only after the current configured engine reports missing NVRTC
and OS inventory identifies NVIDIA hardware. It remains optional: a working
OpenCL backend may not need it. Installation is not evidence of successful CUDA
computation; users rerun diagnostics and explicitly run the computation check.
Throughput remains unmeasured by this check.
Driver/GPU compatibility can still prevent use; the app will not fix that by
silently replacing a driver. Only Hashcat child processes receive the private
NVRTC directory in their environment. No process-wide PATH is changed.

Install requests are authenticated, same-origin, loopback-only, and bound to the
built-in catalog revision and one exact component ID. URLs, command lines and
destinations cannot be supplied by clients. HTTPS redirects cannot leave the
original host or TLS port. Exact size and SHA-256 are checked before extraction.
Downloads are streamed with time/size/space limits and cancellation. Temporary
staging is removed on ordinary failure; an abrupt power/process failure can leave
a `.install-*` directory. Existing component directories are not overwritten.
Versioned files are activated only after validation. A settings-save failure can
leave a valid inactive component, which is reused on retry without downloading.
Receipts record the source, digest, license URL, catalog revision and consent time.

Native macOS/Linux packs include kernels, modules, rules, charsets, configuration,
documentation and dependency sources/notices. The build manifest records the
upstream commit, platform, architecture, exact size and SHA-256. A platform/version
mismatch disables activation; checksum, archive paths/types, expanded size and
executable version are checked before configuration. Existing files are preserved.
The pack runs under the same trust boundary as the application, not as a signed
independent updater. This is not upstream's official macOS binary distribution.

NVRTC downloads remain Windows x86-64 only; macOS does not need this CUDA component.
Linux GPU runtime setup remains the user's responsibility. No driver is changed.
Vendor downloads disclose normal request metadata
(such as IP address) to the publisher, never document/password content.

## Verification

`tests/test_setup.py` uses synthetic packages and mocked downloads for consent,
checksum/size mismatch, redirect rejection, cancellation, concurrent operation
guards, disk errors, minimal DLL extraction, existing-file preservation and child
environment isolation. `tests/release-smoke.cjs` tests tutorial dismissal/reopen,
diagnostic interpretation, separate unchecked consent and responsive layouts.
No real NVIDIA EULA is accepted by these fixture tests.

`tests/setup_integration.py --download-hashcat` is an explicitly enabled Windows
network test in a fresh test-only library. It downloads the official pinned
Hashcat archive, verifies it, extracts it, registers it and queries its version
and devices. It does not install NVRTC or run a password search. A successful
run is not a CUDA execution/performance result or native macOS/Linux evidence.

`scripts/build_engine_pack.py` builds the pinned source and checks eight format
modules with `--hash-info`. Native CI runs `tests/frozen_smoke.py --native-setup`
against the packaged app, consents, verifies private activation/executable mode,
queries the engine version and loads those modules again after extraction.
These checks do not establish physical-GPU recovery or performance results.

# Storage protection and isolation

## What is useful

Disk encryption is strongly recommended for sensitive local documents and
password hints, especially on portable/shared machines. It protects storage
against offline access after loss/theft, not malware running as the logged-in
user. Keep the recovery key somewhere separate and recoverable before enabling
OS encryption. The application never changes OS encryption settings, reads keys,
migrates existing data or silently introduces a new master password.

Code signing identifies a publisher and detects changes to signed code. It does
not make document parsing safe or encrypt documents. Public distribution benefits
from signing; personal development can continue without it. See [SIGNING.md](SIGNING.md).

## Read-only storage check

Open Settings > library storage > protection status and choose check. This is
an authenticated, loopback-only POST. Merely opening the dialog does not execute
OS commands. Results are cached in memory for 30 seconds and are not persisted.

- Windows: resolve the actual containing volume with Win32 volume APIs (including
  mount points), then query only BitLocker protection and conversion status via
  CIM. Both active protection and fully completed encryption are required for
  a positive result. Suspended key protection is not reported as protected.
  Access denied, unavailable providers and encryption in progress are unknown.
- macOS: compare the library's filesystem device with the startup Data volume
  before querying `fdesetup status`. External volumes and nonstandard layouts
  are unknown, even if the startup disk has FileVault enabled.
- Linux: inspect `findmnt` and the inverse `lsblk` device tree for an ext4/xfs
  mount. Every storage branch must pass through dm-crypt. Btrfs, ZFS, overlay,
  network mounts and unsupported layouts are unknown. No dm-crypt detected does
  not exclude filesystem-level encryption or another protection mechanism.

Queries have a 12-second deadline each, use structured OS output where available,
never use a shell/elevation, and discard raw errors and device inventories from
the API. No recovery key, file content or password is queried. This is a best-
effort inventory, not a cryptographic configuration/compliance audit. Separate
downloads, exports and backups are not covered by the library-volume result.

## Isolation boundary

The parser worker has the existing time/memory/output budgets and private task
directory. It now inherits only required system/runtime environment variables,
not API tokens, proxy settings, user Python paths or preload hooks. HOME and
temporary locations use its task directory; unnecessary process handles are
closed on launch. Frozen Linux preserves only its bundle's library search path.

This does not change OS user identity or deny filesystem/network syscalls. A
native parser exploit could still access other files as the current user.
Hashcat/GPU and Office/LibreOffice are outside this worker boundary.

Cross-platform privilege isolation needs separate OS policies (for example,
AppContainer on Windows), restricted IPC/file grants, network-denial tests and
compatibility tests for native modules, GPU runtimes and external converters.
It has NOT been implemented or claimed. For hostile documents, use a separate
disposable VM with no shared private folders and no network; do not assume this
application is such a VM. Virtualized GPU availability is a separate limitation.

## Evidence and remaining work

Unit tests cover conservative storage states, caching, authentication, multiple
Linux storage branches, Mac volume scope and worker environment reduction.
Browser tests cover explicit checks, result states and narrow viewports. Frozen
smoke tests exercise the real OS query but allow unknown; they do not prove that
the runner's disk is encrypted. Signing tests use mocked tools until real signing
identities are available. No data encryption migration has been performed.

References checked 2026-09-26:

- [BitLocker overview](https://learn.microsoft.com/windows/security/operating-system-security/data-protection/bitlocker/)
- [Win32 volume encryption](https://learn.microsoft.com/windows/win32/secprov/win32-encryptablevolume)
- [Conversion status, not percentage alone](https://learn.microsoft.com/windows/win32/secprov/getconversionstatus-win32-encryptablevolume)
- [FileVault](https://support.apple.com/guide/mac-help/protect-data-on-your-mac-with-filevault-mh11785/mac)
- [Ubuntu full disk encryption](https://documentation.ubuntu.com/security/security-features/storage/encryption-full-disk/)
- [Win32 isolation](https://learn.microsoft.com/windows/win32/secauthz/app-isolation-overview)

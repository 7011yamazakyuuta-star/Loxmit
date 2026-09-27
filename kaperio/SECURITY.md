# Security and Privacy

Loxmit is an alpha local desktop application, not a public file-conversion service.
Only open files you own or have explicit permission to recover.
File ownership and permission are separate from the software license.

## Stored data

- Imported source copies, hashes, recovery masks, candidate lists, previews,
  unlocked documents and exports stay in the local data directory. Source runs
  use `../outputs/kaperio/`; native apps use the per-user OS data directory
  listed in [DESKTOP.md](docs/DESKTOP.md). New Unix data directories use mode 0700.
- Candidate lists and masks can contain sensitive password information.
- Recovered passwords are kept in process memory; a temporary Hashcat result
  file is removed after reading, invalid-result errors and ordinary process failures.
  Reads are bounded to 64 KiB and validation errors do not echo result contents.
  An abrupt process/machine failure may still leave it.
- The app does NOT encrypt stored data itself. OS disk encryption can protect
  the containing volume at rest; the app never enables it or retrieves recovery
  keys. Settings > protection status can explicitly query the storage volume.
  Unknown/unsupported results do not mean unencrypted or protected. See
  [storage protection scope](docs/SECURITY_READINESS.md).
- Library deletion removes work copies/exports, not the original imported file.
  It is not secure erasure and does not remove browser downloads, backups or caches.
- Do not publish this data directory, launch URLs, screenshots with private
  content, conversion logs, private documents or unreviewed diagnostic output.

## Network boundary

- Default: loopback only, random launch token, HttpOnly SameSite cookie,
  exact Host/Origin validation, POST header checks, no analytics or remote uploads.
- Setup downloads Python packages from the user's configured package index.
  Optional Windows component setup downloads pinned Hashcat/NVRTC packages only
  after individual consent, validates SHA-256, and preserves component notices.
  It is restricted to authenticated loopback clients and does not install drivers,
  request elevation, or change system PATH. See [setup boundaries](docs/SETUP.md).
- Optional private-LAN HTTPS is experimental and not phone-device validated.
  Do not expose the server to the public internet or forward router ports.
- A launch URL grants full app access, including invoking configured local tools.
  Do not share it with an untrusted person. There is no multi-user permission model.
- Document parsing/decryption/rendering now runs in a disposable, resource-limited
  process. This is NOT a security sandbox: it retains the current OS user's file
  and network privileges. External Office/LibreOffice conversion is separately
  time-bounded; it is not covered by the parser's memory budget.
  Avoid untrusted files; keep Python dependencies, Office and GPU drivers updated.
  Disabling macros does not eliminate parser vulnerabilities or active-content risk.
- Document workers inherit only a small runtime/system environment allowlist.
  API tokens, proxy settings, user Python paths and loader injection hooks are
  not inherited. HOME and temporary paths point to the private task workspace.
  Nonstandard runtime search paths may need a supported native bundle instead.
  This is defense in depth, NOT a filesystem or network access restriction.

## Resource protection

- Office OOXML and ZIP both enforce 512 MiB expanded size / 10,000 entries.
  Office manifests and workbook metadata are additionally limited to 16 MiB.
- One document worker per library, a 2 GiB monitored process-tree RSS budget,
  120-second normal deadline and 300-second export deadline (including queue wait).
  Windows also enforces a 2 GiB job-wide committed-memory cap; Linux enforces a
  4 GiB address-space cap. macOS uses RSS polling, not a hard OS memory cap.
- Private temporary outputs are committed only after successful worker completion.
  Passwords are sent over an anonymous pipe, not command-line arguments or request files.
- Document workers and their helpers use a private working/temp directory. Nested
  temporary output is monitored with a 1 GiB aggregate / 10,000-entry limit; links
  and special files are rejected. These are polling safeguards, not a disk quota
  or a filesystem sandbox. Files written to other absolute paths are not covered.
- HTTP accepts at most 32 concurrent connections. TLS handshakes run off the
  accept loop with a 5-second timeout; HTTP socket inactivity expires at 30 seconds.
  These are local-app safeguards, not a public-service security certification.
- See [hardening scope and limitations](docs/HARDENING.md).

## Dependency checks

Each native CI build audits its installed, declared Python runtime dependencies
against PyPI advisories with pip-audit in a separate tool environment. Missing
inventory entries, incompatible declared dependencies, skipped/incomplete audit
results, service failures and known vulnerabilities fail the build. Audit records
contain public package names and versions, not user files or passwords.

This does not scan bundled PDFium/OpenSSL, Python itself, Hashcat, CUDA, GPU
drivers, Office, the OS, or unknown vulnerabilities. It is not malware detection
or a complete supply-chain audit. See [audit scope](docs/PRIVACY_AUDIT.md).

## Reporting

Do not attach real passwords, document hashes or confidential files to public issues.
Use a synthetic reproduction. Submit sensitive security reports through
[GitHub private vulnerability reporting](https://github.com/7011yamazakyuuta-star/Loxmit/security/advisories/new).
Private vulnerability reporting is enabled for this repository.
No independent security audit, malware certification or code-signing is claimed.
Optional signing build paths are documented in [SIGNING.md](docs/SIGNING.md).
Mocked signing tests are not evidence of a real certificate or Apple acceptance.

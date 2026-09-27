# Optional native signing and notarization

Status: the build paths and failure handling are implemented; no commercial
certificate or Apple Developer identity has been provisioned. No real signing,
notarization acceptance or signed-GPU compatibility is claimed. Normal GitHub
PR builds deliberately have no signing secrets and remain unsigned/ad-hoc.

No store submission is required for these paths. Apple notarization is an
automated security check, distinct from App Store review. Obtaining identities
may require identity verification, a paid account/certificate and secure key
storage. The owner must choose and obtain these; the scripts purchase nothing.

Run commands below in `kaperio/`, after the normal dependency installation,
unit tests and dependency audit. Replace the public identity placeholders.
Never put private keys, passwords or recovery codes in chat, source or command
arguments. Never upload signing keys to ordinary CI artifacts.

## Windows

Use a trusted code-signing certificate accessible through CurrentUser/My and
its provider (for example a hardware-backed key). Install the Windows SDK signing
tools on the developer's build machine. The provider must support this SignTool
certificate-store path; cloud signing services with a different protocol need
a separate adapter and are not supported by these options.

```powershell
python scripts/build_desktop.py --windows-certificate CERTIFICATE_SHA1_THUMBPRINT --timestamp-url https://YOUR_PROVIDER_RFC3161_ENDPOINT --signtool "C:\Program Files (x86)\Windows Kits\10\bin\SDK_VERSION\x64\signtool.exe"
python tests/frozen_smoke.py dist/Loxmit/Loxmit.exe
```

The thumbprint selects a certificate; file/timestamp digests use SHA-256. The
script signs `Loxmit.exe`, then checks Authenticode trust and timestamp presence
with SignTool. All nonzero exits, including warnings, fail. Upstream DLLs are
not silently re-signed; the evidence explicitly limits scope to `Loxmit.exe`,
not the whole portable ZIP or its mutable assets. Whole-package integrity signing
would require an installer/package format or separately trusted signed manifest.
Signing also does not guarantee immediate SmartScreen reputation.

## macOS

Use a Developer ID Application certificate and its private key in Keychain,
the expected 10-character Team ID, and Xcode command-line tools. Configure a
notarytool Keychain profile interactively on the trusted build machine:

```sh
xcrun notarytool store-credentials loxmit-notary
```

First build/sign the native engine from the pinned clean upstream checkout, then
build the app with the same identity. The engine's Mach-O executable/modules are
signed with hardened runtime and timestamps before their archive/checksum is
created. Notices and non-code files are preserved. Module queries run again
after signing; actual GPU execution still needs hardware validation.

```sh
python scripts/build_engine_pack.py --source /path/to/pinned-hashcat --macos-identity "Developer ID Application: YOUR NAME (TEAMID1234)" --macos-team-id TEAMID1234
python scripts/build_desktop.py --macos-identity "Developer ID Application: YOUR NAME (TEAMID1234)" --macos-team-id TEAMID1234 --notary-profile loxmit-notary
python tests/frozen_smoke.py dist/Loxmit.app/Contents/MacOS/Loxmit --native-setup
```

PyInstaller signs the collected binaries and bundle with hardened runtime. The
builder checks the embedded engine archive against the signed pack and verifies
the Developer ID certificate chain/Team ID and deep strict bundle integrity.
No broad entitlements (JIT, library-validation bypass, unsigned executable memory)
are enabled automatically. A runtime that needs an exception must be reproduced
and reviewed on native hardware first; do not weaken all protections to pass.

The ZIP is staged outside the releases directory, submitted with notarytool,
and accepted only for status `Accepted`. The ticket is stapled and validated,
the signature rechecked, and Gatekeeper assessment must pass. The ZIP is then
recreated to include the ticket before its final checksum is written. Failures
do not create a new distributable. A previous successful archive, if any, is
not erased; always check the current command's success and evidence.

`--notary-profile` requires signing options. Omitting it creates a signed but
unnotarized artifact and says so in the sidecar. Do not publish that as notarized.
Store credentials only in Keychain, not inline Apple-ID passwords/API keys.
Notarization sends the built application (not user documents) to Apple.

## Release gates

- Inspect the archive's `.security.json` for exact scope, notarization state and
  matching SHA-256. It is a build receipt, not independently signed evidence.
- Run frozen tests on the final signed bundle and real hardware GPU/Office tests.
- Download the exact archive on a clean machine and check native trust assessment.
- Do not disable SmartScreen/Gatekeeper or install self-signed certificates into
  user trust stores as a distribution workaround.
- Linux archives retain SHA-256 checksums only. Detached publisher signatures
  require a separate maintained signing identity/distribution scheme.

References checked 2026-09-26:

- [SignTool](https://learn.microsoft.com/windows/win32/seccrypto/signtool)
- [SmartScreen reputation](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation)
- [Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [PyInstaller macOS signing](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing)

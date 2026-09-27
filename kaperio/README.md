# Loxmit User Guide

English | [日本語](README.ja.md) | [Project overview](../README.md)

Use Loxmit only with your own files or explicit permission from their owner.
Recovery is not guaranteed. Keep your originals and check exported copies.

## Desktop Setup

Extract a matching [release](https://github.com/7011yamazakyuuta-star/Loxmit/releases).
Keep all package files together. Launch `Loxmit.exe` on Windows, `Loxmit.app` on
macOS, or `Loxmit/Loxmit` on Linux. Python is included in desktop packages.

The interface opens in your browser with an empty library. The first-run guide
never installs components or runs GPU computation without your action. Windows
setup downloads pinned official Hashcat after consent. macOS 15+ and Linux x64
desktop builds extract bundled Hashcat after consent. Drivers, Homebrew, John,
Office, and the full CUDA toolkit are not installed. Optional NVRTC setup is
Windows x64 only. See [setup](docs/SETUP.md) and [packaging](docs/DESKTOP.md).

Packages are unsigned and not notarized. An OS warning does not establish that
a package is safe; review its source, release notes, and checksums.

## Language

Select **English**, **日本語**, or **Browser default** in the top bar. Browser
default chooses Japanese when the preferred browser language is Japanese,
otherwise English. The preference survives restarts and port changes. Switching
does not restart jobs or clear input. Filenames, hints, contents, and passwords
are not translated. External tool logs and unexpected third-party errors stay
in their original language. No translation service or external AI is used.

## Open and Save

1. Add your file. The limit is **200 MiB per file**; RAM and temporary storage
   needs can be much higher. The source is copied, not modified.
2. Choose **I know the password** for direct unlocking, or **Find password**
   for recovery. Direct unlocking does not need Hashcat or John.
3. Automatic search accepts remembered phrases, numbers, lengths, and known
   beginnings/endings. Leave uncertain details unknown. It is a bounded,
   prioritized search, not an unlimited search of every password.
4. After a verified result, copy the password or **Save without password**.
   The eye control hides the on-screen password. The displayed password is lost
   after restart, but saved files remain.
5. Use **Export** for conversion. Quit with the power button; closing the tab
   does not stop processing.

## Supported Files

| Input | Unlock and save | Recovery | Conversion |
| --- | --- | --- | --- |
| PDF | Original format | Standard encryption R2-R6, modes 10400-10700 | Image PDF, page-image Word, PNG ZIP, existing text |
| Excel `.xlsx` | Original format | Recognized Office 2007/2010/2013 encryption | Via PDF; Office or LibreOffice required |
| PowerPoint `.pptx` | Original format | Same as Excel | Same as Excel |
| Word `.docx` | Original format | Same as Excel | Same as Excel |
| ZIP | Repack without password | Recognized WinZip AES / ZipCrypto, separate `zip2john` required | Entry list and unlocked ZIP |

Not supported: Office sheet protection or editing restrictions, legacy
`.xls/.ppt/.doc`, 7z, RAR, certificate encryption, or DRM. Macro-enabled OOXML
extensions are accepted but dedicated real-file coverage is incomplete. ZIP
compression methods and mixed-password archives are not universally supported.

Word image export is not editable text or OCR. Text export uses the existing
text layer and may retain encoding problems. Rewriting a PDF does not preserve
digital signature validity. Unlocked Office bytes are saved without reformatting.

## Recovery Controls

- Automatic mode prioritizes up to 10 million attempts per run. Phrase-derived
  candidates have a separate 100,000-candidate cap. Review the displayed scope.
- Manual mode offers clue-based stages, masks, candidate lists, rules, and
  candidate/prefix/suffix combinations. Lists use UTF-8, one candidate per line.
- Length accepts 1-127, but format-specific UTF-8 byte limits take precedence.
  Non-ASCII characters may use several bytes. Long-clue support does not make
  exhaustive long-password searches practical.
- Defaults: low workload, 80°C stop threshold, 10-minute limit including startup.
  Temperature monitoring depends on the driver. Optional workload tuning uses
  the time budget and applies only to current candidates and hardware.
- Pause stops the process. Resume uses the last valid checkpoint and may repeat
  recent candidates. Without a checkpoint it restarts the current stage.
- A candidate must actually unlock the source and pass output verification.
  GPU recovery jobs run one at a time.

Settings detects existing executable paths or accepts Hashcat/zip2john paths.
GPU detection lists devices; the separate opt-in compute test uses a synthetic
PDF. It is not a speed benchmark or a guarantee for every file format.

## Storage and Security

Settings shows the data directory and an optional OS encryption check. The app
does not enable encryption or retrieve recovery keys. An unknown result does
not prove the disk is unencrypted. Stored work copies, candidates, hashes,
checkpoints, previews, and exports have no app-level encryption.

Password results are held in memory. Transient result files are removed after
ordinary completion/failure; abrupt failures can leave data. Library deletion
does not remove originals, browser downloads, or backups and is not secure erasure.
Unused identifiable temporary workspaces are conservatively cleaned on startup;
unknown or potentially active data is kept.

Document resource limits are not an OS sandbox. Default access is token-protected
loopback only. Do not share launch URLs: they grant control of the app.
Experimental private-LAN HTTPS requires trusted certificates and manual setup.
Do not expose Loxmit to the public internet. Standalone iOS/Android recovery is
not implemented. Read [Security and Privacy](SECURITY.md).

## Run From Source

Install Python 3.12+. On Windows, run root `Setup.cmd`, then `Loxmit.cmd`.
On macOS/Linux, run `sh kaperio/setup.sh`, then `sh kaperio/launch.sh`.
Setup downloads dependencies; administrator permissions are normally unnecessary.

Source archives do not include Hashcat or native component packs. Configure an
existing installation, use opt-in Windows setup, or build a pack as described
in [desktop packaging](docs/DESKTOP.md). `LOXMIT_HASHCAT` and legacy
`KAPERIO_HASHCAT` are supported. Internal paths remain compatible.

From `kaperio/`, with the project's virtual environment activated:

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/build_desktop.py
```

Optional browser tests require Node.js, Playwright, and Edge (or set
`KAPERIO_BROWSER`). Run `node tests/release-smoke.cjs`. Synthetic temporary
libraries are deleted; a bounded set of screenshots remains. GPU integration
tests are separate opt-in operations, not ordinary unit tests.

Only `release-files.json` allowlisted files enter source archives. Never publish
the whole workspace or local data directory. See [contributing](../CONTRIBUTING.md)
and [third-party notices](THIRD_PARTY.md).

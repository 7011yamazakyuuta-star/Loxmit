# English and Japanese Interface

Introduced in 0.4.0-alpha.13. The top-bar selector persists `auto`, `ja`, or `en`
in the library's `language.json` using the same atomic-write helper as other
settings. It does not modify engine paths, existing jobs, input files, or exports.
The API is authenticated and subject to the existing Host/Origin/POST checks.
Language changes are allowed during processing and do not restart jobs.

`auto` uses the browser's first preferred language: Japanese for `ja` variants,
English otherwise. This is a shared library preference, not a multi-user profile.
It is not stored only in origin-bound localStorage, so app port changes do not
discard it. If the preference cannot be loaded, browser detection is used.

## Message Boundaries

- Static app text is explicitly annotated with `data-i18n`.
- Dynamic app strings use `t()` and numbered placeholders in `messages-en.js`.
- Stored events and server-owned labels use exact catalog matches or bounded,
  anchored message-template matches at designated rendering points. Existing
  `job.json` records are not rewritten for translation.
- Values are written as text nodes, never HTML. Filenames, passwords, hints,
  paths, ZIP entries, workbook sheet names, and document content remain unchanged.
- Hashcat/driver logs and unknown third-party exception details remain verbatim;
  translation is not a claim that every OS or external-tool message is English.
- No cloud translation, analytics, or additional document upload is introduced.

## Verification

`test_i18n.py` checks catalog coverage for static markup and dynamic calls,
placeholder consistency, duplicate keys, persistent preferences, and fallback.
HTTP tests cover authentication, cross-origin rejection, invalid preferences,
static assets, and switching while a job is active.

`i18n-smoke.cjs`, called by `release-smoke.cjs`, verifies live switching,
unchanged hints, saved/reloaded preferences, Japanese browser default and English
fallback, API guards, nested progress events, checkpoint messages, wrong-password
errors, all six manual methods, settings, security, and onboarding. It also checks
English layout at 320/390/768/1440 pixels. Result-password switching is checked by
the main browser suite. This uses synthetic data, not a user's library.

English source and local Windows frozen-app browser checks were run on
2026-09-27. Native CI and any release-specific results belong in the corresponding
release notes. This is not physical macOS/Linux browser or GPU evidence.

The README screenshot is generated from a synthetic file in this test suite.
Temporary libraries are removed on completion; screenshots overwrite a fixed
set of filenames rather than accumulating timestamped copies.

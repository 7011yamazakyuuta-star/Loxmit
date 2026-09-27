# Contributing to Loxmit

English and Japanese reports and pull requests are welcome.
日本語での不具合報告・改善提案も歓迎します。

## Report a Problem

Use the [issue templates](https://github.com/7011yamazakyuuta-star/Loxmit/issues/new/choose).
Include the release version, OS/architecture, GPU/runtime when relevant, exact
steps, expected result, and a redacted error. Reproduce with a synthetic file.
Do not attach private files, passwords, hashes, dictionaries, launch URLs, tokens,
or unreviewed logs. Report security vulnerabilities
[privately](https://github.com/7011yamazakyuuta-star/Loxmit/security/advisories/new).

## Changes

1. Discuss substantial changes in an issue first, then work on a focused branch.
2. Preserve originals, authentication boundaries, opt-in setup, and license notices.
3. Add regression tests. Use synthetic fixtures and clean temporary files after
   both success and failure. Do not commit environments or generated packages.
4. Open a pull request explaining the behavior, tests actually run, and remaining
   gaps. Local tests, CI builds, and physical GPU tests are separate evidence.

From `kaperio/`, activate the virtual environment created by setup, install
`requirements-dev.txt`, then run:

```sh
python -m unittest discover -s tests -v
node tests/release-smoke.cjs
```

Browser tests additionally require Playwright and Edge. Set `KAPERIO_NODE_MODULES`
if Playwright is outside this checkout; `KAPERIO_BROWSER` selects another installed
Playwright browser channel. Native smoke tests follow `scripts/build_desktop.py`.
Do not run hardware-heavy integration tests without the operator's consent.

## Translations

Japanese source messages are stable keys in `kaperio/static/messages-en.js`.
`i18n.js` localizes designated interface fields without changing user data.
Preserve numbered placeholders and their meaning. Static markup uses
`data-i18n` attributes; dynamic labels call `t()`. Server-owned display messages
use `i18n.message()`; filenames, passwords, document text, and raw tool logs do not.

Check both languages at 320, 390, 768, and 1440 pixels. Verify dialogs, validation,
long names, busy states, keyboard labels, and language changes during input.
Do not introduce remote translation services. See `tests/test_i18n.py` and the
bilingual browser checks. English/Japanese guides should stay consistent.

## Scope

Loxmit supports authorized local file recovery. Do not submit credentials or
features for unauthorized access. Performance claims need reproducible measurements
against a named baseline, not screenshots of peak speed. Contributions retain
the project's MIT terms, with separate notices for third-party components.

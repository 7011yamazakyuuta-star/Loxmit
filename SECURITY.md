# Security Policy

Loxmit is alpha software. Only the latest published prerelease is currently
maintained; there is no promised response time or independent security audit.

## Report Privately

Use [GitHub private vulnerability reporting](https://github.com/7011yamazakyuuta-star/Loxmit/security/advisories/new).
Private reporting is enabled. English and Japanese are welcome.
Do not publish an exploit containing private files, passwords, hashes, launch
URLs, or tokens. Provide a synthetic reproduction, affected version/platform,
impact, and steps. If private reporting is temporarily unavailable, open a public
issue asking for a private channel without disclosing the vulnerability.

脆弱性は上記の非公開窓口へ報告してください。実文書・パスワード・ハッシュ・起動URLは添付せず、人工データで再現してください。

## Boundaries

- Authorized files only. Originals are preserved, but working copies and unlocked
  outputs contain sensitive data and are not encrypted by the app.
- Loopback and authenticated access are defaults. Never expose the app as a public
  file conversion service or share its launch token with untrusted users.
- Resource-limited document workers are not full OS/network sandboxes.
- Native packages are currently unsigned and not notarized. Checksums are not
  publisher identity verification.

Read the complete [security and privacy details](kaperio/SECURITY.md), including
data retention, dependency-audit coverage, and platform limitations.

# Security policy

## Project status

This is a quarantined legacy desktop snapshot. It has no supported release,
approved native runtime, authorized dataset, production service, or public
plate-recognition result. The static quarantine audit is the only supported
execution path.

## Private reporting

Use GitHub's private **Security → Report a vulnerability** flow for credentials,
Telegram sessions, personal data, plate images, database contents, native
library risks, or other sensitive findings. Never post a token, chat identifier,
session file, private path, plate record, account detail, or exploit payload in
a public issue.

For an exposed provider credential:

1. revoke it at the provider;
2. inspect provider-side activity and access logs;
3. rotate downstream credentials and sessions;
4. preserve only redacted incident metadata;
5. coordinate any Git-history rewrite across branches, tags, forks, caches, and
   existing clones.

Deleting a value from the current branch is not revocation.

## Current boundaries

- The tracked environment template has eight declared keys and zero non-empty
  values.
- \`.env\`, Telegram sessions, local databases, logs, and caches are ignored.
- Two historical Telegram bot-token alerts remain open pending owner revocation.
- DTK publication rights, code provenance, licensing, dependency
  reproducibility, and synthetic-fixture rights remain unresolved in issue #2.
- No file in this repository should be interpreted as a license grant.

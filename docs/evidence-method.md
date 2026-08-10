# Quarantine evidence method

This repository contains a legacy desktop LPR/Telegram snapshot with unresolved
provider credentials, DTK publication rights, source provenance, and licensing.
The evidence workflow therefore performs a static metadata audit only.

\`tools/audit_quarantine.py\` reads the exact current bytes of 15 retained
Python modules and the empty \`.env.example\` template. It parses Python syntax
without importing any module, records file hashes and line counts, derives
top-level class/function surfaces and local import edges, counts environment
keys without emitting values, and builds a machine-readable release gate.

The workflow does not load DTK libraries, open a camera or GUI, create a
database, contact Telegram, display a plate, emit source-code strings, or claim
that the application can run. Promotional screenshots and video are
deliberately excluded until publication rights and a legally usable synthetic
fixture are established.

## Reproduction

Only CPython is required:

\`\`\`bash
python3 tools/audit_quarantine.py --check
\`\`\`

GitHub Actions regenerates the seven-file bundle in pinned CPython, uploads the
candidate for review, compares every adopted byte, and proves that the checkout
remains clean. Provider revocation and rights decisions remain human actions in
issue #2.

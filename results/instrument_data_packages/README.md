# Multi-instrument package store (data snapshot)

**Data-only PR.** Pipeline code: `research/multi-instrument-pipeline-v1`.

- Exactly **one** package tree activated via `CURRENT`.
- Full H1 only; develop is **derived** (no `*_develop.csv` duplicates).
- SHA inventory: `CURRENT.sha256.json` and `<package_id>.sha256.json`.

Prefer Git LFS for CSV blobs when available. This PR tracks them as plain Git
blobs because LFS is not configured on the build host.

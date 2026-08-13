# Multi-instrument package store (schema)

Phase-0 multi-instrument readiness packages for XAUUSD / EURUSD / GBPUSD.

## Layout

```
instrument_data_packages/
  README.md
  CURRENT.sha256.json          # optional pointer inventory (data PR)
  <package_id>.sha256.json     # SHA inventory for one immutable package
  <package_id>/                # data PR / local only (gitignored on pipeline branch)
    instrument_data/
      {xau,eur,gbp}usd_h1.csv  # full H1 only
    instrument_data_manifests/
      committed_artifact_lock.json
      …
    multi_instrument_data_readiness.md
  CURRENT -> <package_id>      # atomic pointer (data PR activation)
```

## Rules

- **Package ID:** `{export_run_id|norun}-{content_sha16}` (content-addressed).
- **Publish model:** `current_indirection_v6` — live roots are static links through
  `packages/CURRENT/...`; only `CURRENT` is atomically replaced.
- **Develop window:** **not stored** by default. Derived as
  `server_time < holdout_start_server` (`2026-01-01 00:00:00`) from full H1.
  Lock field: `"develop_csv": "derived:server_time < holdout_start_server"`.
- **Consumer contract:** pin once per research op:

```python
from build_multi_instrument_data_readiness import load_package_snapshot
snap = load_package_snapshot()
full = snap.read_all_histories()
dev = snap.read_all_develop()  # derived filter
```

## PR split

| PR | Contents |
|----|----------|
| **Pipeline** | exporter, builder, tests, this schema README, SHA manifest format |
| **Data** | exactly one package tree + `CURRENT` + `*.sha256.json` (prefer Git LFS) |

Do not merge bulk CSVs into the pipeline PR.

## Snapshot status (this checkout)

- **Status:** activated data snapshot (data-only PR).
- **Package id:** `4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd`
- **CURRENT** → that package (atomic symlink).
- **Contents:** full H1 only for XAUUSD / EURUSD / GBPUSD; develop derived (no `*_h1_develop.csv`).
- **SHA inventory:** `CURRENT.sha256.json` and `<package_id>.sha256.json`.
- **Pipeline:** merged via PR #4 (`main`).
- **Git LFS:** not used on this host; CSVs tracked as plain Git blobs for this one package.

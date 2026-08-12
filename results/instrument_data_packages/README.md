# Multi-instrument package store

- `CURRENT` — relative symlink to the active package directory (atomic publish pointer).
- `<package_id>/` — immutable content-addressed package (`run_id-content16`).
- `CURRENT.sha256.json` / `<package_id>.sha256.json` — read-only SHA inventory
  (artifact integrity without mutating packages).

## Consumer contract

Resolve the package **once** per research operation:

```python
from build_multi_instrument_data_readiness import load_package_snapshot
snap = load_package_snapshot()  # pins CURRENT
frames = snap.read_all_histories()  # all symbols from same package_dir
```

Do **not** open `results/instrument_data/<symbol>_*.csv` separately per symbol if a
package flip can occur mid-operation — that can cross CURRENT versions.

## PR / storage note

Git LFS is not configured on this host. Prefer one tracked package only; superseded
packages must be removed. SHA manifests are always committed. Future: migrate CSV
blobs to LFS or an external artifact store keyed by these manifests.

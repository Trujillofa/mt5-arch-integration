# Bridge metrics — Prometheus textfile exporter

**Read-only.** `scripts/mt5_metrics_exporter.py` reads the EA snapshots in
`mt5_arch/` and prints Prometheus exposition text. It never writes into the
bridge and never places orders.

```bash
# stdout
python3 scripts/mt5_metrics_exporter.py --bridge-dir "$MT5_BRIDGE_DIR"

# atomic textfile for node_exporter's textfile collector
python3 scripts/mt5_metrics_exporter.py --bridge-dir "$MT5_BRIDGE_DIR" \
  --out /var/lib/node_exporter/textfile/mt5.prom
```

`--max-age` (default 15 s, or `MT5_BRIDGE_MAX_AGE`) sets the heartbeat
staleness threshold. `--bridge-dir` falls back to `MT5_BRIDGE_DIR`.

## Metrics

| Metric | Type | Notes |
|--------|------|-------|
| `mt5_bridge_dir_present` | gauge | 0 when the directory is missing |
| `mt5_feed_stale` | gauge | 1 when `heartbeat.txt` is missing or older than `--max-age` |
| `mt5_heartbeat_age_seconds` | gauge | omitted when no heartbeat |
| `mt5_snapshot_ok{file=...}` | gauge | 1 when `account.json` / `positions.json` / `symbols.json` parses |
| `mt5_account_equity` / `_margin` / `_free_margin` | gauge | account currency |
| `mt5_positions_open` | gauge | omitted when `positions.json` is absent (absence ≠ flat) |
| `mt5_position_volume{symbol,side}` | gauge | lots |
| `mt5_exposure_quote{symbol}` | gauge | **quote-currency** notional, not account-converted |
| `mt5_exposure_quote_total` | gauge | sum over priced symbols |
| `mt5_positions_unpriced` | gauge | positions skipped for exposure (no `contract_size` or price) |
| `mt5_control_present` | gauge | `mt5_arch/control.json` exists |
| `mt5_control_parse_ok` | gauge | parses with a boolean `inhibited` |
| `mt5_control_inhibited` | gauge | **malformed counts as inhibited**, matching `DeskControl.mqh` |
| `mt5_control_age_seconds` | gauge | age of the coordinator write, not the EA read |

## Semantics that matter

- **Staleness is a metric, not an exit code.** A dead bridge still produces a
  scrapeable file; alert on `mt5_feed_stale == 1`.
- **Absence is not flat.** Without `positions.json`, no `mt5_positions_open`
  series is emitted, so a missing snapshot cannot look like an empty book.
- **Exposure uses the broker's `contract_size`** from `symbols.json`, so XAUUSD
  100 oz vs 10 oz is per-firm data, never a hardcoded guess. A symbol missing a
  contract size is counted in `mt5_positions_unpriced`, not priced.
- **No FX conversion.** `mt5_exposure_quote*` is quote-currency notional; a
  USDJPY position is in JPY. Convert in the dashboard if needed.

## Not included

No HTTP scrape endpoint and no host deployment. Point the textfile collector at
`--out`, or run it from cron/systemd on the operator host. See
[STAGE0-CONTROL.md](STAGE0-CONTROL.md) for the entry inhibit switch itself.

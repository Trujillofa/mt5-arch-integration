## Seven Desk (browser copy terminal)

Read-only multi-account paper desk with a WSF live fetch. Nested at
[`apps/seven-desk`](apps/seven-desk). It uses `config/brokers/wsf.env` (login/server
only) and, when the Wine terminal + Mt5ArchBridge EA are running, the same
`account.json` / `positions.json` / `deals_export.csv` snapshots as `mt5-arch account`.
**Does not place live MT5 orders.** Paper fallback when the file bridge is absent.

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/20-seven-desk.sh
# http://127.0.0.1:3847
```

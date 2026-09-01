## Seven Desk (browser copy terminal)

Read-only multi-account paper desk with a WSF live fetch. Nested at
[`apps/seven-desk`](../apps/seven-desk). It uses `config/brokers/wsf.env` (login/server
only) and, when the Wine terminal + Mt5ArchBridge EA are running, the same
`account.json` / `positions.json` / `deals_export.csv` snapshots as `mt5-arch account`.
Paper copy is the default and never live-OrderSends. WSF live fetch is optional
and fails closed when the prefix or bridge is absent. A separate fail-closed
path `POST /api/wsf/order` can send a min-lot scratch on WSF 149736 only when
the body has `{ "live": true, "confirm": "WSF-149736" }`. Arm **WSF live copy**
on the WSF card to send the WSF slave of each master fill the same way
(`action: "open"`, 0.01 lot). Other books stay paper. If the WSF terminal is
down, the order path starts `~/.mt5-wsf` in the background and waits for a
fresh file-bridge snapshot. It never talks to Vantage, FP, or official MCP
on :22346.

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/20-seven-desk.sh
# http://127.0.0.1:3847
```

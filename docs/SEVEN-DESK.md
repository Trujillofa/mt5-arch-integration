## Seven Desk (browser copy terminal)

Read-only multi-account paper desk with a WSF live fetch. Nested at
[`apps/seven-desk`](../apps/seven-desk). It uses `config/brokers/wsf.env` (login/server
only) and, when the Wine terminal + Mt5ArchBridge EA are running, the same
`account.json` / `positions.json` / `deals_export.csv` snapshots as `mt5-arch account`.
Paper copy is the default and never live-OrderSends. WSF live fetch is optional
and fails closed when the prefix or bridge is absent. A separate fail-closed
path `POST /api/wsf/order` can send a min-lot scratch on WSF 149736 only when
the body has `{ "live": true, "confirm": "WSF-149736" }`. Arm **WSF live copy**
or **FundedNext live copy** on those cards for min-lot slave opens. Arm
**FTMO live master** so Place master trade is a real 0.01 EURUSD on 541163357
before any copy. Other books stay paper. One-shots restore the branded
terminal in the background. It never talks to Vantage, FP, or official MCP
on :22346.

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/20-seven-desk.sh
# http://127.0.0.1:3847
```

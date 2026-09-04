## Seven Desk (browser copy terminal)

Read-only multi-account paper desk with a WSF live fetch. Nested at
[`apps/seven-desk`](../apps/seven-desk). It uses `config/brokers/wsf.env` (login/server
only) and, when the Wine terminal + Mt5ArchBridge EA are running, the same
`account.json` / `positions.json` / `deals_export.csv` snapshots as `mt5-arch account`.
Paper copy is the default and never live-OrderSends. WSF live fetch is optional
and fails closed when the prefix or bridge is absent. A separate fail-closed
path `POST /api/wsf/order` can send a min-lot scratch on WSF 149736 only when
the body has `{ "live": true, "confirm": "WSF-149736" }`. Arm **WSF live copy**
or **FundedNext live copy** or **Alpha Capital live copy** on those cards
for min-lot slave opens. Arm
**FTMO live master** so Place master trade is a real 0.01 EURUSD on 541163357
before any copy. Other books stay paper. One-shots restore the branded
terminal in the background and refuse a generic `Program Files/MetaTrader 5`
tree inside those prefixes (that leftover can carry another company’s
`account.json`). Restore writes `Mt5ArchBridge` onto the branded Default
chart (`InpBroker=wsf|ftmo|fundednext|alphacapital`) and restarts that book when
`heartbeat.txt` is stale, so fetch/probe can see a fresh snapshot again.
A stale heartbeat does not block a live one-shot — login/server identity
on the last branded `account.json` does. Fetch/probe still fail closed on
a stale snapshot. **CLOSE positions** on
the blotter bar flattens every desk row (live groups first, fail-closed;
paper after). An already-flat close (`no open … desk position` or
`position vanished`) drops the desk row the same as `ok`. It never talks
to Vantage, FP, or official MCP on :22346.

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/20-seven-desk.sh
# http://127.0.0.1:3847
```

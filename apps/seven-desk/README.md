# Seven Desk

Browser copy-trading desk nested in **mt5-arch-integration**. WSF live fetch reads `config/brokers/wsf.env` and Mt5ArchBridge files (`account.json`, `positions.json`, `deals_export.csv`) when the Wine terminal is up. Paper adapter stays the execution path. No live orders from this UI.

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/20-seven-desk.sh          # or: cd apps/seven-desk && npm install && npm run dev
# http://127.0.0.1:3847
./scripts/16-use-broker.sh wsf      # optional: export WSF MT5 login/server into the shell
```

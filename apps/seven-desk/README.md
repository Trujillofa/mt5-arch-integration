# Seven Desk

Browser copy-trading desk nested in **mt5-arch-integration**. Live fetch reads each firm’s file-bridge snapshots when that Wine terminal is up. Paper adapter stays the default copy path. Live OrderSend is fail-closed and opt-in on **FTMO 541163357** (master), **WSF 149736**, **FundedNext 13981906**, and **Alpha Capital 2765247** — branded `terminal64.exe` trees, never Vantage/FP or a generic `MetaTrader 5` folder inside those prefixes.

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/20-seven-desk.sh          # host systemd --user keep-alive on :3847 (not Podman)
./scripts/20-seven-desk.sh --status
./scripts/20-seven-desk.sh --stop
# http://127.0.0.1:3847
./scripts/16-use-broker.sh wsf      # optional: export WSF MT5 login/server into the shell
```

A browser terminal for **copy-trading across seven of your own prop-firm accounts** from one desk. This slice is paper/demo only: you can place a master trade, watch it fan out, and inspect fills, skips, and exposure without any broker credentials.

This is an operations tool for accounts the operator already owns. It does not include challenge-pass flows, risk-rule spoofing, or anything meant to evade a firm’s evaluation rules.

## Firms on the desk

Each book ships with a seeded paper account, a typical platform, and an honest server hint:

| Firm | Typical platforms | Server hint in the demo |
| --- | --- | --- |
| WSF (Wall Street Funded) | MT5, cTrader, Match-Trader | **`WSFmarkets-Server`** |
| FundedNext | MT4, MT5, cTrader, Match-Trader | **`FundedNext-Server 2`** (login `13981906`) |
| Neomaa (NEOMAAA Funded) | MT5, TradeLocker | `NEOMAAA-Live` |
| Fortraders | MT5, TradeLocker, cTrader | `ForTraders-Server` |
| FundingPips | MT5, cTrader, Match-Trader | `FundingPips-Server` |
| FTMO | MT4, MT5, cTrader, DXtrade | **`FTMO-Server4`** (login `541163357`) |
| Alpha Capital | MT5, cTrader, DXtrade, TradeLocker | **`ACGMarkets`** (login `2765247`) |

FTMO starts as the **master**. The others are slaves with copy rules already filled in so a first trade does something visible.

## How paper copy-trading works

1. You send a market ticket on the master (symbol, side, lots, optional SL/TP).
2. The **paper adapter** fills the master against a local quote book (small fixed slip).
3. The **copy engine** walks every other account:
   - skip if the slave is disabled
   - skip if the master symbol maps to a blank value
   - skip if sized lots exceed `max lot` or fall below 0.01
   - skip if paper slip exceeds `max slippage`
   - error if the account is disconnected
   - otherwise fill, optionally reversed, optionally with SL/TP
4. Positions and floating P&amp;L update on every account. Quotes drift so P&amp;L is not frozen.

Settings, blotter, and positions persist in **localStorage** (`sevendesk.v1`). **Reset demo** wipes that key and reseeds the seven books.

### Seeded skip cases (so the blotter is not all greens)

- **Fortraders** starts with copy **off** → `slave disabled`
- **FundingPips** maps `NAS100` to blank → `symbol unmapped`
- **FundingPips** `max lot` is `1.00` with `0.8×` → a `2.00` lot master → `max lot`
- **Neomaa** maps `XAUUSD` → `GOLD` (still fills)

## Run locally

```bash
npm install
npm run dev
```

The dev script binds **0.0.0.0:3847** (not 3000). Open [http://127.0.0.1:3847](http://127.0.0.1:3847).

```bash
npm run build
npm start
```

No API keys and no `~/.mt5-wsf` prefix are required for paper copy-trading.
Live broker sync is **not** used for fills. WSF live fetch is optional and
fails closed when the Wine prefix or file bridge is absent.

## WSF live fetch (read-only)

Select the WSF card and click **Fetch WSF**, or:

- `GET /api/wsf/probe` — platform reachability + fetched books
- `GET /api/wsf/account` — sanitized account snapshot only

If `MT5_LOGIN` / `WSF_MT5_LOGIN` is set (gitignored `.env.local`, process env, or `config/brokers/wsf.env` from mt5-arch-integration), **Fetch WSF uses that operator book** and does **not** log into the public homepage demo card. Live balance/positions/deals come from the **Mt5ArchBridge** files (`account.json`, `positions.json`, `deals_export.csv`) when the Wine terminal is writing them.

- MT5: operator login + `WSFmarkets-Server` when env is present; otherwise public login `4013`
- Live balance / positions / deals need `MT5_PASSWORD` + `METAAPI_TOKEN`, or an `MT5_BACKEND=file` JSON snapshot from a logged-in terminal
- cTrader / Match-Trader demo logins are skipped when operator MT5 env is present

Passwords are never returned in the JSON or UI. Copy-trading stays on the paper adapter.

## FundedNext live fetch (read-only)

Select the FundedNext card and click **Fetch FundedNext**, or:

- `GET /api/fundednext/probe` — fail-closed file-bridge snapshot
- `GET /api/fundednext/account` — sanitized account snapshot only

Uses `FUNDEDNEXT_MT5_*` from the gitignored repo `.env` (login `13981906`, server `FundedNext-Server 2`, prefix `~/.mt5-fundednext`). It does **not** read WSF `MT5_*` / `WINEPREFIX`. Attaching `Mt5ArchBridge` is a FundedNext add-on risk the operator accepted for the snapshot. Arm **FundedNext live copy** on the same card to send each master fill through `POST /api/fundednext/order` (`confirm: "FN-13981906"`, 0.01 EURUSD).

## FTMO live fetch (read-only)

Select the FTMO card and click **Fetch FTMO**, or:

- `GET /api/ftmo/probe` — fail-closed file-bridge snapshot
- `GET /api/ftmo/account` — sanitized account snapshot only

Uses `FTMO_MT5_*` from the gitignored repo `.env` (login `541163357`, server `FTMO-Server4`, prefix `~/.mt5-ftmo`). It does **not** read WSF `MT5_*` / `WINEPREFIX`. Title-only auto-login (balance 0, empty currency) is treated as `auth_failed`. Attaching `Mt5ArchBridge` is an FTMO add-on risk the operator accepted for the snapshot. Arm **FTMO live master** on the FTMO card (`confirm: "FTMO-541163357"`) so Place master trade is a real 0.01 EURUSD `POST /api/ftmo/order`. Copies wait until that fill.

## Alpha Capital live fetch (read-only)

Select the Alpha Capital card and click **Fetch Alpha Capital**, or:

- `GET /api/alphacapital/probe` — fail-closed file-bridge snapshot
- `GET /api/alphacapital/account` — sanitized account snapshot only

Uses `ALPHA_MT5_*` from the gitignored repo `.env` (login `2765247`, server `ACGMarkets`, prefix `~/.mt5-alphacapital`). It does **not** read WSF `MT5_*` / `WINEPREFIX`. Attaching `Mt5ArchBridge` is an Alpha Capital add-on risk the operator accepted for the snapshot. Arm **Alpha Capital live copy** on the same card to send each master fill through `POST /api/alphacapital/order` (`confirm: "ACG-2765247"`, 0.01 EURUSD).

## WSF live order (opt-in, fail-closed)

Paper remains the default. A live min-lot send requires all of:

1. Select the WSF card
2. Enable **WSF live scratch** (off by default)
3. Tick the acknowledgement
4. Type confirm token `WSF-149736`
5. Click the live scratch button — or `POST /api/wsf/order`

```http
POST /api/wsf/order
{ "live": true, "confirm": "WSF-149736", "action": "scratch", "symbol": "EURUSDc", "volume_min": true }
POST /api/wsf/order/close
{ "live": true, "confirm": "WSF-149736" }
```

Arm **WSF live copy** on the same card (ack + `WSF-149736`) so each **Place master trade** copies the WSF slave as `action: "open"` at 0.01 lot. Other slaves stay paper unless their own live-copy switch is armed. A stale file-bridge heartbeat does not block the one-shot (same as FTMO/FN). After the send, the path restores the branded WSF terminal in the background and reattaches `Mt5ArchBridge` on the Default chart when the heartbeat is stale. **CLOSE positions** on the blotter bar flattens every open desk row: live groups first (fail-closed), then paper. An already-flat close (`no open … desk position` / `position vanished`) drops the desk row. Live close result JSON retries `HistorySelectByPosition` so `deal_close` is not left at 0 when the journal already has the out deal.

The WSF route resolves `WINEPREFIX` to `~/.mt5-wsf` only. FTMO, FundedNext, and Alpha Capital live orders use `DeskLiveOrder.mq5` on `~/.mt5-ftmo` / `~/.mt5-fundednext` / `~/.mt5-alphacapital` only. Volume must be the symbol minimum. `src/mt5_arch` CLI/MCP stays read-only. Vantage and FP are never used.

Optional overrides (not committed; never put secrets in git):

```
MT5_LOGIN=
MT5_SERVER=WSFmarkets-Server
MT5_PASSWORD=
MT5_BACKEND=file
MT5_STATE_FILE=
METAAPI_TOKEN=
WSF_ENV_FILE=
```

## Architecture

- `AccountAdapter` in `src/lib/adapters/types.ts`
- `PaperAdapter` in `src/lib/adapters/paper.ts` — copy-engine fill path unless that book’s live switch is armed
- `POST /api/ftmo/order`, `/api/wsf/order`, `/api/fundednext/order`, `/api/alphacapital/order` — branded-prefix min-lot (scratch, master, or copy-open)
- `src/lib/adapters/metaapi.stub.ts` — comments/stub only for a future MetaAPI/MT5 adapter. If a token were added later, keep falling back to paper when it is missing.

There is no database, no auth, and no second UI kit. UI state lives in React context + localStorage.

## Stack

Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui.

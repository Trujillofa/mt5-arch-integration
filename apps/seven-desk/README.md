# Seven Desk

Browser copy-trading desk nested in **mt5-arch-integration**. Live fetch reads each firm’s file-bridge snapshots when that Wine terminal is up. Paper adapter stays the default copy path. Live OrderSend is fail-closed and opt-in on **FTMO 541163357** (master), **WSF 149736**, **FundedNext 13981906**, **Alpha Capital 2765247**, **FundingPips 11669306**, **Neomaa 7745107**, and **Fortraders 737150** — branded `terminal64.exe` trees, never Vantage/FP Markets or a generic `MetaTrader 5` folder inside those prefixes.

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
| Neomaa (NEOMAAA Funded) | MT5, TradeLocker | **`Neomaaa-global`** (login `7745107`) |
| Fortraders | **MT5** (this challenge; not TradeLocker), cTrader | **`FTTrading-Server`** (login `737150`) |
| FundingPips | MT5, cTrader, Match-Trader | **`FundingPips2-SIM`** (login `11669306`) |
| FTMO | MT4, MT5, cTrader, DXtrade | **`FTMO-Server4`** (login `541163357`) |
| Alpha Capital | MT5, cTrader, DXtrade, TradeLocker | **`ACGMarkets-Main`** (login `2765247`) |

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

Uses `FUNDEDNEXT_MT5_*` from the gitignored repo `.env` (login `13981906`, server `FundedNext-Server 2`, prefix `~/.mt5-fundednext`). It does **not** read WSF `MT5_*` / `WINEPREFIX`. Attaching `Mt5ArchBridge` is a FundedNext add-on risk the operator accepted for the snapshot. Arm **FundedNext live copy** on the same card to send each master fill through `POST /api/fundednext/order` (`confirm: "FN-13981906"`, 0.35 lots, same type as the ticket).

## FTMO live fetch (read-only)

Select the FTMO card and click **Fetch FTMO**, or:

- `GET /api/ftmo/probe` — fail-closed file-bridge snapshot
- `GET /api/ftmo/account` — sanitized account snapshot only

Uses `FTMO_MT5_*` from the gitignored repo `.env` (login `541163357`, server `FTMO-Server4`, prefix `~/.mt5-ftmo`). It does **not** read WSF `MT5_*` / `WINEPREFIX`. Title-only auto-login (balance 0, empty currency) is treated as `auth_failed`. Attaching `Mt5ArchBridge` is an FTMO add-on risk the operator accepted for the snapshot. Arm **FTMO live master** on the FTMO card (`confirm: "FTMO-541163357"`) so Place master trade is a real EURUSD `POST /api/ftmo/order` (default 1.4 lots; market / limit / stop). Copies wait until that send.

## Alpha Capital live fetch (read-only)

Select the Alpha Capital card and click **Fetch Alpha Capital**, or:

- `GET /api/alphacapital/probe` — fail-closed file-bridge snapshot
- `GET /api/alphacapital/account` — sanitized account snapshot only

Uses `ALPHA_MT5_*` from the gitignored repo `.env` (login `2765247`, server `ACGMarkets-Main`, prefix `~/.mt5-alphacapital`). It does **not** read WSF `MT5_*` / `WINEPREFIX`. Attaching `Mt5ArchBridge` is an Alpha Capital add-on risk the operator accepted for the snapshot. Arm **Alpha Capital live copy** on the same card to send each master fill through `POST /api/alphacapital/order` (`confirm: "ACG-2765247"`, 1.4 lots, same type as the ticket). Live order routes return JSON within a 70s HTTP budget — they do not hang on a silent Wine one-shot.

## FundingPips live fetch (read-only)

Select the FundingPips card and click **Fetch FundingPips**, or:

- `GET /api/fundingpips/probe` — fail-closed file-bridge snapshot
- `GET /api/fundingpips/account` — sanitized account snapshot only

Uses `FUNDINGPIPS_MT5_*` from the gitignored repo `.env` (login `11669306`, server `FundingPips2-SIM`, prefix `~/.mt5-fundingpips`). It does **not** read WSF `MT5_*` / `WINEPREFIX`, and it is not FP Markets (`~/.mt5-fpmarkets`). Attaching `Mt5ArchBridge` is a FundingPips add-on risk the operator accepted for the snapshot. Arm **FundingPips live copy** on the same card to send each master fill through `POST /api/fundingpips/order` (`confirm: "FUNDINGPIPS-11669306"`, 0.8 lots, same type as the ticket). The paper card stays until that switch is armed. One-shots return 409 if EURUSD has no history/ticks yet.

## Neomaa live fetch (read-only)

Select the Neomaa card and click **Fetch Neomaa**, or:

- `GET /api/neomaa/probe` — fail-closed file-bridge snapshot
- `GET /api/neomaa/account` — sanitized account snapshot only

Uses `NEOMAA_MT5_*` from the gitignored repo `.env` (login `7745107`, server `Neomaaa-global`, prefix `~/.mt5-neomaa`). It does **not** read WSF `MT5_*` / `WINEPREFIX`. Attaching `Mt5ArchBridge` is a Neomaa add-on risk the operator accepted for the snapshot. Arm **Neomaa live copy** on the same card to send each master fill through `POST /api/neomaa/order` (`confirm: "NEOMAA-7745107"`, 1.4 lots, same type as the ticket). The paper card stays until that switch is armed. One-shots return 409 if `terminal_connected=false` (weekend FX / Neomaaa-global down — not auth) or if EURUSD has no history/ticks yet.

## Fortraders live fetch (read-only)

Select the Fortraders card and click **Fetch Fortraders**, or:

- `GET /api/fortraders/probe` — fail-closed file-bridge snapshot
- `GET /api/fortraders/account` — sanitized account snapshot only

Uses `FORTRADERS_MT5_*` from the gitignored repo `.env` (login `737150`, server `FTTrading-Server`, prefix `~/.mt5-fortraders`). It does **not** read WSF `MT5_*` / `WINEPREFIX`, and it is not FTMO (`~/.mt5-ftmo`), FP Markets, or FundingPips. This challenge is **MT5**, not TradeLocker. Attaching `Mt5ArchBridge` is a Fortraders add-on risk the operator accepted for the snapshot. Arm **Fortraders live copy** on the same card to send each master fill through `POST /api/fortraders/order` (`confirm: "FORTRADERS-737150"`, 1.4 lots, same type as the ticket). The paper card stays until that switch is armed. One-shots return 409 if EURUSD has no history/ticks yet.

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

Arm **WSF live copy** on the same card (ack + `WSF-149736`) so each **Place master trade** copies the WSF slave as the same **BUY LIMIT / SELL LIMIT** at the firm default lots (**1.4**, except FundedNext **0.35** and FundingPips **0.8**). Other slaves stay paper unless their own live-copy switch is armed. The happy path writes `desk_live_order_request.txt` for the already-running `Mt5ArchBridge` v1.25 (seconds). A stale heartbeat, Algo Trading off, or an EA older than v1.25 returns **409** and does **not** fall back to a wine one-shot. **CLOSE positions** cancels working limits too. An already-flat close (`no open … desk position` / `no pending desk order to cancel` / `position vanished`) drops the desk row.

The WSF route resolves `WINEPREFIX` to `~/.mt5-wsf` only. FTMO, FundedNext, Alpha Capital, FundingPips, Neomaa, and Fortraders live orders use the same request file on their branded prefixes. Omit `price` and the EA places a **50-point** offset from bid/ask (5.0 pips on 5-digit FX) so the limit does not instantly market. `volume_min: true` is the explicit 0.01 override for a small prove. `src/mt5_arch` CLI/MCP stays read-only. Vantage and FP Markets are never used.

### US30 pending limit (opt-in)

Paper remains the default. The host places after deploy — this path does not arm itself.

```http
POST /api/ftmo/order
{
  "live": true,
  "confirm": "FTMO-541163357",
  "action": "open",
  "order_type": "buy_limit",
  "symbol": "US30",
  "side": "buy",
  "price": 53100,
  "tp": 53500,
  "sl": 52500,
  "volume": 4.0,
  "volume_confirm": true
}
```

Same body on `/api/wsf/order` (`confirm: "WSF-149736"`), `/api/fundednext/order` (`FN-13981906`), `/api/fundingpips/order` (`FUNDINGPIPS-11669306`), `/api/fortraders/order` (`FORTRADERS-737150`). Broker symbol names differ (`US30`, `US30.cash`, `DJ30`, `DJ30.c`, `US30m`, …); the one-shot `SymbolSelect`s those variants. WSF 149736 @ WSFmarkets-Server uses **`DJ30.c`** and tries that name first (a request may still say `"symbol": "US30"`). If the catalog has no US30 family the route returns JSON `stage=symbol` and does not hang. Startup chart stays EURUSD/EURUSDc because host Market Watch may be FX-only. File-bridge `openPositions` is `PositionsTotal` only — a working WSF pending on `DJ30.c` will not appear there.

Cancel the pending order (ticket from the place result, or omit ticket to match magic + symbol):

```http
POST /api/{firm}/order
{ "live": true, "confirm": "<token>", "action": "cancel", "ticket": 123456789 }
```

`POST /api/{firm}/order/close` still closes a filled position. If no position exists it will `TRADE_ACTION_REMOVE` a matching pending ticket. `{ volume_min: true }` is the explicit 0.01 override. Default live size is 1.4 (FundedNext 0.35, FundingPips 0.8) and requires `volume_confirm: true` when above 0.01. Copy-engine live switches send the same pending type at those lots.

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
- `POST /api/ftmo/order`, `/api/wsf/order`, `/api/fundednext/order`, `/api/alphacapital/order`, `/api/fundingpips/order`, `/api/neomaa/order`, `/api/fortraders/order` — branded-prefix live send (market / limit / stop; scratch stays min-lot)
- `src/lib/adapters/metaapi.stub.ts` — comments/stub only for a future MetaAPI/MT5 adapter. If a token were added later, keep falling back to paper when it is missing.

There is no database, no auth, and no second UI kit. UI state lives in React context + localStorage.

## Stack

Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui.

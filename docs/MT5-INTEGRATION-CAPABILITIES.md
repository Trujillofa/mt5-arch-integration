# MT5 integration — what you can do now

Operator inventory of the **live Wine/MT5 path**: Linux Python reads JSON snapshots written by `Mt5ArchBridge` on a chart, plus the observe overlays you can attach. This is not a research-screen write-up and not a promote path.

**How-tos:** [HOWTO-HTF-FIB.md](HOWTO-HTF-FIB.md) · [HOWTO-US-INDEX-SCALP.md](HOWTO-US-INDEX-SCALP.md) (offline screens, not overlay ops) · [mql5/README.md](../mql5/README.md)

---

## 1. Live stack

```
Linux Python  (MT5_BACKEND=file, default)
    reads MQL5/Files/mt5_arch/*.json
Wine terminal64.exe  +  Mt5ArchBridge EA on ONE chart
    → broker trade server
```

RPyC (`MT5_BACKEND=rpyc`, `mt5server.exe` :18812) exists and often dies with `(-10005, 'IPC timeout')` under Wine 11. Do not treat it as the working path.

A stale `heartbeat.txt` (older than `MT5_BRIDGE_MAX_AGE`, default 15s / FP profile 60s) almost always means **Algo Trading off or the EA detached**, not a Python bug.

---

## 2. CLI / health

```bash
./scripts/16-use-broker.sh fpmarkets    # or vantage / wsf
export WINEPREFIX=~/.mt5-fpmarkets MT5_BACKEND=file
# optional: MT5_BROKER=fpmarkets  so XAUUSD → XAUUSD.r
uv run mt5-arch ping
uv run mt5-arch account
uv run mt5-arch symbols EURUSD XAUUSD
uv run mt5-arch candles EURUSD --tf H1 --count 10
uv run mt5-arch deals                  # read existing deals_export.csv (needs dump_deals.done)
# uv run mt5-arch deals --request      # opt-in: touches dump_deals.request in the live prefix
uv run mt5-arch brokers
uv run mt5-arch resolve fpmarkets XAUUSD
uv run mt5-arch config                  # redacted; no password
uv run mt5-arch mcp                     # read-only MCP stdio (AI agents; no orders)
./scripts/08-status.sh                  # process + bridge age
./scripts/healthcheck.sh --ping         # also probes RPyC; file-only hosts may warn
```

| Command | What you get |
|---------|----------------|
| `ping` | Terminal name / build / `trade_allowed` |
| `account` | Login, balance, equity, margin, server, company |
| `symbols` | Lots / digits / tick — **only names in the EA `InpSymbols` export** |
| `candles` | Last N OHLCV from `candles_<brokerSymbol>_<TF>.json` |
| `deals` | Closed deals from `deals_export.csv` (EA v1.24, 14-day window). Completeness is `dump_deals.done` **only** — a fresh `heartbeat.txt` does not mean the CSV is finished. `time` is **trade-server** `YYYY.MM.DD HH:MM:SS`, not UTC. `--request` touches `dump_deals.request` in the live prefix and waits (bounded `--timeout`, default 30s, fail closed). Default is read-only. File-bridge only |
| `brokers` / `resolve` | Profiles + canonical ↔ broker map. No MT5 connection |
| `config` | Redacted settings |
| `mcp` | Read-only MCP stdio server — same data as the rows above. No positions/orders. See [HOWTO-MT5-AI-MCP.md](HOWTO-MT5-AI-MCP.md) |

`--json` and `-v` / `-vv` work on all of the above. There is **no** `positions` / order CLI. The EA writes `positions.json`; Python does not expose it. `deals` never sends orders.

---

## 3. Brokers / prefixes

One Wine prefix per broker. One `terminal64.exe` per prefix. Brand installers pre-seed the **server list**; cross-company login fails (`Invalid account`).

| Profile | Prefix | Example server | Switch |
|---------|--------|----------------|--------|
| `fpmarkets` | `~/.mt5-fpmarkets` | `FPMarketsSC-Live` | `./scripts/16-use-broker.sh fpmarkets` |
| `vantage` | `~/.mt5-vantage` | `VantageMarkets-Live 5` | `./scripts/16-use-broker.sh vantage` |
| `wsf` | `~/.mt5-wsf` | `WSFmarkets-Server` | `./scripts/16-use-broker.sh wsf` |

`~/.mt5-exness` exists on disk; there is no `config/brokers/exness.env`. Registry maps Exness `XAUUSD` → `XAUUSDm` only.

Deploy MQL5 into every found prefix:

```bash
./scripts/18-install-forex-indicator.sh
# then MetaEditor F7 (Wine will not reload an already-attached .ex5)
```

---

## 4. Indicators you can attach

Signal buffers (do **not** use old Fib-at-7 notes):

| Indicator | Signal | Chart | What you see |
|-----------|-------:|-------|----------------|
| `ForexHtfPivotsFib` | **8** | FX / gold **H1 or M15** | 4H/D pivots, Fib 61.8–78.6, EMA cloud, RSI+MA, lime/red markers |
| `UsIndexSessionScalp` | **8** | **US100 / US30 M5** (M1/M15 OK) | Session vlines, NY 15m OR, VWAP, EMA 9/21, flatten 15:45 ET |
| `BtcTrendPullback` | **7** | **BTCUSD H1** | H4 EMA bias, H1 reclaim, ATR guides |
| `ForexIndicatorTemplate` | **9** | Optional FX | EMA cloud + prior-day H/L/O. Prefer Fib alone on the trade chart |

### Chart recipes

| Book | TF | Attach | Logger inputs |
|------|----|--------|----------------|
| EURUSD / GBPUSD / XAUUSD (`.r` on FP) | H1 or M15 | `ForexHtfPivotsFib` | name=`ForexHtfPivotsFib` buf **8** |
| US100 / NAS100 / USTEC or US30 / DJ30.r | M5 | `UsIndexSessionScalp` | name=`UsIndexSessionScalp` buf **8**, `InpMaxSpreadPips=0` |
| BTCUSD | H1 | `BtcTrendPullback` | name=`BtcTrendPullback` buf **7**, `InpMaxSpreadPips=0` |

Fib modes: **INTRADAY** = EMA 20/50 + bias 200, London/NY, 4H pivots. **SWING** = 50/200, sessions off, Daily pivots. Tabs per TF under Wine — do not spam the timeframe toolbar.

---

## 5. Expert Advisors

| EA | Orders? | Role |
|----|---------|------|
| `Mt5ArchBridge` v1.24 source | Never | File bridge. **One chart only.** `InpBroker` required (`vantage\|fpmarkets\|exness\|wsf`). Timer writes, not OnTick. Request-gated 14-day deal dump: touch `dump_deals.request` → `deals_export.csv` + `dump_deals.done` |
| `ForexSignalLogger` | **Never** (`OrderSend` absent) | `iCustom` → Experts print + `MQL5/Files/forex_signals/<SYM>_<TF>.csv` |
| `TradeTransactionJournal` | Never | Read-only trade-id journal → `mt5_arch/journal/<session_id>/`. Live attach **not claimed** |
| `ForexHtfFibTester` v1.40 | **Yes in Strategy Tester** (`CTrade`) | EA-native Fib + ATR SL/TP. **Not** iCustom buffer 8. Default `InpAllowLiveTrading=false` |

Logger preset: `Presets/ForexSignalLogger-UsIndexSessionScalp.set` (name / buf 8 / max-spread pips 0). Copied by `18-install-forex-indicator.sh`.

### Navigator attach — logger (human, when convenient)

Do this on the **already-open** chart. Do not start a second terminal. Do not attach `ForexHtfFibTester` to a live book.

1. Navigator → Expert Advisors → **ForexSignalLogger** → drag onto the same tab as the indicator.
2. Inputs → Load `ForexSignalLogger-UsIndexSessionScalp.set` (US index) or set name / buffer / `InpMaxSpreadPips` from the table above.
3. Leave Algo Trading green (needed for the bridge). The logger still never sends orders.
4. Experts tab: `ForexSignalLogger ON | … | NO ORDERS`.
5. CSV appears only after a **non-zero closed-bar** signal. Flat days stay empty.

---

## 6. Scripts / exports

| Script | Safe on a live terminal? | Output |
|--------|--------------------------|--------|
| `ExportUsIndexM5` | **Yes** | `history_US100_M5.csv` / `history_US30_M5.csv` |
| Drop file `MQL5/Files/mt5_arch/export_us_index.request` | **Yes** (indicator consumes it) | Same CSVs; request deleted |
| `ExportHtfFibParityFixture` | Yes (read-only) | `mt5_arch/parity/<tag>/` |
| `ExportSymbolCapabilities` | Yes | `mt5_arch/capabilities/…` |
| `ExportSymbolSyncAudit` | Yes | `mt5_arch/sync_audit/…` |
| `ExportXauHistory` | Script itself is CopyRates-only | `xauusd_mt5_export.csv` |
| `ExportInstrumentHistory` | **No** | Wrapper `export-instruments-from-wine-mt5.sh` **kills that prefix's `terminal64`** |
| `scripts/19-run-htf-fib-backtest.sh` | **No** on a live prefix | `KILL_EXISTING=1` by default |

`export-xau-from-wine-mt5.sh` also kills `terminal64` in the prefix. GUI Strategy Tester is fine on a prefix you are willing to use for tester — not the live FP book.

---

## 7. US100 / US30 session overlay

Frozen chart family: **NY cash ORB + VWAP + EMA 9/21** (`UsIndexSessionScalp` v1.40). Optional `InpFamily` = VWAP bounce / EMA+MACD (observe only). Signal buffer **8**. Never `OrderSend`.

| Need | How |
|------|-----|
| See the overlay | Drag `UsIndexSessionScalp` onto US100 or US30 **M5** (M15 OK) |
| Panel | `UsIndexSessionScalp v1.40` + ET clock + OR + last signal |
| Clock wrong | Set **Server UTC offset hours** (FP often `+3`). Panel prints auto offset |
| M5 CSV for Python | `export_us_index.request` or `ExportUsIndexM5` — not `ExportInstrumentHistory` |
| Journal markers | Logger + preset above. **promote=no** |

---

## 8. Not on the chart (Python-only)

US-index v1–v8 screens, flatten replay, `us_index_session_core.py`, and `scripts/htf_fib_offline_backtest.py` read exported CSV / cache. They are **not** `InpFamily` modes and are **not** MT5 capabilities. The 1%/20% index goal is **archived** (`results/us_index_session_goal_archived.md`). Overlay stays observe-only. **promote=no**. No live-go.

`src/mt5_arch` must not import that research layer. `live_trader.py` is dry unless you pass `--live` (never from this observe path).

---

## 9. Safety / do-not

| Do | Do not |
|----|--------|
| One `Mt5ArchBridge` on one chart | Second `terminal64` in the same prefix |
| Logger / journal (no orders) | `ForexHtfFibTester` on a live book |
| `ExportUsIndexM5` / request file | `ExportInstrumentHistory` or `19-run-…` on the open FP prefix |
| Tabs per timeframe | Undocked charts under Wine (often black) |
| Treat stale heartbeat as EA / Algo Trading | Treat it as a Python bug first |
| Keep `.env` / prefixes / `*.exe` gitignored | Log `MT5_PASSWORD` |

This repo’s observe path never `OrderSend`s. A journal line is not a live-go.

---

## 10. Verified on FP (`~/.mt5-fpmarkets`) — 2026-08-18

Read-only: process list, `.ex5` mtimes, Default `*.chr`, bridge files, `uv run mt5-arch ping`. Did not attach, did not `OrderSend`, did not start a second terminal.

| Item | State |
|------|--------|
| Process | One `terminal64.exe /portable` — left running |
| Login | `84076984` / `FPMarketsSC-Live` / build 6090 / Algo Trading green |
| Bridge | Heartbeat fresh; writer on **US500 H1**. Live `.ex5` is **v1.20** (2026-08-04); repo source is v1.23 |
| CLI | `ping` connected; `account` live; `candles EURUSD H1` OK; `resolve fpmarkets XAUUSD` → `XAUUSD.r` |
| Bridge symbols | `EURUSD, GBPUSD, USDJPY, XAUUSD.r, BTCUSD` (H1/H4/D1). Not US100 |
| Open book | `positions.json`: **3× NZDCHF.r** |
| US100 | Default `chart05.chr` = **US100 M15** + `UsIndexSessionScalp` (OR 15 / EMA 9/21). No `<expert>`. Last Experts print **v1.20** (12:23). **v1.40** `.ex5` written 16:00 — reattach if the panel is not v1.40 |
| Other charts | Fib on NZDCHF.r, XAUUSD.r, US30, BTCUSD. BTC is **not** on `BtcTrendPullback` |
| Logger | Compiled **0 errors / 0 warnings** (16:27). Preset present. **`forex_signals/` empty.** No `ForexSignalLogger ON` today |
| Also compiled, not attached | `BtcTrendPullback`, `ForexIndicatorTemplate`, `TradeTransactionJournal`, `ForexHtfFibTester`, all export scripts |

---

## Related

| Doc | Why |
|-----|-----|
| [MULTI-BROKER-MT5.md](MULTI-BROKER-MT5.md) | Prefix model + evidence |
| [SYMBOL-REGISTRY.md](SYMBOL-REGISTRY.md) | Explicit maps; no suffix walk |
| [TRADE-JOURNAL.md](TRADE-JOURNAL.md) | Journal schema; live attach not claimed |
| [TESTER-PROVENANCE.md](TESTER-PROVENANCE.md) | Headless tester identity |
| [FOREX-MT5-ROADMAP.md](FOREX-MT5-ROADMAP.md) | Observe → paper → live waves (not done) |

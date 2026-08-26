# Phase 0 — Symbol & connection discovery

**Date:** 2026-08-04 (Tuesday)  
**Branch:** `research/algo-trading-btc-gold-forex`  
**Status:** **Vantage live complete** (majors + gold); FP Markets earlier pass; BTC bridge export pending EA v1.04 re-attach; WSF empty

Raw dumps: [`docs/research/phase0/`](phase0/)

---

## 1. Terminals / prefixes

| Prefix | Brand | Process | Bridge | Notes |
|--------|-------|---------|--------|-------|
| **`~/.mt5-vantage`** | Vantage | **Running** (capture ~10:47–10:48 local) | **Live** | Primary after switch — majors + **XAUUSD FULL** |
| `~/.mt5-fpmarkets` | FP Markets | Was running earlier | Live at first pass; later idle | Gold name `XAUUSD.r`; BTC name `BTCUSD` |
| `~/.mt5-wsf` | WSFmarkets | Not running | Empty | No snapshot |
| `~/.mt5` | Legacy generic | Not running | Stale | Ignore |

**Symlink:** `~/.mt5-fpmarkets/.../MetaTrader 5` → `FP Markets MT5 Terminal` (CLI default path works).

**Active profile used for live CLI:**

```bash
set -a; source config/brokers/fpmarkets.env; set +a
export MT5_BACKEND=file
uv run mt5-arch ping --json
```

---

## 2. Live connection (FP Markets)

| Field | Value |
|-------|--------|
| Ping | `connected=true`, build **6090**, company First Prudential Markets Limited |
| Login | `84076984` |
| Server | `FPMarketsSC-Live` |
| Currency / leverage | USD / **500** |
| Balance / equity (snapshot) | ~3346 / ~2270 USD (open loss) |
| Algo trading | `algo_allowed=true` (account JSON) |
| Terminal | `trade_allowed=true`, `tradeapi_disabled=false` |
| Bridge | Mt5ArchBridge writing `MQL5/Files/mt5_arch/` every ~1s |

**Open positions (bridge `positions.json`):**

| Ticket | Symbol | Side | Volume | Notes |
|--------|--------|------|--------|-------|
| 237511830 | **NZDCHF.r** | sell | 0.48 | `.r` raw-pricing suffix |
| 237702274 | **NZDCHF.r** | sell | 0.48 | |
| 242365136 | **US30** | sell | 0.2 | Index CFD |

**Journal evidence (2026-08-03):**

- Market sell **0.01 BTCUSD** filled @ **63677.80** (order #242248269) — BTC is tradeable on this account.
- Close buy 0.01 BTCUSD @ 64003.55 later same day.

---

## 3. Server time vs UTC

| Clock | Value at capture |
|-------|------------------|
| Host UTC | 2026-08-04 **15:37–15:41** UTC |
| Host local | **10:37–10:41** America/Chicago (UTC−5) |
| Last EURUSD H1 bar time in bridge | `2026.08.04 **18:00:00**` (MT5 format; CLI labels as `+00:00` **incorrectly**) |

**Conclusion:** Bar timestamps are **broker server time**, not UTC. At capture, server hour ≈ **18** while UTC hour ≈ **15** → **server ≈ UTC+3** (or GMT+3 summer; confirm after DST change).

**Implications:**

1. Session gates in `ForexUtils` use **server hours** — good — but do **not** assume server = UTC.
2. `FileBridgeClient` currently forces `tzinfo=UTC` when parsing `YYYY.MM.DD HH:MM:SS` — **mislabel**. Track as follow-up (treat as naive server time or document offset).
3. Heartbeat **file content** uses `TimeLocal()` (Wine host local), while **staleness** correctly uses **file mtime** — do not parse heartbeat integer as UTC wall clock.

**Documented offset (FP Markets, 2026-08-04):**

```
server_utc_offset_hours ≈ +3
# session_wall_utc ≈ server_hour - 3
```

---

## 4. Symbol matrix

### 4.1 FP Markets — live via bridge (InpSymbols default at capture)

EA still exporting only names that **SymbolSelect** succeeds for under the **running** input list (majors + bare XAUUSD). Gold/BTC charts exist, but export list was not yet reloaded with new defaults (see §6).

| Symbol | min | max | step | contract | digits | point | tick_value | tick_size | trade_mode | H1 candles |
|--------|-----|-----|------|----------|--------|-------|------------|-----------|------------|------------|
| EURUSD | 0.01 | 50 | 0.01 | 100000 | 5 | 1e-5 | 1.0 | 1e-5 | **DISABLED** | Live (5+ bars) |
| GBPUSD | 0.01 | 50 | 0.01 | 100000 | 5 | 1e-5 | 1.0 | 1e-5 | **DISABLED** | Live |
| USDJPY | 0.01 | 50 | 0.01 | 100000 | 3 | 0.001 | ~0.635 | 0.001 | **DISABLED** | Live |
| USDCHF | 0.01 | 50 | 0.01 | 100000 | 5 | 1e-5 | ~1.235 | 1e-5 | **DISABLED** | Live |
| XAUUSD | — | — | — | — | — | — | — | — | **not in export** | Empty files from Aug 3 (`SymbolSelect` fail) |
| BTCUSD | — | — | — | — | — | — | — | — | **not in export yet** | Pending EA input reload |

**`trade_mode=DISABLED` on a Tuesday with live quotes:** treat as a hard gate for any live path until re-checked. Account can still trade other symbols (NZDCHF.r, US30, BTCUSD per journal). Possible causes: per-symbol session, product enablement, or account group rules — **not** “market is closed globally.”

### 4.2 FP Markets — discovered names (journal + charts)

| Asset | Exact Market Watch name | Evidence |
|-------|-------------------------|----------|
| **BTC** | **`BTCUSD`** | EA loaded on `BTCUSD,M15`; live trade 0.01 lot |
| **Gold** | **`XAUUSD.r`** | EA loaded on `XAUUSD.r,H1` |
| FX raw | `*.r` suffix (e.g. **NZDCHF.r**) | Open positions |
| Index | `US30` | Open position |

Broker catalog size (journal): **834 symbols** synchronized.

**Do not use bare `XAUUSD` on FP Markets** — use **`XAUUSD.r`**.

### 4.3 Vantage — **LIVE** (2026-08-04 ~15:48 UTC)

CLI: `source config/brokers/vantage.env` + `uv run mt5-arch …`  
Artifacts: `phase0/vantage-*.json`, `phase0/vantage-live-SUMMARY.json`

| Field | Value |
|-------|--------|
| Login | `27496181` |
| Server | `VantageMarkets-Live 5` |
| Company | Vantage Markets (Pty) Ltd / Vantage International Group Limited |
| Currency / leverage | USD / **500** |
| Balance / equity | ~8983 / ~7080 USD |
| Ping | connected, build **6090**, trade_allowed |
| Server clock | same pattern as FP — H1 bar `18:00` vs UTC `15:48` → **≈ UTC+3** |

| Symbol | min | max | step | contract | digits | point | tick_value | tick_size | trade_mode | H1 |
|--------|-----|-----|------|----------|--------|-------|------------|-----------|------------|-----|
| EURUSD | 0.01 | 100 | 0.01 | 100000 | 5 | 1e-5 | 1.0 | 1e-5 | **FULL** | live |
| GBPUSD | 0.01 | 100 | 0.01 | 100000 | 5 | 1e-5 | 1.0 | 1e-5 | **FULL** | live |
| USDJPY | 0.01 | 100 | 0.01 | 100000 | 3 | 0.001 | ~0.635 | 0.001 | **FULL** | live |
| USDCHF | 0.01 | 100 | 0.01 | 100000 | 5 | 1e-5 | ~1.235 | 1e-5 | **FULL** | live |
| **XAUUSD** | 0.01 | 100 | 0.01 | **100** | **2** | 0.01 | **1.0** | **0.01** | **FULL** | **live** |

**XAUUSD H1 last bar (server time 18:00):** O 4083.53 · H 4087.22 · L 4074.79 · C 4083.61 · vol 23277

**BTC on Vantage:**

- Journal: `Mt5ArchBridge (BTCUSD,H1) loaded successfully` → chart/symbol name is **`BTCUSD`**
- Bridge export at capture still **missing BTCUSD** (running EA inputs were v1.03 list without BTC)
- **v1.04** source + `.ex5` deployed/compiled on Vantage (0 errors) — **re-attach EA once** so `InpSymbols` includes `BTCUSD`, then re-dump

**Open positions (not algo targets):** 3× NZDCHF sells (1.36 each), 1× DJ30.r sell 0.4

**vs FP Markets:**

| | Vantage | FP Markets |
|--|---------|------------|
| Gold symbol | `XAUUSD` | `XAUUSD.r` |
| Majors trade_mode (Tue capture) | **FULL** | DISABLED |
| max_lot majors | 100 | 50 |
| BTC chart name | `BTCUSD` | `BTCUSD` |
| Index in positions | `DJ30.r` | `US30` |

### 4.4 WSF

No live or stale symbol matrix. Prefix exists; bridge never populated.

---

## 5. H1 candle sample (FP, EURUSD)

Last 5 H1 bars (server timestamps):

| time (server) | O | H | L | C | vol |
|---------------|---|---|---|---|-----|
| 2026-08-04 14:00 | 1.15133 | 1.15230 | 1.15110 | 1.15156 | 4584 |
| 15:00 | 1.15156 | 1.15227 | 1.15127 | 1.15143 | 3734 |
| 16:00 | 1.15142 | 1.15255 | 1.15088 | 1.15231 | 6084 |
| 17:00 | 1.15231 | 1.15303 | 1.15182 | 1.15225 | 4907 |
| 18:00 | 1.15225 | 1.15248 | 1.15128 | 1.15157 | 2403 |

GBPUSD / USDJPY / USDCHF similarly live. Full JSON under `phase0/fpmarkets-candles-*-H1.json`.

---

## 6. Platform change made during Phase 0

Updated `mql5/Mt5ArchBridge.mq5` defaults (**v1.04**):

```
InpSymbols = "EURUSD,GBPUSD,USDJPY,USDCHF,XAUUSD,XAUUSD.r,BTCUSD"
```

- Compiled cleanly on FP prefix (`0 errors, 0 warnings`).
- Deployed to `~/.mt5-fpmarkets/.../MQL5/Experts/`.
- **Running EA instances still use prior saved inputs** until charts are re-attached or Inputs are edited in the terminal UI.

### Manual step (required to finish gold/BTC specs on live bridge)

In FP Markets MT5 (running):

1. Open Navigator → Experts → Mt5ArchBridge (v1.04).
2. On the **BTCUSD** and/or **XAUUSD.r** chart: remove old EA → attach again **or** open Inputs and set:

   `EURUSD,GBPUSD,USDJPY,USDCHF,XAUUSD,XAUUSD.r,BTCUSD`

3. Confirm Algo Trading green.
4. Re-run:

```bash
set -a; source config/brokers/fpmarkets.env; set +a
uv run mt5-arch symbols XAUUSD.r BTCUSD EURUSD --json
uv run mt5-arch candles BTCUSD --tf H1 --count 5 --json
uv run mt5-arch candles XAUUSD.r --tf H1 --count 5 --json
```

5. Append results into the phase0 dumps under `docs/research/phase0/` (existing:
   `fpmarkets-symbols-majors.json`, `fpmarkets-symbols-xauusd.json` — the once-planned
   `fpmarkets-symbols-btc-xau.json` was never written).

---

## 7. Priority matrix (post-discovery)

| Symbol | Broker | Priority | Ready for Wave B observe? |
|--------|--------|----------|---------------------------|
| EURUSD | FP live | **P0** | Yes (quotes + candles); watch trade_mode |
| GBPUSD | FP live | **P0** | Yes |
| USDJPY | FP live | **P0** | Yes |
| XAUUSD.r | FP live | **P0** | After EA input reload |
| BTCUSD | FP live | **P1** | After EA input reload; already proven tradeable |
| USDCHF | FP live | **P1** | Yes (quotes) |
| XAUUSD | Vantage | **P0** when that prefix is live | Specs known (stale FULL) |
| NZDCHF.r / US30 | FP | out of P0 research scope | Open risk today — not algo targets |

---

## 8. Risks confirmed by discovery

1. **Broker symbol suffixes differ** — FP gold = `XAUUSD.r`; Vantage gold = `XAUUSD`; BTC = `BTCUSD` (no suffix here).
2. **`trade_mode` must be read live** — DISABLED ≠ no quotes.
3. **Candle times are server time**; Python currently tags them as UTC.
4. **One prefix at a time** — only FP live; Vantage/WSF not measured simultaneously.
5. **Open discretionary risk** on NZDCHF.r / US30 — unrelated to algo path but affects equity/margin headroom.
6. **Agent margin math** still unsafe for BTC until price is included (research memo).

---

## 9. Exit criteria checklist

| Criterion | Status |
|-----------|--------|
| Effective connection on at least one prefix | **Done** (FP + **Vantage live**) |
| Majors symbol dump (contract/tick/digits/min_lot) | **Done** (FP + Vantage) |
| XAUUSD (or broker alias) specs | **Done on Vantage** (`XAUUSD` FULL, contract 100); FP still needs `XAUUSD.r` reload |
| BTC exact name | **Done** (`BTCUSD` on FP and Vantage charts) |
| BTC live SymbolInfo + H1 sample via bridge | **Pending** one EA re-attach after v1.04 (both brokers) |
| Server-time offset documented | **Done** (~UTC+3 FP + Vantage, 2026-08-04) |
| Vantage live dumps | **Done** |
| WSF live dumps | **Not done** |

---

## 10. Next actions

1. **One more UI step (Vantage):** remove/re-add Mt5ArchBridge so v1.04 inputs load (`…,XAUUSD,XAUUSD.r,BTCUSD`). Then tell agent to dump BTC.
2. Optional: same re-attach on FP for `XAUUSD.r` + `BTCUSD` bridge export.
3. **Wave B:** Fib + logger on Vantage `EURUSD` / `GBPUSD` / `USDJPY` / `XAUUSD` (H1).
4. Optional: WSF prefix when that terminal is up.
5. Engineering: candle timezone labeling; `positions` CLI reader.

---

## 11. Artifact index

| File | Content |
|------|---------|
| `phase0/fpmarkets-ping.json` | Live ping |
| `phase0/fpmarkets-account.json` | Live account |
| `phase0/fpmarkets-symbols-majors.json` | EURUSD–USDCHF specs |
| `phase0/fpmarkets-candles-*-H1.json` | H1 samples |
| `phase0/fpmarkets-positions.json` | Open positions |
| `phase0/fpmarkets-config.json` | Redacted settings |
| `phase0/fpmarkets-journal-20260804.txt` | Journal extract (BTC/XAU load lines) |
| `phase0/vantage-stale-snapshot.json` | Pre-live snapshot (superseded) |
| `phase0/vantage-ping.json` / `account` / `symbols-p0` / `candles-*-H1` | **Live** Vantage dumps |
| `phase0/vantage-live-SUMMARY.json` | Machine-readable Vantage matrix |
| `phase0/vantage-positions.json` | Open NZDCHF / DJ30.r |
| `mql5/Mt5ArchBridge.mq5` | v1.04 InpSymbols (deployed FP + Vantage) |

*Phase 0 is discovery only. No live algo orders were placed by this work. Prior BTCUSD fill is historical journal evidence from discretionary trading.*

# Timescale true CVD — design memo (`timescale_true_cvd_v1`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-19 |
| **search / architecture id** | `timescale_true_cvd_v1` |
| **Kind** | Research-layer **infra** (not an OHLCV family) |
| **Lock** | [`results/timescale_true_cvd_v1_lock.json`](../../results/timescale_true_cvd_v1_lock.json) |
| **Grill** | [`results/timescale_true_cvd_v1_grill.md`](../../results/timescale_true_cvd_v1_grill.md) |
| **promote / live_go** | **no / false** |
| **Instruments** | **TBD** — do not silently restart US100 session-scalp |
| **Timescale** | Schema + compose **sketch only**. Not started. |
| **XAU** | Idle. `results/xau_loop_status.md` **not edited**. |

This is Path 2 after sealed BTC H1 PA (`btc_h1_trend_pullback_v1`, `btc_h1_range_vol_breakout_v1` Config #5 holdout n=37&lt;40) and sealed US100 v1–v8. It is **not** a retune and **not** Timescale-as-M5-proxy.

---

## 1. Question

Can the research layer keep a **tick tape** (broker `MqlTick`: bid, ask, last, volume, flags, `time_msc`) and compute **signed-volume CVD** from last trades — and later ask whether that tape shows absorption at a session node?

Until last-trade fields populate, the honest answer is “we do not know.” This increment freezes the contract so a later dump cannot redefine CVD as bar `tick_volume`.

---

## 2. What is already on disk (2026-08-19, read-only)

| Claim | Fact |
|-------|------|
| Research tick store in this repo | **None** |
| `docker-compose` in this repo (before this increment) | **None** |
| Parseable `MqlTick` CSV / JSONL | **None** (`MQL5/Files` = OHLC / parity / SR, not ticks) |
| `CopyTicks` / `MqlTick` export in `mql5/` | **None**. Bridge is timer OHLC. `ExportInstrumentHistory.mq5` is bars. |
| Wine `Bases/**/ticks/*.tkc` | **Yes** — MetaQuotes compressed monthly caches (UTF-16 “Copyright … MetaQuote” header). FP: BTCUSD Jul–Aug, US100 Aug, US30 Aug; `ticks.dat` indexes. Vantage BTCUSD Aug; Exness BTCUSDm Aug. |
| `.tkc` = research store? | **No.** Do not parse, commit, or screen from it. |
| Dukascopy tick files in this repo | **No.** Other workspace repos have Dukascopy **candle** importers. |
| Unrelated Timescale | `crypto-agent-timescaledb-1` on `127.0.0.1:15432` — **do not use**. |

`US500/ticks.dat` exists under FP. That does **not** reopen US500 or the US-index memo line “not in any prefix.”

---

## 3. Schema (sketch — unused)

Files: [`docs/research/timescale/schema.sql`](timescale/schema.sql), [`docs/research/timescale/docker-compose.yml`](timescale/docker-compose.yml).

**Grain:** one row per `MqlTick` after a dump. Not a bar. Not `tick_volume` on `MqlRates`.

| Column | Role |
|--------|------|
| `time_utc` | `timestamptz`, hypertable partition. From `time_msc` minus documented `server_utc_offset_sec`. Do not assume `time_msc` is UTC. |
| `time_msc` | Broker millisecond stamp as stored |
| `seq` | Order among ticks that share `time_msc` |
| `broker` / `symbol` / `source` | Identity. `source` ∈ `copyticks_csv`, `synthetic`, (later) others. Never `tkc`. |
| `bid` / `ask` / `last` | Quotes + last trade. `last=0` means no last. |
| `volume` / `volume_real` | Last-trade size. Both 0 → no size. |
| `flags` | MT5 bitmask (BID=2, ASK=4, LAST=8, VOLUME=16, BUY=32, SELL=64) |
| `server_utc_offset_sec` | Same idea as HC exports (FP history used +10800). Per-row so DST mistakes are visible. |

Primary key: `(broker, symbol, time_utc, time_msc, seq)`. Unique also on `(broker, symbol, source, time_msc, seq)`.

**Timezone:** store UTC. Session clocks (America/New_York, Europe/London) are **query-time** labels, not storage TZ. Do not freeze a session split until an instrument is picked.

**Not in v1 SQL:** `cvd_bars` hypertables. Aggregate later from `ticks`. Do not pre-bake a proxy.

Compose (if ever started, **not now**): `127.0.0.1:15433:5432` so it cannot collide with crypto-agent `:15432`. Localhost bind only.

---

## 4. Ingest pipeline (designed, not run)

```
Wine MT5 CopyTicksRange  →  CSV in MQL5/Files/mt5_arch/ticks/  →  host copy to results/tick_data/
                                                                    →  (later) COPY into ticks
```

### Live-safe (later increment — do not compile on the live prefix now)

- New script, not `ExportInstrumentHistory.mq5` (that is OHLC + spread).
- `CopyTicksRange(symbol, from_msc, to_msc, ticks, COPY_TICKS_ALL)`.
- **Timer / script once**, never `OnTick` file I/O (bridge freeze lesson: timer-only writes).
- Bounded window (minutes/hours), not “download all history.”
- Do not kill `terminal64.exe`. Do not use `19-run-htf-fib-backtest.sh`.
- Algo Trading must already be on if an EA helper is used; prefer a **script** the user runs once.
- CSV columns must match `scripts/tick_cvd_core.py` (`MQL_TICK_CSV_COLUMNS`).

### Offline files

- Accept only the documented CSV. Reject `.tkc` / `ticks.dat` / bar history CSVs.
- Gitignore `results/tick_data/` (fat tapes). Fixtures stay tiny and synthetic.

### What this increment does **not** do

No dump, no `COPY`, no `docker compose up`, no attach, no prefix wipe.

---

## 5. How CVD is computed

Implementation: [`scripts/tick_cvd_core.py`](../../scripts/tick_cvd_core.py).

**True signed volume** (only these add to `cvd_true`):

1. `flags & TICK_FLAG_BUY` and qty &gt; 0 → `+qty`
2. `flags & TICK_FLAG_SELL` and qty &gt; 0 → `−qty`
3. qty = `volume_real` if &gt; 0 else `volume` if &gt; 0

**Inferred** (separate series, never labeled true):

- LAST set, no BUY/SELL, qty &gt; 0: `last >= ask` buy, `last <= bid` sell, else last vs mid.
- BUY/SELL with qty unset: **not** counted as volume CVD. Optional later `signed_tick_count` must be named as such.

**Quote-only** (BID/ASK, `last==0`, no qty): BBO update. **CVD unchanged.**

`cvd_true[i] = sum(signed_true[0..i])`. Session reset is **not** frozen (instrument TBD).

If a dump shows `last==0` on every row, Path 2 **falsifies** for that broker/symbol. Do not fall back to `sign(close-open)*tick_volume`.

Retail CFD last size is often 1: then CVD is **signed last-tick count**, still not exchange depth, still not bar `tick_volume`. Say so when it happens.

---

## 6. Session nodes of interest (not a screen)

Do not attach a clock until `instruments` is set. Candidates only:

| If later instrument is… | Nodes worth a pre-register |
|-------------------------|----------------------------|
| US equity-index CFD | NY cash 09:30–10:00 ET; IB 09:30–10:30; 15:45 flatten as an *exit* clock only |
| BTCUSD CFD | 24/5; London/NY overlap; weekend gap. **Not** a US100 ORB recycle |
| XAU | **Not this path.** XAU stays idle |

Picking US100 here would reopen a sealed lane. That is a lock falsifier.

---

## 7. What would prove “absorption”

Not computable this increment (no tape).

A later `search_id` would need, frozen first:

1. Last-trade ticks (`cvd_true` moves) at a named node.
2. **Divergence:** price makes a node high (low); CVD does not make a confirming high (low).
3. Or **stall:** `|ΔCVD|` in the top pre-registered quantile of that node while price range ≤ *k* ticks.
4. Costs and a split that do not reuse a burned US100 window as if it were virgin.

Quote-only tape → absorption **unprovable**. Bar `tick_volume` spike → **not** absorption.

---

## 8. Honest gap list

1. No research tick store.
2. No parseable dump; `.tkc` is not a substitute.
3. Last/volume/flags populate **unknown** on FP BTCUSD / US100 / others.
4. No `CopyTicks` script shipped.
5. Timescale not running for this repo; compose is a sketch.
6. Instruments TBD.
7. Absorption undefined as a trade rule.
8. History depth of `CopyTicksRange` unknown (often days, not years).

---

## 9. Charter / platform

Option B dual-layer: this lives under `docs/research/`, `scripts/tick_cvd_core.py`, `results/`. **`src/mt5_arch` must not import it.** File-bridge stays the overlay path.

Platform docs that say “no Timescale in `mt5-arch-integration`” mean **no production DB in the platform package**. A research sketch does not change that.

---

## 10. Leftover

1. User-authorized, live-safe `CopyTicks` dump of a short window.
2. Populate audit (`last`, qty, BUY/SELL rates).
3. Then freeze an instrument — or stop.
4. Do **not** screen OHLCV under `timescale_true_cvd_v1`.

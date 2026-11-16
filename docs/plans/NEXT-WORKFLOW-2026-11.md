# mt5-arch-integration — Next Workflow (2026-11)

**Written:** 2026-11-16 · **For:** builders (Cursor, Hermes, Claude Code) and the operator
**Context:** cross-repo review of all trading agents. The XAU research loop is
`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` with `K_prior=25` (see
`results/xau_loop_status.md`). Every closed family used OHLC bars. This repo's MT5
terminals expose two **free data types no repo uses yet**: the built-in **economic
calendar** and **real tick history**. This plan turns both into platform data
products, then gates any research on them behind the existing charter discipline.

## Ground rules for every item

- `AGENTS.md`, `CLAUDE.md` and `docs/CHARTER-RESEARCH-LAYER.md` stay authoritative.
- **Platform vs research:** exporters and readers are platform (`mql5/Scripts/`,
  `src/mt5_arch/`). Studies are research (root scripts, `results/`). `src/mt5_arch`
  must not import from research code.
- No orders anywhere in this plan. Exporters are read-only scripts. `live_trader.py`
  is never run with `--live`.
- Pre-registered holdout `holdout_start = 2026-01-01` (`results/xau_holdout_lock.json`)
  applies to every study: selection strictly before it.
- MQL5 files: repo `mql5/` is source of truth; deploy with
  `scripts/18-install-forex-indicator.sh` (add new scripts to its copy list) and
  compile with MetaEditor (`/compile:`). Export shells follow the pattern of
  `scripts/export-instruments-from-wine-mt5.sh` (challenge file, completion record).
- Clock rule (lesson from manual-trading-agent's NY-13:30 lane): broker server time is
  **not** UTC and not a fixed offset. Convert with the per-date rule and prove it with
  a lag-0 check against a UTC-native series before any study uses the timestamps.
- Tests: `uv run pytest`; lint: `uv run ruff check src tests scripts`.
- One PR per item, branch `feat/<item-id>-<slug>`.

## Status board

| ID | Item | Owner | Depends on | Size |
|----|------|-------|-----------|------|
| MT-1 | Economic-calendar history exporter + Python reader | Builder | — | M |
| MT-2 | Calendar point-in-time (PIT) forward logger + audit | Builder, then Hermes runs | MT-1 | M |
| MT-3 | Tick-spread / all-in cost exporter per broker | Builder, Hermes runs per prefix | — | M |
| MT-4 | Calendar event-study **charter** (freeze only) | Builder → Operator says "screen it" | MT-1, MT-2 audit PASS | S |
| MT-5 | #132 REDUCE/FLAT actor: defer | Operator | — | — |

---

## MT-1 — Economic-calendar history exporter + reader

**Why:** MT5 ships MetaQuotes' calendar (actual, forecast/consensus, previous,
revised previous, importance, impact) for every major economy, free on every
broker terminal (Vantage, Exness, FP Markets …). It fixes crypto-agent's broken NFP
consensus source (crypto **CR-1**) and enables event studies on XAU/FX/indices with the
broker's own prices.

**MQL5 — new `mql5/Scripts/ExportEconomicCalendar.mq5`** (script, not EA: one-shot,
no bridge bloat):

- Inputs: `InpCountries="US,EU,GB,JP,AU,CA,CH,NZ,CN"`, `InpFrom` (datetime, default
  2015-01-01), `InpTo` (default now), `InpMinImportance` (default MODERATE),
  `InpOutDir="mt5_arch\\calendar"`, `InpChallengeFile` (same pattern as
  `ExportInstrumentHistory.mq5`).
- API: `CalendarCountries()` → map country id ↔ code/currency;
  `CalendarEventByCountry(code, events)` → event metadata;
  `CalendarValueHistory(values, from, to, code)` **in yearly chunks** (large ranges
  can return partial arrays; check `ResetLastError`/`GetLastError` per chunk and log
  counts per chunk).
- Values are `long` scaled by 10^6 with `LONG_MIN` meaning missing. Use the struct
  helpers (`HasActualValue()`, `GetActualValue()`, `GetForecastValue()`, …); write
  blank for missing. **Never write 0 for missing.**
- Output CSV `calendar_values_<from>_<to>.csv`, columns:
  `value_id,event_id,event_code,event_name,country_code,currency,importance,
  event_type,sector,frequency,time_mode,unit,multiplier,digits,
  time_server,period,revision,actual,forecast,prev,revised_prev,impact_type`
  (`time_server` = raw `MqlCalendarValue.time`, which is trade-server time).
- Completion record `calendar_export_complete.json`: terminal/broker, account server,
  `TimeTradeServer()`, `TimeGMT()`, rows per country, first/last time, sha256 of CSV.
- Shell wrapper `scripts/export-calendar-from-wine-mt5.sh` mirroring
  `export-instruments-from-wine-mt5.sh`; copies the CSV into
  `results/calendar/<broker>/` (**add to `.gitignore`**; commit only manifests).

**Python — `src/mt5_arch/calendar.py` (platform reader, stdlib + pydantic only):**

- `CalendarValue` model; `load_calendar_csv(path) -> list[CalendarValue]` with
  strict parsing (blank → `None`, bad row → error with line number).
- `server_to_utc(ts_server, broker)`: per-date conversion. Default rule for the
  ET+7 brokers already proven in the NY-13:30 lane (server = America/New_York + 7h);
  table of brokers in `config/broker_install_dirs.json` gains a `server_tz_rule` key.
  Unknown broker → raise, don't guess.
- CLI: `mt5-arch calendar --csv PATH [--country US] [--event-code nonfarm-payrolls]
  [--from --to] [--json]`.
- Tests with a small fixture CSV: missing values stay `None`; DST edges (US March/
  November shoulder weeks) convert correctly; unknown broker raises.

**Validation (must be in the PR):** export US 2015→now on one broker; show
NFP rows for 3 known releases with actual/forecast; prove `server_to_utc` gives
12:30/13:30 UTC across DST for NFP; report coverage (first year with forecasts).

**Done when:** exporter, reader, CLI, tests merged; a manifest of one real export
committed under `results/calendar/manifests/`.

## MT-2 — Point-in-time forward logger + audit

**Why:** a history export shows today's stored `forecast`. If MetaQuotes revises
forecasts after the fact, history-based surprise studies have look-ahead. This item
proves (or disproves) that history forecasts equal what was visible before release.

**Build:**

- Bridge EA addition (bump `BRIDGE_VERSION` to 1.30): every `InpCalendarSnapshotMin`
  (default 30) minutes, and only on the writer instance, call
  `CalendarValueLast(change_id, values)` for the configured countries; write changed
  values to `calendar_changes.jsonl` (append) with `snapshot_server_time` and
  `change_id`; on first run seed with `CalendarValueHistory(now-1d, now+7d)`.
  Keep it out of `OnTick`; respect the Wine I/O cautions in the EA header.
- Python `scripts/calendar_pit_logger.py` (cron on the MT5 host, every 15 min): copies
  new lines from the bridge dir into `results/calendar_pit/<broker>/YYYY-MM.jsonl`
  (gitignored), deduped by `(value_id, change_id)`, never edits past lines.
- Health: add `calendar_last_change_age_seconds` to
  `scripts/mt5_metrics_exporter.py` textfile metrics.
- **Transport to Hetzner** (consumers there: crypto CR-1, manual MA-3): MT5 runs on the
  Arch desktop, the agents on the Hetzner host. Do **not** use the research Kafka bus
  (`research/kafka-signal-bus/` is local, research-only). Add
  `scripts/push_calendar_pit.sh`: `rsync -a --append-verify` of
  `results/calendar_pit/` to the server over Tailscale (target path from
  `config/local.paths`, gitignored; e.g. `/opt/shared/calendar_pit/`), run from the same
  cron after the logger. Consumers treat the copy as read-only and check file age.

**Audit (Hermes, after ≥ 6 weeks of logging):** `scripts/calendar_pit_audit.py`
compares, for each released value, the last pre-release `forecast` in the PIT log
with the `forecast` in a fresh history export. Report per event: n, exact-match %,
max abs difference. Write `results/calendar_pit_audit_<date>.md` with verdict
`PIT_PASS` (≥ 99% exact match on HIGH-importance events) or `PIT_FAIL`.

**Done when:** logger running on ≥ 1 broker, audit report written. MT-4 may not start
before `PIT_PASS`. On `PIT_FAIL`, only forward-logged forecasts may ever be used.

## MT-3 — Tick-spread and all-in cost exporter per broker

**Why:** ctrader's validated edge loses more than half of gross R to a 1.5 pip
assumed cost (`ctrader-trading-agent/research/floor_bind_report.md`). Measuring each
broker's real cost tells the operator where that edge nets most (ctrader **CT-2**,
**CT-6**). **Caveat:** `MqlRates.spread` is the *minimum* tick spread in a bar (see
`scripts/fetch_m1_official_mcp.py` header), so bar spreads understate cost. Use ticks.

**MQL5 — new `mql5/Scripts/ExportTickSpreads.mq5`:**

- Inputs: `InpBroker`, `InpSymbols` (default the 11 SM pairs:
  `AUDUSD,EURGBP,EURJPY,EURUSD,GBPJPY,GBPUSD,NZDJPY,NZDUSD,USDCAD,USDCHF,USDJPY` plus
  `XAUUSD`), `InpDays=60`, `InpOutDir`.
- Resolve symbols via `FxSymbolRegistry.mqh` (suffixes differ per broker).
- `CopyTicksRange(sym, ticks, COPY_TICKS_INFO, from_ms, to_ms)` **one day at a time**
  (memory); aggregate in-script into buckets `(symbol, weekday, utc_hour)`: tick count,
  mean, median, p90 spread in points, using `SYMBOL_POINT`/`SYMBOL_DIGITS` to convert to
  pips (pip = 10 points on 5/3-digit quotes; write both). Server→UTC per MT-1's rule.
- Commission: read `HistoryDealsTotal` for the last 90 days; if this login has deals,
  report median `DEAL_COMMISSION` per lot per side; otherwise write `null` and let the
  operator fill it from the broker's published schedule in the JSON (field
  `commission_source: "deals" | "published" | null`).
- Output `tick_spreads_<broker>_<from>_<to>.csv` + completion record.

**Python — `scripts/broker_cost_report.py` (research, offline):**

- Reads all brokers' exports; computes all-in round-turn pips per pair =
  median spread in the **SM entry windows** (UTC 01–03, 08–10, 13–15; match
  `ctrader-trading-agent/src/strategies/session_clock.py`) + 2 × commission per side
  in pips (commission USD/lot → pips via pip value per lot).
- Writes `results/broker_costs/<date>/summary.md` and one
  `<broker>.json` per broker in the exact format ctrader CT-2 reads:
  `{"EURUSD": 0.92, "GBPUSD": 1.10, ...}` + a `_meta` block (window, n ticks,
  commission source).

**Hermes runs:** each broker prefix that has a working login
(`~/.mt5-vantage`, `~/.mt5-exness`, `~/.mt5-fpmarkets`, prop prefixes). One terminal
per prefix at a time (`KILL_EXISTING` caution in `CLAUDE.md`).

**Done when:** ≥ 2 brokers measured, JSONs copied to ctrader
`config/cost_scenarios/` via a ctrader PR (CT-2).

## MT-4 — Calendar event-study charter (freeze only)

**Gate:** MT-1 merged, MT-2 audit = `PIT_PASS`. Charter only; **no PF computed** in
this item. Screening needs the operator to say "screen it" (repo convention).

**Steps:** write `results/xau_charters/<date>_<family_id>.json` following the
existing charter schema (see `2026-09-19_*` files), with:
- `K_prior = 25` (current count from `xau_loop_status.md`), this family = K 26.
- One hypothesis, zero free knobs. Example to adapt, not to tune: *US HIGH-importance
  release with standardized surprise |z| ≥ 1 (z from develop-window SD per event,
  frozen) → XAUUSD position opposite USD surprise sign at the first M5 close after
  release, exit at +4h; costs from MT-3 for the broker that supplies the tape.*
- Develop window ends 2025-12-31; holdout untouched; control arm (e.g. same-time
  random-side or always-flat) named.
- Kill criteria and `do not` list in the same style as the loop status entries.
- Add a `FROZEN` entry to `results/xau_loop_status.md`.

## MT-5 — #132 REDUCE/FLAT actor: defer (operator)

PR #134 (positions read), #135 (control.json entry gate) and #136 (metrics) delivered
the visibility half. The REDUCE/FLAT actor matters only once MT5 holds live risk.
Comment on #132: parked until an MT5 account trades live (see ctrader CT-6).

---

## Cross-repo dependencies

| This item | Feeds | Where |
|-----------|-------|-------|
| MT-1 + MT-2 | NFP consensus capture v2 | crypto-agent **CR-1** |
| MT-1 | optional second news source | manual-trading-agent **MA-3** |
| MT-3 | `config/cost_scenarios/<broker>.json` | ctrader-trading-agent **CT-2**, **CT-6** |

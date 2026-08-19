# Grill — `timescale_true_cvd_v1` (Path 2, first increment)

Frozen **before** any ingest run, compose up, or OHLCV screen.

## Proposal

Build the **store contract** for true CVD: millisecond MqlTick rows (bid/ask/last/volume/flags), a file-first ingest plan, and a signed-volume definition that is not `tick_volume` on bars. Do not pick an instrument. Do not stand up Timescale.

## Decisions (adversarial)

| Probe | Decision |
|-------|----------|
| Is this a new OHLCV family? | **No.** Infra-first. `n_configs_expected = 0`. A later screen needs a new `search_id`. |
| True CVD from H1/M5 `tick_volume`? | **Forbidden.** That is the sealed US100 `tick_proxy_cvd` lie. |
| Parse Wine `.tkc`? | **No.** Caches exist (FP BTCUSD/US100/US30, Vantage BTCUSD, Exness BTCUSDm). Header is MetaQuotes compressed copyright, not a dump format. Treating `.tkc` as the store is a falsifier. |
| Sample on disk? | **No parseable MqlTick CSV.** Bridge and `Files/` dumps are OHLC. Prototype uses a **synthetic** fixture only. Skip runtime DB. |
| Use crypto-agent Timescale `:15432`? | **No.** Different repo, already bound on localhost. This sketch (if ever started) must use another localhost port. |
| `docker compose up` now? | **No.** This repo had no compose. Sketch is unused/unstarted. |
| Instrument = US100 because leftover named “NY-open CVD”? | **No.** Instruments **TBD**. Sealed v1–v8 stay sealed. Do not restart session-scalp. |
| Instrument = BTCUSD because Path 1b just died? | **Not this increment.** BTC is a *candidate for a later audit*, not a frozen symbol. Last-trade populate is unknown. |
| Dukascopy / cTrader pipeline? | **Ideas only.** Those scripts ingest **H1 candles**, not MT5 MqlTick. Out of charter to copy that Timescale into this repo. |
| Add `ExportMqlTicks.mq5` and compile on FP? | **Not this increment.** Dump contract is written; compile/attach would touch the live prefix. Leftover. |
| Platform Timescale? | **No.** `src/mt5_arch` stays file-bridge. Research must not import into the platform package. Prior docs that say “no Timescale in the platform” still hold. |
| Charter vs old DISCARD? | Old DISCARD was “no store + do not use Timescale as a US100 M5 proxy.” This increment designs a research store. It does **not** un-DISCARD the proxy. |
| Absorption now? | **Define only.** Cannot prove absorption without a last-trade tape. |
| XAU / `--live` / `OrderSend`? | **Off.** Do not edit `xau_loop_status.md`. |

## What would falsify (this increment)

1. Publishing a CVD number from bar `tick_volume`.
2. Setting `symbol` to US100/US30/US500 (or any name) to sneak a screen.
3. Starting compose or writing into crypto-agent’s DB.
4. Claiming `.tkc` was decoded.
5. `promote=true` / `live_go=true`.
6. Editing the XAU status file.

## Acceptance

Lock + design memo + unused SQL/compose + parser/SQL unit tests + pivot note. **promote=no.** No PR required.

## Next action (not this commit)

Live-safe `CopyTicks` dump of a **short** window, then a last-trade populate audit. Only then pick an instrument. Do not screen OHLCV.

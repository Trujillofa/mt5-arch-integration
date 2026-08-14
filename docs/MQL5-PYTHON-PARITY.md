# MQL5 ↔ Python parity (HTF Fib)

**Status:** harness in repo · offline tests use a committed synthetic golden master  
**Does not place orders.** Does not score strategies. Does not authorize live trading.

This is a platform check for buffer indices, bar order, Wilder ATR, and pivot
confirmation timing. It exists because those have already drifted between
`mql5/README.md`, `docs/HOWTO-HTF-FIB.md`, and `ForexHtfPivotsFib.mq5`.

Community Strategy Tester profit-factor numbers are not evidence.

## What is and is not proven

| Claim | Status |
|-------|--------|
| Signal buffer is **8**, shift **1** | Proven against `SetIndexBuffer` + logger defaults + fixture contract |
| Committed fixture vs `htf_fib_core` recompute | Proven. Changing the core without regenerating the fixture fails |
| Hand-derived planted pivots / fib 61.8–78.6 / ATR seed | Proven independently of `htf_fib_core` |
| `--write-synthetic` byte-match | Schema-migration guard only |
| Numbers originally came from a live MT5 terminal | Live dumps are regenerable (`MT5_PARITY_FIXTURE`); not committed. CI is the synthetic golden master |
| Live dump vs Python on default 5/5/H4 | **Passed** on v1.45 (ATR, 141 pivots, fib/swing, sidecar 5/5/0). One broker / symbol / TF pair / param set / 256 H1 bars. Not committed |
| Full RSI + EMA-bias confluence | **Not claimed.** `signal_kind=indicator_buffer` checks intermediates and no-activation-before-confirm, not row-matched signals |
| Strategy Tester / other brokers / other symbols / non-default inputs | **Not claimed** |
| `ForexSignalLogger` is live-safe | **Not claimed.** The HTF scan used to treat the forming bar as a confirm wing; a chronological bar-by-bar replay is still required |

Python is the causal reference for **same-TF** closed-bar replay: fib may be live
at `confirm_idx` and is consumed via `CopyBuffer(..., 8, 1, 1, sig)`. For **MTF**,
a chart row is eligible only when

```
available_at = htf_confirm_open + htf_period   # confirm-bar close
chart_bar_close >= available_at
```

v1.45 stamps snapshots at that `available_at` and passes the chart bar's close
into `FibAt`. v1.44 stamped the confirm **open** and compared the chart **open**,
which lit the first three H1 hours of an H4 confirmation bar early on historical
one-shot `CopyBuffer` reads. Forward-live was already clean: the forming HTF bar
is excluded as a confirmation wing.

A live export that lights fib / swing / signal before `available_at` fails.

**Configuration pin.** `iCustom` is called with defaults only (a full input list
returns 4002 on Vantage 6090). The indicator writes
`MQL5/Files/mt5_arch/htf_fib_effective_<SYMBOL>.txt` from `OnInit`. The exporter
copies those values into the manifest (`indicator_left` / `indicator_right` /
`indicator_fib_source` / `indicator_version`). For `source=mql5_export` the
verifier requires them and asserts left/right/source equal the scan and the
HTF mapping (H4→0, D1→1). `indicator_version` must be present (from
`HTF_FIB_VER`); the optional live test asserts it equals the source define.
The pin catches a mismatched **scan** (exporter `InpLeft` ≠ indicator defaults).
It does not prove a non-default chart setup: `iCustom` still cannot take an
input list. Live evidence is the default 5/5/H4 configuration only.

The synthetic golden master has no `indicator_version`. It never ran the
indicator; a hardcoded string there is how 1.44 drifted through a 1.45 bump.

## What is compared

| Stage | MQL5 side | Python side | Failure mode |
|-------|-----------|-------------|--------------|
| Bar order | `CopyRates` reversed to index 0 = oldest | timestamps must increase | reverse-sorted / duplicate times |
| Schema / copy | `export_ok=true`, `n_bars` / `n_htf_bars` match rows, every buffer 0–10 listed | refuse missing members, `abs_tol` missing / ≤0 / >1e-3 | incomplete or mixed dump |
| Signal index | buffer **8**, shift **1** | `HTF_FIB_BUFFERS` | reading swing-dir (7) as signal |
| Closed bar | forming bar signal must be 0 | last row signal == 0 | consuming the in-progress bar |
| Pivot timing | `confirm_idx = center_idx + right`; last HTF bar excluded | `exclude_forming=True` | forming bar used as confirm wing; center stamp |
| Fib / swing | exported buffers (confirm-**close** snaps; `FibAt` sees chart-bar close) | `walk_swing_and_fibs` + `expand_fib_states` | lookahead on `[center, confirm_close)` or MTF-early |
| Config pin | `indicator_left/right/fib_source/version` from OnInit sidecar | must equal scan `left`/`right` and HTF map; version required | exporter scan ≠ iCustom defaults |
| ATR14 | `FxAtrSeries` (Wilder) | `htf_fib_core.wilder_atr` | SMA-of-TR |

MQL5 still fail-closes on a short `CopyRates` / `CopyBuffer` (writes
`mt5_arch/parity/_failed/manifest.json` with `export_ok=false`). Python does not
see a successful fixture in that case; the copy block on a **completed** dump is
an immutable completion record, not a live short-copy detector.

## Buffer contract (ForexHtfPivotsFib v1.45+)

| Index | Name | Role |
|------:|------|------|
| 0 | `ema_fast` | plot |
| 1 | `ema_slow` | plot |
| 2 | `ema_bias` | plot / regime |
| 3 | `long_arrow` | plot |
| 4 | `short_arrow` | plot |
| 5 | `fib_618` | calculation |
| 6 | `fib_786` | calculation |
| 7 | `swing_dir` | calculation (+1/−1) |
| **8** | **`signal`** | **+1 / −1 / 0 — `CopyBuffer(..., 8, 1, 1, sig)`** |
| 9 | `rsi` | calculation |
| 10 | `rsi_ma` | calculation |

`ForexHtfFibTester` v1.40 uses an EA-native engine (not iCustom buffer 8). It
must still obey the same confirmation and Wilder ATR rules.

## Files

| Path | Role |
|------|------|
| `mql5/Scripts/ExportHtfFibParityFixture.mq5` | Terminal dump (no `OrderSend`) |
| `scripts/htf_fib_core.py` | Shared pivots + Wilder ATR |
| `scripts/verify_mql5_python_parity.py` | Compare a fixture directory |
| `tests/test_mql5_python_parity.py` | Offline adversarial tests |
| `tests/fixtures/mql5_parity/htf_fib_h1_synthetic/` | Committed golden master |

Fixture schema `mql5-python-parity/v1`:

```
manifest.json     written last; export_ok, buffer_map, copy{requested,copied},
                  left/right, ATR, n_bars, n_htf_bars, abs_tol
bars.csv          chronological chart OHLC (idx 0 = oldest)
htf_bars.csv      required; chronological HTF OHLC used for the pivot scan
buffers.csv       atr14, fib_618, fib_786, swing_dir, signal (+ optional EMA/RSI)
pivots.csv        center_idx, confirm_idx, center_time, confirm_time, ptype, price
```

## Offline (default)

```bash
python3 scripts/verify_mql5_python_parity.py
uv run pytest tests/test_mql5_python_parity.py
```

Regenerate the synthetic fixture only when the schema or planted geometry changes,
then keep the byte-match test green:

```bash
python3 scripts/verify_mql5_python_parity.py \
  --write-synthetic tests/fixtures/mql5_parity/htf_fib_h1_synthetic
```

## Optional live dump

1. `./scripts/18-install-forex-indicator.sh`
2. MetaEditor F7: `Indicators/ForexHtfPivotsFib.mq5`, then
   `Scripts/ExportHtfFibParityFixture.mq5`
3. Attach the script to an H1 chart (compile the indicator first).
   `iCustom` uses indicator defaults (4002 workaround). The dump is unique
   `symbol_tf_datetime_epoch/`. Manifest is written last and must carry
   `indicator_left` / `indicator_right` / `indicator_fib_source` matching
   the scan. Do not commit live dumps — they are regenerable artifacts;
   CI stays on `htf_fib_h1_synthetic`. `MT5_PARITY_FIXTURE` points at a
   live directory when you want the optional test.
4. Copy `MQL5/Files/mt5_arch/parity/<tag>/` out of the Wine prefix.
5. Verify:

```bash
python3 scripts/verify_mql5_python_parity.py /path/to/exported/dir
MT5_PARITY_FIXTURE=/path/to/exported/dir uv run pytest -m live \
  tests/test_mql5_python_parity.py::test_optional_live_fixture_if_present
```

HTF window default is `FX_HTF_PIVOT_SCAN_BARS` (1200), matching the indicator.
Compare only chart bars from `compare_from_chart_idx` (HTF ancestry inside the
exported window).

## Scope of the live pass (do not cite as general validation)

The v1.45 Vantage dump is evidence for **one** slice:

| Axis | What was compared | What was not |
|------|-------------------|--------------|
| Broker | Vantage | Exness, FP Markets, WSF, others |
| Symbol | XAUUSD | every other symbol the indicator is attached to |
| Timeframes | H1 chart / H4 fib source | other pairs, same-TF live |
| Parameters | default 5/5/H4 | any `InpLeft4h` / `InpRight4h` / Daily override |
| Window | 256 H1 bars, 1200 H4 bars | longer history, other sessions |
| Engine | one-shot `CopyBuffer` of closed history | Strategy Tester, forward tick replay |
| Signal | intermediates + no-activation-before-confirm | row-matched RSI/EMA confluence |

Broadening any one of those axes is a larger step than the v1.44/v1.45
causality fixes. Priorities 2–5 (broker symbol registry, MT5-versus-package
sync audit, tester provenance wrapper, `OnTradeTransaction` journal,
article-intake gate, chronological logger replay) are untouched.

## Adversarial cases the tests already cover

- Signal buffer relabelled as 7 (the old README table).
- `confirm_idx` stamped at the pivot center.
- `copied != requested` / missing `copy` members / missing `htf_bars.csv`.
- `export_ok` not true; `abs_tol` missing or huge.
- Equal chart/HTF row counts with different timeframes (identity expansion).
- Reverse-sorted timestamps; forming-bar signal ≠ 0.
- SMA-of-TR ≠ Wilder ATR14.
- Monkeypatched `expand_fib_states` / `wilder_atr` vs the frozen fixture.
- Forming HTF bar used as a confirmation wing (`exclude_forming`).
- `mql5_export` without `indicator_left` / `indicator_right` / `indicator_fib_source` / `indicator_version`.
- Sidecar left/right ≠ scan left/right.
- Synthetic manifest carrying `indicator_version` (it describes no indicator run).

## Out of scope (later PRs)

- Broker symbol capability registry (explicit mappings, no fuzzy first-match).
- MT5-versus-package multi-symbol synchronization audit.
- Strategy Tester reproducibility wrapper around `19-run-htf-fib-backtest.sh`.
- Read-only `OnTradeTransaction` journal.
- Article-intake gate / new research charters.
- Chronological bar-by-bar replay that would be required to call the logger live-safe.

Do not copy MQL5.com catalog experts into the research loop because a blog PF
looks good. Any new idea needs an independent Python implementation and this
kind of stage comparison first.

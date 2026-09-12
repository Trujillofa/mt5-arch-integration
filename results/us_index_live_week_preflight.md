# Live-week preflight (Vantage + Seven Desk)

Checked 2026-09-12 (Saturday). Re-check Monday before the cash open.

## Do not

- Host-wide `KILL_EXISTING=1` / `scripts/19-run-htf-fib-backtest.sh` on a live prefix
- Vantage ↔ prop copy
- Grid Scalper or `ForexHtfFibTester` on a live chart
- `live_trader.py --live`

## Vantage (retail overlay lane)

- [x] `Mt5ArchBridge` one chart (EURUSD M5, chart `26180515069381`), `InpBroker=vantage`, Algo Trading green (`algo_allowed=true`, `trade_allowed=true`). Heartbeat fresh, **v1.27** — leave it. Do not compile v1.28 on Vantage.
- [x] `UsIndexSessionScalp` v1.41 compiled; **DJ30.r M5** chart opened (`45942642771079`) with the overlay attached (`InpShowAtrStops=true`, ATR 1.0 / 1.5). Existing DJ30.r **M1** chart was left alone.
- [ ] **Human:** attach `ForexSignalLogger` on that DJ30.r M5 chart with `Presets/ForexSignalLogger-UsIndexSessionScalp.set` (`InpMaxSpreadPips=0`). Confirm Experts line **NO ORDERS**. MCP cannot attach EAs.
- [x] Clock: trade server last known `2026-09-12T19:19:58` vs UTC `16:19` = **UTC+3** (same as the Aug–Sep dump). Auto `InpServerUtcOffsetHours=-99` should be +3. **Monday:** panel ET vs 09:30 cash = **16:30 server**. If boxes miss, set the offset explicitly.
- [x] Current DJ30.r opens **have SL** — not flattened, not modified:

| Ticket | Side | Lots | Entry | SL | TP | Last | Note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 196446502 | buy | 2 | 53377.54 | **51700** | 52880 | 52579.51 | SL present; ~1678 pt — inventory, not ATR 1.0 |
| 197563393 | buy | 2 | 53049.56 | **51700** | 53300 | 52579.51 | same |
| 197954056 | buy | 2 | 52906.56 | **51700** | 53300 | 52579.51 | same |

Credit $3,000 is still on the book. Size next week from **balance** ($14,576), not equity-with-credit.

## Seven Desk (prop lane only)

- [x] `./scripts/20-seven-desk.sh --status` — HTTP **200**, unit active
- [ ] Armed prefixes after this compile: **v1.28 .ex5 is on disk**. Running heartbeats still say **v1.27** until you reattach the EA. Market DEAL+SL needs **v1.28**.

| Prefix | Heartbeat | Version | Notes |
| --- | --- | --- | --- |
| ftmo branded | **stale ~19h** | 1.27 | Live send will 409. Reattach/restart FTMO terminal Monday. Branded `positions.json` is empty. |
| wsf | fresh | 1.27 → reattach 1.28 | 0 positions |
| fundednext | fresh | 1.27 → reattach 1.28 | 0 positions |
| fundingpips | fresh | 1.27 → reattach 1.28 | 0 positions |
| neomaa | fresh | 1.27 → reattach 1.28 | 0 positions |
| fortraders | fresh | 1.27 → reattach 1.28 | 0 positions |
| alphacapital | fresh | 1.25 readonly | fetch-only; do not compile trading 1.28 |
| vantage | fresh | 1.27 | observe only; Seven Desk never talks here |
| fpmarkets | fresh | 1.27 | **not** a Seven Desk path |

- [x] Desk code refuses `~/.mt5-vantage` / `~/.mt5-fpmarkets`
- [x] Leftover US30/DJ30 **4.0** rows on live prop snapshots: **none**
- [x] Ticket: SL required on live US30; ATR 1.0/1.5 auto-fill; `copySlTp` locked while a live-copy switch is armed
- [ ] Firm map still: WSF `DJ30.c`; FundingPips NAS100 blank; Neomaa EURUSD-only; Alpha read-only. Do not fan out US30 blindly.

### Ignore this leftover tree

`~/.mt5-ftmo/drive_c/Program Files/MetaTrader 5/` still holds a **stale Vantage** `account.json` / `positions.json` (DJ30.r 2.0s with SL 0). That is not the FTMO book. Branded path is `FTMO Global Markets MT5 Terminal`.

## Leftover 4.0 inventory

| Prefix | Ticket | Symbol | Lots | SL | TP | leftover? |
| --- | --- | --- | --- | --- | --- | --- |
| *(none on branded live snapshots)* |  |  |  |  |  |  |

## Monday pre-open

1. Confirm overlay ET clock vs 09:30 (16:30 server).
2. Attach logger; Experts `NO ORDERS`.
3. Reattach `Mt5ArchBridge` on FTMO + armed slaves until heartbeat `version=1.28`.
4. Re-list leftover 4.0s. Flatten does not mass-close them.

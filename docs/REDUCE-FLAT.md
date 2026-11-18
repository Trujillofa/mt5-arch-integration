# REDUCE / FLAT actor — coordinator exits

`DeskOrderBridge.mqh` now executes two exit actions requested by the
coordinator through the same one-shot request file:

| Action | Effect |
|--------|--------|
| `flat` | Close the **whole** position for the given ticket |
| `reduce` | Close `volume` lots of the position (partial; equal to full is allowed) |

Both are **exits**: they are never gated by `control.json` (see
[STAGE0-CONTROL.md](STAGE0-CONTROL.md)).

## Request fields

Required as for every desk request: `request_id`, `action`, `symbol`,
`confirm`, `expect_confirm`, `expect_login`, `expect_needle`, `issued_at`.

Additional:

| Field | Notes |
|-------|-------|
| `ticket` | **Required** for `flat`/`reduce`. Explicit only: a symbol-wide flat in a hedging account is ambiguous |
| `volume` | Required for `reduce`; rounded to the symbol's volume step, must be ≥ min and ≤ the position volume |
| `magic` | Recorded on the closing deal; the explicit ticket is not magic-filtered |

## Idempotency

- The request file is already single-shot: `request_id` dedupe (result file +
  claim file) and `issued_at` TTL apply before any action.
- Re-issuing a flat with a **new** request id after the ticket is gone returns
  `ok:true, stage:"already_flat", volume_after:0` — it does not double-close.
- A ticket that never existed is a failure (`stage:"ticket"`), not a fake
  success. `HistorySelectByPosition` + `HistoryDealsTotal()` distinguishes the
  two cases.

## Response

```json
{
  "ok": true,
  "stage": "flat",              // flat | reduced | already_flat
  "reason": "seven-desk position flattened",
  "symbol": "XAUUSD",
  "ticket": 123456,
  "volume_before": 0.20,
  "volume_closed": 0.20,
  "volume_after": 0.00,
  "retcode": 10009,
  "balance_after": 4980.5
}
```

`volume_after` is read back from the position after the deal (netting may keep
the ticket with a smaller volume), so the coordinator verifies instead of
assuming. A partial close on a hedging account returns `stage:"reduced"` with
`volume_after > 0`.

## Refusals

- `expect_login` / `expect_needle` mismatch (same account gate as entries).
- Symbol outside the bridge allowlist (`EURUSD*`, `BTCUSD*`, US30 family) or a
  position whose symbol is not the resolved request symbol.
- Missing/invalid ticket; reduce volume above the position; reduce volume below
  the symbol minimum.
- Rejected `OrderSend` — **not retried** by the EA; the coordinator decides.

## Not automatic

The EA only acts when a request file is present; there is no local risk logic,
no timer-driven flatten, and no Kafka/Seven Desk wiring. Deploy requires F7
compile + `./scripts/18-install-forex-indicator.sh` per prefix.

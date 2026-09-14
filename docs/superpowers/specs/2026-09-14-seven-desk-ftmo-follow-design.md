# Seven Desk FTMO terminal follow

Date: 2026-09-14
Status: approved
Owner: seven-desk

You click in the FTMO MT5 terminal. Seven Desk copies **new** tickets (market and pending) to armed live slaves, copies later SL/TP edits, and closes those slave legs when FTMO closes.

## Locked decisions

- Origin is the FTMO terminal, not Place master trade. Desk ticket + **FTMO live master** stay as they are.
- Copy **only tickets that appear after arm**. Baseline at arm is never copied.
- When a followed FTMO position or pending is gone, close or cancel the matching slave group.
- Include new pendings and later SL/TP modifies.
- Alpha Capital stays fetch-only (`COPY_FANOUT_SKIP`).
- Approach A: diff the existing FTMO file-bridge probe. No new EA, no deal stream.
- v1 is hedging full-ticket only. Partial volume on the same ticket is out of scope.
- Open+close inside one poll window is a miss. No EA deal stream in v1.

## Non-goals

- Do not `OrderSend` on FTMO from follow (the human already did).
- Do not copy leftover US30/DJ30 (or any pre-arm ticket) when follow is armed.
- Do not persist the follow switch across reload.
- Do not restart `seven-desk.service` from this work (local main is dirty and serving :3847).
- Do not merge the PR until the operator says so.
- Do not touch Vantage / FP Markets / generic `MetaTrader 5` trees.
- Do not change `src/mt5_arch` or research-layer files.

## Architecture

```
FTMO terminal (manual click)
  → Mt5ArchBridge positions.json / orders.json
  → FTMO probe (8s idle, ~2s while follow armed)
  → follow diff (pure)
  → copy engine group
  → POST /api/{wsf,fundednext,fundingpips,neomaa,fortraders}/order
     open | cancel | close | modify
Alpha: skip. Unarmed slaves: skip. Paper: paper.
```

Follow is a **second origin** for the same copy engine. Desk-originated FTMO tickets keep desk magic `20263848` and a `groupId`; the diff ignores them so they are not copied twice.

## Session state (not localStorage)

On `DeskState`:

- `ftmoFollowTerminal: boolean` — always `false` in `loadDesk()` / seed, same as other live switches.
- Follow baseline and ticket→group map live in React/module session memory, **not** in persisted `DeskState`, so a refresh cannot copy leftovers. Suggested module state in `desk-store` or a small `follow-session.ts`:

```
baselineTickets: Set<number>     // positions ∪ pendings at arm
followGroups: Map<number, string> // FTMO ticket → groupId
pendingToGroup: Map<number, string>
```

Disarm or reset demo clears all three. Re-arm snapshots again from the current probe.

## Arm / disarm

New FTMO-card control `FtmoLiveFollow` under `FtmoLiveMaster` (same ack + confirm `FTMO-541163357`).

- Require FTMO as `masterId`.
- On arm: snapshot every current FTMO `openPositions.ticket` and `pendingOrders.ticket`. Those stay leftovers.
- `copySlTp` must stay on while follow is armed (`liveCopySlTpError` treats follow like live master).
- Slave live-copy switches stay independent. Follow fans out only to `armedCopyBrokers()`. If none are armed, still track FTMO rows as followed desk groups locally, but send no slave POSTs.
- Stale FTMO heartbeat / probe not `connected`: no new opens, no phantom closes (fail closed). Do not treat a leftover `positions.json` as live.

## Diff (pure, unit-tested)

Input: previous followed tickets + current `BridgeOpenPosition[]` + `BridgePendingOrder[]` + desk positions.

| Snapshot change | Action |
|---|---|
| Ticket in baseline | Ignore forever (leftover). |
| Desk-magic FTMO ticket (`DESK_MAGIC.ftmo`) or already a desk `liveOrder` | Ignore (desk origin). |
| New pending, not baseline | Follow group, `livePending=true`, fan-out same type. |
| New position, not baseline, not a fill of a followed pending | Follow group, market fan-out. |
| Followed pending gone **and** new position same symbol/side/lots in this poll | Fill, not close. MT5 assigns a new position ticket — retarget `followGroups`. Leave slave working limits. If a slave is still pending on the **next** poll after FTMO filled, cancel that pending and market-fill the slave. |
| Followed pending gone, no matching position | Cancel slave pendings. |
| Followed **position** ticket gone | Close the group (`close` filled legs, `cancel` still-working). |
| Followed ticket SL or TP changed (including 0 → null) | `action=modify` on every live slave leg in that group. Do not modify FTMO. |

Matching a pending fill: same `symbol` (after trim), same `side`, lots within 0.001. If two candidates, pick the new position ticket that is not already in `followGroups`.

## Fan-out

Reuse `placeLiveMasterFill` / `resolveQueuedCopies` / `fanOutLiveSlaves` / `closeLiveGroup` / existing modify POST.

- Master row: `liveBroker: "ftmo"`, `fromSnapshot: true`, `leftover: false`, `groupId` set, `followOrigin` optional flag if useful for UI.
- Lots: FTMO ticket volume is the master size; slaves use `liveLotsForFirm` / existing copy settings (max lot skip stays).
- Symbols: existing `symbolMap` + live symbol allowlists. If the mapped symbol is not on that firm’s live path, skip that slave with the current skip reason. Do not invent new symbols.
- US30 still requires SL on live legs (`liveUs30SlError`). If the FTMO ticket has no SL on US30, skip live fan-out and blotter-error; do not send naked US30.

## Poll

`useLiveProbePoll` gains an optional interval (default `8000`). Only the FTMO probe passes `2000` while `ftmoFollowTerminal` is true. Other firm cards stay at 8s. Do not hammer Wine.

Hook: after `ingestBridgePendings` / `ingestBridgePositions` in `ftmo-live-probe.tsx`, if follow is armed and the report is connected, run the diff and the resulting POSTs. Keep probe ingest itself read-only for leftovers when follow is off.

## Error handling

- Stale/missing heartbeat: no follow actions this tick.
- Slave POST 409 / fail: blotter error, keep the desk row, do not retry-storm (one attempt per event).
- Close already-flat: drop the row (`liveCloseAlreadyFlat`).
- Modify fail: keep previous SL/TP on the desk row, blotter error.
- Probe JSON error: same as today; do not disarm follow.
- Refresh while armed: switch comes back off (not persisted); operator re-arms; current tickets become the new baseline (safe).

## UI

- `FtmoLiveFollow` on the FTMO copy panel: amber/follow copy, ack, confirm token, arm switch, hint that only **new** terminal tickets copy and that closes/SLTP follow.
- Positions: followed rows are desk rows (flattenable), not leftovers.
- Blotter reason prefix: `follow · FTMO ticket N`.
- Docs: `apps/seven-desk/README.md` and `docs/SEVEN-DESK.md` — one short subsection. Merge ≠ deploy.

## Testing

Extend `tests/test_desk_copy_fanout.ts` (node `--experimental-strip-types --import tests/desk-alias-register.mjs`):

1. Baseline tickets never appear in opens.
2. New position after arm → one master follow group.
3. Desk-magic FTMO ticket ignored.
4. New pending → pending follow group.
5. Pending gone + matching position → fill (group survives, ticket retargeted), not close.
6. Followed position gone → close action.
7. Pending gone, no position → cancel action.
8. SL/TP change → modify action with new prices.
9. `liveCopySlTpError` fires when follow is armed and a slave has `copySlTp` off.
10. Alpha never in `armedCopyBrokers`.

Python: `tests/test_desk_live_order_hardening.py` — `loadDesk` does not persist `ftmoFollowTerminal`; client modules still do not import `/env`; confirm token unchanged.

No live Wine, no `--live`, no OrderSend from tests.

## Files (expected)

- `apps/seven-desk/src/lib/copy-engine.ts` — pure diff + apply
- `apps/seven-desk/src/lib/copy-fanout.ts` — follow counts as live-armed for SL/TP
- `apps/seven-desk/src/lib/types.ts`, `seed.ts`, `storage.ts`, `desk-store.ts`, `desk-context.tsx`
- `apps/seven-desk/src/lib/use-live-probe-poll.ts`
- `apps/seven-desk/src/components/desk/ftmo-live-follow.tsx` (new)
- `apps/seven-desk/src/components/desk/ftmo-live-probe.tsx`, `copy-panel.tsx`
- `tests/test_desk_copy_fanout.ts`, `tests/test_desk_live_order_hardening.py`
- `apps/seven-desk/README.md`, `docs/SEVEN-DESK.md`
- this spec, committed on the feature branch

## PR

Branch: `feat/seven-desk-ftmo-follow` from **origin/main** (not dirty local main).
Title: `feat(seven-desk): follow new FTMO terminal tickets onto armed slaves`
Do not merge. Do not deploy. Do not force-push.

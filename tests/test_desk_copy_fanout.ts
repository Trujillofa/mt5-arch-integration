import assert from "node:assert/strict";
import { parsePendingOrders } from "../apps/seven-desk/src/lib/bridge-orders.ts";
import {
  applyLiveFill,
  describeFlattenTargets,
  flattenAllTargets,
  pendingLiveSlaveEvents,
  placeMasterTrade,
  recordHttpBlotter,
  resolveQueuedCopies,
  upsertSnapshotPendings,
} from "../apps/seven-desk/src/lib/copy-engine.ts";
import {
  COPY_FANOUT_SKIP,
  armedCopyBrokers,
  needsSizeConfirm,
  sizeConfirmLines,
  worstLegMs,
} from "../apps/seven-desk/src/lib/copy-fanout.ts";
import { seedDesk } from "../apps/seven-desk/src/lib/seed.ts";
import { ACCOUNT_IDS } from "../apps/seven-desk/src/lib/seed.ts";

const parsed = parsePendingOrders({
  orders: [
    {
      ticket: 88001,
      symbol: "EURUSD",
      type: "buy_limit",
      side: "buy",
      volume: 0.01,
      price_open: 1.08,
      stop_loss: 0,
      take_profit: 0,
      status: "pending",
    },
  ],
});
assert.equal(parsed.length, 1);
assert.equal(parsed[0].ticket, 88001);
assert.equal(parsed[0].type, "buy_limit");
assert.equal(parsePendingOrders({ history: [] }).length, 0);
assert.equal(parsePendingOrders(null).length, 0);

assert.equal(needsSizeConfirm(0.01), false);
assert.equal(needsSizeConfirm(1.4), true);
assert.equal(needsSizeConfirm(0.35), true);
assert.equal(COPY_FANOUT_SKIP.has("alphacapital"), true);

let desk = seedDesk();
desk = {
  ...desk,
  wsfLiveCopy: true,
  fundednextLiveCopy: true,
  fundingpipsLiveCopy: true,
  neomaaLiveCopy: true,
  fortradersLiveCopy: true,
  alphacapitalLiveCopy: true,
  ftmoLiveMaster: true,
};
const armed = armedCopyBrokers(desk);
assert.deepEqual(armed.sort(), ["fortraders", "fundednext", "fundingpips", "neomaa", "wsf"].sort());
assert.equal(armed.includes("alphacapital"), false);

const lines = sizeConfirmLines(1.4, armed, true);
assert.equal(lines.some((row) => row.id === "ftmo" && row.lots === 1.4), true);
assert.equal(lines.some((row) => row.id === "fundednext" && row.lots === 0.35), true);
assert.equal(lines.some((row) => row.id === "fundingpips" && row.lots === 0.8), true);
assert.equal(lines.some((row) => row.id === "alphacapital"), false);

const placed = placeMasterTrade(desk, {
  symbol: "EURUSD",
  side: "buy",
  lots: 0.01,
  sl: null,
  tp: null,
  price: 1.08,
  orderType: "buy_limit",
});
assert.ok(placed.groupId);
const resolved = resolveQueuedCopies(placed.state, placed.groupId!);
const pending = pendingLiveSlaveEvents(resolved, placed.groupId!);
assert.equal(
  pending.some((row) => row.accountId === ACCOUNT_IDS.alphacapital),
  false,
  "fan-out must skip Alpha"
);
assert.ok(pending.some((row) => row.accountId === ACCOUNT_IDS.wsf));
assert.ok(pending.some((row) => row.accountId === ACCOUNT_IDS.fundednext));

const alphaEvent = resolved.blotter.find((row) => row.accountId === ACCOUNT_IDS.alphacapital);
assert.ok(alphaEvent);
assert.equal(alphaEvent.status, "skipped");
assert.match(alphaEvent.reason ?? "", /fetch-only/);

const wsfEvent = pending.find((row) => row.accountId === ACCOUNT_IDS.wsf);
assert.ok(wsfEvent);
const filled = applyLiveFill(
  resolved,
  wsfEvent.id,
  {
    ok: true,
    source: "seven-desk",
    endpoint: "/api/wsf/order",
    requestId: "r1",
    stage: "pending",
    reason: "seven-desk pending placed",
    login: 149736,
    server: "WSFmarkets-Server",
    winePrefix: ".mt5-wsf",
    order: 99001,
    orderType: "buy_limit",
    volume: 0.01,
    price: 1.08,
    holdMs: 142,
  },
  "wsf"
);
const wsfRow = filled.blotter.find((row) => row.id === wsfEvent.id);
assert.ok(wsfRow);
assert.equal(wsfRow.httpAction, "send");
assert.equal(wsfRow.liveTicket, 99001);
assert.equal(wsfRow.latencyMs, 142);
assert.match(wsfRow.reason ?? "", /HTTP send/);

const cancelled = recordHttpBlotter(filled, {
  accountId: ACCOUNT_IDS.wsf,
  role: "slave",
  symbol: "EURUSDc",
  side: "buy",
  lots: 0.01,
  price: 1.08,
  orderType: "buy_limit",
  status: "filled",
  reason: "HTTP cancel · ticket 99001 · 88ms",
  liveTicket: 99001,
  latencyMs: 88,
  httpAction: "cancel",
  groupId: placed.groupId,
});
assert.equal(cancelled.blotter[0].httpAction, "cancel");
assert.equal(cancelled.blotter[0].liveTicket, 99001);

const ingested = upsertSnapshotPendings(seedDesk(), ACCOUNT_IDS.ftmo, "ftmo", parsed);
const snap = ingested.positions.find((row) => row.liveOrder === 88001);
assert.ok(snap);
assert.equal(snap.livePending, true);
assert.equal(snap.fromSnapshot, true);
assert.equal(snap.orderType, "buy_limit");

assert.equal(worstLegMs([12, 40, 9]), 40);
assert.equal(worstLegMs([]), null);

const emptyFlatten = describeFlattenTargets(seedDesk());
assert.equal(emptyFlatten.filled, 0);
assert.equal(emptyFlatten.pending, 0);
assert.equal(emptyFlatten.us30Rows.length, 0);

const us30LeftoverDesk = {
  ...seedDesk(),
  positions: [
    {
      id: "pos_us30_leftover",
      accountId: ACCOUNT_IDS.wsf,
      symbol: "DJ30.c",
      side: "buy" as const,
      lots: 4,
      entry: 39000,
      sl: null,
      tp: null,
      openedAt: 1,
      mark: 39000,
      pnl: 0,
      liveBroker: "wsf" as const,
      livePending: true,
      fromSnapshot: true,
      orderType: "buy_limit" as const,
    },
  ],
};
const us30Flatten = describeFlattenTargets(us30LeftoverDesk);
assert.equal(us30Flatten.pending, 1);
assert.equal(us30Flatten.filled, 0);
assert.equal(us30Flatten.us30Rows.length, 1);
assert.equal(us30Flatten.us30Rows[0]?.lots, 4);
const us30Targets = flattenAllTargets(us30LeftoverDesk);
assert.deepEqual(us30Targets.liveRepIds, ["pos_us30_leftover"]);
assert.deepEqual(us30Targets.paperIds, []);

console.log("test_desk_copy_fanout ok");

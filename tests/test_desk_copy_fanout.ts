import assert from "node:assert/strict";
import { parsePendingOrders } from "../apps/seven-desk/src/lib/bridge-orders.ts";
import {
  applyLiveFill,
  describeFlattenTargets,
  flattenAllTargets,
  isBrokerLeftover,
  pendingLiveSlaveEvents,
  placeMasterTrade,
  recordHttpBlotter,
  resolveQueuedCopies,
  upsertSnapshotPendings,
  upsertSnapshotPositions,
} from "../apps/seven-desk/src/lib/copy-engine.ts";
import { parseOpenPositions } from "../apps/seven-desk/src/lib/bridge-orders.ts";
import { DESK_MAGIC } from "../apps/seven-desk/src/lib/desk-magic.ts";
import {
  COPY_FANOUT_SKIP,
  armedCopyBrokers,
  needsSizeConfirm,
  sizeConfirmLines,
  worstLegMs,
} from "../apps/seven-desk/src/lib/copy-fanout.ts";
import {
  defaultLotsForFirm,
  liveLotsForFirm,
  planLiveLots,
} from "../apps/seven-desk/src/lib/firms.ts";
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
assert.equal(needsSizeConfirm(4), true);
assert.equal(needsSizeConfirm(0.4), true);
assert.equal(liveLotsForFirm("fundednext", 4), 0.4);
assert.equal(liveLotsForFirm("fundingpips", 4), 0.8);
assert.equal(liveLotsForFirm("wsf", 4), 4);
assert.equal(liveLotsForFirm("fundednext", 2), 0.2);
assert.equal(liveLotsForFirm("fundingpips", 2), 0.4);
assert.equal(liveLotsForFirm("fundednext", 0.01), 0.01);
assert.equal(liveLotsForFirm("fundingpips", 0.01), 0.01);
assert.equal(liveLotsForFirm("wsf", 0.01), 0.01);
assert.equal(defaultLotsForFirm("fundednext", 2), 0.2);
assert.equal(planLiveLots("fundednext", 0.03).roundedUp, true);
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

const lines = sizeConfirmLines(4, armed, true);
assert.equal(lines.some((row) => row.id === "ftmo" && row.lots === 4), true);
assert.equal(lines.some((row) => row.id === "fundednext" && row.lots === 0.4), true);
assert.equal(lines.some((row) => row.id === "fundingpips" && row.lots === 0.8), true);
assert.equal(lines.some((row) => row.id === "wsf" && row.lots === 4), true);
assert.equal(lines.some((row) => row.id === "alphacapital"), false);
const linesAtTwo = sizeConfirmLines(2, armed, true);
assert.equal(linesAtTwo.some((row) => row.id === "fundednext" && row.lots === 0.2), true);
assert.equal(linesAtTwo.some((row) => row.id === "fundingpips" && row.lots === 0.4), true);
assert.equal(linesAtTwo.some((row) => row.id === "wsf" && row.lots === 2), true);
const proveLines = sizeConfirmLines(0.01, armed, true);
assert.equal(proveLines.every((row) => row.lots === 0.01), true);

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
assert.equal(pending.find((row) => row.accountId === ACCOUNT_IDS.wsf)?.lots, 0.01);
assert.equal(pending.find((row) => row.accountId === ACCOUNT_IDS.fundednext)?.lots, 0.01);
assert.equal(pending.find((row) => row.accountId === ACCOUNT_IDS.fundingpips)?.lots, 0.01);

const placedStd = placeMasterTrade(desk, {
  symbol: "EURUSD",
  side: "buy",
  lots: 4,
  sl: null,
  tp: null,
  price: 1.08,
  orderType: "buy_limit",
});
assert.ok(placedStd.groupId);
const resolvedStd = resolveQueuedCopies(placedStd.state, placedStd.groupId!);
const pendingStd = pendingLiveSlaveEvents(resolvedStd, placedStd.groupId!);
assert.equal(pendingStd.find((row) => row.accountId === ACCOUNT_IDS.wsf)?.lots, 4);
assert.equal(pendingStd.find((row) => row.accountId === ACCOUNT_IDS.fundednext)?.lots, 0.4);
assert.equal(pendingStd.find((row) => row.accountId === ACCOUNT_IDS.fundingpips)?.lots, 0.8);
assert.equal(pendingStd.find((row) => row.accountId === ACCOUNT_IDS.neomaa)?.lots, 4);
assert.equal(pendingStd.find((row) => row.accountId === ACCOUNT_IDS.fortraders)?.lots, 4);
assert.equal(
  pendingStd.some((row) => row.accountId === ACCOUNT_IDS.alphacapital),
  false
);

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
assert.equal(snap.leftover, true);
assert.equal(snap.orderType, "buy_limit");

assert.equal(worstLegMs([12, 40, 9]), 40);
assert.equal(worstLegMs([]), null);

const emptyFlatten = describeFlattenTargets(seedDesk());
assert.equal(emptyFlatten.filled, 0);
assert.equal(emptyFlatten.pending, 0);
assert.equal(emptyFlatten.leftovers, 0);
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
      leftover: true,
      orderType: "buy_limit" as const,
    },
  ],
};
const us30Flatten = describeFlattenTargets(us30LeftoverDesk);
assert.equal(us30Flatten.pending, 0);
assert.equal(us30Flatten.filled, 0);
assert.equal(us30Flatten.leftovers, 1);
assert.equal(us30Flatten.us30Rows.length, 0);
assert.equal(isBrokerLeftover(us30LeftoverDesk.positions[0]!), true);
const us30Targets = flattenAllTargets(us30LeftoverDesk);
assert.deepEqual(us30Targets.liveRepIds, []);
assert.deepEqual(us30Targets.paperIds, []);

const deskUs30 = {
  ...seedDesk(),
  positions: [
    {
      id: "pos_us30_desk",
      accountId: ACCOUNT_IDS.wsf,
      symbol: "DJ30.c",
      side: "buy" as const,
      lots: 1.4,
      entry: 39000,
      sl: null,
      tp: null,
      openedAt: 1,
      mark: 39000,
      pnl: 0,
      liveBroker: "wsf" as const,
      leftover: false,
      groupId: "grp_desk",
      orderType: "market" as const,
    },
  ],
};
const deskFlatten = describeFlattenTargets(deskUs30);
assert.equal(deskFlatten.filled, 1);
assert.equal(deskFlatten.us30Rows[0]?.lots, 1.4);
assert.deepEqual(flattenAllTargets(deskUs30).liveRepIds, ["pos_us30_desk"]);

const parsedPos = parseOpenPositions({
  positions: [
    {
      ticket: 77001,
      symbol: "DJ30.c",
      side: "buy",
      volume: 4,
      open_price: 39000,
      stop_loss: 0,
      take_profit: 0,
      profit: -12,
      magic: 0,
    },
    {
      ticket: 77002,
      symbol: "EURUSDc",
      side: "buy",
      volume: 1.4,
      open_price: 1.08,
      stop_loss: 1.07,
      take_profit: 1.09,
      profit: 2,
      magic: DESK_MAGIC.wsf,
    },
  ],
});
assert.equal(parsedPos.length, 2);
const ingestedLive = upsertSnapshotPositions(seedDesk(), ACCOUNT_IDS.wsf, "wsf", parsedPos);
const leftoverRow = ingestedLive.positions.find((row) => row.liveOrder === 77001);
const deskRow = ingestedLive.positions.find((row) => row.liveOrder === 77002);
assert.ok(leftoverRow);
assert.equal(leftoverRow.leftover, true);
assert.equal(leftoverRow.lots, 4);
assert.ok(deskRow);
assert.equal(deskRow.leftover, true);
assert.equal(deskRow.sl, 1.07);
const ingestedFlatten = flattenAllTargets(ingestedLive);
assert.equal(ingestedFlatten.liveRepIds.includes(leftoverRow.id), false);
assert.equal(ingestedFlatten.liveRepIds.includes(deskRow.id), false);
const ingestedAgain = upsertSnapshotPositions(ingestedLive, ACCOUNT_IDS.wsf, "wsf", parsedPos);
assert.equal(
  ingestedAgain.positions.find((row) => row.liveOrder === 77001)?.id,
  leftoverRow.id,
  "leftover ticket must keep the same desk row across probe polls"
);
const deskMagicUs30 = upsertSnapshotPositions(
  seedDesk(),
  ACCOUNT_IDS.ftmo,
  "ftmo",
  parseOpenPositions({
    positions: [
      {
        ticket: 165085534,
        symbol: "US30.cash",
        side: "buy",
        volume: 4,
        open_price: 52500,
        stop_loss: 52500,
        take_profit: 53300,
        profit: 0,
        magic: DESK_MAGIC.ftmo,
      },
    ],
  })
);
const orphan = deskMagicUs30.positions.find((row) => row.liveOrder === 165085534);
assert.ok(orphan);
assert.equal(orphan.leftover, true);
assert.equal(flattenAllTargets(deskMagicUs30).liveRepIds.includes(orphan.id), false);

console.log("test_desk_copy_fanout ok");

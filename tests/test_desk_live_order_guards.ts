import assert from "node:assert/strict";
import {
  LIVE_ORDER_VOLUME_HARD_MAX,
  alphaStartupChartSymbol,
  classifyOrphanRequest,
  deadlineExceeded,
  disconnectedOrderReason,
  httpTimeoutResult,
  inFlightOrphanReason,
  isTradeServerDisconnected,
  isUs30Family,
  oneshotChartSymbol,
  parseLiveOrderRequest,
  parseRequestFields,
  quotesPathMatchesSymbol,
  remainingMs,
  requestIssuedAtMs,
  resolveStartupServer,
  resultBelongsToRequest,
  resultMatchesRequest,
  symbolAllowedForFirm,
  us30SelectVariantsForFirm,
  withDeadline,
} from "../apps/seven-desk/src/lib/live-order/guards.ts";

assert.equal(isTradeServerDisconnected(false), true);
assert.equal(isTradeServerDisconnected(true), false);
assert.equal(isTradeServerDisconnected(null), false);
assert.equal(isTradeServerDisconnected(undefined), false);

assert.equal(
  resolveStartupServer("ACGMarkets-Main", "ACGMarkets-Main", "ACG"),
  "ACGMarkets-Main"
);
assert.equal(resolveStartupServer("ACGMarkets-Main", "ACGMarkets", "ACG"), "ACGMarkets-Main");
assert.equal(resolveStartupServer(null, "ACGMarkets-Main", "ACG"), "ACGMarkets-Main");
assert.equal(resolveStartupServer("WSFmarkets-Server", "ACGMarkets-Main", "ACG"), "ACGMarkets-Main");

assert.equal(
  quotesPathMatchesSymbol(
    "/Bases/ACGMarkets-Main/history/EURUSD.pro/2026.hcc",
    "2026.hcc",
    "EURUSD"
  ),
  true
);
assert.equal(
  quotesPathMatchesSymbol(
    "/Bases/ACGMarkets-Main/history/EURUSD/2026.hcc",
    "2026.hcc",
    "EURUSD"
  ),
  true
);
assert.equal(
  quotesPathMatchesSymbol(
    "C:\\Bases\\ACGMarkets-Main\\history\\EURUSD.pro\\2026.hcc",
    "2026.hcc",
    "EURUSD"
  ),
  true
);
assert.equal(
  quotesPathMatchesSymbol(
    "/Bases/ACGMarkets-Main/history/GBPUSD.pro/2026.hcc",
    "2026.hcc",
    "EURUSD"
  ),
  false
);
assert.equal(quotesPathMatchesSymbol("/Bases/history/EURUSD.pro/2026.hcc", "2026.hcc", "GBPUSD"), false);
assert.equal(alphaStartupChartSymbol("alphacapital", "EURUSD"), "EURUSD.pro");
assert.equal(alphaStartupChartSymbol("alphacapital", "EURUSDc"), "EURUSD.pro");
assert.equal(alphaStartupChartSymbol("alphacapital", "BTCUSD"), "BTCUSD");
assert.equal(alphaStartupChartSymbol("ftmo", "EURUSD"), "EURUSD");

assert.equal(resultMatchesRequest("abc", "abc"), true);
assert.equal(resultMatchesRequest("", "abc"), false);
assert.equal(resultMatchesRequest(undefined, "abc"), false);
assert.equal(resultMatchesRequest("other", "abc"), false);
assert.equal(resultBelongsToRequest("alphacapital-mtqehcjkdtlj", "alphacapital-mtqehcjkdtlj"), true);

const parsedReq = parseRequestFields(
  "request_id=alphacapital-mtqehcjkdtlj\naction=open\nissued_at=1757200000\n"
);
assert.equal(parsedReq.requestId, "alphacapital-mtqehcjkdtlj");
assert.equal(parsedReq.issuedAt, 1757200000);
assert.equal(requestIssuedAtMs(1757200000, 0), 1757200000 * 1000);

assert.equal(
  classifyOrphanRequest({
    requestPresent: true,
    requestId: "alphacapital-mtqehcjkdtlj",
    issuedAt: 1_757_200_000,
    fileMtimeMs: 1_757_200_000_000,
    matchingResult: false,
    nowMs: 1_757_200_030_000,
    ttlMs: 90_000,
  }),
  "in_flight"
);
assert.equal(
  classifyOrphanRequest({
    requestPresent: true,
    requestId: "alphacapital-mtqehcjkdtlj",
    issuedAt: 1_757_199_900,
    fileMtimeMs: 1_757_199_900_000,
    matchingResult: false,
    nowMs: 1_757_200_000_000,
    ttlMs: 90_000,
  }),
  "stale"
);
assert.equal(
  classifyOrphanRequest({
    requestPresent: true,
    requestId: "alphacapital-mtqehcjkdtlj",
    issuedAt: 1_757_200_000,
    fileMtimeMs: 1_757_200_000_000,
    matchingResult: true,
    nowMs: 1_757_200_030_000,
  }),
  "done"
);
assert.match(inFlightOrphanReason("alphacapital-mtqehcjkdtlj"), /alphacapital-mtqehcjkdtlj/);
assert.match(inFlightOrphanReason("alphacapital-mtqehcjkdtlj"), /refusing a second OrderSend/);

assert.equal(deadlineExceeded(Date.now() - 1), true);
assert.ok(remainingMs(Date.now() + 5_000) > 0);

const reason = disconnectedOrderReason("neomaa", "Neomaaa-Live");
assert.match(reason, /terminal_connected=false/);
assert.match(reason, /Neomaaa-Live/);
assert.match(reason, /not an auth failure/);

const timeout = httpTimeoutResult({
  endpoint: "/api/alphacapital/order",
  requestId: "alphacapital-test",
  winePrefix: ".mt5-alphacapital",
});
assert.equal(timeout.ok, false);
assert.equal(timeout.stage, "timeout");
assert.equal(timeout.source, "seven-desk");
assert.match(timeout.reason, /HTTP deadline/);

const raced = await withDeadline(
  new Promise<string>((resolve) => {
    setTimeout(() => resolve("late"), 50);
  }),
  5,
  "fallback"
);
assert.equal(raced, "fallback");

const won = await withDeadline(Promise.resolve("soon"), 50, "fallback");
assert.equal(won, "soon");

assert.equal(isUs30Family("US30"), true);
assert.equal(isUs30Family("US30.cash"), true);
assert.equal(isUs30Family("US30.c"), true);
assert.equal(isUs30Family("us30m"), true);
assert.equal(isUs30Family("DJ30"), true);
assert.equal(isUs30Family("DJ30.c"), true);
assert.equal(isUs30Family("dj30.c"), true);
assert.equal(isUs30Family("DJ30c"), true);
assert.equal(isUs30Family("DJI30"), true);
assert.equal(isUs30Family("EURUSD"), false);
assert.equal(isUs30Family("US500"), false);
assert.equal(us30SelectVariantsForFirm("wsf")[0], "DJ30.c");
assert.equal(us30SelectVariantsForFirm("ftmo")[0], "US30");
assert.ok(us30SelectVariantsForFirm("ftmo").includes("DJ30.c"));
assert.equal(symbolAllowedForFirm("ftmo", "US30"), true);
assert.equal(symbolAllowedForFirm("wsf", "US30.cash"), true);
assert.equal(symbolAllowedForFirm("wsf", "DJ30.c"), true);
assert.equal(symbolAllowedForFirm("wsf", "dj30.c"), true);
assert.equal(symbolAllowedForFirm("fundednext", "DJ30"), true);
assert.equal(symbolAllowedForFirm("fundingpips", "US30"), true);
assert.equal(symbolAllowedForFirm("fortraders", "US30"), true);
assert.equal(symbolAllowedForFirm("alphacapital", "US30"), false);
assert.equal(symbolAllowedForFirm("neomaa", "US30"), false);
assert.equal(symbolAllowedForFirm("alphacapital", "BTCUSD"), true);
assert.equal(symbolAllowedForFirm("ftmo", "EURUSD"), true);
assert.equal(oneshotChartSymbol("ftmo", "US30"), "EURUSD");
assert.equal(oneshotChartSymbol("wsf", "US30.cash"), "EURUSDc");
assert.equal(oneshotChartSymbol("alphacapital", "EURUSD"), "EURUSD.pro");

const base = { live: true as const, confirm: "FTMO-541163357" };

const market = parseLiveOrderRequest({
  body: { ...base, action: "open", volume_min: true },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(market.ok, true);
if (market.ok) {
  assert.equal(market.fields.action, "open");
  assert.equal(market.fields.orderType, "market");
  assert.equal(market.fields.symbol, "EURUSD");
  assert.equal(market.fields.useVolumeMin, true);
}

const paper = parseLiveOrderRequest({
  body: { live: false, confirm: "FTMO-541163357" },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(paper.ok, false);
if (!paper.ok) {
  assert.match(paper.reason, /paper is the default/);
}

const bigNoConfirm = parseLiveOrderRequest({
  body: { ...base, action: "open", symbol: "US30", volume: 4 },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(bigNoConfirm.ok, false);
if (!bigNoConfirm.ok) {
  assert.equal(bigNoConfirm.stage, "volume");
  assert.match(bigNoConfirm.reason, /volume_confirm/);
}

const absurd = parseLiveOrderRequest({
  body: { ...base, action: "open", symbol: "US30", volume: LIVE_ORDER_VOLUME_HARD_MAX + 1, volume_confirm: true },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(absurd.ok, false);
if (!absurd.ok) assert.match(absurd.reason, /hard max/);

const vminPlusSize = parseLiveOrderRequest({
  body: { ...base, action: "open", symbol: "US30", volume: 4, volume_min: true, volume_confirm: true },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(vminPlusSize.ok, false);

const limit = parseLiveOrderRequest({
  body: {
    ...base,
    action: "open",
    order_type: "buy_limit",
    symbol: "US30",
    side: "buy",
    price: 53100,
    tp: 53500,
    sl: 52500,
    volume: 4,
    volume_confirm: true,
  },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(limit.ok, true);
if (limit.ok) {
  assert.equal(limit.fields.orderType, "buy_limit");
  assert.equal(limit.fields.price, 53100);
  assert.equal(limit.fields.tp, 53500);
  assert.equal(limit.fields.sl, 52500);
  assert.equal(limit.fields.volume, 4);
  assert.equal(limit.fields.useVolumeMin, false);
  assert.equal(limit.fields.symbol, "US30");
}

const noPrice = parseLiveOrderRequest({
  body: { ...base, action: "open", order_type: "buy_limit", symbol: "US30", volume: 4, volume_confirm: true },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(noPrice.ok, false);
if (!noPrice.ok) assert.equal(noPrice.stage, "price");

const slWrong = parseLiveOrderRequest({
  body: {
    ...base,
    order_type: "buy_limit",
    symbol: "US30",
    price: 53100,
    sl: 53200,
    volume: 4,
    volume_confirm: true,
  },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(slWrong.ok, false);
if (!slWrong.ok) assert.match(slWrong.reason, /sl < price/);

const tpWrong = parseLiveOrderRequest({
  body: {
    ...base,
    order_type: "buy_limit",
    symbol: "US30",
    price: 53100,
    tp: 53000,
    volume: 4,
    volume_confirm: true,
  },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(tpWrong.ok, false);
if (!tpWrong.ok) assert.match(tpWrong.reason, /tp > price/);

const scratchBig = parseLiveOrderRequest({
  body: { ...base, action: "scratch", volume: 4, volume_confirm: true },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(scratchBig.ok, false);
if (!scratchBig.ok) assert.match(scratchBig.reason, /scratch is min-lot/);

const scratchPending = parseLiveOrderRequest({
  body: { ...base, action: "scratch", order_type: "buy_limit", symbol: "US30", price: 53100 },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(scratchPending.ok, false);

const alphaUs30 = parseLiveOrderRequest({
  body: {
    live: true,
    confirm: "ACG-2765247",
    order_type: "buy_limit",
    symbol: "US30",
    price: 53100,
    volume: 4,
    volume_confirm: true,
  },
  expectedConfirm: "ACG-2765247",
  defaultSymbol: "EURUSD",
  firmId: "alphacapital",
});
assert.equal(alphaUs30.ok, false);
if (!alphaUs30.ok) assert.equal(alphaUs30.stage, "symbol");

const sellLimit = parseLiveOrderRequest({
  body: {
    live: true,
    confirm: "WSF-149736",
    order_type: "sell_limit",
    symbol: "DJ30",
    side: "sell",
    price: 53100,
    sl: 53500,
    tp: 52500,
    volume: 4,
    volume_confirm: true,
  },
  expectedConfirm: "WSF-149736",
  defaultSymbol: "EURUSDc",
  firmId: "wsf",
});
assert.equal(sellLimit.ok, true);
if (sellLimit.ok) {
  assert.equal(sellLimit.fields.orderType, "sell_limit");
  assert.equal(sellLimit.fields.side, "SELL");
}

const wsfDj30c = parseLiveOrderRequest({
  body: {
    live: true,
    confirm: "WSF-149736",
    action: "open",
    order_type: "buy_limit",
    symbol: "DJ30.c",
    side: "buy",
    price: 53100,
    tp: 53500,
    sl: 52500,
    volume: 4,
    volume_confirm: true,
  },
  expectedConfirm: "WSF-149736",
  defaultSymbol: "EURUSDc",
  firmId: "wsf",
});
assert.equal(wsfDj30c.ok, true);
if (wsfDj30c.ok) {
  assert.equal(wsfDj30c.fields.symbol, "DJ30.c");
  assert.equal(wsfDj30c.fields.orderType, "buy_limit");
  assert.equal(wsfDj30c.fields.volume, 4);
}

const wsfUs30Resolves = parseLiveOrderRequest({
  body: {
    live: true,
    confirm: "WSF-149736",
    action: "open",
    order_type: "buy_limit",
    symbol: "US30",
    side: "buy",
    price: 53100,
    tp: 53500,
    sl: 52500,
    volume: 4,
    volume_confirm: true,
  },
  expectedConfirm: "WSF-149736",
  defaultSymbol: "EURUSDc",
  firmId: "wsf",
});
assert.equal(wsfUs30Resolves.ok, true);
if (wsfUs30Resolves.ok) {
  assert.equal(wsfUs30Resolves.fields.symbol, "US30");
}

const cancel = parseLiveOrderRequest({
  body: { ...base, action: "cancel", ticket: 123456 },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(cancel.ok, true);
if (cancel.ok) {
  assert.equal(cancel.fields.action, "cancel");
  assert.equal(cancel.fields.ticket, 123456);
}

const closePending = parseLiveOrderRequest({
  body: { ...base, action: "close", order_type: "buy_limit", symbol: "US30", price: 53100 },
  expectedConfirm: "FTMO-541163357",
  defaultSymbol: "EURUSD",
  firmId: "ftmo",
});
assert.equal(closePending.ok, false);
if (!closePending.ok) assert.match(closePending.reason, /action=cancel/);

console.log("test_desk_live_order_guards.ts ok");

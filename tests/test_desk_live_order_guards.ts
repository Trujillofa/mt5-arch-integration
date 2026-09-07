import assert from "node:assert/strict";
import {
  alphaStartupChartSymbol,
  classifyOrphanRequest,
  deadlineExceeded,
  disconnectedOrderReason,
  httpTimeoutResult,
  inFlightOrphanReason,
  isTradeServerDisconnected,
  parseRequestFields,
  quotesPathMatchesSymbol,
  remainingMs,
  requestIssuedAtMs,
  resolveStartupServer,
  resultBelongsToRequest,
  resultMatchesRequest,
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

console.log("test_desk_live_order_guards.ts ok");

import assert from "node:assert/strict";
import {
  deadlineExceeded,
  disconnectedOrderReason,
  httpTimeoutResult,
  isTradeServerDisconnected,
  remainingMs,
  resolveStartupServer,
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

assert.equal(resultMatchesRequest("abc", "abc"), true);
assert.equal(resultMatchesRequest("", "abc"), true);
assert.equal(resultMatchesRequest(undefined, "abc"), true);
assert.equal(resultMatchesRequest("other", "abc"), false);

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

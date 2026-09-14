import assert from "node:assert/strict";
import {
  parseBridgeQuotes,
  quoteSymbolMatches,
  type QuoteSnapshot,
} from "../apps/seven-desk/src/lib/live-order/bridge-quotes.ts";
import {
  buildRequestRecord,
  fillPriceOf,
  fillTicketOf,
  journalBeforeSend,
  requestedQuoteFields,
  type LiveJournalCtx,
  type QuoteJournalIo,
  type QuoteJournalRecord,
} from "../apps/seven-desk/src/lib/live-order/quote-journal.ts";

const nowMs = 1_700_000_000_000;

function memoryIo(): QuoteJournalIo & { lines: string[]; order: string[] } {
  const lines: string[] = [];
  const order: string[] = [];
  return {
    lines,
    order,
    journalPath: "/tmp/seven-desk-quote-journal-test.jsonl",
    nowMs: () => nowMs,
    append(_path, line) {
      order.push("journal");
      lines.push(line);
    },
  };
}

function ctx(quote: QuoteSnapshot, extra?: Partial<LiveJournalCtx>): LiveJournalCtx {
  return {
    requestId: "ftmo-test1",
    firm: "ftmo",
    symbol: "EURUSD",
    side: "BUY",
    action: "open",
    orderType: "market",
    lots: 4,
    intendedPrice: 1.0852,
    quote,
    sendPath: "ea",
    ...extra,
  };
}

const liveQuote: QuoteSnapshot = {
  ok: true,
  bid: 1.08512,
  ask: 1.08518,
  tsMs: nowMs - 200,
  source: "bridge",
};

assert.equal(quoteSymbolMatches("EURUSD.pro", "EURUSD"), true);
assert.equal(quoteSymbolMatches("EURUSDc", "EURUSD"), true);
assert.equal(quoteSymbolMatches("DJ30.c", "DJ30"), true);
assert.equal(quoteSymbolMatches("US30.cash", "US30"), true);
assert.equal(quoteSymbolMatches("XAUUSD", "GOLD"), false);
assert.equal(quoteSymbolMatches("DJ30.c", "US30"), false);

const parsedOk = parseBridgeQuotes(
  {
    updated_at: nowMs / 1000,
    quotes: [{ symbol: "EURUSD.pro", bid: 1.08512, ask: 1.08518, time_msc: nowMs - 100 }],
  },
  {
    symbol: "EURUSD",
    nowMs,
    maxAgeSeconds: 15,
    heartbeatFresh: true,
    fileMtimeMs: nowMs - 100,
  }
);
assert.equal(parsedOk.ok, true);
if (parsedOk.ok) {
  assert.equal(parsedOk.bid, 1.08512);
  assert.equal(parsedOk.ask, 1.08518);
}

assert.equal(
  parseBridgeQuotes(
    { quotes: [{ symbol: "EURUSD", bid: 1.08, ask: 1.09 }] },
    { symbol: "EURUSD", nowMs, maxAgeSeconds: 15, heartbeatFresh: false, fileMtimeMs: nowMs }
  ).ok,
  false
);
assert.equal(
  parseBridgeQuotes(
    { quotes: [{ symbol: "EURUSD", bid: 1.08, ask: 1.09 }] },
    { symbol: "EURUSD", nowMs, maxAgeSeconds: 15, heartbeatFresh: false }
  ).reason,
  "stale"
);

const missing = parseBridgeQuotes(null, {
  symbol: "EURUSD",
  nowMs,
  maxAgeSeconds: 15,
  heartbeatFresh: true,
});
assert.equal(missing.ok, false);
if (!missing.ok) assert.equal(missing.reason, "missing");

const staleFile = parseBridgeQuotes(
  { quotes: [{ symbol: "EURUSD", bid: 1.08, ask: 1.09, time_msc: nowMs - 60_000 }] },
  {
    symbol: "EURUSD",
    nowMs,
    maxAgeSeconds: 15,
    heartbeatFresh: true,
    fileMtimeMs: nowMs - 60_000,
  }
);
assert.equal(staleFile.ok, false);
if (!staleFile.ok) assert.equal(staleFile.reason, "stale");

const invalid = parseBridgeQuotes(
  { quotes: [{ symbol: "EURUSD", bid: 0, ask: 1.09 }] },
  { symbol: "EURUSD", nowMs, maxAgeSeconds: 15, heartbeatFresh: true, fileMtimeMs: nowMs }
);
assert.equal(invalid.ok, false);
if (!invalid.ok) assert.equal(invalid.reason, "invalid");

const unmapped = parseBridgeQuotes(
  { quotes: [{ symbol: "GBPUSD", bid: 1.27, ask: 1.28 }] },
  { symbol: "EURUSD", nowMs, maxAgeSeconds: 15, heartbeatFresh: true, fileMtimeMs: nowMs }
);
assert.equal(unmapped.ok, false);
if (!unmapped.ok) assert.equal(unmapped.reason, "symbol_unmapped");

const missingFields = requestedQuoteFields({ ok: false, reason: "missing" });
assert.equal(missingFields.requestedBid, null);
assert.equal(missingFields.requestedAsk, null);
assert.equal(missingFields.quoteStatus, "missing");

const requestShape = buildRequestRecord(ctx(liveQuote), nowMs);
assert.equal(requestShape.v, 1);
assert.equal(requestShape.kind, "request");
assert.equal(requestShape.firm, "ftmo");
assert.equal(requestShape.requestedBid, 1.08512);
assert.equal(requestShape.requestedAsk, 1.08518);
assert.equal(requestShape.intendedPrice, 1.0852);
assert.equal(requestShape.lots, 4);
assert.equal("login" in requestShape, false);
assert.equal("password" in requestShape, false);
assert.equal("confirm" in requestShape, false);

const io = memoryIo();
const sent = await journalBeforeSend(
  ctx(liveQuote),
  async () => {
    io.order.push("send");
    return { ok: true, price: 1.08525, ticket: 77001, stage: "open" };
  },
  (result) => result,
  io
);
assert.deepEqual(io.order, ["journal", "send", "journal"]);
assert.equal(sent.result.ok, true);
assert.equal(sent.journalError, undefined);
const requestLine = JSON.parse(io.lines[0]) as QuoteJournalRecord;
const fillLine = JSON.parse(io.lines[1]) as QuoteJournalRecord;
assert.equal(requestLine.kind, "request");
assert.equal(requestLine.requestedBid, 1.08512);
assert.equal(requestLine.requestedAsk, 1.08518);
assert.equal(requestLine.quoteStatus, "ok");
assert.equal(fillLine.kind, "fill");
assert.equal(fillLine.fillPrice, 1.08525);
assert.equal(fillLine.fillTicket, 77001);
assert.equal(fillLine.requestedBid, 1.08512);
assert.equal(fillPriceOf(sent.result), 1.08525);
assert.equal(fillTicketOf(sent.result), 77001);

const missingIo = memoryIo();
let sendRan = false;
const missingSend = await journalBeforeSend(
  ctx({ ok: false, reason: "missing" }, { intendedPrice: null }),
  async () => {
    sendRan = true;
    missingIo.order.push("send");
    return { ok: true, ticket: 1 };
  },
  (result) => result,
  missingIo
);
assert.equal(sendRan, true);
assert.deepEqual(missingIo.order, ["journal", "send", "journal"]);
const missingReq = JSON.parse(missingIo.lines[0]) as QuoteJournalRecord;
assert.equal(missingReq.requestedBid, null);
assert.equal(missingReq.requestedAsk, null);
assert.equal(missingReq.quoteStatus, "missing");
assert.equal(missingReq.intendedPrice, null);
assert.equal(missingSend.result.ok, true);

const staleIo = memoryIo();
await journalBeforeSend(
  ctx({ ok: false, reason: "stale" }),
  async () => {
    staleIo.order.push("send");
    return { ok: false, stage: "ea" };
  },
  (result) => result,
  staleIo
);
const staleReq = JSON.parse(staleIo.lines[0]) as QuoteJournalRecord;
assert.equal(staleReq.requestedBid, null);
assert.equal(staleReq.requestedAsk, null);
assert.equal(staleReq.quoteStatus, "stale");

const boomIo: QuoteJournalIo & { order: string[] } = {
  order: [],
  journalPath: "/tmp/seven-desk-quote-journal-test.jsonl",
  nowMs: () => nowMs,
  append() {
    boomIo.order.push("journal");
    throw new Error("disk full");
  },
};
let boomSend = false;
const boom = await journalBeforeSend(
  ctx(liveQuote),
  async () => {
    boomSend = true;
    boomIo.order.push("send");
    return { ok: true, price: 1.09, ticket: 2 };
  },
  (result) => result,
  boomIo
);
assert.equal(boomSend, true);
assert.equal(boom.result.ok, true);
assert.equal(boom.journalError, "disk full");
assert.ok(boomIo.order.includes("send"));

console.log("test_desk_live_order_quote_journal.ts ok");

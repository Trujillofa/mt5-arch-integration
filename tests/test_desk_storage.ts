import assert from "node:assert/strict";
import { SEED_QUOTES } from "../apps/seven-desk/src/lib/quotes.ts";
import { mergeSeedQuotes } from "../apps/seven-desk/src/lib/storage.ts";

const subset = SEED_QUOTES.slice(0, 2).map((quote) => ({ ...quote, bid: 9 }));
const merged = mergeSeedQuotes(subset);
assert.equal(merged.length, SEED_QUOTES.length);
assert.equal(merged[0].bid, 9);
assert.equal(merged[1].bid, 9);
for (const seed of SEED_QUOTES) {
  assert.ok(merged.some((quote) => quote.symbol === seed.symbol), seed.symbol);
}

const full = SEED_QUOTES.map((quote) => ({ ...quote }));
assert.equal(mergeSeedQuotes(full), full);

const empty = mergeSeedQuotes([]);
assert.equal(empty.length, SEED_QUOTES.length);
assert.deepEqual(
  empty.map((quote) => quote.symbol),
  SEED_QUOTES.map((quote) => quote.symbol),
);

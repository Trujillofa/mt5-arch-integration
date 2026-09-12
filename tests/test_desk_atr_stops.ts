import assert from "node:assert/strict";
import {
  SCALP_SL_ATR,
  SCALP_TP_ATR,
  US30_FALLBACK_SL_POINTS,
  applyScalpStopsIfEmpty,
  suggestScalpStops,
  wilderAtr,
} from "../apps/seven-desk/src/lib/live-order/atr-stops.ts";

assert.equal(SCALP_SL_ATR, 1.0);
assert.equal(SCALP_TP_ATR, 1.5);
assert.equal(US30_FALLBACK_SL_POINTS, 80);

const atr = wilderAtr(
  [10, 12, 11, 13, 14, 15, 14, 16, 17, 16, 18, 19, 18, 20, 21],
  [9, 10, 10, 11, 12, 13, 13, 14, 15, 14, 16, 17, 16, 18, 19],
  [9.5, 11, 10.5, 12, 13, 14, 13.5, 15, 16, 15, 17, 18, 17, 19, 20]
);
assert.ok(atr != null && atr > 0);

const fallback = suggestScalpStops({
  side: "buy",
  entry: 52500,
  atr: null,
  point: 1,
  lots: 4,
  contractSize: 1,
});
assert.ok(fallback);
assert.equal(fallback.source, "fallback80");
assert.equal(fallback.sl, 52420);
assert.equal(fallback.tp, 52620);
assert.equal(fallback.slPoints, 80);
assert.equal(fallback.tpPoints, 120);
assert.equal(fallback.riskUsd, 320);
assert.match(fallback.preview, /SL 52420 \/ TP 52620/);
assert.match(fallback.preview, /\$320/);

const sell = suggestScalpStops({
  side: "sell",
  entry: 52500,
  atr: null,
  point: 1,
  lots: 4,
  contractSize: 1,
});
assert.ok(sell);
assert.equal(sell.sl, 52580);
assert.equal(sell.tp, 52380);

const clamped = suggestScalpStops({
  side: "buy",
  entry: 52500,
  atr: 10,
  point: 1,
  stopsLevelPoints: 50,
  spreadPoints: 4,
  lots: 4,
  contractSize: 1,
});
assert.ok(clamped);
assert.equal(clamped.source, "atr14");
assert.ok(clamped.slDistance >= 54);

const applied = applyScalpStopsIfEmpty({
  side: "sell",
  entry: 52500,
  sl: fallback.sl,
  tp: fallback.tp,
  buySuggestion: fallback,
  sellSuggestion: sell,
});
assert.equal(applied.sl, sell.sl);
assert.equal(applied.tp, sell.tp);

console.log("test_desk_atr_stops.ts ok");

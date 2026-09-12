/** Frozen UsIndexSessionScalp ATR guides. Not a 1%-of-price preset. */

export const SCALP_SL_ATR = 1.0;
export const SCALP_TP_ATR = 1.5;
/** Overlay US30 auto spread cap; above Vantage DJ30.r stops_level 50. */
export const US30_FALLBACK_SL_POINTS = 80;
export const US30_DEFAULT_STOPS_LEVEL_POINTS = 50;
export const ATR_PERIOD = 14;

export function wilderAtr(
  highs: number[],
  lows: number[],
  closes: number[],
  period = ATR_PERIOD
): number | null {
  const n = Math.min(highs.length, lows.length, closes.length);
  if (n < period + 1) return null;
  const tr: number[] = [];
  for (let i = 0; i < n; i += 1) {
    const high = highs[i];
    const low = lows[i];
    if (!Number.isFinite(high) || !Number.isFinite(low) || high < low) return null;
    if (i === 0) {
      tr.push(high - low);
      continue;
    }
    const prev = closes[i - 1];
    if (!Number.isFinite(prev)) return null;
    tr.push(Math.max(high - low, Math.abs(high - prev), Math.abs(low - prev)));
  }
  let atr = 0;
  for (let i = 1; i <= period; i += 1) atr += tr[i];
  atr /= period;
  for (let i = period + 1; i < tr.length; i += 1) {
    atr = (atr * (period - 1) + tr[i]) / period;
  }
  return atr > 0 ? atr : null;
}

export type ScalpStopSource = "atr14" | "fallback80";

export interface ScalpStopInput {
  side: "buy" | "sell" | "BUY" | "SELL";
  entry: number;
  atr: number | null;
  point?: number;
  stopsLevelPoints?: number;
  spreadPoints?: number;
  lots?: number;
  contractSize?: number;
}

export interface ScalpStopSuggestion {
  sl: number;
  tp: number;
  slPoints: number;
  tpPoints: number;
  slDistance: number;
  tpDistance: number;
  riskUsd: number | null;
  source: ScalpStopSource;
  preview: string;
}

function roundToPoint(value: number, point: number): number {
  if (!(point > 0)) return value;
  return Math.round(value / point) * point;
}

export function suggestScalpStops(input: ScalpStopInput): ScalpStopSuggestion | null {
  const entry = input.entry;
  if (!Number.isFinite(entry) || entry <= 0) return null;
  const point = input.point != null && input.point > 0 ? input.point : 1;
  const stops = input.stopsLevelPoints ?? US30_DEFAULT_STOPS_LEVEL_POINTS;
  const spread = Math.max(0, input.spreadPoints ?? 0);
  const atr = input.atr != null && input.atr > 0 ? input.atr : null;
  const source: ScalpStopSource = atr != null ? "atr14" : "fallback80";
  const rawSl = atr != null ? SCALP_SL_ATR * atr : US30_FALLBACK_SL_POINTS * point;
  const minDist = Math.max(0, stops + spread) * point;
  const slDistance = Math.max(rawSl, minDist);
  const tpDistance = SCALP_TP_ATR * slDistance;
  const buy = input.side === "buy" || input.side === "BUY";
  const sl = roundToPoint(buy ? entry - slDistance : entry + slDistance, point);
  const tp = roundToPoint(buy ? entry + tpDistance : entry - tpDistance, point);
  const slPoints = slDistance / point;
  const tpPoints = tpDistance / point;
  const lots = input.lots != null && input.lots > 0 ? input.lots : null;
  const contract = input.contractSize != null && input.contractSize > 0 ? input.contractSize : 1;
  const riskUsd = lots != null ? slDistance * lots * contract : null;
  const riskBit =
    riskUsd != null && lots != null ? ` · ~$${Math.round(riskUsd)} at ${lots.toFixed(2)} lots` : "";
  const preview = `SL ${sl} / TP ${tp} · ${Math.round(slPoints)} pts / ${Math.round(tpPoints)} pts${riskBit}`;
  return {
    sl,
    tp,
    slPoints,
    tpPoints,
    slDistance,
    tpDistance,
    riskUsd,
    source,
    preview,
  };
}

export function applyScalpStopsIfEmpty(input: {
  side: "buy" | "sell";
  entry: number;
  sl: number | null;
  tp: number | null;
  buySuggestion: ScalpStopSuggestion;
  sellSuggestion: ScalpStopSuggestion;
}): { sl: number | null; tp: number | null } {
  const want = input.side === "buy" ? input.buySuggestion : input.sellSuggestion;
  const other = input.side === "buy" ? input.sellSuggestion : input.buySuggestion;
  if (input.sl == null && input.tp == null) {
    return { sl: want.sl, tp: want.tp };
  }
  if (input.sl === other.sl && input.tp === other.tp) {
    return { sl: want.sl, tp: want.tp };
  }
  return { sl: input.sl, tp: input.tp };
}

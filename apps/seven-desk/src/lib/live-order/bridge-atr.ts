import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { inspectBridgeFreshness } from "@/lib/bridge-freshness";
import { isUs30Family } from "@/lib/live-order/guards";
import { ATR_PERIOD, wilderAtr } from "@/lib/live-order/atr-stops";

const lastAtr = new Map<string, { atr: number; at: number }>();

export function parseCandleAtr(jsonText: string): number | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonText);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const candles = (parsed as { candles?: unknown }).candles;
  if (!Array.isArray(candles)) return null;
  const highs: number[] = [];
  const lows: number[] = [];
  const closes: number[] = [];
  for (const row of candles) {
    if (!row || typeof row !== "object") continue;
    const high = Number((row as { high?: unknown }).high);
    const low = Number((row as { low?: unknown }).low);
    const close = Number((row as { close?: unknown }).close);
    if (!Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) continue;
    highs.push(high);
    lows.push(low);
    closes.push(close);
  }
  return wilderAtr(highs, lows, closes, ATR_PERIOD);
}

export function readAtr14FromBridgeDirs(
  dirs: string[],
  symbol: string
): { atr: number; sourceFile: string } | null {
  const wantUs30 = isUs30Family(symbol);
  for (const dir of dirs) {
    if (!existsSync(dir)) continue;
    let names: string[] = [];
    try {
      names = readdirSync(dir);
    } catch {
      continue;
    }
    const matches = names.filter((name) => {
      if (!name.startsWith("candles_") || !name.endsWith("_M5.json")) return false;
      const mid = name.slice("candles_".length, -"_M5.json".length);
      if (wantUs30) return isUs30Family(mid);
      return mid.toUpperCase() === symbol.toUpperCase();
    });
    for (const name of matches) {
      const path = join(dir, name);
      try {
        if (!statSync(path).isFile()) continue;
        const atr = parseCandleAtr(readFileSync(path, "utf8"));
        if (atr != null) return { atr, sourceFile: path };
      } catch {
        continue;
      }
    }
  }
  return null;
}

export function resolveBridgeAtr(input: {
  broker: string;
  symbol: string;
  dirs: string[];
}): { atr: number | null; source: "atr14" | "last_known" | "fallback80"; heartbeatFresh: boolean } {
  const freshness = inspectBridgeFreshness({
    bridgeDirs: input.dirs,
    winePrefix: "",
  });
  const key = `${input.broker}:${input.symbol}`;
  const live = freshness.heartbeatFresh
    ? readAtr14FromBridgeDirs(input.dirs, input.symbol)
    : null;
  if (live) {
    lastAtr.set(key, { atr: live.atr, at: Date.now() });
    return { atr: live.atr, source: "atr14", heartbeatFresh: true };
  }
  const cached = lastAtr.get(key);
  if (cached && cached.atr > 0) {
    return { atr: cached.atr, source: "last_known", heartbeatFresh: freshness.heartbeatFresh };
  }
  return { atr: null, source: "fallback80", heartbeatFresh: freshness.heartbeatFresh };
}

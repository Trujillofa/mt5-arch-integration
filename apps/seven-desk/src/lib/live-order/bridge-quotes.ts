import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { bridgeMaxAgeSeconds } from "@/lib/bridge-freshness";
import { normalizeSymbolKey } from "@/lib/live-order/guards";

export type QuoteSnapshot =
  | {
      ok: true;
      bid: number;
      ask: number;
      tsMs: number;
      source: "bridge";
    }
  | {
      ok: false;
      reason: "missing" | "stale" | "invalid" | "symbol_unmapped";
    };

const SUFFIXES = ["PRO", "CASH", "C", "M", "R"] as const;

export function quoteSymbolAliases(symbol: string): string[] {
  const key = normalizeSymbolKey(symbol);
  const aliases = new Set<string>([key]);
  for (const suffix of SUFFIXES) {
    if (key.endsWith(suffix) && key.length > suffix.length) {
      aliases.add(key.slice(0, -suffix.length));
    }
  }
  return [...aliases];
}

export function quoteSymbolMatches(rowSymbol: string, want: string): boolean {
  const have = quoteSymbolAliases(rowSymbol);
  const need = quoteSymbolAliases(want);
  return have.some((alias) => need.includes(alias));
}

function asFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function quoteAgeMs(input: {
  nowMs: number;
  fileMtimeMs?: number;
  updatedAtSec?: number | null;
  timeMsc?: number | null;
}): number | null {
  const ages: number[] = [];
  if (input.fileMtimeMs != null && input.fileMtimeMs > 0) {
    ages.push(input.nowMs - input.fileMtimeMs);
  }
  if (input.updatedAtSec != null && input.updatedAtSec > 0) {
    ages.push(input.nowMs - input.updatedAtSec * 1000);
  }
  if (input.timeMsc != null && input.timeMsc > 0) {
    ages.push(input.nowMs - input.timeMsc);
  }
  if (ages.length === 0) return null;
  return Math.max(...ages);
}

export function parseBridgeQuotes(
  raw: unknown,
  input: {
    symbol: string;
    nowMs: number;
    maxAgeSeconds: number;
    heartbeatFresh: boolean;
    fileMtimeMs?: number;
  }
): QuoteSnapshot {
  if (!input.heartbeatFresh) return { ok: false, reason: "stale" };
  if (raw == null || typeof raw !== "object") return { ok: false, reason: "missing" };

  const body = raw as Record<string, unknown>;
  const rows = Array.isArray(body) ? body : body.quotes;
  if (!Array.isArray(rows)) return { ok: false, reason: "missing" };

  const updatedAtSec = asFiniteNumber(body.updated_at ?? body.updatedAt);
  const maxAgeMs = input.maxAgeSeconds * 1000;
  let matched: { bid: number; ask: number; timeMsc: number | null } | null = null;

  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const item = row as Record<string, unknown>;
    const symbol = typeof item.symbol === "string" ? item.symbol : "";
    if (!symbol || !quoteSymbolMatches(symbol, input.symbol)) continue;
    const bid = asFiniteNumber(item.bid);
    const ask = asFiniteNumber(item.ask);
    if (bid == null || ask == null || bid <= 0 || ask <= 0 || ask < bid) {
      return { ok: false, reason: "invalid" };
    }
    matched = {
      bid,
      ask,
      timeMsc: asFiniteNumber(item.time_msc ?? item.timeMsc),
    };
    break;
  }

  if (!matched) return { ok: false, reason: "symbol_unmapped" };

  const ageMs = quoteAgeMs({
    nowMs: input.nowMs,
    fileMtimeMs: input.fileMtimeMs,
    updatedAtSec,
    timeMsc: matched.timeMsc,
  });
  if (ageMs != null && ageMs > maxAgeMs) return { ok: false, reason: "stale" };

  return {
    ok: true,
    bid: matched.bid,
    ask: matched.ask,
    tsMs: matched.timeMsc != null && matched.timeMsc > 0 ? matched.timeMsc : (input.fileMtimeMs ?? input.nowMs),
    source: "bridge",
  };
}

export function readBridgeQuote(input: {
  bridgeDirs: string[];
  symbol: string;
  heartbeatFresh: boolean;
  nowMs?: number;
  maxAgeSeconds?: number;
}): QuoteSnapshot {
  const nowMs = input.nowMs ?? Date.now();
  const maxAgeSeconds = input.maxAgeSeconds ?? bridgeMaxAgeSeconds();
  if (!input.heartbeatFresh) return { ok: false, reason: "stale" };

  for (const dir of input.bridgeDirs) {
    const file = join(dir, "quotes.json");
    if (!existsSync(file)) continue;
    let fileMtimeMs: number | undefined;
    try {
      fileMtimeMs = statSync(file).mtimeMs;
    } catch {
      continue;
    }
    try {
      const raw: unknown = JSON.parse(readFileSync(file, "utf8"));
      const parsed = parseBridgeQuotes(raw, {
        symbol: input.symbol,
        nowMs,
        maxAgeSeconds,
        heartbeatFresh: input.heartbeatFresh,
        fileMtimeMs,
      });
      if (parsed.ok) return parsed;
      if (parsed.reason === "invalid" || parsed.reason === "stale") return parsed;
    } catch {
      return { ok: false, reason: "invalid" };
    }
  }
  return { ok: false, reason: "missing" };
}

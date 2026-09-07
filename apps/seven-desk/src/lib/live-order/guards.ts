/** Pure live-order helpers. Safe to unit-test without Wine. */

import type { LiveOrderResult } from "./types";

/** HTTP routes must return JSON before typical client 120s cutoffs. */
export const LIVE_ORDER_HTTP_BUDGET_MS = 70_000;
/** One-shot wine/terminal64 wall clock. Must stay under the HTTP budget. */
export const WINE_ONESHOT_BUDGET_MS = 50_000;
/** Browser / desk-context AbortSignal. Slightly above the server budget. */
export const LIVE_ORDER_CLIENT_BUDGET_MS = 75_000;
/**
 * Orphan request without a matching result is stale after this TTL.
 * In-flight leftovers (script died mid-restart) must not be OrderSent again.
 */
export const LIVE_ORDER_REQUEST_TTL_MS = 90_000;

export type OrphanClass = "absent" | "done" | "in_flight" | "stale";

export function parseRequestFields(text: string): {
  requestId: string;
  issuedAt: number | null;
} {
  let requestId = "";
  let issuedAt: number | null = null;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (line.startsWith("request_id=")) {
      requestId = line.slice("request_id=".length).trim();
    } else if (line.startsWith("issued_at=")) {
      const parsed = Number(line.slice("issued_at=".length).trim());
      issuedAt = Number.isFinite(parsed) && parsed > 0 ? parsed : null;
    }
  }
  return { requestId, issuedAt };
}

/** Node writes unix seconds; accept ms if a host already stamped that way. */
export function requestIssuedAtMs(issuedAt: number | null, fileMtimeMs: number): number {
  if (issuedAt == null || !Number.isFinite(issuedAt) || issuedAt <= 0) return fileMtimeMs;
  return issuedAt < 1e12 ? issuedAt * 1000 : issuedAt;
}

export function resultBelongsToRequest(
  resultId: string | null | undefined,
  requestId: string
): boolean {
  if (!requestId || !resultId) return false;
  return resultId === requestId;
}

export function classifyOrphanRequest(input: {
  requestPresent: boolean;
  requestId: string;
  issuedAt: number | null;
  fileMtimeMs: number;
  matchingResult: boolean;
  nowMs?: number;
  ttlMs?: number;
}): OrphanClass {
  if (!input.requestPresent) return "absent";
  if (input.matchingResult && input.requestId) return "done";
  const now = input.nowMs ?? Date.now();
  const origin = requestIssuedAtMs(input.issuedAt, input.fileMtimeMs);
  const age = now - origin;
  const ttl = input.ttlMs ?? LIVE_ORDER_REQUEST_TTL_MS;
  if (age >= ttl) return "stale";
  return "in_flight";
}

export function inFlightOrphanReason(requestId: string): string {
  const id = requestId || "unknown";
  return (
    `orphan desk_live_order_request ${id} has no matching result and is still within TTL — ` +
    `refusing a second OrderSend (host hang left request without response)`
  );
}

export function isTradeServerDisconnected(
  terminalConnected: boolean | null | undefined
): boolean {
  return terminalConnected === false;
}

export function resolveStartupServer(
  identityServer: string | null | undefined,
  expected: string,
  needle: string
): string {
  const server = (identityServer ?? "").trim();
  if (server && needle && server.includes(needle)) return server;
  return expected;
}

/** ACG Markets stores FX history under EURUSD.pro when the desk asks for EURUSD. */
export function quotesPathMatchesSymbol(
  fullPath: string,
  fileName: string,
  symbol: string
): boolean {
  const want = symbol.toUpperCase();
  const upper = fullPath.toUpperCase();
  const file = fileName.toUpperCase();
  if (upper.includes(`/${want}/`) || upper.includes(`\\${want}\\`) || file.startsWith(want)) {
    return true;
  }
  return upper.includes(`/${want}.`) || upper.includes(`\\${want}.`);
}

/** One-shot chart must open the ACG *.pro name or the script never gets quotes. */
export function alphaStartupChartSymbol(firmId: string, symbol: string): string {
  if (firmId !== "alphacapital") return symbol;
  const upper = symbol.toUpperCase();
  if (upper === "EURUSD" || upper === "EURUSDC") return "EURUSD.pro";
  return symbol;
}

export function resultMatchesRequest(
  resultId: string | null | undefined,
  requestId: string
): boolean {
  return resultBelongsToRequest(resultId, requestId);
}

export function remainingMs(deadlineMs: number, nowMs = Date.now()): number {
  return deadlineMs - nowMs;
}

export function deadlineExceeded(deadlineMs: number, nowMs = Date.now()): boolean {
  return nowMs >= deadlineMs;
}

export function httpTimeoutResult(input: {
  endpoint: string;
  requestId: string;
  winePrefix: string;
  login?: number | null;
  server?: string | null;
  reason?: string;
}): LiveOrderResult {
  return {
    ok: false,
    source: "seven-desk",
    endpoint: input.endpoint,
    requestId: input.requestId,
    stage: "timeout",
    reason:
      input.reason ??
      "live order exceeded HTTP deadline — wine one-shot aborted; no hang without JSON",
    login: input.login ?? null,
    server: input.server ?? null,
    winePrefix: input.winePrefix,
  };
}

export function disconnectedOrderReason(firmId: string, server: string | null): string {
  const book = server || firmId;
  return (
    `${firmId} trade server is disconnected (terminal_connected=false) — refusing OrderSend. ` +
    `${book} session is down (weekend FX / broker disconnect), not an auth failure.`
  );
}

export async function withDeadline<T>(
  work: Promise<T>,
  budgetMs: number,
  fallback: T
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<T>((resolve) => {
    timer = setTimeout(() => resolve(fallback), budgetMs);
  });
  try {
    return await Promise.race([work, timeout]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export function asJsonBool(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (value === "true" || value === 1 || value === "1") return true;
  if (value === "false" || value === 0 || value === "0") return false;
  return null;
}

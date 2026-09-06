/** Pure live-order helpers. Safe to unit-test without Wine. */

import type { LiveOrderResult } from "./types";

/** HTTP routes must return JSON before typical client 120s cutoffs. */
export const LIVE_ORDER_HTTP_BUDGET_MS = 70_000;
/** One-shot wine/terminal64 wall clock. Must stay under the HTTP budget. */
export const WINE_ONESHOT_BUDGET_MS = 50_000;
/** Browser / desk-context AbortSignal. Slightly above the server budget. */
export const LIVE_ORDER_CLIENT_BUDGET_MS = 75_000;

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

export function resultMatchesRequest(
  resultId: string | null | undefined,
  requestId: string
): boolean {
  if (!resultId) return true;
  return resultId === requestId;
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

/** Pure live-order helpers. Safe to unit-test without Wine. */

import type {
  LiveBroker,
  LiveOrderAction,
  LiveOrderInput,
  LiveOrderResult,
  LiveOrderType,
} from "./types";

/** Conservative FX/index min used when the body omits volume. */
export const MIN_LIVE_LOT = 0.01;
/**
 * Hard refuse above this even with volume_confirm. Broker SYMBOL_VOLUME_MAX
 * is the second cap inside the one-shot. 4.0 US30 lots is inside this bound.
 */
export const LIVE_ORDER_VOLUME_HARD_MAX = 10;

/** Broker names tried by SymbolSelect, requested name first at runtime. */
export const US30_SELECT_VARIANTS = [
  "US30",
  "US30.cash",
  "US30.Cash",
  "US30c",
  "US30.c",
  "US30.m",
  "US30m",
  "US30.r",
  "DJ30",
  "DJ30.c",
  "DJ30c",
  "DJ30.cash",
  "DJI30",
  "WS30",
] as const;

/** WSF 149736 @ WSFmarkets-Server Market Watch name is DJ30.c (host evidence). */
export const WSF_US30_PREFERRED = "DJ30.c";

export function normalizeSymbolKey(symbol: string): string {
  return symbol.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

const US30_KEYS = new Set(US30_SELECT_VARIANTS.map((name) => normalizeSymbolKey(name)));

export function isUs30Family(symbol: string): boolean {
  return US30_KEYS.has(normalizeSymbolKey(symbol));
}

/** SymbolSelect try-list. WSF tries DJ30.c first; other books keep the shared order. */
export function us30SelectVariantsForFirm(firmId: string): readonly string[] {
  if (firmId !== "wsf") return US30_SELECT_VARIANTS;
  return [
    WSF_US30_PREFERRED,
    ...US30_SELECT_VARIANTS.filter((name) => name !== WSF_US30_PREFERRED),
  ];
}

export function us30AllowedForFirm(firmId: string): boolean {
  return (
    firmId === "wsf" ||
    firmId === "ftmo" ||
    firmId === "fundednext" ||
    firmId === "fundingpips" ||
    firmId === "fortraders"
  );
}

export function symbolAllowedForFirm(firmId: string, symbol: string): boolean {
  if (symbol === "EURUSD" || symbol === "EURUSDc") return true;
  if (firmId === "alphacapital") {
    return symbol === "BTCUSD" || symbol === "BTCUSDc" || symbol === "BTCUSD.r";
  }
  if (!us30AllowedForFirm(firmId)) return false;
  return isUs30Family(symbol);
}

export function allowedSymbolHint(firmId: string): string {
  if (firmId === "alphacapital") return "EURUSD/EURUSDc or BTCUSD/BTCUSDc/BTCUSD.r";
  if (firmId === "neomaa") return "EURUSD/EURUSDc only";
  if (firmId === "wsf") {
    return "EURUSD/EURUSDc or US30 family (DJ30.c, US30, …)";
  }
  return "EURUSD/EURUSDc or US30 family (US30, US30.cash, DJ30, DJ30.c, …)";
}

/** One-shot chart must already exist in Market Watch. US30 may not. */
export function oneshotChartSymbol(firmId: string, symbol: string): string {
  if (isUs30Family(symbol)) {
    return firmId === "wsf" ? "EURUSDc" : "EURUSD";
  }
  return alphaStartupChartSymbol(firmId, symbol);
}

export type ParsedLiveOrder = {
  action: LiveOrderAction;
  orderType: LiveOrderType;
  symbol: string;
  side: "BUY" | "SELL";
  useVolumeMin: boolean;
  volume: number | null;
  price: number | null;
  sl: number | null;
  tp: number | null;
  ticket: number | null;
  confirm: string;
};

export type LiveOrderParseResult =
  | { ok: true; fields: ParsedLiveOrder }
  | { ok: false; status: number; stage: string; reason: string };

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function parseNumberField(
  value: unknown,
  name: string
): { ok: true; value: number | null } | { ok: false; reason: string } {
  if (value === undefined || value === null || value === "") {
    return { ok: true, value: null };
  }
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) {
    return { ok: false, reason: `${name} must be a number` };
  }
  return { ok: true, value: parsed };
}

export function parseLiveOrderRequest(input: {
  body: LiveOrderInput;
  expectedConfirm: string;
  defaultSymbol: string;
  firmId: LiveBroker | string;
}): LiveOrderParseResult {
  const { body, expectedConfirm, defaultSymbol, firmId } = input;
  if (body.live !== true) {
    return { ok: false, status: 400, stage: "confirm", reason: "live must be true — paper is the default" };
  }
  const confirm = asString(body.confirm);
  if (confirm !== expectedConfirm) {
    return { ok: false, status: 403, stage: "confirm", reason: `confirm must be exactly ${expectedConfirm}` };
  }

  const orderTypeRaw = asString(body.order_type).toLowerCase() || "market";
  let orderType: LiveOrderType;
  if (orderTypeRaw === "market") {
    orderType = "market";
  } else if (orderTypeRaw === "buy_limit") {
    orderType = "buy_limit";
  } else if (orderTypeRaw === "sell_limit") {
    orderType = "sell_limit";
  } else if (orderTypeRaw === "limit") {
    orderType = "buy_limit";
  } else {
    return {
      ok: false,
      status: 400,
      stage: "order_type",
      reason: "order_type must be market, buy_limit, sell_limit, or limit",
    };
  }

  const pending = orderType === "buy_limit" || orderType === "sell_limit";
  const actionRaw = asString(body.action).toLowerCase() || (pending ? "open" : "scratch");
  if (
    actionRaw !== "scratch" &&
    actionRaw !== "open" &&
    actionRaw !== "close" &&
    actionRaw !== "cancel"
  ) {
    return { ok: false, status: 400, stage: "action", reason: "action must be scratch, open, close, or cancel" };
  }
  const action: LiveOrderAction = actionRaw;
  if (pending && action === "scratch") {
    return {
      ok: false,
      status: 400,
      stage: "action",
      reason: "scratch is market open+close only — use action=open with order_type=buy_limit",
    };
  }
  if (pending && action === "close") {
    return {
      ok: false,
      status: 400,
      stage: "action",
      reason: "close is for positions — use action=cancel to remove a pending order",
    };
  }

  const symbol = asString(body.symbol) || defaultSymbol;
  if (!symbolAllowedForFirm(firmId, symbol)) {
    return { ok: false, status: 400, stage: "symbol", reason: `symbol not allowed — ${allowedSymbolHint(firmId)}` };
  }

  const sideRaw = asString(body.side).toLowerCase() || (orderType === "sell_limit" ? "sell" : "buy");
  if (sideRaw !== "buy" && sideRaw !== "sell") {
    return { ok: false, status: 400, stage: "side", reason: "side must be buy or sell" };
  }
  if (orderTypeRaw === "limit") {
    orderType = sideRaw === "sell" ? "sell_limit" : "buy_limit";
  }
  if (orderType === "buy_limit" && sideRaw === "sell") {
    return { ok: false, status: 400, stage: "side", reason: "order_type=buy_limit requires side=buy" };
  }
  if (orderType === "sell_limit" && sideRaw === "buy") {
    return { ok: false, status: 400, stage: "side", reason: "order_type=sell_limit requires side=sell" };
  }
  const side: "BUY" | "SELL" = sideRaw === "sell" ? "SELL" : "BUY";

  const priceField = parseNumberField(body.price, "price");
  if (!priceField.ok) return { ok: false, status: 400, stage: "price", reason: priceField.reason };
  const slField = parseNumberField(body.sl, "sl");
  if (!slField.ok) return { ok: false, status: 400, stage: "sl", reason: slField.reason };
  const tpField = parseNumberField(body.tp, "tp");
  if (!tpField.ok) return { ok: false, status: 400, stage: "tp", reason: tpField.reason };
  const ticketRaw = body.ticket !== undefined && body.ticket !== null && body.ticket !== "" ? body.ticket : body.order;
  const ticketField = parseNumberField(ticketRaw, "ticket");
  if (!ticketField.ok) return { ok: false, status: 400, stage: "ticket", reason: ticketField.reason };
  if (ticketField.value != null && (ticketField.value <= 0 || !Number.isInteger(ticketField.value))) {
    return { ok: false, status: 400, stage: "ticket", reason: "ticket must be a positive integer" };
  }

  if (pending && action === "open") {
    if (priceField.value == null || priceField.value <= 0) {
      return { ok: false, status: 400, stage: "price", reason: "pending order requires price > 0" };
    }
    if (slField.value != null && slField.value <= 0) {
      return { ok: false, status: 400, stage: "sl", reason: "sl must be greater than 0 when set" };
    }
    if (tpField.value != null && tpField.value <= 0) {
      return { ok: false, status: 400, stage: "tp", reason: "tp must be greater than 0 when set" };
    }
    if (orderType === "buy_limit") {
      if (slField.value != null && slField.value >= priceField.value) {
        return { ok: false, status: 400, stage: "sl", reason: "buy_limit requires sl < price" };
      }
      if (tpField.value != null && tpField.value <= priceField.value) {
        return { ok: false, status: 400, stage: "tp", reason: "buy_limit requires tp > price" };
      }
    } else {
      if (slField.value != null && slField.value <= priceField.value) {
        return { ok: false, status: 400, stage: "sl", reason: "sell_limit requires sl > price" };
      }
      if (tpField.value != null && tpField.value >= priceField.value) {
        return { ok: false, status: 400, stage: "tp", reason: "sell_limit requires tp < price" };
      }
    }
  }

  const volumeMinFlag = body.volume_min === true || body.volume === undefined || body.volume === null;
  const volumeConfirm = asJsonBool(body.volume_confirm) === true;
  const volumeField = parseNumberField(body.volume, "volume");
  if (!volumeField.ok) return { ok: false, status: 400, stage: "volume", reason: volumeField.reason };
  let volume = volumeField.value;
  let useVolumeMin = volumeMinFlag || volume == null;
  if (volume != null) {
    if (volume <= 0) {
      return { ok: false, status: 400, stage: "volume", reason: "volume must be greater than 0" };
    }
    if (volume > LIVE_ORDER_VOLUME_HARD_MAX + 1e-8) {
      return {
        ok: false,
        status: 400,
        stage: "volume",
        reason: `volume exceeds hard max ${LIVE_ORDER_VOLUME_HARD_MAX} — refusing absurd size`,
      };
    }
    if (!volumeMinFlag && volume > MIN_LIVE_LOT + 1e-8 && !volumeConfirm) {
      return {
        ok: false,
        status: 400,
        stage: "volume",
        reason: "volume above 0.01 requires volume_confirm=true (confirm token is identity, not size intent)",
      };
    }
    if (volumeMinFlag) {
      if (volume > MIN_LIVE_LOT + 1e-8) {
        return {
          ok: false,
          status: 400,
          stage: "volume",
          reason: "volume_min=true refuses a larger volume — omit volume_min and pass volume_confirm=true",
        };
      }
      useVolumeMin = true;
      volume = MIN_LIVE_LOT;
    } else {
      useVolumeMin = false;
    }
  }
  if (action === "scratch") {
    if (volume != null && volume > MIN_LIVE_LOT + 1e-8) {
      return {
        ok: false,
        status: 400,
        stage: "volume",
        reason: "scratch is min-lot market open+close only — omit volume or pass volume_min=true",
      };
    }
    useVolumeMin = true;
  }

  return {
    ok: true,
    fields: {
      action,
      orderType: pending ? orderType : "market",
      symbol,
      side,
      useVolumeMin,
      volume,
      price: pending ? priceField.value : null,
      sl: pending ? slField.value : null,
      tp: pending ? tpField.value : null,
      ticket: ticketField.value,
      confirm,
    },
  };
}

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

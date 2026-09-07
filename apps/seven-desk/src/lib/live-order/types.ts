/** Shared live OrderSend result. Safe to import from the browser. */

export type LiveBroker = "wsf" | "ftmo" | "fundednext" | "alphacapital" | "fundingpips" | "neomaa" | "fortraders";
export type LiveOrderAction = "scratch" | "open" | "close" | "cancel";
export type LiveOrderType = "market" | "buy_limit" | "sell_limit";

export interface LiveOrderResult {
  ok: boolean;
  source: "seven-desk";
  endpoint: string;
  requestId: string;
  stage: string;
  reason: string;
  login: number | null;
  server: string | null;
  company?: string;
  symbol?: string;
  volume?: number;
  side?: string;
  orderType?: string;
  price?: number;
  sl?: number;
  tp?: number;
  order?: number;
  ticket?: number;
  position?: number;
  dealOpen?: number;
  dealClose?: number;
  openPrice?: number;
  closePrice?: number;
  profit?: number;
  holdMs?: number;
  balanceAfter?: number;
  closeRetcode?: number;
  winePrefix: string;
  restoreNote?: string;
  stoppedPids?: number[];
}

export interface LiveOrderInput {
  live: unknown;
  confirm: unknown;
  action?: unknown;
  order_type?: unknown;
  symbol?: unknown;
  side?: unknown;
  volume?: unknown;
  volume_min?: unknown;
  volume_confirm?: unknown;
  price?: unknown;
  sl?: unknown;
  tp?: unknown;
  ticket?: unknown;
  order?: unknown;
}

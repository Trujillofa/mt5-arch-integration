/** Shared live OrderSend result. Safe to import from the browser. */

export type LiveBroker = "wsf" | "ftmo" | "fundednext" | "alphacapital";
export type LiveOrderAction = "scratch" | "open" | "close";

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
  order?: number;
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
  symbol?: unknown;
  side?: unknown;
  volume?: unknown;
  volume_min?: unknown;
}

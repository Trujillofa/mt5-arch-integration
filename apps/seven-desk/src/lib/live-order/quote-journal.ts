import { appendFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import type { QuoteSnapshot } from "@/lib/live-order/bridge-quotes";

export type QuoteJournalKind = "request" | "fill";
export type QuoteStatus = "ok" | "missing" | "stale" | "invalid" | "symbol_unmapped";

export interface QuoteJournalRecord {
  v: 1;
  kind: QuoteJournalKind;
  ts: string;
  tsMs: number;
  requestId: string;
  firm: string;
  symbol: string;
  side: string;
  action: string;
  orderType: string | null;
  lots: number | null;
  intendedPrice: number | null;
  requestedBid: number | null;
  requestedAsk: number | null;
  quoteStatus: QuoteStatus;
  quoteSource: "bridge" | null;
  quoteTsMs: number | null;
  sendPath?: "ea" | "oneshot";
  fillPrice?: number | null;
  fillTicket?: number | null;
  ok?: boolean;
  stage?: string;
}

export interface LiveJournalCtx {
  requestId: string;
  firm: string;
  symbol: string;
  side: string;
  action: string;
  orderType?: string | null;
  lots: number | null;
  intendedPrice: number | null;
  quote: QuoteSnapshot;
  sendPath?: "ea" | "oneshot";
}

export interface FillSource {
  ok?: boolean;
  stage?: string;
  price?: number;
  openPrice?: number;
  closePrice?: number;
  ticket?: number;
  order?: number;
  journalError?: string;
}

export interface QuoteJournalIo {
  journalPath: string;
  nowMs: () => number;
  append: (path: string, line: string) => void;
}

export function resolveQuoteJournalPath(
  env: NodeJS.ProcessEnv = process.env,
  cwd = process.cwd()
): string {
  const override = env.SEVEN_DESK_QUOTE_JOURNAL?.trim();
  if (override) return override;
  const desk = cwd.endsWith("seven-desk") ? cwd : join(cwd, "apps", "seven-desk");
  return join(desk, "data", "live-order-journal.jsonl");
}

export function quoteStatusOf(quote: QuoteSnapshot): QuoteStatus {
  if (quote.ok) return "ok";
  return quote.reason;
}

export function requestedQuoteFields(quote: QuoteSnapshot): {
  requestedBid: number | null;
  requestedAsk: number | null;
  quoteStatus: QuoteStatus;
  quoteSource: "bridge" | null;
  quoteTsMs: number | null;
} {
  if (!quote.ok) {
    return {
      requestedBid: null,
      requestedAsk: null,
      quoteStatus: quote.reason,
      quoteSource: null,
      quoteTsMs: null,
    };
  }
  return {
    requestedBid: quote.bid,
    requestedAsk: quote.ask,
    quoteStatus: "ok",
    quoteSource: quote.source,
    quoteTsMs: quote.tsMs,
  };
}

export function fillPriceOf(result: FillSource): number | null {
  if (typeof result.price === "number" && result.price > 0) return result.price;
  if (typeof result.openPrice === "number" && result.openPrice > 0) return result.openPrice;
  if (typeof result.closePrice === "number" && result.closePrice > 0) return result.closePrice;
  return null;
}

export function fillTicketOf(result: FillSource): number | null {
  if (typeof result.ticket === "number" && result.ticket > 0) return result.ticket;
  if (typeof result.order === "number" && result.order > 0) return result.order;
  return null;
}

function intendedPriceOf(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

function defaultAppend(path: string, line: string): void {
  mkdirSync(dirname(path), { recursive: true });
  appendFileSync(path, `${line}\n`, { encoding: "utf8" });
}

export function defaultQuoteJournalIo(): QuoteJournalIo {
  return {
    journalPath: resolveQuoteJournalPath(),
    nowMs: () => Date.now(),
    append: defaultAppend,
  };
}

function journalErrorMessage(caught: unknown): string {
  if (caught instanceof Error && caught.message) return caught.message;
  return "quote journal write failed";
}

export function buildRequestRecord(ctx: LiveJournalCtx, nowMs: number): QuoteJournalRecord {
  const quoted = requestedQuoteFields(ctx.quote);
  return {
    v: 1,
    kind: "request",
    ts: new Date(nowMs).toISOString(),
    tsMs: nowMs,
    requestId: ctx.requestId,
    firm: ctx.firm,
    symbol: ctx.symbol,
    side: ctx.side,
    action: ctx.action,
    orderType: ctx.orderType ?? null,
    lots: ctx.lots,
    intendedPrice: intendedPriceOf(ctx.intendedPrice),
    ...quoted,
    sendPath: ctx.sendPath,
  };
}

export function buildFillRecord(
  ctx: LiveJournalCtx,
  result: FillSource,
  nowMs: number
): QuoteJournalRecord {
  return {
    ...buildRequestRecord(ctx, nowMs),
    kind: "fill",
    fillPrice: fillPriceOf(result),
    fillTicket: fillTicketOf(result),
    ok: result.ok,
    stage: result.stage,
  };
}

function appendRecord(record: QuoteJournalRecord, io: QuoteJournalIo): void {
  io.append(io.journalPath, JSON.stringify(record));
}

/** Snapshot + request line happen here. Call immediately before writeRequest / OrderSend. */
export function openLiveQuoteJournal(
  ctx: LiveJournalCtx,
  io: QuoteJournalIo = defaultQuoteJournalIo()
): { finish: (result: FillSource) => void } {
  const errors: string[] = [];
  try {
    appendRecord(buildRequestRecord(ctx, io.nowMs()), io);
  } catch (caught) {
    errors.push(journalErrorMessage(caught));
  }
  return {
    finish(result: FillSource) {
      try {
        appendRecord(buildFillRecord(ctx, result, io.nowMs()), io);
      } catch (caught) {
        errors.push(journalErrorMessage(caught));
      }
      const err = errors[0];
      if (!err) return;
      result.journalError = result.journalError ?? err;
      console.error("journal_error", err);
    },
  };
}

/**
 * Test seam: the request journal line is always written before `send`.
 * A journal failure never invents bid/ask and never swallows the send.
 */
export async function journalBeforeSend<T>(
  ctx: LiveJournalCtx,
  send: () => Promise<T>,
  fillFrom: (result: T) => FillSource,
  io: QuoteJournalIo = defaultQuoteJournalIo()
): Promise<{ result: T; journalError?: string }> {
  const qj = openLiveQuoteJournal(ctx, io);
  const result = await send();
  const fill = fillFrom(result);
  qj.finish(fill);
  return { result, journalError: fill.journalError };
}

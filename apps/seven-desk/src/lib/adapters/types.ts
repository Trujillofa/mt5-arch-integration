import type { PaperQuote, Side, TradingAccount } from "@/lib/types";

export interface MarketOrder {
  symbol: string;
  side: Side;
  lots: number;
  sl: number | null;
  tp: number | null;
}

export interface AdapterFill {
  price: number;
  slippagePips: number;
  at: number;
}

export interface AdapterError {
  ok: false;
  reason: string;
}

export interface AdapterSuccess {
  ok: true;
  fill: AdapterFill;
}

export type AdapterResult = AdapterSuccess | AdapterError;

export interface AccountAdapter {
  readonly kind: "paper" | "live-stub";
  getQuote(symbol: string, quotes: PaperQuote[]): PaperQuote | null;
  placeMarket(
    account: TradingAccount,
    order: MarketOrder,
    quotes: PaperQuote[]
  ): AdapterResult;
  closeMarket(
    account: TradingAccount,
    symbol: string,
    side: Side,
    quotes: PaperQuote[]
  ): AdapterResult;
}

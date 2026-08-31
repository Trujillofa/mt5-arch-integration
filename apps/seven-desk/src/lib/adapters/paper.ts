import { pipDistance, quoteBySymbol } from "@/lib/quotes";
import type {
  AccountAdapter,
  AdapterResult,
  MarketOrder,
} from "@/lib/adapters/types";
import type { PaperQuote, Side, TradingAccount } from "@/lib/types";

/** Paper fills always slip this many pips against the trader. */
export const PAPER_SLIP_PIPS = 0.25;

export class PaperAdapter implements AccountAdapter {
  readonly kind = "paper" as const;

  getQuote(symbol: string, quotes: PaperQuote[]): PaperQuote | null {
    return quoteBySymbol(quotes, symbol) ?? null;
  }

  placeMarket(
    account: TradingAccount,
    order: MarketOrder,
    quotes: PaperQuote[]
  ): AdapterResult {
    if (account.status !== "connected") {
      return {
        ok: false,
        reason:
          account.status === "error"
            ? account.statusReason ?? "account error"
            : "account disconnected",
      };
    }
    const quote = this.getQuote(order.symbol, quotes);
    if (!quote) {
      return { ok: false, reason: `no paper quote for ${order.symbol}` };
    }
    if (order.lots < 0.01) {
      return { ok: false, reason: "lot too small" };
    }
    const raw = order.side === "buy" ? quote.ask : quote.bid;
    const slip = quote.pip * PAPER_SLIP_PIPS;
    const price =
      order.side === "buy"
        ? raw + slip
        : raw - slip;
    return {
      ok: true,
      fill: {
        price,
        slippagePips: pipDistance(quote, raw, price),
        at: Date.now(),
      },
    };
  }

  closeMarket(
    account: TradingAccount,
    symbol: string,
    side: Side,
    quotes: PaperQuote[]
  ): AdapterResult {
    if (account.status !== "connected") {
      return { ok: false, reason: "account disconnected" };
    }
    const quote = this.getQuote(symbol, quotes);
    if (!quote) {
      return { ok: false, reason: `no paper quote for ${symbol}` };
    }
    const raw = side === "buy" ? quote.bid : quote.ask;
    return {
      ok: true,
      fill: { price: raw, slippagePips: 0, at: Date.now() },
    };
  }
}

export const paperAdapter = new PaperAdapter();

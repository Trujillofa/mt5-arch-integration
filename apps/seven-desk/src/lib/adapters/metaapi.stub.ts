/**
 * Future MetaAPI / MT5 adapter — not wired in this slice.
 *
 * A live adapter would:
 * - take a MetaAPI token + account id from env (never required for paper mode)
 * - stream deals from the MT5 terminal
 * - place market / SL / TP orders on the connected account
 *
 * This file is a stub so the AccountAdapter boundary stays obvious.
 * Do not import it from UI code. PaperAdapter is the only live path.
 *
 * If a token is missing later, keep falling back to PaperAdapter.
 */
import type { AccountAdapter, AdapterResult } from "@/lib/adapters/types";

export class MetaApiAdapterStub implements AccountAdapter {
  readonly kind = "live-stub" as const;

  getQuote(): null {
    return null;
  }

  placeMarket(): AdapterResult {
    return {
      ok: false,
      reason: "MetaAPI/MT5 adapter is not wired. Use the paper adapter.",
    };
  }

  closeMarket(): AdapterResult {
    return {
      ok: false,
      reason: "MetaAPI/MT5 adapter is not wired. Use the paper adapter.",
    };
  }
}

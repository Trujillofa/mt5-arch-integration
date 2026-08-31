/**
 * Read-only WSF live adapter.
 * Trading still goes through PaperAdapter. This type exists so the
 * AccountAdapter boundary has a real WSF client next to the MetaAPI stub.
 */
import type { AccountAdapter, AdapterResult } from "@/lib/adapters/types";

export class WsfLiveAdapter implements AccountAdapter {
  readonly kind = "live-stub" as const;

  getQuote(): null {
    return null;
  }

  placeMarket(): AdapterResult {
    return {
      ok: false,
      reason:
        "WSF live path is read-only (connect / account probe). Use the paper adapter to place desk trades.",
    };
  }

  closeMarket(): AdapterResult {
    return {
      ok: false,
      reason:
        "WSF live path is read-only (connect / account probe). Use the paper adapter to flatten paper positions.",
    };
  }
}

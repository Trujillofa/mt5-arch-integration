/**
 * Read-only WSF adapter for the copy engine.
 * Live OrderSend is not here — it is POST /api/wsf/order (WSF 149736 only).
 * Desk copy fills still go through PaperAdapter.
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

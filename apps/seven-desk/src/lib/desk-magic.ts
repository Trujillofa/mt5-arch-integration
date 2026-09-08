/** Client-safe desk OrderSend magic numbers. Do not import env modules here. */

import type { LiveBroker } from "@/lib/live-order/types";

export const DESK_MAGIC: Record<LiveBroker, number> = {
  wsf: 20263847,
  ftmo: 20263848,
  fundednext: 20263849,
  alphacapital: 20263850,
  fundingpips: 20263851,
  neomaa: 20263852,
  fortraders: 20263853,
};

export function deskMagicFor(broker: LiveBroker): number {
  return DESK_MAGIC[broker];
}

/** True when magic matches this book's live OrderSend. Snapshot ingest still
 *  treats unknown tickets as leftovers — flatten is this-session desk rows only. */
export function isDeskMagic(broker: LiveBroker, magic: number | null | undefined): boolean {
  if (magic == null || !Number.isFinite(magic) || magic === 0) return false;
  return magic === DESK_MAGIC[broker];
}

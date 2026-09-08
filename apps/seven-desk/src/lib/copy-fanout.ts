import {
  FUNDEDNEXT_SCALE,
  FUNDINGPIPS_SCALE,
  planLiveLots,
} from "@/lib/firms";
import type { LiveBroker } from "@/lib/live-order/types";
import type { DeskState } from "@/lib/types";

/** Alpha is fetch-only / ACG. Never fan-out even if the card is armed. */
export const COPY_FANOUT_SKIP = new Set<LiveBroker>(["alphacapital"]);

const MIN_NO_CONFIRM = 0.01;

export function needsSizeConfirm(lots: number): boolean {
  return Number.isFinite(lots) && lots > MIN_NO_CONFIRM + 1e-8;
}

export function armedCopyBrokers(state: DeskState): LiveBroker[] {
  const out: LiveBroker[] = [];
  if (state.wsfLiveCopy) out.push("wsf");
  if (state.fundednextLiveCopy) out.push("fundednext");
  if (state.fundingpipsLiveCopy) out.push("fundingpips");
  if (state.neomaaLiveCopy) out.push("neomaa");
  if (state.fortradersLiveCopy) out.push("fortraders");
  return out.filter((broker) => !COPY_FANOUT_SKIP.has(broker));
}

export function masterLotsForGroup(state: DeskState, groupId: string): number | null {
  const master = state.blotter.find((row) => row.groupId === groupId && row.role === "master");
  return master && Number.isFinite(master.lots) ? master.lots : null;
}

export function sizeConfirmLines(
  ticketLots: number,
  armed: LiveBroker[],
  includeMaster: boolean
): { id: string; name: string; lots: number; roundedUp: boolean }[] {
  const rows: { id: string; name: string; lots: number; roundedUp: boolean }[] = [];
  if (includeMaster) {
    const plan = planLiveLots("ftmo", ticketLots);
    rows.push({
      id: "ftmo",
      name: "FTMO master",
      lots: plan.lots,
      roundedUp: plan.roundedUp,
    });
  }
  const names: Record<LiveBroker, string> = {
    wsf: "WSF",
    fundednext: `FN ×${FUNDEDNEXT_SCALE}`,
    fundingpips: `FundingPips ×${FUNDINGPIPS_SCALE}`,
    neomaa: "Neomaa",
    fortraders: "Fortraders",
    ftmo: "FTMO",
    alphacapital: "Alpha",
  };
  for (const broker of armed) {
    if (COPY_FANOUT_SKIP.has(broker)) continue;
    const plan = planLiveLots(broker, ticketLots);
    rows.push({
      id: broker,
      name: names[broker],
      lots: plan.lots,
      roundedUp: plan.roundedUp,
    });
  }
  return rows;
}

export function worstLegMs(latencies: number[]): number | null {
  const finite = latencies.filter((ms) => Number.isFinite(ms) && ms >= 0);
  if (finite.length === 0) return null;
  return Math.max(...finite);
}

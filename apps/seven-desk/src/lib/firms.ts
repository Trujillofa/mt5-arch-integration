import type { FirmId, FirmProfile } from "@/lib/types";

/** Master / ticket standard. Change this; FN/FP lots follow their scales. */
export const STANDARD_LOT = 4;
/** Alias kept for seed/storage paper multipliers (scale = firm default / standard). */
export const DEFAULT_DESK_LOTS = STANDARD_LOT;
export const FUNDEDNEXT_SCALE = 0.1;
export const FUNDINGPIPS_SCALE = 0.2;
/** Broker volume step and min. Prove / volume_min is this size, unscaled. */
export const LOT_STEP = 0.01;

export function firmLotScale(firmId: FirmId | string): number {
  if (firmId === "fundednext") return FUNDEDNEXT_SCALE;
  if (firmId === "fundingpips") return FUNDINGPIPS_SCALE;
  return 1;
}

export function isMinLotProve(lots: number | null | undefined): boolean {
  return lots != null && Number.isFinite(lots) && Math.abs(lots - LOT_STEP) <= 1e-8;
}

export function roundToBrokerStep(lots: number): number {
  return Math.round(lots / LOT_STEP) * LOT_STEP;
}

export function scaleLiveLots(
  masterLots: number,
  scale: number
): { lots: number; roundedUp: boolean } {
  const raw = masterLots * scale;
  const stepped = Math.round(roundToBrokerStep(raw) * 100) / 100;
  if (stepped + 1e-8 < LOT_STEP) {
    return { lots: LOT_STEP, roundedUp: true };
  }
  return { lots: stepped, roundedUp: false };
}

export function defaultLotsForFirm(
  firmId: FirmId | string,
  standard: number = STANDARD_LOT
): number {
  return scaleLiveLots(standard, firmLotScale(firmId)).lots;
}

export type LiveLotPlan = {
  lots: number;
  roundedUp: boolean;
  prove: boolean;
  scale: number;
};

/** Empty / omitted master volume uses the standard lot, then scale. */
export function planLiveLots(
  firmId: FirmId | string,
  masterLots?: number | null,
  standard: number = STANDARD_LOT
): LiveLotPlan {
  const scale = firmLotScale(firmId);
  if (masterLots == null || !Number.isFinite(masterLots) || masterLots <= 0) {
    const planned = scaleLiveLots(standard, scale);
    return { ...planned, prove: false, scale };
  }
  if (isMinLotProve(masterLots)) {
    return { lots: LOT_STEP, roundedUp: false, prove: true, scale };
  }
  const planned = scaleLiveLots(masterLots, scale);
  return { ...planned, prove: false, scale };
}

/** Live slave size: master × firm scale, except an explicit 0.01 prove. */
export function liveLotsForFirm(
  firmId: FirmId | string,
  masterLots?: number | null,
  standard: number = STANDARD_LOT
): number {
  return planLiveLots(firmId, masterLots, standard).lots;
}

export const FIRMS: FirmProfile[] = [
  {
    id: "wsf",
    name: "WSF",
    legalName: "Wall Street Funded",
    platforms: ["MT5", "cTrader", "Match-Trader"],
    typicalServer: "WSFmarkets-Server",
    notes:
      "MT5 149736 @ WSFmarkets-Server. Fetch is read-only. Arm WSF live copy to send the WSF slave of each master fill at ticket × 1.0 (standard lot). Scratch remains a separate control. Not Vantage/FP/MCP.",
  },
  {
    id: "fundednext",
    name: "FundedNext",
    legalName: "FundedNext",
    platforms: ["MT4", "MT5", "cTrader", "Match-Trader"],
    typicalServer: "FundedNext-Server 2",
    notes:
      "Operator book is MT5 13981906 @ FundedNext-Server 2 (Stellar 2-Step P1 100K). Fetch is read-only. Arm FundedNext live copy to send the FN slave at ticket × 0.1. Not Vantage/FP/MCP.",
  },
  {
    id: "neomaa",
    name: "Neomaa",
    legalName: "NEOMAAA Funded",
    platforms: ["MT5", "TradeLocker"],
    typicalServer: "Neomaaa-global",
    notes:
      "Operator book is MT5 7745107 @ Neomaaa-global. Fetch is read-only. Arm Neomaa live copy to send the Neomaa slave at ticket × 1.0. Not Vantage/FP/MCP.",
  },
  {
    id: "fortraders",
    name: "Fortraders",
    legalName: "For Traders",
    platforms: ["MT5", "TradeLocker", "cTrader"],
    typicalServer: "FTTrading-Server",
    notes:
      "Operator book is MT5 737150 @ FTTrading-Server (this challenge is MT5, not TradeLocker). Fetch is read-only. Arm Fortraders live copy to send the Fortraders slave at ticket × 1.0. Not FTMO/FP Markets/FundingPips/MCP.",
  },
  {
    id: "fundingpips",
    name: "FundingPips",
    legalName: "Funding Pips",
    platforms: ["MT5", "cTrader", "Match-Trader"],
    typicalServer: "FundingPips2-SIM",
    notes:
      "Operator book is MT5 11669306 @ FundingPips2-SIM. Fetch is read-only. Arm FundingPips live copy to send the FundingPips slave at ticket × 0.2. Not Vantage/FP Markets/MCP.",
  },
  {
    id: "ftmo",
    name: "FTMO",
    legalName: "FTMO",
    platforms: ["MT4", "MT5", "cTrader", "DXtrade"],
    typicalServer: "FTMO-Server4",
    notes:
      "Operator book is MT5 541163357 @ FTMO-Server4. Fetch is read-only. Arm FTMO live master to send Place master trade at the ticket lots (standard lot); slaves copy the same type at their scale. Not Vantage/FP/MCP.",
  },
  {
    id: "alphacapital",
    name: "Alpha Capital",
    legalName: "Alpha Capital Group",
    platforms: ["MT5", "cTrader", "DXtrade", "TradeLocker"],
    typicalServer: "ACGMarkets-Main",
    notes:
      "Operator book is MT5 2765247 @ ACGMarkets-Main. Fetch is read-only. Alpha stays fetch-only — no copy POST. If it ever sent, size would be ticket × 1.0. Not Vantage/FP/MCP.",
  },
];

export const FIRM_BY_ID: Record<FirmId, FirmProfile> = Object.fromEntries(
  FIRMS.map((firm) => [firm.id, firm])
) as Record<FirmId, FirmProfile>;

export const FIRM_ACCENT: Record<FirmId, string> = {
  wsf: "bg-amber-500",
  fundednext: "bg-sky-500",
  neomaa: "bg-violet-500",
  fortraders: "bg-orange-500",
  fundingpips: "bg-teal-500",
  ftmo: "bg-blue-500",
  alphacapital: "bg-emerald-500",
};

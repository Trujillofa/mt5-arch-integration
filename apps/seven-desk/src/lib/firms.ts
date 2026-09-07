import type { FirmId, FirmProfile } from "@/lib/types";

/** Desk default size. “one 4” means 1.4, not 1 or 4. */
export const DEFAULT_DESK_LOTS = 1.4;
export const FUNDEDNEXT_DEFAULT_LOTS = 0.35;
export const FUNDINGPIPS_DEFAULT_LOTS = 0.8;

export function defaultLotsForFirm(firmId: FirmId | string): number {
  if (firmId === "fundednext") return FUNDEDNEXT_DEFAULT_LOTS;
  if (firmId === "fundingpips") return FUNDINGPIPS_DEFAULT_LOTS;
  return DEFAULT_DESK_LOTS;
}

/** Live slave size: firm table, unless the ticket is an explicit smaller override (e.g. 0.01 test). */
export function liveLotsForFirm(firmId: FirmId | string, masterLots?: number | null): number {
  const def = defaultLotsForFirm(firmId);
  if (masterLots != null && Number.isFinite(masterLots) && masterLots + 1e-8 < def) {
    return masterLots;
  }
  return def;
}

export const FIRMS: FirmProfile[] = [
  {
    id: "wsf",
    name: "WSF",
    legalName: "Wall Street Funded",
    platforms: ["MT5", "cTrader", "Match-Trader"],
    typicalServer: "WSFmarkets-Server",
    notes:
      "MT5 149736 @ WSFmarkets-Server. Fetch is read-only. Arm WSF live copy to send the WSF slave of each master fill as a 1.4-lot order of the same type (market / limit / stop). Scratch remains a separate control. Not Vantage/FP/MCP.",
  },
  {
    id: "fundednext",
    name: "FundedNext",
    legalName: "FundedNext",
    platforms: ["MT4", "MT5", "cTrader", "Match-Trader"],
    typicalServer: "FundedNext-Server 2",
    notes:
      "Operator book is MT5 13981906 @ FundedNext-Server 2 (Stellar 2-Step P1 100K). Fetch is read-only. Arm FundedNext live copy to send the FN slave of each master fill as a 0.35-lot order of the same type (market / limit / stop). Not Vantage/FP/MCP.",
  },
  {
    id: "neomaa",
    name: "Neomaa",
    legalName: "NEOMAAA Funded",
    platforms: ["MT5", "TradeLocker"],
    typicalServer: "Neomaaa-global",
    notes:
      "Operator book is MT5 7745107 @ Neomaaa-global. Fetch is read-only. Arm Neomaa live copy to send the Neomaa slave of each master fill as a 1.4-lot order of the same type (market / limit / stop). Not Vantage/FP/MCP.",
  },
  {
    id: "fortraders",
    name: "Fortraders",
    legalName: "For Traders",
    platforms: ["MT5", "TradeLocker", "cTrader"],
    typicalServer: "FTTrading-Server",
    notes:
      "Operator book is MT5 737150 @ FTTrading-Server (this challenge is MT5, not TradeLocker). Fetch is read-only. Arm Fortraders live copy to send the Fortraders slave of each master fill as a 1.4-lot order of the same type (market / limit / stop). Not FTMO/FP Markets/FundingPips/MCP.",
  },
  {
    id: "fundingpips",
    name: "FundingPips",
    legalName: "Funding Pips",
    platforms: ["MT5", "cTrader", "Match-Trader"],
    typicalServer: "FundingPips2-SIM",
    notes:
      "Operator book is MT5 11669306 @ FundingPips2-SIM. Fetch is read-only. Arm FundingPips live copy to send the FundingPips slave of each master fill as a 0.8-lot order of the same type (market / limit / stop). Not Vantage/FP Markets/MCP.",
  },
  {
    id: "ftmo",
    name: "FTMO",
    legalName: "FTMO",
    platforms: ["MT4", "MT5", "cTrader", "DXtrade"],
    typicalServer: "FTMO-Server4",
    notes:
      "Operator book is MT5 541163357 @ FTMO-Server4. Fetch is read-only. Arm FTMO live master to send Place master trade as a 1.4-lot order of the ticket type (market / limit / stop); slaves copy the same type. Not Vantage/FP/MCP.",
  },
  {
    id: "alphacapital",
    name: "Alpha Capital",
    legalName: "Alpha Capital Group",
    platforms: ["MT5", "cTrader", "DXtrade", "TradeLocker"],
    typicalServer: "ACGMarkets-Main",
    notes:
      "Operator book is MT5 2765247 @ ACGMarkets-Main. Fetch is read-only. Arm Alpha Capital live copy to send the Alpha slave of each master fill as a 1.4-lot order of the same type (market / limit / stop). Not Vantage/FP/MCP.",
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

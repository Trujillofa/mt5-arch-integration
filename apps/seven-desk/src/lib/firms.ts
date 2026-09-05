import type { FirmId, FirmProfile } from "@/lib/types";

export const FIRMS: FirmProfile[] = [
  {
    id: "wsf",
    name: "WSF",
    legalName: "Wall Street Funded",
    platforms: ["MT5", "cTrader", "Match-Trader"],
    typicalServer: "WSFmarkets-Server",
    notes:
      "MT5 149736 @ WSFmarkets-Server. Fetch is read-only. Arm WSF live copy to send the WSF slave of each master fill as a min-lot OrderSend. Scratch remains a separate control. Not Vantage/FP/MCP.",
  },
  {
    id: "fundednext",
    name: "FundedNext",
    legalName: "FundedNext",
    platforms: ["MT4", "MT5", "cTrader", "Match-Trader"],
    typicalServer: "FundedNext-Server 2",
    notes:
      "Operator book is MT5 13981906 @ FundedNext-Server 2 (Stellar 2-Step P1 100K). Fetch is read-only. Arm FundedNext live copy to send the FN slave of each master fill as a min-lot OrderSend. Not Vantage/FP/MCP.",
  },
  {
    id: "neomaa",
    name: "Neomaa",
    legalName: "NEOMAAA Funded",
    platforms: ["MT5", "TradeLocker"],
    typicalServer: "Neomaaa-Live",
    notes:
      "Operator book is MT5 7745107 @ Neomaaa-Live. Fetch is read-only. Arm Neomaa live copy to send the Neomaa slave of each master fill as a min-lot OrderSend. Not Vantage/FP/MCP.",
  },
  {
    id: "fortraders",
    name: "Fortraders",
    legalName: "For Traders",
    platforms: ["MT5", "TradeLocker", "cTrader"],
    typicalServer: "FTTrading-Server",
    notes:
      "Operator book is MT5 737150 @ FTTrading-Server (this challenge is MT5, not TradeLocker). Fetch is read-only. Arm Fortraders live copy to send the Fortraders slave of each master fill as a min-lot OrderSend. Not FTMO/FP Markets/FundingPips/MCP.",
  },
  {
    id: "fundingpips",
    name: "FundingPips",
    legalName: "Funding Pips",
    platforms: ["MT5", "cTrader", "Match-Trader"],
    typicalServer: "FundingPips2-SIM",
    notes:
      "Operator book is MT5 11669306 @ FundingPips2-SIM. Fetch is read-only. Arm FundingPips live copy to send the FundingPips slave of each master fill as a min-lot OrderSend. Not Vantage/FP Markets/MCP.",
  },
  {
    id: "ftmo",
    name: "FTMO",
    legalName: "FTMO",
    platforms: ["MT4", "MT5", "cTrader", "DXtrade"],
    typicalServer: "FTMO-Server4",
    notes:
      "Operator book is MT5 541163357 @ FTMO-Server4. Fetch is read-only. Arm FTMO live master to send Place master trade as a min-lot OrderSend first; slaves copy only after that fill. Not Vantage/FP/MCP.",
  },
  {
    id: "alphacapital",
    name: "Alpha Capital",
    legalName: "Alpha Capital Group",
    platforms: ["MT5", "cTrader", "DXtrade", "TradeLocker"],
    typicalServer: "ACGMarkets",
    notes:
      "Operator book is MT5 2765247 @ ACGMarkets. Fetch is read-only. Arm Alpha Capital live copy to send the Alpha slave of each master fill as a min-lot OrderSend. Not Vantage/FP/MCP.",
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

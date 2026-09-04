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
    typicalServer: "NEOMAAA-Live",
    notes:
      "Typically MT5 via NEOMAAA Ltd. TradeLocker is also offered on some funded programmes.",
  },
  {
    id: "fortraders",
    name: "Fortraders",
    legalName: "For Traders",
    platforms: ["MT5", "TradeLocker", "cTrader"],
    typicalServer: "ForTraders-Server",
    notes: "Typically MT5, TradeLocker, or cTrader depending on the challenge you bought.",
  },
  {
    id: "fundingpips",
    name: "FundingPips",
    legalName: "Funding Pips",
    platforms: ["MT5", "cTrader", "Match-Trader"],
    typicalServer: "FundingPips-Server",
    notes:
      "Typically Match-Trader or cTrader. MT5 still appears on some programmes (e.g. later Prime stages).",
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
      "MT5 commonly connects to the ACGMarkets server. Other platforms vary by programme and region.",
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

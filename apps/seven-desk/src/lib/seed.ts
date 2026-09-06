import { FIRM_BY_ID } from "@/lib/firms";
import { SEED_QUOTES } from "@/lib/quotes";
import type { CopySettings, DeskState, TradingAccount } from "@/lib/types";

export const ACCOUNT_IDS = {
  wsf: "acct_wsf",
  fundednext: "acct_fundednext",
  neomaa: "acct_neomaa",
  fortraders: "acct_fortraders",
  fundingpips: "acct_fundingpips",
  ftmo: "acct_ftmo",
  alphacapital: "acct_alphacapital",
} as const;

export const MASTER_ID = ACCOUNT_IDS.ftmo;

function account(
  id: string,
  firmId: keyof typeof ACCOUNT_IDS,
  login: string,
  platform: string,
  server: string,
  balance: number,
  status: TradingAccount["status"] = "connected",
  statusReason?: string
): TradingAccount {
  const firm = FIRM_BY_ID[firmId];
  return {
    id,
    firmId,
    label: `${firm.name} ${compact(balance)}`,
    login,
    server,
    platform,
    currency: "USD",
    balance,
    equity: balance,
    status,
    statusReason,
  };
}

function compact(balance: number): string {
  return `$${(balance / 1000).toFixed(0)}k`;
}

export function seedAccounts(): TradingAccount[] {
  return [
    account(ACCOUNT_IDS.ftmo, "ftmo", "541163357", "MT5", "FTMO-Server4", 100_000),
    account(ACCOUNT_IDS.wsf, "wsf", "149736", "MT5", "WSFmarkets-Server", 50_000),
    account(
      ACCOUNT_IDS.fundednext,
      "fundednext",
      "13981906",
      "MT5",
      "FundedNext-Server 2",
      100_000
    ),
    account(ACCOUNT_IDS.neomaa, "neomaa", "7745107", "MT5", "Neomaaa-Live", 25_000),
    account(
      ACCOUNT_IDS.fortraders,
      "fortraders",
      "737150",
      "MT5",
      "FTTrading-Server",
      50_000
    ),
    account(
      ACCOUNT_IDS.fundingpips,
      "fundingpips",
      "11669306",
      "MT5",
      "FundingPips2-SIM",
      100_000
    ),
    account(
      ACCOUNT_IDS.alphacapital,
      "alphacapital",
      "2765247",
      "MT5",
      "ACGMarkets-Main",
      100_000
    ),
  ];
}

export function seedCopySettings(): CopySettings[] {
  return [
    {
      slaveAccountId: ACCOUNT_IDS.wsf,
      enabled: true,
      lotMultiplier: 0.5,
      maxLot: 2,
      maxSlippagePips: 2,
      copySlTp: true,
      reverse: false,
      symbolMap: { EURUSD: "EURUSDc" },
    },
    {
      slaveAccountId: ACCOUNT_IDS.fundednext,
      enabled: true,
      lotMultiplier: 1,
      maxLot: 2,
      maxSlippagePips: 2,
      copySlTp: true,
      reverse: false,
      symbolMap: {},
    },
    {
      slaveAccountId: ACCOUNT_IDS.neomaa,
      enabled: true,
      lotMultiplier: 0.4,
      maxLot: 1,
      maxSlippagePips: 2,
      copySlTp: true,
      reverse: false,
      symbolMap: { XAUUSD: "GOLD" },
    },
    {
      slaveAccountId: ACCOUNT_IDS.fortraders,
      enabled: true,
      lotMultiplier: 0.5,
      maxLot: 1,
      maxSlippagePips: 2,
      copySlTp: true,
      reverse: false,
      symbolMap: {},
    },
    {
      slaveAccountId: ACCOUNT_IDS.fundingpips,
      enabled: true,
      lotMultiplier: 0.8,
      maxLot: 1,
      maxSlippagePips: 2,
      copySlTp: true,
      reverse: false,
      symbolMap: { NAS100: "" },
    },
    {
      slaveAccountId: ACCOUNT_IDS.alphacapital,
      enabled: true,
      lotMultiplier: 0.5,
      maxLot: 1,
      maxSlippagePips: 2,
      copySlTp: true,
      reverse: false,
      symbolMap: {},
    },
  ];
}

export function seedDesk(): DeskState {
  const accounts = seedAccounts();
  return {
    accounts,
    copySettings: seedCopySettings(),
    masterId: MASTER_ID,
    blotter: [],
    positions: [],
    quotes: SEED_QUOTES.map((quote) => ({ ...quote })),
    selectedAccountId: ACCOUNT_IDS.wsf,
    wsfLiveCopy: false,
    ftmoLiveMaster: false,
    fundednextLiveCopy: false,
    alphacapitalLiveCopy: false,
    fundingpipsLiveCopy: false,
    neomaaLiveCopy: false,
    fortradersLiveCopy: false,
  };
}

/** Client-safe identity. Do not import `@/lib/fundingpips/env` from the browser. */
export const FUNDINGPIPS_EXPECTED_LOGIN = "11669306";
export const FUNDINGPIPS_EXPECTED_SERVER = "FundingPips2-SIM";
export const FUNDINGPIPS_SERVER_NEEDLE = "FundingPips";
export const FUNDINGPIPS_LIVE_CONFIRM = "FUNDINGPIPS-11669306";
export const FUNDINGPIPS_LIVE_PENDING = "fundingpips-live-pending";
export const FUNDINGPIPS_LIVE_SYMBOLS = ["EURUSD"] as const;

export type FundingPipsConnectionStatus =
  | "connected"
  | "disconnected"
  | "missing_wine"
  | "auth_failed"
  | "password_missing"
  | "no_credentials"
  | "wrong_account";

export interface FundingPipsLiveReport {
  source: "operator-env";
  fetchedAt: string;
  usedOperatorEnv: boolean;
  ordersPlaced: false;
  winePrefixPresent: boolean;
  fileBridgePresent: boolean;
  connectionStatus: FundingPipsConnectionStatus;
  login: string | null;
  server: string | null;
  platform: "MT5";
  balance: number | null;
  equity: number | null;
  currency: string | null;
  leverage: string | null;
  name: string | null;
  terminalConnected: boolean | null;
  hasPassword: boolean;
  bookHonesty: string;
  fetchNotes: string[];
  nextSecretNeeded: string | null;
}

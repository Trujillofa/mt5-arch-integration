/** Client-safe identity. Do not import `@/lib/fundednext/env` from the browser. */
export const FUNDEDNEXT_EXPECTED_LOGIN = "13981906";
export const FUNDEDNEXT_EXPECTED_SERVER = "FundedNext-Server 2";
export const FUNDEDNEXT_SERVER_NEEDLE = "FundedNext";

export type FundedNextConnectionStatus =
  | "connected"
  | "missing_wine"
  | "auth_failed"
  | "password_missing"
  | "no_credentials"
  | "wrong_account";

export interface FundedNextLiveReport {
  source: "operator-env";
  fetchedAt: string;
  usedOperatorEnv: boolean;
  ordersPlaced: false;
  winePrefixPresent: boolean;
  fileBridgePresent: boolean;
  connectionStatus: FundedNextConnectionStatus;
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

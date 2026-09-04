/** Client-safe identity. Do not import `@/lib/alphacapital/env` from the browser. */
export const ALPHACAPITAL_EXPECTED_LOGIN = "2765247";
export const ALPHACAPITAL_EXPECTED_SERVER = "ACGMarkets";
export const ALPHACAPITAL_SERVER_NEEDLE = "ACG";
export const ALPHACAPITAL_LIVE_CONFIRM = "ACG-2765247";
export const ALPHACAPITAL_LIVE_PENDING = "alphacapital-live-pending";
export const ALPHACAPITAL_LIVE_SYMBOLS = ["EURUSD", "BTCUSD", "BTCUSDc", "BTCUSD.r"] as const;

export type AlphaCapitalConnectionStatus =
  | "connected"
  | "missing_wine"
  | "auth_failed"
  | "password_missing"
  | "no_credentials"
  | "wrong_account";

export interface AlphaCapitalLiveReport {
  source: "operator-env";
  fetchedAt: string;
  usedOperatorEnv: boolean;
  ordersPlaced: false;
  winePrefixPresent: boolean;
  fileBridgePresent: boolean;
  connectionStatus: AlphaCapitalConnectionStatus;
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

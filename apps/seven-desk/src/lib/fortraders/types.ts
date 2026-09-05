/** Client-safe identity. Do not import `@/lib/fortraders/env` from the browser. */
export const FORTRADERS_EXPECTED_LOGIN = "737150";
export const FORTRADERS_EXPECTED_SERVER = "FTTrading-Server";
export const FORTRADERS_SERVER_NEEDLE = "FTTrading";
export const FORTRADERS_LIVE_CONFIRM = "FORTRADERS-737150";
export const FORTRADERS_LIVE_PENDING = "fortraders-live-pending";
export const FORTRADERS_LIVE_SYMBOLS = ["EURUSD"] as const;

export type FortradersConnectionStatus =
  | "connected"
  | "disconnected"
  | "missing_wine"
  | "auth_failed"
  | "password_missing"
  | "no_credentials"
  | "wrong_account";

export interface FortradersLiveReport {
  source: "operator-env";
  fetchedAt: string;
  usedOperatorEnv: boolean;
  ordersPlaced: false;
  winePrefixPresent: boolean;
  fileBridgePresent: boolean;
  connectionStatus: FortradersConnectionStatus;
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

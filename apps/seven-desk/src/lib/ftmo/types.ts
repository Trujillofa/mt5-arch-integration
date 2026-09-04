/** Client-safe identity. Do not import `@/lib/ftmo/env` from the browser. */
export const FTMO_EXPECTED_LOGIN = "541163357";
export const FTMO_EXPECTED_SERVER = "FTMO-Server4";
export const FTMO_SERVER_NEEDLE = "FTMO";

export type FtmoConnectionStatus =
  | "connected"
  | "missing_wine"
  | "auth_failed"
  | "password_missing"
  | "no_credentials"
  | "wrong_account";

export interface FtmoLiveReport {
  source: "operator-env";
  fetchedAt: string;
  usedOperatorEnv: boolean;
  ordersPlaced: false;
  winePrefixPresent: boolean;
  fileBridgePresent: boolean;
  connectionStatus: FtmoConnectionStatus;
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

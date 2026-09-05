/** Client-safe identity. Do not import `@/lib/neomaa/env` from the browser. */
export const NEOMAA_EXPECTED_LOGIN = "7745107";
export const NEOMAA_EXPECTED_SERVER = "Neomaaa-Live";
export const NEOMAA_SERVER_NEEDLE = "Neomaaa";
export const NEOMAA_LIVE_CONFIRM = "NEOMAA-7745107";
export const NEOMAA_LIVE_PENDING = "neomaa-live-pending";
export const NEOMAA_LIVE_SYMBOLS = ["EURUSD"] as const;

export type NeomaaConnectionStatus =
  | "connected"
  | "disconnected"
  | "missing_wine"
  | "auth_failed"
  | "password_missing"
  | "no_credentials"
  | "wrong_account";

export interface NeomaaLiveReport {
  source: "operator-env";
  fetchedAt: string;
  usedOperatorEnv: boolean;
  ordersPlaced: false;
  winePrefixPresent: boolean;
  fileBridgePresent: boolean;
  connectionStatus: NeomaaConnectionStatus;
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

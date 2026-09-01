export interface WsfPlatformProbe {
  platform: "mt5" | "ctrader" | "match-trader";
  endpoint: string;
  httpStatus: number | null;
  reachable: boolean;
  authenticated: boolean | null;
  detail: string;
  publicLogin?: string;
  publicServer?: string;
}

export interface WsfFetchedAccount {
  source: "ctrader-id" | "wsf-id-app" | "mt5-public-card" | "mt5-env";
  kind: "published-demo" | "wsf-plant" | "public-identifier" | "personal-env";
  broker: string;
  accountId: string;
  login: string;
  name: string;
  environment: "demo" | "live" | "unknown";
  accountType: string | null;
  balance: number | null;
  equity: number | null;
  currency: string | null;
  leverage: string | null;
  plantIsWsf: boolean;
}

export interface WsfPositionRow {
  accountLogin: string;
  symbol: string;
  side: string;
  volume: number | null;
  entry: number | null;
  pnl: number | null;
}

export interface WsfDealRow {
  accountLogin: string;
  symbol: string;
  side: string;
  volume: number | null;
  price: number | null;
  time: string | null;
}

export interface WsfIdentity {
  email: string | null;
  nickname: string | null;
  host: string;
  login: string | null;
  server: string | null;
  platform: string | null;
  hasPassword: boolean;
  credentialSource: "operator-env" | "homepage-demo" | "none";
}

export type WsfConnectionStatus =
  | "connected"
  | "missing_wine"
  | "auth_failed"
  | "password_missing"
  | "no_credentials";

export interface WsfLiveReport {
  source: string;
  fetchedAt: string;
  homepageOk: boolean;
  usedOfficialDemoCard: boolean;
  usedOperatorEnv: boolean;
  email: string | null;
  identity: WsfIdentity;
  portal: string;
  platforms: WsfPlatformProbe[];
  books: WsfFetchedAccount[];
  openPositions: WsfPositionRow[];
  recentDeals: WsfDealRow[];
  fetchNotes: string[];
  bookHonesty: string;
  ordersPlaced: false;
  nextSecretNeeded: string | null;
  winePrefixPresent: boolean;
  fileBridgePresent: boolean;
  connectionStatus: WsfConnectionStatus;
  login: string | null;
  server: string | null;
  balance: number | null;
  equity: number | null;
  currency: string | null;
}

export type WsfLiveOrderAction = "scratch" | "open" | "close";

export interface WsfLiveOrderResult {
  ok: boolean;
  source: "seven-desk";
  endpoint: string;
  requestId: string;
  stage: string;
  reason: string;
  login: number | null;
  server: string | null;
  company?: string;
  symbol?: string;
  volume?: number;
  side?: string;
  order?: number;
  position?: number;
  dealOpen?: number;
  dealClose?: number;
  openPrice?: number;
  closePrice?: number;
  profit?: number;
  holdMs?: number;
  balanceAfter?: number;
  closeRetcode?: number;
  winePrefix: string;
  journalOpen?: string;
  journalClose?: string;
  stoppedWsfPids?: number[];
  restoreNote?: string;
}

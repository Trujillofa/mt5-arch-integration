export type FirmId =
  | "wsf"
  | "fundednext"
  | "neomaa"
  | "fortraders"
  | "fundingpips"
  | "ftmo"
  | "alphacapital";

export type ConnectionStatus =
  | "connected"
  | "disconnected"
  | "connecting"
  | "error";

export type Side = "buy" | "sell";

export type CopyStatus = "queued" | "filled" | "skipped" | "error";

export type AccountRole = "master" | "slave";

export interface FirmProfile {
  id: FirmId;
  name: string;
  legalName: string;
  platforms: string[];
  typicalServer: string;
  notes: string;
}

export interface TradingAccount {
  id: string;
  firmId: FirmId;
  label: string;
  login: string;
  server: string;
  platform: string;
  currency: "USD";
  balance: number;
  equity: number;
  status: ConnectionStatus;
  statusReason?: string;
}

export interface CopySettings {
  slaveAccountId: string;
  enabled: boolean;
  lotMultiplier: number;
  maxLot: number;
  maxSlippagePips: number;
  copySlTp: boolean;
  reverse: boolean;
  /** Master symbol → slave symbol. Empty string means unmapped (skip). Missing key copies 1:1. */
  symbolMap: Record<string, string>;
}

export interface PaperQuote {
  symbol: string;
  bid: number;
  ask: number;
  pip: number;
}

export interface Position {
  id: string;
  accountId: string;
  symbol: string;
  side: Side;
  lots: number;
  entry: number;
  sl: number | null;
  tp: number | null;
  openedAt: number;
  mark: number;
  pnl: number;
  /** Set when the fill was a real OrderSend, not paper. */
  liveBroker?: "wsf" | "ftmo" | "fundednext" | "alphacapital";
  liveOrder?: number;
  /** Copy-group id so flatten can close sibling live books. */
  groupId?: string;
}

export interface BlotterEvent {
  id: string;
  groupId: string;
  accountId: string;
  role: AccountRole;
  symbol: string;
  side: Side;
  lots: number;
  requestedPrice: number;
  fillPrice?: number;
  sl: number | null;
  tp: number | null;
  status: CopyStatus;
  reason?: string;
  createdAt: number;
  updatedAt: number;
}

export interface MasterTradeInput {
  symbol: string;
  side: Side;
  lots: number;
  sl: number | null;
  tp: number | null;
}

export interface DeskState {
  accounts: TradingAccount[];
  copySettings: CopySettings[];
  masterId: string;
  blotter: BlotterEvent[];
  positions: Position[];
  quotes: PaperQuote[];
  selectedAccountId: string;
  /** Session flags. Not persisted. */
  wsfLiveCopy: boolean;
  ftmoLiveMaster: boolean;
  fundednextLiveCopy: boolean;
  alphacapitalLiveCopy: boolean;
}

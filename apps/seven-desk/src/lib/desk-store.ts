import {
  applyFollowFill,
  applyFollowMasterLevels,
  applyLiveFill,
  applyQuoteMarks,
  applyWsfLiveFill,
  closePosition,
  createFollowSession,
  defaultCopySettings,
  dropDeskPosition,
  markLiveCloseError,
  placeFollowMasterFill,
  placeLiveMasterFill,
  placeMasterTrade,
  recordHttpBlotter,
  resolveQueuedCopies,
  snapshotFollowBaseline,
  applyLiveModify,
  upsertSnapshotPendings,
  upsertSnapshotPositions,
  type FollowSession,
} from "@/lib/copy-engine";
import type { BridgeOpenPosition, BridgePendingOrder } from "@/lib/bridge-orders";
import type { LiveBroker, LiveOrderResult } from "@/lib/live-order/types";
import { seedDesk } from "@/lib/seed";
import { clearDesk, loadDesk, saveDesk } from "@/lib/storage";
import type {
  ConnectionStatus,
  CopySettings,
  DeskState,
  MasterTradeInput,
  TradingAccount,
} from "@/lib/types";

const SERVER_SEED = applyQuoteMarks(seedDesk());
let desk: DeskState = SERVER_SEED;
let persistError: string | null = null;
let hydrated = false;
let clientReleased = false;
const listeners = new Set<() => void>();

let followSession: FollowSession = createFollowSession();
const followSlaveCatchup = new Set<string>();
let lastFtmoPositions: BridgeOpenPosition[] = [];
let lastFtmoPendings: BridgePendingOrder[] = [];

function emit() {
  listeners.forEach((listener) => listener());
}

function persist(next: DeskState) {
  desk = next;
  clientReleased = true;
  if (typeof window !== "undefined") {
    try {
      saveDesk(next);
    } catch {
      persistError = "Could not persist the desk. Changes may vanish on refresh.";
    }
  }
  emit();
}

export function subscribeDesk(listener: () => void) {
  listeners.add(listener);
  if (typeof window !== "undefined" && !hydrated) {
    hydrated = true;
    queueMicrotask(() => {
      try {
        desk = applyQuoteMarks(loadDesk());
      } catch {
        desk = applyQuoteMarks(seedDesk());
        persistError =
          "Could not restore the desk from local storage. Loaded a fresh paper book.";
      }
      clientReleased = true;
      emit();
    });
  }
  return () => {
    listeners.delete(listener);
  };
}

export function getDeskSnapshot() {
  if (!clientReleased) return SERVER_SEED;
  return desk;
}

export function getServerDeskSnapshot() {
  return SERVER_SEED;
}

export function getPersistError() {
  return persistError;
}

export function patchDesk(updater: (current: DeskState) => DeskState) {
  persist(updater(desk));
}

export function selectAccount(id: string) {
  patchDesk((current) => ({ ...current, selectedAccountId: id }));
}

export function setMaster(id: string) {
  patchDesk((current) => ({
    ...current,
    masterId: id,
    selectedAccountId:
      current.selectedAccountId === id
        ? current.accounts.find((account) => account.id !== id)?.id ?? id
        : current.selectedAccountId,
  }));
}

export function updateAccount(id: string, accountPatch: Partial<TradingAccount>) {
  patchDesk((current) => ({
    ...current,
    accounts: current.accounts.map((account) =>
      account.id === id ? { ...account, ...accountPatch } : account
    ),
  }));
}

export function setConnection(
  id: string,
  status: ConnectionStatus,
  reason?: string
) {
  patchDesk((current) => ({
    ...current,
    accounts: current.accounts.map((account) =>
      account.id === id ? { ...account, status, statusReason: reason } : account
    ),
  }));
}

export function updateCopy(
  slaveAccountId: string,
  copyPatch: Partial<CopySettings>
) {
  patchDesk((current) => {
    const existing = current.copySettings.find(
      (row) => row.slaveAccountId === slaveAccountId
    );
    const nextRow = {
      ...(existing ?? defaultCopySettings(slaveAccountId)),
      ...copyPatch,
      slaveAccountId,
    };
    const copySettings = existing
      ? current.copySettings.map((row) =>
          row.slaveAccountId === slaveAccountId ? nextRow : row
        )
      : [...current.copySettings, nextRow];
    return { ...current, copySettings };
  });
}

export function setSymbolMap(
  slaveAccountId: string,
  masterSymbol: string,
  mapped: string
) {
  patchDesk((current) => {
    const existing = current.copySettings.find(
      (row) => row.slaveAccountId === slaveAccountId
    );
    const base = existing ?? defaultCopySettings(slaveAccountId);
    const nextRow = {
      ...base,
      symbolMap: { ...base.symbolMap, [masterSymbol]: mapped },
    };
    const copySettings = existing
      ? current.copySettings.map((row) =>
          row.slaveAccountId === slaveAccountId ? nextRow : row
        )
      : [...current.copySettings, nextRow];
    return { ...current, copySettings };
  });
}

export function placeTrade(input: MasterTradeInput): {
  error: string | null;
  groupId?: string;
} {
  const result = placeMasterTrade(desk, input);
  persist(result.state);
  return { error: result.error ?? null, groupId: result.groupId };
}

export function placeLiveMaster(
  input: MasterTradeInput,
  result: LiveOrderResult,
  broker: LiveBroker
): { error: string | null; groupId?: string } {
  const next = placeLiveMasterFill(desk, input, result, broker);
  persist(next.state);
  return { error: next.error ?? null, groupId: next.groupId };
}

export function resolveGroup(groupId: string) {
  persist(resolveQueuedCopies(desk, groupId));
}

export function setWsfLiveCopy(enabled: boolean) {
  patchDesk((current) => ({ ...current, wsfLiveCopy: enabled }));
}

export function setFtmoLiveMaster(enabled: boolean) {
  patchDesk((current) => ({ ...current, ftmoLiveMaster: enabled }));
}

export function rememberFtmoBridge(
  positions: BridgeOpenPosition[],
  pendings: BridgePendingOrder[]
) {
  lastFtmoPositions = positions;
  lastFtmoPendings = pendings;
}

export function getFollowSession(): FollowSession {
  return followSession;
}

export function setFollowSession(next: FollowSession) {
  followSession = next;
}

export function takeFollowSlaveCatchup(): string[] {
  const ids = [...followSlaveCatchup];
  followSlaveCatchup.clear();
  return ids;
}

export function markFollowSlaveCatchup(groupId: string) {
  followSlaveCatchup.add(groupId);
}

function baselineTicketsAtArm(current: DeskState): Set<number> {
  const tickets = snapshotFollowBaseline(lastFtmoPositions, lastFtmoPendings);
  for (const row of current.positions) {
    if (row.liveBroker === "ftmo" && row.liveOrder && row.liveOrder > 0) {
      tickets.add(row.liveOrder);
    }
  }
  return tickets;
}

export function clearFollowSession() {
  followSession = createFollowSession();
  followSlaveCatchup.clear();
}

export function setFtmoFollowTerminal(enabled: boolean) {
  patchDesk((current) => {
    if (enabled) {
      followSession = createFollowSession(baselineTicketsAtArm(current));
      followSlaveCatchup.clear();
    } else {
      followSession = createFollowSession();
      followSlaveCatchup.clear();
    }
    return { ...current, ftmoFollowTerminal: enabled };
  });
}

export function placeFollowMaster(
  input: Parameters<typeof placeFollowMasterFill>[1]
) {
  persist(placeFollowMasterFill(desk, input));
}

export function applyFollowTicketFill(
  input: Parameters<typeof applyFollowFill>[1]
) {
  persist(applyFollowFill(desk, input));
}

export function applyFollowLevels(groupId: string, sl: number | null, tp: number | null) {
  persist(applyFollowMasterLevels(desk, groupId, sl, tp));
}

export function dropLiveDeskRow(
  positionId: string,
  reason: string,
  httpAction: "close" | "cancel" = "close"
) {
  persist(dropDeskPosition(desk, positionId, reason, httpAction));
}

export function setFundednextLiveCopy(enabled: boolean) {
  patchDesk((current) => ({ ...current, fundednextLiveCopy: enabled }));
}

export function setAlphacapitalLiveCopy(enabled: boolean) {
  patchDesk((current) => ({ ...current, alphacapitalLiveCopy: enabled }));
}

export function setFundingpipsLiveCopy(enabled: boolean) {
  patchDesk((current) => ({ ...current, fundingpipsLiveCopy: enabled }));
}

export function setNeomaaLiveCopy(enabled: boolean) {
  patchDesk((current) => ({ ...current, neomaaLiveCopy: enabled }));
}

export function setFortradersLiveCopy(enabled: boolean) {
  patchDesk((current) => ({ ...current, fortradersLiveCopy: enabled }));
}

export function applyWsfLiveCopyResult(eventId: string, result: LiveOrderResult) {
  persist(applyWsfLiveFill(desk, eventId, result));
}

export function applyLiveCopyResult(
  eventId: string,
  result: LiveOrderResult,
  broker: LiveBroker
) {
  persist(applyLiveFill(desk, eventId, result, broker));
}

export function flattenPosition(positionId: string): string | null {
  const result = closePosition(desk, positionId);
  persist(result.state);
  return result.error ?? null;
}

export function markLiveCloseFailed(positionId: string, reason: string) {
  persist(markLiveCloseError(desk, positionId, reason));
}

export function recordLiveHttpBlotter(
  input: Parameters<typeof recordHttpBlotter>[1]
) {
  persist(recordHttpBlotter(desk, input));
}

export function ingestBridgePendings(
  accountId: string,
  broker: LiveBroker,
  orders: BridgePendingOrder[]
) {
  persist(upsertSnapshotPendings(desk, accountId, broker, orders));
}

export function ingestBridgePositions(
  accountId: string,
  broker: LiveBroker,
  positions: BridgeOpenPosition[]
) {
  persist(upsertSnapshotPositions(desk, accountId, broker, positions));
}

export function applyPositionModify(
  positionId: string,
  sl: number | null,
  tp: number | null
) {
  persist(applyLiveModify(desk, positionId, sl, tp));
}

export function resetDemo() {
  clearDesk();
  persistError = null;
  followSession = createFollowSession();
  followSlaveCatchup.clear();
  persist(applyQuoteMarks(seedDesk()));
}

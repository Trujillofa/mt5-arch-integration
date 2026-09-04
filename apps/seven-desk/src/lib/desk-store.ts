import {
  applyLiveFill,
  applyQuoteMarks,
  applyWsfLiveFill,
  closePosition,
  defaultCopySettings,
  placeLiveMasterFill,
  placeMasterTrade,
  resolveQueuedCopies,
} from "@/lib/copy-engine";
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
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function persist(next: DeskState) {
  desk = next;
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
      emit();
    });
  }
  return () => {
    listeners.delete(listener);
  };
}

export function getDeskSnapshot() {
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

export function setFundednextLiveCopy(enabled: boolean) {
  patchDesk((current) => ({ ...current, fundednextLiveCopy: enabled }));
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

export function resetDemo() {
  clearDesk();
  persistError = null;
  persist(applyQuoteMarks(seedDesk()));
}

import { seedDesk } from "@/lib/seed";
import type { DeskState } from "@/lib/types";

export const STORAGE_KEY = "sevendesk.v1";

type PersistShape = Pick<
  DeskState,
  | "accounts"
  | "copySettings"
  | "masterId"
  | "blotter"
  | "positions"
  | "quotes"
  | "selectedAccountId"
>;

export function loadDesk(): DeskState {
  if (typeof window === "undefined") return seedDesk();
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return seedDesk();
  const parsed = JSON.parse(raw) as Partial<PersistShape>;
  const fallback = seedDesk();
  if (!Array.isArray(parsed.accounts) || parsed.accounts.length === 0) {
    return fallback;
  }
  return {
    accounts: parsed.accounts,
    copySettings: parsed.copySettings ?? fallback.copySettings,
    masterId: parsed.masterId ?? fallback.masterId,
    blotter: parsed.blotter ?? [],
    positions: parsed.positions ?? [],
    quotes: parsed.quotes ?? fallback.quotes,
    selectedAccountId: parsed.selectedAccountId ?? fallback.selectedAccountId,
  };
}

export function saveDesk(state: DeskState): void {
  const payload: PersistShape = {
    accounts: state.accounts,
    copySettings: state.copySettings,
    masterId: state.masterId,
    blotter: state.blotter,
    positions: state.positions,
    quotes: state.quotes,
    selectedAccountId: state.selectedAccountId,
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

export function clearDesk(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

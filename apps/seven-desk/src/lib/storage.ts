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

function migrateOperatorLogins(state: DeskState): DeskState {
  return {
    ...state,
    accounts: state.accounts.map((account) => {
      if (account.firmId === "fundednext") {
        if (account.login === "13981906" && account.server === "FundedNext-Server 2") {
          return account;
        }
        return {
          ...account,
          login: "13981906",
          server: "FundedNext-Server 2",
          platform: "MT5",
        };
      }
      if (account.firmId === "wsf") {
        if (account.login === "4013" || account.login === "") {
          return {
            ...account,
            login: "149736",
            server: "WSFmarkets-Server",
            platform: "MT5",
          };
        }
      }
      if (account.firmId === "ftmo") {
        if (account.login === "541163357" && account.server === "FTMO-Server4") {
          return account;
        }
        if (account.login === "51022981" || account.server === "FTMO-Server") {
          return {
            ...account,
            login: "541163357",
            server: "FTMO-Server4",
            platform: "MT5",
          };
        }
      }
      return account;
    }),
  };
}

export function loadDesk(): DeskState {
  if (typeof window === "undefined") return seedDesk();
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return seedDesk();
  const parsed = JSON.parse(raw) as Partial<PersistShape>;
  const fallback = seedDesk();
  if (!Array.isArray(parsed.accounts) || parsed.accounts.length === 0) {
    return fallback;
  }
  return migrateOperatorLogins({
    accounts: parsed.accounts,
    copySettings: parsed.copySettings ?? fallback.copySettings,
    masterId: parsed.masterId ?? fallback.masterId,
    blotter: parsed.blotter ?? [],
    positions: parsed.positions ?? [],
    quotes: parsed.quotes ?? fallback.quotes,
    selectedAccountId: parsed.selectedAccountId ?? fallback.selectedAccountId,
    wsfLiveCopy: false,
    ftmoLiveMaster: false,
    fundednextLiveCopy: false,
  });
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

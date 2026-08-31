"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { applyQuoteMarks } from "@/lib/copy-engine";
import {
  flattenPosition,
  getDeskSnapshot,
  getPersistError,
  getServerDeskSnapshot,
  placeTrade as placeTradeStore,
  resetDemo as resetDemoStore,
  resolveGroup,
  selectAccount as selectAccountStore,
  setConnection as setConnectionStore,
  setMaster as setMasterStore,
  setSymbolMap as setSymbolMapStore,
  subscribeDesk,
  updateAccount as updateAccountStore,
  updateCopy as updateCopyStore,
  patchDesk,
} from "@/lib/desk-store";
import { nudgeQuotes } from "@/lib/quotes";
import type {
  ConnectionStatus,
  CopySettings,
  DeskState,
  MasterTradeInput,
  TradingAccount,
} from "@/lib/types";

type Hydration = "loading" | "ready" | "error";

interface DeskApi {
  hydration: Hydration;
  hydrateError: string | null;
  state: DeskState;
  busy: boolean;
  selectAccount: (id: string) => void;
  setMaster: (id: string) => void;
  updateAccount: (id: string, patch: Partial<TradingAccount>) => void;
  setConnection: (id: string, status: ConnectionStatus, reason?: string) => void;
  updateCopy: (slaveAccountId: string, patch: Partial<CopySettings>) => void;
  setSymbolMap: (slaveAccountId: string, masterSymbol: string, mapped: string) => void;
  placeTrade: (input: MasterTradeInput) => string | null;
  flatten: (positionId: string) => string | null;
  resetDemo: () => void;
}

const DeskContext = createContext<DeskApi | null>(null);

export function DeskProvider({ children }: { children: React.ReactNode }) {
  const state = useSyncExternalStore(
    subscribeDesk,
    getDeskSnapshot,
    getServerDeskSnapshot
  );
  const [busy, setBusy] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const tick = window.setInterval(() => {
      patchDesk((current) =>
        applyQuoteMarks({
          ...current,
          quotes: nudgeQuotes(current.quotes),
        })
      );
    }, 2200);
    return () => window.clearInterval(tick);
  }, []);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((id) => window.clearTimeout(id));
  }, []);

  const selectAccount = useCallback((id: string) => {
    selectAccountStore(id);
  }, []);

  const setMaster = useCallback((id: string) => {
    setMasterStore(id);
  }, []);

  const updateAccount = useCallback(
    (id: string, accountPatch: Partial<TradingAccount>) => {
      updateAccountStore(id, accountPatch);
    },
    []
  );

  const setConnection = useCallback(
    (id: string, status: ConnectionStatus, reason?: string) => {
      setConnectionStore(id, status, reason);
    },
    []
  );

  const updateCopy = useCallback(
    (slaveAccountId: string, copyPatch: Partial<CopySettings>) => {
      updateCopyStore(slaveAccountId, copyPatch);
    },
    []
  );

  const setSymbolMap = useCallback(
    (slaveAccountId: string, masterSymbol: string, mapped: string) => {
      setSymbolMapStore(slaveAccountId, masterSymbol, mapped);
    },
    []
  );

  const placeTrade = useCallback((input: MasterTradeInput) => {
    const result = placeTradeStore(input);
    if (result.groupId && !result.error) {
      setBusy(true);
      const handle = window.setTimeout(() => {
        resolveGroup(result.groupId!);
        setBusy(false);
      }, 160);
      timers.current.push(handle);
    }
    return result.error;
  }, []);

  const flatten = useCallback((positionId: string) => {
    return flattenPosition(positionId);
  }, []);

  const resetDemo = useCallback(() => {
    timers.current.forEach((id) => window.clearTimeout(id));
    timers.current = [];
    setBusy(false);
    resetDemoStore();
  }, []);

  const persistError = getPersistError();
  const api = useMemo<DeskApi>(
    () => ({
      hydration: persistError ? "error" : "ready",
      hydrateError: persistError,
      state,
      busy,
      selectAccount,
      setMaster,
      updateAccount,
      setConnection,
      updateCopy,
      setSymbolMap,
      placeTrade,
      flatten,
      resetDemo,
    }),
    [
      persistError,
      state,
      busy,
      selectAccount,
      setMaster,
      updateAccount,
      setConnection,
      updateCopy,
      setSymbolMap,
      placeTrade,
      flatten,
      resetDemo,
    ]
  );

  return <DeskContext.Provider value={api}>{children}</DeskContext.Provider>;
}

export function useDesk(): DeskApi {
  const value = useContext(DeskContext);
  if (!value) throw new Error("useDesk must be used inside DeskProvider");
  return value;
}

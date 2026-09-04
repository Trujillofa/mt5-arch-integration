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
import { applyQuoteMarks, pendingWsfLiveEvents } from "@/lib/copy-engine";
import {
  applyWsfLiveCopyResult,
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
  setWsfLiveCopy as setWsfLiveCopyStore,
  subscribeDesk,
  updateAccount as updateAccountStore,
  updateCopy as updateCopyStore,
  patchDesk,
} from "@/lib/desk-store";
import { WSF_LIVE_CONFIRM } from "@/lib/wsf/constants";
import type { WsfLiveOrderResult } from "@/lib/wsf/types";
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
  setWsfLiveCopy: (enabled: boolean, confirm: string) => string | null;
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
  const wsfConfirm = useRef("");

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

  const setWsfLiveCopy = useCallback((enabled: boolean, confirm: string) => {
    if (enabled && confirm !== WSF_LIVE_CONFIRM) {
      return `Type ${WSF_LIVE_CONFIRM} to arm WSF live copy.`;
    }
    wsfConfirm.current = enabled ? confirm : "";
    setWsfLiveCopyStore(enabled);
    return null;
  }, []);

  const placeTrade = useCallback((input: MasterTradeInput) => {
    const result = placeTradeStore(input);
    if (result.groupId && !result.error) {
      setBusy(true);
      const handle = window.setTimeout(() => {
        void (async () => {
          resolveGroup(result.groupId!);
          const pending = pendingWsfLiveEvents(getDeskSnapshot(), result.groupId!);
          for (const event of pending) {
            try {
              const response = await fetch("/api/wsf/order", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                cache: "no-store",
                body: JSON.stringify({
                  live: true,
                  confirm: wsfConfirm.current || WSF_LIVE_CONFIRM,
                  action: "open",
                  symbol: event.symbol === "EURUSD" ? "EURUSDc" : event.symbol,
                  side: event.side,
                  volume_min: true,
                }),
              });
              const payload = (await response.json()) as WsfLiveOrderResult;
              applyWsfLiveCopyResult(event.id, payload);
            } catch (caught) {
              applyWsfLiveCopyResult(event.id, {
                ok: false,
                source: "seven-desk",
                endpoint: "/api/wsf/order",
                requestId: "",
                stage: "copy",
                reason: caught instanceof Error ? caught.message : "WSF live copy failed",
                login: null,
                server: null,
                winePrefix: ".mt5-wsf",
              });
            }
          }
          setBusy(false);
        })();
      }, 160);
      timers.current.push(handle);
    }
    return result.error;
  }, []);

  const flatten = useCallback((positionId: string) => {
    const position = getDeskSnapshot().positions.find((row) => row.id === positionId);
    if (position?.liveBroker === "wsf") {
      setBusy(true);
      void (async () => {
        try {
          await fetch("/api/wsf/order/close", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            cache: "no-store",
            body: JSON.stringify({
              live: true,
              confirm: wsfConfirm.current || WSF_LIVE_CONFIRM,
              action: "close",
              symbol: position.symbol,
              side: position.side,
              volume_min: true,
            }),
          });
        } finally {
          flattenPosition(positionId);
          setBusy(false);
        }
      })();
      return null;
    }
    return flattenPosition(positionId);
  }, []);

  const resetDemo = useCallback(() => {
    timers.current.forEach((id) => window.clearTimeout(id));
    timers.current = [];
    setBusy(false);
    wsfConfirm.current = "";
    setWsfLiveCopyStore(false);
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
      setWsfLiveCopy,
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
      setWsfLiveCopy,
    ]
  );

  return <DeskContext.Provider value={api}>{children}</DeskContext.Provider>;
}

export function useDesk(): DeskApi {
  const value = useContext(DeskContext);
  if (!value) throw new Error("useDesk must be used inside DeskProvider");
  return value;
}

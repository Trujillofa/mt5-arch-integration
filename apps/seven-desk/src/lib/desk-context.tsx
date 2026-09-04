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
import { applyQuoteMarks, pendingLiveSlaveEvents } from "@/lib/copy-engine";
import {
  applyLiveCopyResult,
  flattenPosition,
  getDeskSnapshot,
  getPersistError,
  getServerDeskSnapshot,
  placeLiveMaster,
  placeTrade as placeTradeStore,
  resetDemo as resetDemoStore,
  resolveGroup,
  selectAccount as selectAccountStore,
  setConnection as setConnectionStore,
  setFundednextLiveCopy as setFundednextLiveCopyStore,
  setFtmoLiveMaster as setFtmoLiveMasterStore,
  setMaster as setMasterStore,
  setSymbolMap as setSymbolMapStore,
  setWsfLiveCopy as setWsfLiveCopyStore,
  subscribeDesk,
  updateAccount as updateAccountStore,
  updateCopy as updateCopyStore,
  patchDesk,
} from "@/lib/desk-store";
import { FUNDEDNEXT_LIVE_CONFIRM, FUNDEDNEXT_LIVE_PENDING } from "@/lib/fundednext/types";
import { FTMO_LIVE_CONFIRM } from "@/lib/ftmo/types";
import type { LiveBroker, LiveOrderResult } from "@/lib/live-order/types";
import { WSF_LIVE_CONFIRM, WSF_LIVE_PENDING } from "@/lib/wsf/constants";
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
  setFtmoLiveMaster: (enabled: boolean, confirm: string) => string | null;
  setFundednextLiveCopy: (enabled: boolean, confirm: string) => string | null;
}

const DeskContext = createContext<DeskApi | null>(null);

function endpointFor(broker: LiveBroker, action: "open" | "close"): string {
  if (broker === "wsf") return action === "close" ? "/api/wsf/order/close" : "/api/wsf/order";
  if (broker === "ftmo") return action === "close" ? "/api/ftmo/order/close" : "/api/ftmo/order";
  return action === "close" ? "/api/fundednext/order/close" : "/api/fundednext/order";
}

function confirmFor(
  broker: LiveBroker,
  refs: { wsf: string; ftmo: string; fn: string }
): string {
  if (broker === "wsf") return refs.wsf || WSF_LIVE_CONFIRM;
  if (broker === "ftmo") return refs.ftmo || FTMO_LIVE_CONFIRM;
  return refs.fn || FUNDEDNEXT_LIVE_CONFIRM;
}

function brokerForPendingReason(reason: string | undefined): LiveBroker | null {
  if (reason === WSF_LIVE_PENDING) return "wsf";
  if (reason === FUNDEDNEXT_LIVE_PENDING) return "fundednext";
  return null;
}

async function postLiveOrder(
  broker: LiveBroker,
  action: "open" | "close",
  confirm: string,
  symbol: string,
  side: string
): Promise<LiveOrderResult> {
  const endpoint = endpointFor(broker, action);
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify({
      live: true,
      confirm,
      action,
      symbol,
      side,
      volume_min: true,
    }),
  });
  return (await response.json()) as LiveOrderResult;
}

export function DeskProvider({ children }: { children: React.ReactNode }) {
  const state = useSyncExternalStore(
    subscribeDesk,
    getDeskSnapshot,
    getServerDeskSnapshot
  );
  const [busy, setBusy] = useState(false);
  const timers = useRef<number[]>([]);
  const wsfConfirm = useRef("");
  const ftmoConfirm = useRef("");
  const fnConfirm = useRef("");

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
    const account = getDeskSnapshot().accounts.find((row) => row.id === id);
    if (!account || account.firmId !== "ftmo") {
      ftmoConfirm.current = "";
      setFtmoLiveMasterStore(false);
    }
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

  const setFtmoLiveMaster = useCallback((enabled: boolean, confirm: string) => {
    if (enabled && confirm !== FTMO_LIVE_CONFIRM) {
      return `Type ${FTMO_LIVE_CONFIRM} to arm FTMO live master.`;
    }
    const master = getDeskSnapshot().accounts.find((row) => row.id === getDeskSnapshot().masterId);
    if (enabled && master?.firmId !== "ftmo") {
      return "Make FTMO the master before arming live master.";
    }
    ftmoConfirm.current = enabled ? confirm : "";
    setFtmoLiveMasterStore(enabled);
    return null;
  }, []);

  const setFundednextLiveCopy = useCallback((enabled: boolean, confirm: string) => {
    if (enabled && confirm !== FUNDEDNEXT_LIVE_CONFIRM) {
      return `Type ${FUNDEDNEXT_LIVE_CONFIRM} to arm FundedNext live copy.`;
    }
    fnConfirm.current = enabled ? confirm : "";
    setFundednextLiveCopyStore(enabled);
    return null;
  }, []);

  const fanOutLiveSlaves = useCallback(async (groupId: string) => {
    const refs = {
      wsf: wsfConfirm.current,
      ftmo: ftmoConfirm.current,
      fn: fnConfirm.current,
    };
    const pending = pendingLiveSlaveEvents(getDeskSnapshot(), groupId);
    for (const event of pending) {
      const broker = brokerForPendingReason(event.reason);
      if (!broker) continue;
      const symbol =
        broker === "wsf" && event.symbol === "EURUSD" ? "EURUSDc" : event.symbol;
      try {
        const payload = await postLiveOrder(
          broker,
          "open",
          confirmFor(broker, refs),
          symbol,
          event.side
        );
        applyLiveCopyResult(event.id, payload, broker);
      } catch (caught) {
        applyLiveCopyResult(
          event.id,
          {
            ok: false,
            source: "seven-desk",
            endpoint: endpointFor(broker, "open"),
            requestId: "",
            stage: "copy",
            reason: caught instanceof Error ? caught.message : `${broker} live copy failed`,
            login: null,
            server: null,
            winePrefix: broker === "wsf" ? ".mt5-wsf" : broker === "ftmo" ? ".mt5-ftmo" : ".mt5-fundednext",
          },
          broker
        );
      }
    }
  }, []);

  const placeTrade = useCallback((input: MasterTradeInput) => {
    const snapshot = getDeskSnapshot();
    const master = snapshot.accounts.find((row) => row.id === snapshot.masterId);
    if (snapshot.ftmoLiveMaster) {
      if (master?.firmId !== "ftmo") {
        return "FTMO live master is armed but FTMO is not the master.";
      }
      if (input.symbol !== "EURUSD" && input.symbol !== "EURUSDc") {
        return "FTMO live master is EURUSD min-lot only.";
      }
      setBusy(true);
      const handle = window.setTimeout(() => {
        void (async () => {
          try {
            const liveInput: MasterTradeInput = {
              ...input,
              symbol: "EURUSD",
              lots: 0.01,
            };
            const payload = await postLiveOrder(
              "ftmo",
              "open",
              ftmoConfirm.current || FTMO_LIVE_CONFIRM,
              "EURUSD",
              liveInput.side
            );
            const placed = placeLiveMaster(liveInput, payload, "ftmo");
            if (placed.groupId && !placed.error) {
              resolveGroup(placed.groupId);
              await fanOutLiveSlaves(placed.groupId);
            }
          } finally {
            setBusy(false);
          }
        })();
      }, 160);
      timers.current.push(handle);
      return null;
    }

    const result = placeTradeStore(input);
    if (result.groupId && !result.error) {
      setBusy(true);
      const handle = window.setTimeout(() => {
        void (async () => {
          resolveGroup(result.groupId!);
          await fanOutLiveSlaves(result.groupId!);
          setBusy(false);
        })();
      }, 160);
      timers.current.push(handle);
    }
    return result.error;
  }, [fanOutLiveSlaves]);

  const flatten = useCallback((positionId: string) => {
    const position = getDeskSnapshot().positions.find((row) => row.id === positionId);
    if (position?.liveBroker) {
      const broker = position.liveBroker;
      const refs = {
        wsf: wsfConfirm.current,
        ftmo: ftmoConfirm.current,
        fn: fnConfirm.current,
      };
      setBusy(true);
      void (async () => {
        try {
          await postLiveOrder(
            broker,
            "close",
            confirmFor(broker, refs),
            position.symbol,
            position.side
          );
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
    ftmoConfirm.current = "";
    fnConfirm.current = "";
    setWsfLiveCopyStore(false);
    setFtmoLiveMasterStore(false);
    setFundednextLiveCopyStore(false);
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
      setFtmoLiveMaster,
      setFundednextLiveCopy,
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
      setFtmoLiveMaster,
      setFundednextLiveCopy,
    ]
  );

  return <DeskContext.Provider value={api}>{children}</DeskContext.Provider>;
}

export function useDesk(): DeskApi {
  const value = useContext(DeskContext);
  if (!value) throw new Error("useDesk must be used inside DeskProvider");
  return value;
}

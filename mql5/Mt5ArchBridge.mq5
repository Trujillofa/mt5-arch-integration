//+------------------------------------------------------------------+
//| Mt5ArchBridge.mq5                                                |
//| File bridge for Linux/Wine (MetaTrader5 Python IPC often fails)  |
//|                                                                  |
//| FREEZE FIX (v1.20):                                              |
//|  • Attach to ONE chart only                                      |
//|  • Timer-only writes (no OnTick storm)                           |
//|  • File lock so extra instances stay standby                     |
//|  • Default 5s interval, leaner symbol/TF set                     |
//| v1.23: explicit FxSymbolRegistry (no suffix first-match)         |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property link      ""
#property version   "1.28"
#property description "JSON bridge → MQL5/Files/mt5_arch/  |  ONE chart only under Wine"
#property description "v1.20: timer-only + file lock (stops multi-EA freeze / err 5004)"
#property description "v1.21: per-bar spread in candles + one-shot deep history dump"
#property description "v1.23: explicit symbol registry — set InpBroker"
#property description "v1.24: request-gated deal dump (dump_deals.request → deals_export.csv)"
#property description "v1.25: in-process desk_live_order_request → pending OrderSend"
#property description "v1.26: OrdersTotal dump → orders.json (working limits/stops)"
#property description "v1.27: TRADE_ACTION_SLTP modify + magic on positions.json"
#property description "v1.28: request-gated history dump (dump_history.request)"

// Single source for the running version. #property takes a literal, so
// tests/test_ea_version.py asserts the two stay equal — a deployed EA that
// misreports its version is how a stale build hides in plain sight.
#define BRIDGE_VERSION "1.28"
#define BRIDGE_READONLY false

#include <FxSymbolRegistry.mqh>
#include <DeskOrderBridge.mqh>

input int    InpTimerSec    = 5;       // Snapshot interval (seconds). Use 5+ under Wine.
input string InpBroker      = "";      // required: vantage|fpmarkets|exness|wsf|alphacapital
// Canonical names; FxResolveSymbol maps via config/symbols/registry.json
input string InpSymbols     = "EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD";
input string InpTimeframes  = "H1,H4,D1";
input int    InpCandleCount = 30;
input bool   InpSingleWriter= true;    // Extra instances go standby (must stay true on Wine)
// One-shot deep history dump (OHLC + per-bar spread) for offline cost modelling.
// Runs once per marker file; delete mt5_arch\history_dump.done to re-run.
input bool   InpDumpHistory   = true;
input string InpHistorySymbol = "XAUUSD";
input string InpHistoryTfs    = "M15,H1";
input int    InpHistoryMonths = 60;

#include <FileBridgeSnapshots.mqh>

//+------------------------------------------------------------------+
int OnInit()
  {
   if(StringLen(InpBroker) == 0)
     {
      Print("Mt5ArchBridge: InpBroker is required (vantage|fpmarkets|exness|wsf)");
      return INIT_PARAMETERS_INCORRECT;
     }
   FolderCreate(g_dir);
   FolderCreate(g_dir, FILE_COMMON);
   g_lock_rel = g_dir + "\\writer.lock";

   g_is_writer = ClaimWriterLock();
   if(!g_is_writer)
     {
      Print("Mt5ArchBridge STANDBY on ", _Symbol, " chart=", ChartID(),
            " — another chart owns the bridge. REMOVE this EA from this chart.");
      // Still set a slow timer to reclaim if owner dies
      EventSetTimer(30);
      return INIT_SUCCEEDED;
     }

   EventSetTimer((int)MathMax(3, InpTimerSec));
   Print("Mt5ArchBridge WRITER v" + BRIDGE_VERSION + " broker=", InpBroker, " ON ", _Symbol,
         " -> Files/", g_dir, " every ", InpTimerSec, "s (timer only, no tick writes)");
   WriteAll();
   DumpHistoryOnce();
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_is_writer)
      ReleaseWriterLock();
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   if(!g_is_writer)
     {
      // Try to become writer if lock is stale / missing
      if(ClaimWriterLock())
        {
         g_is_writer = true;
         EventKillTimer();
         EventSetTimer((int)MathMax(3, InpTimerSec));
         Print("Mt5ArchBridge: claimed writer lock after standby");
         WriteAll();
        }
      return;
     }
   // Refresh lock heartbeat
   TouchWriterLock();
   // Desk orders first — do not wait on snapshot/deal-dump I/O.
   DeskOrderProcessIfRequested();
   WriteAll();
   // After heartbeat — HistorySelect can block on a fresh reconnect.
   DumpDealsIfRequested();
   DumpHistoryIfRequested();
  }

//+------------------------------------------------------------------+
//| NO OnTick snapshot writes — tick storms + multi-EA = Wine freeze.|
//| FileIsExist for a desk order is throttled to 200ms in the include.|
//+------------------------------------------------------------------+
void OnTick()
  {
   if(g_is_writer)
      DeskOrderPollOnTick();
  }
//+------------------------------------------------------------------+

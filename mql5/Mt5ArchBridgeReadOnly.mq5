//+------------------------------------------------------------------+
//| Mt5ArchBridgeReadOnly.mq5                                        |
//| Snapshot-only file bridge for Alpha Capital / email attach.      |
//| Never sends live orders. Does not compile the trading include.   |
//| Ignores desk order-bridge request files if they appear.          |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property link      ""
#property version   "1.25"
#property description "READ-ONLY JSON bridge → MQL5/Files/mt5_arch/"
#property description "No live orders. No desk request files. Email-safe."
#property description "heartbeat: version=1.25 readonly=true"

#define BRIDGE_VERSION "1.25"
#define BRIDGE_READONLY true

#include <FxSymbolRegistry.mqh>

input int    InpTimerSec    = 5;       // Snapshot interval (seconds). Use 5+ under Wine.
input string InpBroker      = "";      // required: alphacapital (or vantage|fpmarkets|exness|wsf)
input string InpSymbols     = "EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD";
input string InpTimeframes  = "H1,H4,D1";
input int    InpCandleCount = 30;
input bool   InpSingleWriter= true;    // Extra instances go standby (must stay true on Wine)
input bool   InpDumpHistory   = false;
input string InpHistorySymbol = "XAUUSD";
input string InpHistoryTfs    = "M15,H1";
input int    InpHistoryMonths = 60;

#include <FileBridgeSnapshots.mqh>

//+------------------------------------------------------------------+
int OnInit()
  {
   if(StringLen(InpBroker) == 0)
     {
      Print("Mt5ArchBridgeReadOnly: InpBroker is required (alphacapital|vantage|fpmarkets|exness|wsf)");
      return INIT_PARAMETERS_INCORRECT;
     }
   FolderCreate(g_dir);
   FolderCreate(g_dir, FILE_COMMON);
   g_lock_rel = g_dir + "\\writer.lock";

   g_is_writer = ClaimWriterLock();
   if(!g_is_writer)
     {
      Print("Mt5ArchBridgeReadOnly STANDBY on ", _Symbol, " chart=", ChartID(),
            " — another chart owns the bridge. REMOVE this EA from this chart.");
      EventSetTimer(30);
      return INIT_SUCCEEDED;
     }

   EventSetTimer((int)MathMax(3, InpTimerSec));
   Print("Mt5ArchBridgeReadOnly WRITER v" + BRIDGE_VERSION + " readonly=true broker=", InpBroker, " ON ", _Symbol,
         " -> Files/", g_dir, " every ", InpTimerSec, "s (timer only, no live orders)");
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
      if(ClaimWriterLock())
        {
         g_is_writer = true;
         EventKillTimer();
         EventSetTimer((int)MathMax(3, InpTimerSec));
         Print("Mt5ArchBridgeReadOnly: claimed writer lock after standby");
         WriteAll();
        }
      return;
     }
   TouchWriterLock();
   WriteAll();
   DumpDealsIfRequested();
  }

//+------------------------------------------------------------------+
//| No OnTick. No desk-order poll. Request files are ignored.        |
//+------------------------------------------------------------------+
void OnTick()
  {
  }
//+------------------------------------------------------------------+

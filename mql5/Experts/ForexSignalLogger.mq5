//+------------------------------------------------------------------+
//| ForexSignalLogger.mq5                                            |
//| Thin EA: reads indicator signal buffers, logs only (no orders)   |
//|                                                                  |
//| Attach to the same chart as the indicator you want to monitor.   |
//| Default: ForexHtfPivotsFib buffer 8.                             |
//| For ForexIndicatorTemplate use buffer 9 and name that indicator. |
//|                                                                  |
//| Output:                                                           |
//|  • Experts tab Print lines                                        |
//|  • Optional CSV under MQL5/Files/forex_signals/                  |
//|  • Optional Alert / Push                                          |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.00"
#property description "Logs iCustom signals only — never places orders"
#property strict

#include <ForexUtils.mqh>

input group "=== Indicator ==="
input string InpIndicatorName   = "ForexHtfPivotsFib"; // Indicator file name (no .ex5)
input int    InpSignalBuffer    = 8;                   // Signal buffer (HTF Fib=8, Template=9)
input int    InpSignalShift     = 1;                   // 1 = last closed bar

input group "=== Filters ==="
input double InpMaxSpreadPips   = 2.5;  // Skip log if spread wider (0=off)
input bool   InpOnlyNewBar      = true; // Evaluate once per new bar

input group "=== Output ==="
input bool   InpWriteCsv        = true;
input string InpCsvDir          = "forex_signals";
input bool   InpAlertPopup      = false;
input bool   InpAlertPush       = false;
input bool   InpAlertSound      = false;
input string InpSoundFile       = "alert.wav";

//---
int      g_handle = INVALID_HANDLE;
datetime g_last_bar = 0;
datetime g_last_logged_bar = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   // Create handle with default inputs of the indicator (user must match chart settings
   // if they changed inputs — advanced: pass inputs explicitly in iCustom).
   g_handle = iCustom(_Symbol, PERIOD_CURRENT, InpIndicatorName);
   if(g_handle == INVALID_HANDLE)
     {
      Print("ForexSignalLogger: iCustom failed for '", InpIndicatorName,
            "' err=", GetLastError(),
            " — compile the indicator and attach it once first.");
      return INIT_FAILED;
     }

   if(InpWriteCsv)
      FolderCreate(InpCsvDir);

   Print("ForexSignalLogger ON | ", _Symbol, " ", EnumToString(Period()),
         " | ind=", InpIndicatorName, " buf=", InpSignalBuffer,
         " | NO ORDERS");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_handle != INVALID_HANDLE)
      IndicatorRelease(g_handle);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   datetime t[];
   if(CopyTime(_Symbol, PERIOD_CURRENT, 0, 1, t) < 1)
      return;

   if(InpOnlyNewBar)
     {
      if(t[0] == g_last_bar)
         return;
      g_last_bar = t[0];
     }

   if(InpMaxSpreadPips > 0.0 && FxSpreadPips(_Symbol) > InpMaxSpreadPips)
      return;

   double sig[];
   ArraySetAsSeries(sig, true);
   if(CopyBuffer(g_handle, InpSignalBuffer, InpSignalShift, 1, sig) < 1)
      return;

   int s = (int)MathRound(sig[0]);
   if(s == 0)
      return;

   // Bar time of the signal bar
   datetime bar_time[];
   ArraySetAsSeries(bar_time, true);
   if(CopyTime(_Symbol, PERIOD_CURRENT, InpSignalShift, 1, bar_time) < 1)
      return;

   if(bar_time[0] == g_last_logged_bar)
      return;
   g_last_logged_bar = bar_time[0];

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   string side = (s > 0) ? "LONG" : "SHORT";
   string msg = StringFormat("%s %s %s | %s @ %s | spread=%.1fp | buf=%d",
                             TimeToString(bar_time[0], TIME_DATE|TIME_MINUTES),
                             _Symbol, EnumToString(Period()),
                             side, DoubleToString(bid, _Digits),
                             FxSpreadPips(_Symbol), InpSignalBuffer);

   Print("SIGNAL ", msg);

   if(InpWriteCsv)
      AppendCsv(bar_time[0], side, bid, s);

   if(InpAlertPopup)
      Alert(msg);
   if(InpAlertPush)
      SendNotification(msg);
   if(InpAlertSound)
      PlaySound(InpSoundFile);
  }

//+------------------------------------------------------------------+
void AppendCsv(const datetime bar_time, const string side,
               const double price, const int sig)
  {
   string path = InpCsvDir + "\\" + _Symbol + "_" +
                 EnumToString(Period()) + ".csv";
   bool exists = FileIsExist(path);
   int h = FileOpen(path, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ, ',');
   if(h == INVALID_HANDLE)
     {
      Print("CSV open fail ", path, " err=", GetLastError());
      return;
     }
   FileSeek(h, 0, SEEK_END);
   if(!exists || FileSize(h) == 0)
      FileWrite(h, "time", "symbol", "tf", "side", "price", "signal", "spread_pips");

   FileWrite(h,
             TimeToString(bar_time, TIME_DATE|TIME_SECONDS),
             _Symbol,
             EnumToString(Period()),
             side,
             DoubleToString(price, _Digits),
             IntegerToString(sig),
             DoubleToString(FxSpreadPips(_Symbol), 2));
   FileClose(h);
  }

//+------------------------------------------------------------------+
//| SAFETY: this EA never calls OrderSend / trade classes.           |
//+------------------------------------------------------------------+

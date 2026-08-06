//+------------------------------------------------------------------+
//| ExportXauHistory.mq5                                             |
//| Dump XAUUSD M15 + H1 to MQL5/Files/xauusd_mt5_export.csv         |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property version   "1.00"
#property script_show_inputs

input string InpSymbol  = "XAUUSD";
input int    InpMonths  = 24;
input string InpOutFile = "xauusd_mt5_export.csv";

//+------------------------------------------------------------------+
bool ExportTf(const string symbol, const ENUM_TIMEFRAMES tf, const string tf_name,
              const int handle)
  {
   datetime to = TimeCurrent();
   datetime from = to - (datetime)((long)InpMonths * 30L * 24L * 3600L);
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   ResetLastError();
   int n = CopyRates(symbol, tf, from, to, rates);
   if(n <= 0)
     {
      // try count-based from present
      n = CopyRates(symbol, tf, 0, InpMonths * 30 * 24, rates);
     }
   if(n <= 0)
     {
      Print("ExportTf fail ", tf_name, " err=", GetLastError());
      return false;
     }
   Print("ExportTf ", tf_name, " bars=", n,
         " from=", TimeToString(rates[0].time, TIME_DATE | TIME_MINUTES),
         " to=", TimeToString(rates[n - 1].time, TIME_DATE | TIME_MINUTES));

   for(int i = 0; i < n; i++)
     {
      string line = TimeToString(rates[i].time, TIME_DATE | TIME_MINUTES);
      line += "," + tf_name;
      line += "," + symbol;
      line += "," + DoubleToString(rates[i].open, 5);
      line += "," + DoubleToString(rates[i].high, 5);
      line += "," + DoubleToString(rates[i].low, 5);
      line += "," + DoubleToString(rates[i].close, 5);
      line += "," + IntegerToString((int)rates[i].tick_volume);
      FileWrite(handle, line);
     }
   return true;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   if(!SymbolSelect(InpSymbol, true))
     {
      Print("SymbolSelect failed ", InpSymbol, " err=", GetLastError());
      return;
     }

   datetime to = TimeCurrent();
   datetime from = to - (datetime)((long)InpMonths * 30L * 24L * 3600L);
   MqlRates tmp[];
   CopyRates(InpSymbol, PERIOD_M15, from, to, tmp);
   CopyRates(InpSymbol, PERIOD_H1, from, to, tmp);
   Sleep(1500);

   int h = FileOpen(InpOutFile, FILE_WRITE | FILE_CSV | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("FileOpen failed err=", GetLastError());
      return;
     }
   FileWrite(h, "time,timeframe,symbol,open,high,low,close,tick_volume");
   bool ok15 = ExportTf(InpSymbol, PERIOD_M15, "M15", h);
   bool okh1 = ExportTf(InpSymbol, PERIOD_H1, "H1", h);
   FileClose(h);
   Print("Export done okM15=", ok15, " okH1=", okh1,
         " path=MQL5/Files/", InpOutFile);
  }
//+------------------------------------------------------------------+

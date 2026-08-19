//+------------------------------------------------------------------+
//| IndexM5Export.mqh                                                |
//| Dump US30/US100 M5 + spread for the offline flatten backtest.    |
//| Trigger: MQL5/Files/mt5_arch/export_us_index.request             |
//| Never OrderSend. Does not kill the terminal.                     |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef INDEX_M5_EXPORT_MQH
#define INDEX_M5_EXPORT_MQH

#include <IndexSessionUtils.mqh>

#ifndef IDX_EXPORT_MAX_BARS
#define IDX_EXPORT_MAX_BARS 100000
#endif

//+------------------------------------------------------------------+
bool IdxExportWriteMeta(const string symbol, const string requested,
                        const int offset_sec, const int n_bars,
                        const datetime t0, const datetime t1)
  {
   string path = "mt5_arch\\symbol_meta_" + requested + ".csv";
   int h = FileOpen(path, FILE_WRITE | FILE_CSV | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("IdxExportWriteMeta FileOpen fail ", requested, " err=", GetLastError());
      return false;
     }
   FileWrite(h, "key,value");
   FileWrite(h, "requested," + requested);
   FileWrite(h, "resolved," + symbol);
   FileWrite(h, "digits," + IntegerToString((int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)));
   FileWrite(h, "point," + DoubleToString(SymbolInfoDouble(symbol, SYMBOL_POINT), 8));
   FileWrite(h, "contract_size," + DoubleToString(SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE), 4));
   FileWrite(h, "tick_size," + DoubleToString(SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE), 8));
   FileWrite(h, "tick_value," + DoubleToString(SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE), 8));
   FileWrite(h, "currency_profit," + SymbolInfoString(symbol, SYMBOL_CURRENCY_PROFIT));
   FileWrite(h, "server_utc_offset_sec," + IntegerToString(offset_sec));
   FileWrite(h, "bars," + IntegerToString(n_bars));
   FileWrite(h, "from," + TimeToString(t0, TIME_DATE | TIME_MINUTES));
   FileWrite(h, "to," + TimeToString(t1, TIME_DATE | TIME_MINUTES));
   FileWrite(h, "tf,M5");
   FileClose(h);
   return true;
  }

//+------------------------------------------------------------------+
bool IdxExportSymbolM5(const string symbol, const string requested,
                       const int offset_sec)
  {
   if(!SymbolSelect(symbol, true))
     {
      Print("IdxExportSymbolM5 SymbolSelect fail ", symbol);
      return false;
     }
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   datetime to = TimeCurrent();
   datetime from = to - (datetime)(400L * 24L * 3600L);
   int n = CopyRates(symbol, PERIOD_M5, from, to, rates);
   if(n <= 0)
      n = CopyRates(symbol, PERIOD_M5, 0, IDX_EXPORT_MAX_BARS, rates);
   if(n <= 0)
     {
      Print("IdxExportSymbolM5 CopyRates fail ", symbol, " err=", GetLastError());
      return false;
     }
   if(n > IDX_EXPORT_MAX_BARS)
      n = IDX_EXPORT_MAX_BARS;

   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   string path = "mt5_arch\\history_" + requested + "_M5.csv";
   int h = FileOpen(path, FILE_WRITE | FILE_CSV | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("IdxExportSymbolM5 FileOpen fail ", path, " err=", GetLastError());
      return false;
     }
   FileWrite(h, "time,tf,symbol,open,high,low,close,tick_volume,spread,server_epoch");
   for(int i = 0; i < n; i++)
     {
      string line = TimeToString(rates[i].time, TIME_DATE | TIME_MINUTES);
      line += ",M5";
      line += "," + symbol;
      line += "," + DoubleToString(rates[i].open, digits);
      line += "," + DoubleToString(rates[i].high, digits);
      line += "," + DoubleToString(rates[i].low, digits);
      line += "," + DoubleToString(rates[i].close, digits);
      line += "," + IntegerToString((long)rates[i].tick_volume);
      line += "," + IntegerToString((long)rates[i].spread);
      line += "," + IntegerToString((long)rates[i].time);
      FileWrite(h, line);
     }
   FileClose(h);
   Print("IdxExportSymbolM5 ", symbol, " bars=", n,
         " from=", TimeToString(rates[0].time, TIME_DATE | TIME_MINUTES),
         " to=", TimeToString(rates[n - 1].time, TIME_DATE | TIME_MINUTES));
   return IdxExportWriteMeta(symbol, requested, offset_sec, n,
                             rates[0].time, rates[n - 1].time);
  }

//+------------------------------------------------------------------+
int IdxExportUsIndexM5Now()
  {
   int offset = IdxDetectServerUtcOffsetSec(-99);
   string want = "US100,US30,DJ30.r";
   string parts[];
   int n = StringSplit(want, ',', parts);
   int done = 0;
   for(int i = 0; i < n; i++)
     {
      string req = parts[i];
      StringTrimLeft(req);
      StringTrimRight(req);
      if(StringLen(req) == 0)
         continue;
      if(!SymbolSelect(req, true) && req != _Symbol)
         continue;
      string resolved = SymbolSelect(req, true) ? req : _Symbol;
      if(IdxExportSymbolM5(resolved, req, offset))
         done++;
     }
   if(IdxLooksLikeUsIndex(_Symbol) && done == 0)
     {
      if(IdxExportSymbolM5(_Symbol, _Symbol, offset))
         done++;
     }
   return done;
  }

//+------------------------------------------------------------------+
void IdxExportUsIndexM5IfRequested()
  {
   string req = "mt5_arch\\export_us_index.request";
   if(!FileIsExist(req))
      return;
   Print("IdxExportUsIndexM5IfRequested: request seen");
   int done = IdxExportUsIndexM5Now();
   FileDelete(req);
   int h = FileOpen("mt5_arch\\export_us_index.done", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h != INVALID_HANDLE)
     {
      FileWriteString(h, IntegerToString(done) + "\n");
      FileClose(h);
     }
   Print("IdxExportUsIndexM5IfRequested: done=", done);
  }

#endif // INDEX_M5_EXPORT_MQH
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| ExportInstrumentHistory.mq5                                      |
//| Multi-symbol H1 (+ optional M15) dump with per-bar MqlRates.spread|
//| For multi-instrument data readiness (offline research).          |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property version   "1.00"
#property script_show_inputs

input string InpSymbols = "XAUUSD,EURUSD,GBPUSD";
input int    InpMonths  = 60;
input string InpTfs     = "H1";              // comma list: H1 and/or M15
input string InpOutDir  = "mt5_arch";        // under MQL5/Files/

//+------------------------------------------------------------------+
ENUM_TIMEFRAMES ParseTf(const string tf)
  {
   if(tf == "M15") return PERIOD_M15;
   if(tf == "H1")  return PERIOD_H1;
   if(tf == "H4")  return PERIOD_H4;
   if(tf == "D1")  return PERIOD_D1;
   return PERIOD_H1;
  }

//+------------------------------------------------------------------+
string ResolveSymbol(const string requested)
  {
   string base = requested;
   StringTrimLeft(base);
   StringTrimRight(base);
   if(StringLen(base) == 0)
      return "";
   if(SymbolSelect(base, true))
      return base;
   string suffixes[] = {"m", ".r", ".m", "#", "pro", ".i", ".a"};
   for(int i = 0; i < ArraySize(suffixes); i++)
     {
      string cand = base + suffixes[i];
      if(SymbolSelect(cand, true))
         return cand;
     }
   return "";
  }

//+------------------------------------------------------------------+
bool ExportTf(const string symbol, const ENUM_TIMEFRAMES period,
              const string tf_name, const int handle, const int digits,
              const datetime from, const datetime to)
  {
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int n = 0;
   for(int attempt = 0; attempt < 5; attempt++)
     {
      ResetLastError();
      n = CopyRates(symbol, period, from, to, rates);
      if(n > 0)
         break;
      Sleep(2000);
     }
   if(n <= 0)
     {
      // count-based fallback
      n = CopyRates(symbol, period, 0, InpMonths * 30 * 24, rates);
     }
   if(n <= 0)
     {
      Print("ExportTf fail ", symbol, " ", tf_name, " err=", GetLastError());
      return false;
     }
   Print("ExportTf ", symbol, " ", tf_name, " bars=", n,
         " from=", TimeToString(rates[0].time, TIME_DATE | TIME_MINUTES),
         " to=", TimeToString(rates[n - 1].time, TIME_DATE | TIME_MINUTES));

   for(int i = 0; i < n; i++)
     {
      string line = TimeToString(rates[i].time, TIME_DATE | TIME_MINUTES);
      line += "," + tf_name;
      line += "," + symbol;
      line += "," + DoubleToString(rates[i].open, digits);
      line += "," + DoubleToString(rates[i].high, digits);
      line += "," + DoubleToString(rates[i].low, digits);
      line += "," + DoubleToString(rates[i].close, digits);
      line += "," + IntegerToString((long)rates[i].tick_volume);
      line += "," + IntegerToString((long)rates[i].spread);
      FileWrite(handle, line);
     }
   return true;
  }

//+------------------------------------------------------------------+
void WriteSymbolMeta(const string requested, const string resolved)
  {
   string path = InpOutDir + "\\symbol_meta_" + requested + ".csv";
   int h = FileOpen(path, FILE_WRITE | FILE_CSV | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("WriteSymbolMeta FileOpen fail ", GetLastError());
      return;
     }
   FileWrite(h, "key,value");
   FileWrite(h, "requested," + requested);
   FileWrite(h, "resolved," + resolved);
   FileWrite(h, "digits," + IntegerToString((int)SymbolInfoInteger(resolved, SYMBOL_DIGITS)));
   FileWrite(h, "point," + DoubleToString(SymbolInfoDouble(resolved, SYMBOL_POINT), 8));
   FileWrite(h, "contract_size," + DoubleToString(SymbolInfoDouble(resolved, SYMBOL_TRADE_CONTRACT_SIZE), 4));
   FileWrite(h, "tick_size," + DoubleToString(SymbolInfoDouble(resolved, SYMBOL_TRADE_TICK_SIZE), 8));
   FileWrite(h, "tick_value," + DoubleToString(SymbolInfoDouble(resolved, SYMBOL_TRADE_TICK_VALUE), 8));
   FileWrite(h, "currency_base," + SymbolInfoString(resolved, SYMBOL_CURRENCY_BASE));
   FileWrite(h, "currency_profit," + SymbolInfoString(resolved, SYMBOL_CURRENCY_PROFIT));
   FileWrite(h, "trade_mode," + IntegerToString((int)SymbolInfoInteger(resolved, SYMBOL_TRADE_MODE)));
   FileClose(h);
   Print("Wrote ", path);
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   string symbols[];
   int ns = StringSplit(InpSymbols, ',', symbols);
   string tfs[];
   int nt = StringSplit(InpTfs, ',', tfs);

   datetime to = TimeCurrent();
   datetime from = to - (datetime)((long)InpMonths * 30L * 24L * 3600L);

   // Prefetch
   for(int s = 0; s < ns; s++)
     {
      string req = symbols[s];
      StringTrimLeft(req); StringTrimRight(req);
      string sym = ResolveSymbol(req);
      if(StringLen(sym) == 0)
        {
         Print("ResolveSymbol failed ", req);
         continue;
        }
      for(int j = 0; j < nt; j++)
        {
         string tf = tfs[j];
         StringTrimLeft(tf); StringTrimRight(tf);
         MqlRates tmp[];
         CopyRates(sym, ParseTf(tf), from, to, tmp);
        }
     }
   Sleep(2000);

   for(int s = 0; s < ns; s++)
     {
      string req = symbols[s];
      StringTrimLeft(req); StringTrimRight(req);
      if(StringLen(req) == 0)
         continue;
      string sym = ResolveSymbol(req);
      if(StringLen(sym) == 0)
        {
         Print("Skip unresolved ", req);
         continue;
        }
      WriteSymbolMeta(req, sym);

      int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      string out = InpOutDir + "\\history_" + req + ".csv";
      int h = FileOpen(out, FILE_WRITE | FILE_CSV | FILE_ANSI);
      if(h == INVALID_HANDLE)
        {
         Print("FileOpen failed ", out, " err=", GetLastError());
         continue;
        }
      FileWrite(h, "time,timeframe,symbol,open,high,low,close,tick_volume,spread");
      bool any = false;
      for(int j = 0; j < nt; j++)
        {
         string tf = tfs[j];
         StringTrimLeft(tf); StringTrimRight(tf);
         if(StringLen(tf) == 0)
            continue;
         if(ExportTf(sym, ParseTf(tf), tf, h, digits, from, to))
            any = true;
        }
      FileClose(h);
      Print("Export done ", req, " -> ", out, " any=", any);
     }
   Print("ExportInstrumentHistory finished");
  }
//+------------------------------------------------------------------+

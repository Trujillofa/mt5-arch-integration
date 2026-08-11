//+------------------------------------------------------------------+
//| ExportInstrumentHistory.mq5                                      |
//| Multi-symbol H1 dump with per-bar MqlRates.spread + completion   |
//| record (runtime account / connection attestation).               |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property version   "1.10"
#property script_show_inputs

input string InpSymbols = "XAUUSD,EURUSD,GBPUSD";
input int    InpMonths  = 60;
input string InpTfs     = "H1";
input string InpOutDir  = "mt5_arch";
// Pre-launch challenge written by shell as export_challenge.json (must be echoed).
input string InpChallengeFile = "mt5_arch\\export_challenge.json";

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
              const datetime from, const datetime to, int &out_n,
              datetime &out_from, datetime &out_to)
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
      n = CopyRates(symbol, period, 0, InpMonths * 30 * 24, rates);
   if(n <= 0)
     {
      Print("ExportTf fail ", symbol, " ", tf_name, " err=", GetLastError());
      out_n = 0;
      return false;
     }
   out_n = n;
   out_from = rates[0].time;
   out_to = rates[n - 1].time;
   Print("ExportTf ", symbol, " ", tf_name, " bars=", n,
         " from=", TimeToString(out_from, TIME_DATE | TIME_MINUTES),
         " to=", TimeToString(out_to, TIME_DATE | TIME_MINUTES));

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
  }

//+------------------------------------------------------------------+
//| Simple JSON string escape                                        |
//+------------------------------------------------------------------+
string JEsc(const string s)
  {
   string o = s;
   StringReplace(o, "\\", "\\\\");
   StringReplace(o, "\"", "\\\"");
   return o;
  }

//+------------------------------------------------------------------+
string ReadChallengeRaw()
  {
   // FILE_TXT whole-file read of pre-launch challenge (JSON).
   int h = FileOpen(InpChallengeFile, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      Print("ReadChallenge fail err=", GetLastError(), " path=", InpChallengeFile);
      return "";
     }
   string raw = "";
   while(!FileIsEnding(h))
     {
      string line = FileReadString(h);
      raw += line;
     }
   FileClose(h);
   return raw;
  }

// Extract "run_id":"...." from challenge JSON (simple scanner; hex only).
string ExtractRunId(const string challenge)
  {
   int p = StringFind(challenge, "\"run_id\"");
   if(p < 0) return "";
   int c = StringFind(challenge, ":", p);
   if(c < 0) return "";
   int q1 = StringFind(challenge, "\"", c + 1);
   if(q1 < 0) return "";
   int q2 = StringFind(challenge, "\"", q1 + 1);
   if(q2 < 0) return "";
   return StringSubstr(challenge, q1 + 1, q2 - q1 - 1);
  }

void WriteCompletion(const bool ok, const string details_json_array,
                     const string challenge_raw, const string run_id)
  {
   // Runtime account / connection attestation — not from common.ini alone.
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string server = AccountInfoString(ACCOUNT_SERVER);
   string company = AccountInfoString(ACCOUNT_COMPANY);
   bool connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   string path = InpOutDir + "\\export_complete.json";
   int h = FileOpen(path, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("WriteCompletion FileOpen fail ", GetLastError());
      return;
     }
   // challenge_echo is the exact challenge body (escaped for JSON string)
   string j = "{";
   j += "\"ok\":" + (ok ? "true" : "false") + ",";
   j += "\"run_id\":\"" + JEsc(run_id) + "\",";
   j += "\"challenge_echo\":\"" + JEsc(challenge_raw) + "\",";
   j += "\"terminal_connected\":" + (connected ? "true" : "false") + ",";
   j += "\"account_login\":" + IntegerToString(login) + ",";
   j += "\"account_server\":\"" + JEsc(server) + "\",";
   j += "\"account_company\":\"" + JEsc(company) + "\",";
   j += "\"trade_mode\":" + IntegerToString((int)AccountInfoInteger(ACCOUNT_TRADE_MODE)) + ",";
   j += "\"finished_server\":\"" + TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + "\",";
   j += "\"symbols\":" + details_json_array;
   j += "}";
   FileWriteString(h, j);
   FileClose(h);
   Print("Wrote ", path, " ok=", ok, " connected=", connected, " login=", login, " run_id=", run_id);
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   string challenge_raw = ReadChallengeRaw();
   string run_id = ExtractRunId(challenge_raw);
   if(StringLen(run_id) == 0)
     {
      Print("FATAL: missing/invalid export_challenge.json run_id");
      WriteCompletion(false, "[]", challenge_raw, "");
      return;
     }

   string symbols[];
   int ns = StringSplit(InpSymbols, ',', symbols);
   string tfs[];
   int nt = StringSplit(InpTfs, ',', tfs);

   datetime to = TimeCurrent();
   datetime from = to - (datetime)((long)InpMonths * 30L * 24L * 3600L);

   bool connected0 = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   if(!connected0)
      Print("WARNING: TERMINAL_CONNECTED=false at start — history may be cache-only");

   for(int s = 0; s < ns; s++)
     {
      string req = symbols[s];
      StringTrimLeft(req); StringTrimRight(req);
      string sym = ResolveSymbol(req);
      if(StringLen(sym) == 0)
         continue;
      for(int j = 0; j < nt; j++)
        {
         string tf = tfs[j];
         StringTrimLeft(tf); StringTrimRight(tf);
         MqlRates tmp[];
         CopyRates(sym, ParseTf(tf), from, to, tmp);
        }
     }
   Sleep(2000);

   string details = "[";
   bool first = true;
   bool all_ok = true;
   int done = 0;

   for(int s = 0; s < ns; s++)
     {
      string req = symbols[s];
      StringTrimLeft(req); StringTrimRight(req);
      if(StringLen(req) == 0)
         continue;
      string sym = ResolveSymbol(req);
      if(StringLen(sym) == 0)
        {
         all_ok = false;
         Print("Skip unresolved ", req);
         continue;
        }
      WriteSymbolMeta(req, sym);

      int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      string out = InpOutDir + "\\history_" + req + ".csv";
      int h = FileOpen(out, FILE_WRITE | FILE_CSV | FILE_ANSI);
      if(h == INVALID_HANDLE)
        {
         all_ok = false;
         Print("FileOpen failed ", out, " err=", GetLastError());
         continue;
        }
      FileWrite(h, "time,timeframe,symbol,open,high,low,close,tick_volume,spread");
      bool any = false;
      int bars = 0;
      datetime bf = 0, bt = 0;
      for(int j = 0; j < nt; j++)
        {
         string tf = tfs[j];
         StringTrimLeft(tf); StringTrimRight(tf);
         if(StringLen(tf) == 0)
            continue;
         int bn = 0;
         datetime f0 = 0, t0 = 0;
         if(ExportTf(sym, ParseTf(tf), tf, h, digits, from, to, bn, f0, t0))
           {
            any = true;
            bars += bn;
            if(bf == 0 || f0 < bf) bf = f0;
            if(t0 > bt) bt = t0;
           }
        }
      FileClose(h);
      if(!any)
         all_ok = false;
      else
         done++;

      if(!first)
         details += ",";
      first = false;
      details += "{";
      details += "\"requested\":\"" + JEsc(req) + "\",";
      details += "\"resolved\":\"" + JEsc(sym) + "\",";
      details += "\"bars\":" + IntegerToString(bars) + ",";
      details += "\"from\":\"" + TimeToString(bf, TIME_DATE | TIME_MINUTES) + "\",";
      details += "\"to\":\"" + TimeToString(bt, TIME_DATE | TIME_MINUTES) + "\",";
      details += "\"ok\":" + (any ? "true" : "false");
      details += "}";
      Print("Export done ", req, " -> ", out, " any=", any, " bars=", bars);
     }
   details += "]";

   if(done < 1)
      all_ok = false;
   WriteCompletion(all_ok, details, challenge_raw, run_id);
   Print("ExportInstrumentHistory finished ok=", all_ok, " symbols_done=", done, " run_id=", run_id);
  }
//+------------------------------------------------------------------+

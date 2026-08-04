//+------------------------------------------------------------------+
//| Mt5ArchBridge.mq5                                                |
//| File bridge for Linux/Wine (MetaTrader5 Python IPC often fails)  |
//| Attach to a chart and enable Algo Trading (green).               |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property link      ""
#property version   "1.04"
#property description "Writes account/symbols/candles JSON under MQL5/Files/mt5_arch/"

input int    InpTimerSec    = 1;       // Snapshot interval (seconds) — more reliable than ms under Wine
// Phase 0 (FP Markets): gold is XAUUSD.r; BTC is BTCUSD. Keep bare XAUUSD for brokers without .r.
// SymbolSelect silently skips missing names — safe to list both conventions.
input string InpSymbols     = "EURUSD,GBPUSD,USDJPY,USDCHF,XAUUSD,XAUUSD.r,BTCUSD";
input string InpTimeframes  = "M15,H1,H4,D1";
input int    InpCandleCount = 50;

string g_dir = "mt5_arch";
datetime g_last_write = 0;

int OnInit()
  {
   FolderCreate(g_dir);
   // Second-based timer is more reliable under Wine than EventSetMillisecondTimer
   EventSetTimer((int)MathMax(1, InpTimerSec));
   Print("Mt5ArchBridge ON -> Files/", g_dir, " timer=", InpTimerSec, "s");
   WriteAll();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   WriteAll();
  }

void OnTick()
  {
   // Backup path if timer stalls under Wine (at most once per second)
   datetime now = TimeLocal();
   if(now != g_last_write)
      WriteAll();
  }

void WriteAll()
  {
   g_last_write = TimeLocal();
   WriteAccount();
   WriteTerminal();
   WriteSymbols();
   WriteCandles();
   WritePositions();
   int h = FileOpen(g_dir + "\\heartbeat.txt", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h != INVALID_HANDLE)
     {
      FileWriteString(h, IntegerToString((long)TimeLocal()) + " connected=" +
         (TerminalInfoInteger(TERMINAL_CONNECTED) ? "1" : "0"));
      FileClose(h);
     }
  }

string Esc(const string s)
  {
   string o = s;
   StringReplace(o, "\\", "\\\\");
   StringReplace(o, "\"", "\\\"");
   return o;
  }

void Put(const string rel, const string body)
  {
   int h = FileOpen(rel, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("Write fail ", rel, " err=", GetLastError());
      return;
     }
   FileWriteString(h, body);
   FileClose(h);
  }

// Under Wine, TERMINAL_CONNECTED is often false even when the trade session is
// healthy. Do NOT treat login+server alone as connected: those fields stay
// populated from the last cached account while balance/currency/leverage are 0.
// Live session heuristic: login+server AND at least one of currency/leverage/company.
bool IsEffectivelyConnected()
  {
   if(TerminalInfoInteger(TERMINAL_CONNECTED))
      return true;
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   if(login <= 0)
      return false;
   if(StringLen(AccountInfoString(ACCOUNT_SERVER)) == 0)
      return false;
   if(StringLen(AccountInfoString(ACCOUNT_CURRENCY)) > 0)
      return true;
   if(AccountInfoInteger(ACCOUNT_LEVERAGE) > 0)
      return true;
   if(StringLen(AccountInfoString(ACCOUNT_COMPANY)) > 0)
      return true;
   return false;
  }

void WriteAccount()
  {
   // Prefer trade-server fields; zeros + empty currency usually mean not fully connected
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   string currency = AccountInfoString(ACCOUNT_CURRENCY);
   int leverage = (int)AccountInfoInteger(ACCOUNT_LEVERAGE);
   bool connected = IsEffectivelyConnected();
   // Periodic diagnostics when still offline (avoid spam: once per 30s via last write stamp)
   static datetime s_last_diag = 0;
   datetime now = TimeLocal();
   if(!connected && (now - s_last_diag) >= 30)
     {
      s_last_diag = now;
      Print("Mt5ArchBridge account offline-ish login=", login,
            " bal=", DoubleToString(balance, 2),
            " cur=", currency,
            " lev=", leverage,
            " raw_conn=", (TerminalInfoInteger(TERMINAL_CONNECTED) ? "1" : "0"));
     }
   string j = "{";
   j += "\"login\":" + IntegerToString(login) + ",";
   j += "\"balance\":" + DoubleToString(balance, 2) + ",";
   j += "\"equity\":" + DoubleToString(equity, 2) + ",";
   j += "\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN), 2) + ",";
   j += "\"free_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) + ",";
   j += "\"margin_level\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL), 2) + ",";
   j += "\"currency\":\"" + Esc(currency) + "\",";
   j += "\"leverage\":" + IntegerToString(leverage) + ",";
   j += "\"server\":\"" + Esc(AccountInfoString(ACCOUNT_SERVER)) + "\",";
   j += "\"name\":\"" + Esc(AccountInfoString(ACCOUNT_NAME)) + "\",";
   j += "\"company\":\"" + Esc(AccountInfoString(ACCOUNT_COMPANY)) + "\",";
   j += "\"trade_mode\":" + IntegerToString((int)AccountInfoInteger(ACCOUNT_TRADE_MODE)) + ",";
   j += "\"trade_allowed\":" + (TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ? "true" : "false") + ",";
   j += "\"algo_allowed\":" + (MQLInfoInteger(MQL_TRADE_ALLOWED) ? "true" : "false") + ",";
   j += "\"terminal_connected\":" + (connected ? "true" : "false") + ",";
   j += "\"terminal_connected_raw\":" + (TerminalInfoInteger(TERMINAL_CONNECTED) ? "true" : "false");
   j += "}";
   Put(g_dir + "\\account.json", j);
  }

void WriteTerminal()
  {
   bool connected = IsEffectivelyConnected();
   string j = "{";
   j += "\"connected\":" + (connected ? "true" : "false") + ",";
   j += "\"connected_raw\":" + (TerminalInfoInteger(TERMINAL_CONNECTED) ? "true" : "false") + ",";
   j += "\"name\":\"" + Esc(TerminalInfoString(TERMINAL_NAME)) + "\",";
   j += "\"path\":\"" + Esc(TerminalInfoString(TERMINAL_PATH)) + "\",";
   j += "\"company\":\"" + Esc(TerminalInfoString(TERMINAL_COMPANY)) + "\",";
   j += "\"build\":" + IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD)) + ",";
   j += "\"trade_allowed\":" + (TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ? "true" : "false") + ",";
   j += "\"tradeapi_disabled\":false";
   j += "}";
   Put(g_dir + "\\terminal.json", j);
  }

void WriteSymbols()
  {
   string parts[];
   int n = StringSplit(InpSymbols, ',', parts);
   string j = "[";
   bool first = true;
   for(int i=0; i<n; i++)
     {
      string sym = parts[i];
      StringTrimLeft(sym);
      StringTrimRight(sym);
      if(StringLen(sym) == 0) continue;
      if(!SymbolSelect(sym, true)) continue;
      if(!first) j += ",";
      first = false;
      string mode_s = "FULL";
      long mode = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
      if(mode == SYMBOL_TRADE_MODE_DISABLED) mode_s = "DISABLED";
      else if(mode == SYMBOL_TRADE_MODE_LONGONLY) mode_s = "LONGONLY";
      else if(mode == SYMBOL_TRADE_MODE_SHORTONLY) mode_s = "SHORTONLY";
      else if(mode == SYMBOL_TRADE_MODE_CLOSEONLY) mode_s = "CLOSEONLY";
      j += "{";
      j += "\"symbol\":\"" + Esc(sym) + "\",";
      j += "\"min_lot\":" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), 4) + ",";
      j += "\"max_lot\":" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX), 4) + ",";
      j += "\"lot_step\":" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP), 4) + ",";
      j += "\"contract_size\":" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE), 2) + ",";
      j += "\"digits\":" + IntegerToString((int)SymbolInfoInteger(sym, SYMBOL_DIGITS)) + ",";
      j += "\"point\":" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_POINT), 8) + ",";
      j += "\"tick_value\":" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE), 8) + ",";
      j += "\"tick_size\":" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE), 8) + ",";
      j += "\"trade_mode\":\"" + mode_s + "\"";
      j += "}";
     }
   j += "]";
   Put(g_dir + "\\symbols.json", j);
  }

ENUM_TIMEFRAMES ParseTf(const string tf)
  {
   if(tf == "M1")  return PERIOD_M1;
   if(tf == "M5")  return PERIOD_M5;
   if(tf == "M15") return PERIOD_M15;
   if(tf == "M30") return PERIOD_M30;
   if(tf == "H1")  return PERIOD_H1;
   if(tf == "H4")  return PERIOD_H4;
   if(tf == "D1")  return PERIOD_D1;
   if(tf == "W1")  return PERIOD_W1;
   if(tf == "MN1") return PERIOD_MN1;
   return PERIOD_H1;
  }

void WriteCandles()
  {
   string syms[];
   string tfs[];
   int ns = StringSplit(InpSymbols, ',', syms);
   int nt = StringSplit(InpTimeframes, ',', tfs);
   for(int i=0; i<ns; i++)
     {
      string sym = syms[i];
      StringTrimLeft(sym); StringTrimRight(sym);
      if(StringLen(sym)==0) continue;
      if(!SymbolSelect(sym, true)) continue;
      int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      for(int j=0; j<nt; j++)
        {
         string tf = tfs[j];
         StringTrimLeft(tf); StringTrimRight(tf);
         if(StringLen(tf)==0) continue;
         MqlRates rates[];
         int copied = CopyRates(sym, ParseTf(tf), 0, InpCandleCount, rates);
         string jsn = "{\"symbol\":\"" + Esc(sym) + "\",\"timeframe\":\"" + tf + "\",\"candles\":[";
         for(int k=0; k<copied; k++)
           {
            if(k>0) jsn += ",";
            jsn += "{";
            jsn += "\"time\":\"" + TimeToString(rates[k].time, TIME_DATE|TIME_SECONDS) + "\",";
            jsn += "\"open\":" + DoubleToString(rates[k].open, digits) + ",";
            jsn += "\"high\":" + DoubleToString(rates[k].high, digits) + ",";
            jsn += "\"low\":" + DoubleToString(rates[k].low, digits) + ",";
            jsn += "\"close\":" + DoubleToString(rates[k].close, digits) + ",";
            jsn += "\"volume\":" + IntegerToString((long)rates[k].tick_volume);
            jsn += "}";
           }
         jsn += "]}";
         Put(g_dir + "\\candles_" + sym + "_" + tf + ".json", jsn);
        }
     }
  }

void WritePositions()
  {
   string j = "{\"positions\":[";
   bool first = true;
   int total = PositionsTotal();
   for(int i=0; i<total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!first) j += ",";
      first = false;
      string side = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? "buy" : "sell";
      j += "{";
      j += "\"ticket\":" + IntegerToString((long)ticket) + ",";
      j += "\"symbol\":\"" + Esc(PositionGetString(POSITION_SYMBOL)) + "\",";
      j += "\"side\":\"" + side + "\",";
      j += "\"volume\":" + DoubleToString(PositionGetDouble(POSITION_VOLUME), 4) + ",";
      j += "\"open_price\":" + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), 8) + ",";
      j += "\"stop_loss\":" + DoubleToString(PositionGetDouble(POSITION_SL), 8) + ",";
      j += "\"take_profit\":" + DoubleToString(PositionGetDouble(POSITION_TP), 8) + ",";
      j += "\"profit\":" + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2) + ",";
      j += "\"status\":\"open\"";
      j += "}";
     }
   j += "]}";
   Put(g_dir + "\\positions.json", j);
  }
//+------------------------------------------------------------------+

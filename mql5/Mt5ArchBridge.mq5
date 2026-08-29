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
#property version   "1.24"
#property description "JSON bridge → MQL5/Files/mt5_arch/  |  ONE chart only under Wine"
#property description "v1.20: timer-only + file lock (stops multi-EA freeze / err 5004)"
#property description "v1.21: per-bar spread in candles + one-shot deep history dump"
#property description "v1.23: explicit symbol registry — set InpBroker"
#property description "v1.24: request-gated deal dump (dump_deals.request → deals_export.csv)"

#include <FxSymbolRegistry.mqh>

input int    InpTimerSec    = 5;       // Snapshot interval (seconds). Use 5+ under Wine.
input string InpBroker      = "";      // required: vantage|fpmarkets|exness|wsf
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

string   g_dir = "mt5_arch";
datetime g_last_write = 0;
bool     g_is_writer = false;
string   g_lock_rel;

//+------------------------------------------------------------------+
//| Explicit registry only. Empty InpBroker or unknown name → "".    |
//| symbols.json / candle files use the *resolved* broker name.      |
//+------------------------------------------------------------------+
string ResolveSymbol(const string requested)
  {
   if(StringLen(InpBroker) == 0)
      return "";
   return FxResolveSymbol(InpBroker, requested);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(StringLen(InpBroker) == 0)
     {
      Print("Mt5ArchBridge: InpBroker is required (vantage|fpmarkets|exness|wsf)");
      return INIT_PARAMETERS_INCORRECT;
     }
   FolderCreate(g_dir);
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
   Print("Mt5ArchBridge WRITER v1.23 broker=", InpBroker, " ON ", _Symbol,
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
   WriteAll();
   // After heartbeat — HistorySelect can block on a fresh reconnect.
   DumpDealsIfRequested();
  }

//+------------------------------------------------------------------+
//| NO OnTick writes — tick storms + multi-EA = Wine freeze          |
//+------------------------------------------------------------------+
void OnTick()
  {
  }

//+------------------------------------------------------------------+
bool ClaimWriterLock()
  {
   if(!InpSingleWriter)
      return true;

   // Stale lock: older than 60s → steal
   if(FileIsExist(g_lock_rel, 0))
     {
      int hr = FileOpen(g_lock_rel, FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE);
      if(hr != INVALID_HANDLE)
        {
         string line = FileReadString(hr);
         FileClose(hr);
         // format: chartId|unixTime
         string parts[];
         int n = StringSplit(line, '|', parts);
         long owner = (n >= 1) ? StringToInteger(parts[0]) : 0;
         long ts    = (n >= 2) ? StringToInteger(parts[1]) : 0;
         long now   = (long)TimeLocal();
         if(owner == ChartID())
            return true;
         if(ts > 0 && (now - ts) < 60)
            return false; // live owner
         // stale — fall through and take
        }
     }

   int hw = FileOpen(g_lock_rel, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(hw == INVALID_HANDLE)
      return false;
   FileWriteString(hw, IntegerToString(ChartID()) + "|" + IntegerToString((long)TimeLocal()));
   FileClose(hw);
   return true;
  }

//+------------------------------------------------------------------+
void TouchWriterLock()
  {
   int hw = FileOpen(g_lock_rel, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(hw == INVALID_HANDLE)
      return;
   FileWriteString(hw, IntegerToString(ChartID()) + "|" + IntegerToString((long)TimeLocal()));
   FileClose(hw);
  }

//+------------------------------------------------------------------+
void ReleaseWriterLock()
  {
   if(!FileIsExist(g_lock_rel, 0))
      return;
   int hr = FileOpen(g_lock_rel, FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE);
   if(hr != INVALID_HANDLE)
     {
      string line = FileReadString(hr);
      FileClose(hr);
      string parts[];
      StringSplit(line, '|', parts);
      if(ArraySize(parts) >= 1 && StringToInteger(parts[0]) == ChartID())
         FileDelete(g_lock_rel);
     }
  }

//+------------------------------------------------------------------+
void WriteAll()
  {
   g_last_write = TimeLocal();
   WriteAccount();
   WriteTerminal();
   WriteSymbols();
   WriteCandles();
   WritePositions();
   Put(g_dir + "\\heartbeat.txt",
       IntegerToString((long)TimeLocal()) + " connected=" +
       (TerminalInfoInteger(TERMINAL_CONNECTED) ? "1" : "0") +
       " writer_chart=" + IntegerToString(ChartID()) +
       " symbol=" + _Symbol);
  }

//+------------------------------------------------------------------+
string Esc(const string s)
  {
   string o = s;
   StringReplace(o, "\\", "\\\\");
   StringReplace(o, "\"", "\\\"");
   return o;
  }

//+------------------------------------------------------------------+
//| Simple direct write + share flags; throttle error spam           |
//+------------------------------------------------------------------+
void Put(const string rel, const string body)
  {
   int h = FileOpen(rel, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE)
     {
      static datetime s_last_err = 0;
      datetime now = TimeLocal();
      if(now - s_last_err >= 60)
        {
         s_last_err = now;
         Print("Write fail ", rel, " err=", GetLastError(),
               " — remove EXTRA Mt5ArchBridge from other charts");
        }
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
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   string currency = AccountInfoString(ACCOUNT_CURRENCY);
   int leverage = (int)AccountInfoInteger(ACCOUNT_LEVERAGE);
   bool connected = IsEffectivelyConnected();
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
      string requested = parts[i];
      StringTrimLeft(requested);
      StringTrimRight(requested);
      if(StringLen(requested) == 0) continue;
      string sym = ResolveSymbol(requested);
      if(StringLen(sym) == 0) continue;
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
      string requested = syms[i];
      StringTrimLeft(requested); StringTrimRight(requested);
      if(StringLen(requested)==0) continue;
      string sym = ResolveSymbol(requested);
      if(StringLen(sym) == 0) continue;
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
            jsn += "\"volume\":" + IntegerToString((long)rates[k].tick_volume) + ",";
            jsn += "\"spread\":" + IntegerToString((long)rates[k].spread);
            jsn += "}";
           }
         jsn += "]}";
         Put(g_dir + "\\candles_" + sym + "_" + tf + ".json", jsn);
        }
     }
  }

//+------------------------------------------------------------------+
//| One-shot deep history dump: OHLC + per-bar spread (points).       |
//| MqlRates carries .spread, which the old Scripts/ExportXauHistory  |
//| discarded — without it the offline backtest is frictionless.      |
//| Row-at-a-time FileWrite: string concat over ~100k rows is O(n^2)  |
//| and would stall the EA thread under Wine.                         |
//+------------------------------------------------------------------+
void DumpHistoryOnce()
  {
   if(!InpDumpHistory)
      return;
   string marker = g_dir + "\\history_dump.done";
   if(FileIsExist(marker, 0))
      return;

   string requested = InpHistorySymbol;
   StringTrimLeft(requested); StringTrimRight(requested);
   string sym = ResolveSymbol(requested);
   if(StringLen(sym) == 0)
     {
      Print("DumpHistory: ResolveSymbol failed for ", requested,
            " (tried bare + m/.r/.m/#/pro) err=", GetLastError());
      return;
     }
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);

   string tfs[];
   int nt = StringSplit(InpHistoryTfs, ',', tfs);
   datetime to = TimeCurrent();
   datetime from = to - (datetime)((long)InpHistoryMonths * 30L * 24L * 3600L);

   string rel = g_dir + "\\history_" + sym + ".csv";
   int h = FileOpen(rel, FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      Print("DumpHistory: FileOpen failed err=", GetLastError());
      return;
     }
   FileWrite(h, "time,timeframe,symbol,open,high,low,close,tick_volume,spread");

   long total = 0;
   for(int j=0; j<nt; j++)
     {
      string tf = tfs[j];
      StringTrimLeft(tf); StringTrimRight(tf);
      if(StringLen(tf) == 0) continue;
      ENUM_TIMEFRAMES period = ParseTf(tf);

      // Deep history may need a server download; first CopyRates can come back
      // short or empty while it streams in.
      MqlRates rates[];
      ArraySetAsSeries(rates, false);
      int n = 0;
      for(int attempt=0; attempt<5; attempt++)
        {
         n = CopyRates(sym, period, from, to, rates);
         if(n > 0) break;
         Sleep(2000);
        }
      if(n <= 0)
        {
         Print("DumpHistory: no ", tf, " bars for ", sym, " err=", GetLastError());
         continue;
        }

      for(int k=0; k<n; k++)
        {
         string line = TimeToString(rates[k].time, TIME_DATE|TIME_MINUTES);
         line += "," + tf;
         line += "," + sym;
         line += "," + DoubleToString(rates[k].open, digits);
         line += "," + DoubleToString(rates[k].high, digits);
         line += "," + DoubleToString(rates[k].low, digits);
         line += "," + DoubleToString(rates[k].close, digits);
         line += "," + IntegerToString((long)rates[k].tick_volume);
         line += "," + IntegerToString((long)rates[k].spread);
         FileWrite(h, line);
        }
      total += n;
      Print("DumpHistory ", tf, " bars=", n,
            " from=", TimeToString(rates[0].time, TIME_DATE|TIME_MINUTES),
            " to=", TimeToString(rates[n-1].time, TIME_DATE|TIME_MINUTES));
     }
   FileClose(h);

   Put(marker, "dumped=" + IntegerToString(total) +
       " symbol=" + sym + " at=" + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS));
   Print("DumpHistory done rows=", total, " -> Files/", rel);
  }

//+------------------------------------------------------------------+
string DealTypeName(const long t)
  {
   if(t == DEAL_TYPE_BUY) return "buy";
   if(t == DEAL_TYPE_SELL) return "sell";
   if(t == DEAL_TYPE_BALANCE) return "balance";
   if(t == DEAL_TYPE_CREDIT) return "credit";
   if(t == DEAL_TYPE_CHARGE) return "charge";
   if(t == DEAL_TYPE_CORRECTION) return "correction";
   if(t == DEAL_TYPE_BONUS) return "bonus";
   if(t == DEAL_TYPE_COMMISSION) return "commission";
   return IntegerToString(t);
  }

//+------------------------------------------------------------------+
string DealEntryName(const long e)
  {
   if(e == DEAL_ENTRY_IN) return "in";
   if(e == DEAL_ENTRY_OUT) return "out";
   if(e == DEAL_ENTRY_INOUT) return "inout";
   if(e == DEAL_ENTRY_OUT_BY) return "out_by";
   return IntegerToString(e);
  }

//+------------------------------------------------------------------+
//| Request-gated deal dump for weekly account reports.               |
//| Touch Files/mt5_arch/dump_deals.request — next timer writes       |
//| deals_export.csv (14 days) and dump_deals.done. Does not trade.   |
//+------------------------------------------------------------------+
void DumpDealsIfRequested()
  {
   string req = g_dir + "\\dump_deals.request";
   if(!FileIsExist(req, 0))
      return;
   if(TimeCurrent() < D'2020.01.01')
     {
      Print("DumpDeals: skipped, trade server time not ready");
      return;
     }

   datetime to = TimeCurrent();
   datetime from = to - (datetime)(14L * 24L * 3600L);
   ResetLastError();
   if(!HistorySelect(from, to))
     {
      Print("DumpDeals: HistorySelect failed err=", GetLastError());
      return;
     }

   string rel = g_dir + "\\deals_export.csv";
   int h = FileOpen(rel, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      Print("DumpDeals: FileOpen failed err=", GetLastError());
      return;
     }
   FileWriteString(h, "time,deal_id,order_id,position_id,symbol,type,entry,volume,price,profit,swap,commission,fee,reason,magic,comment\n");

   int n = HistoryDealsTotal();
   int wrote = 0;
   for(int i = 0; i < n; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      string cmt = HistoryDealGetString(ticket, DEAL_COMMENT);
      StringReplace(cmt, ",", ";");
      StringReplace(cmt, "\n", " ");
      string line = TimeToString((datetime)HistoryDealGetInteger(ticket, DEAL_TIME), TIME_DATE|TIME_SECONDS);
      line += "," + IntegerToString((long)ticket);
      line += "," + IntegerToString((long)HistoryDealGetInteger(ticket, DEAL_ORDER));
      line += "," + IntegerToString((long)HistoryDealGetInteger(ticket, DEAL_POSITION_ID));
      line += "," + HistoryDealGetString(ticket, DEAL_SYMBOL);
      line += "," + DealTypeName(HistoryDealGetInteger(ticket, DEAL_TYPE));
      line += "," + DealEntryName(HistoryDealGetInteger(ticket, DEAL_ENTRY));
      line += "," + DoubleToString(HistoryDealGetDouble(ticket, DEAL_VOLUME), 4);
      line += "," + DoubleToString(HistoryDealGetDouble(ticket, DEAL_PRICE), 8);
      line += "," + DoubleToString(HistoryDealGetDouble(ticket, DEAL_PROFIT), 2);
      line += "," + DoubleToString(HistoryDealGetDouble(ticket, DEAL_SWAP), 2);
      line += "," + DoubleToString(HistoryDealGetDouble(ticket, DEAL_COMMISSION), 2);
      line += "," + DoubleToString(HistoryDealGetDouble(ticket, DEAL_FEE), 2);
      line += "," + IntegerToString((long)HistoryDealGetInteger(ticket, DEAL_REASON));
      line += "," + IntegerToString((long)HistoryDealGetInteger(ticket, DEAL_MAGIC));
      line += "," + cmt;
      FileWriteString(h, line + "\n");
      wrote++;
     }
   FileClose(h);
   FileDelete(req);
   Put(g_dir + "\\dump_deals.done",
       "rows=" + IntegerToString(wrote) +
       " from=" + TimeToString(from, TIME_DATE|TIME_SECONDS) +
       " to=" + TimeToString(to, TIME_DATE|TIME_SECONDS) +
       " at=" + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS));
   Print("DumpDeals done rows=", wrote, " -> Files/", rel);
  }

//+------------------------------------------------------------------+
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

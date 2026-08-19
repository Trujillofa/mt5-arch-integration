//+------------------------------------------------------------------+
//| TickCopyRangeExport.mqh                                          |
//| Live-safe CopyTicksRange dump. Never OrderSend. Does not kill.   |
//| Trigger: MQL5/Files/mt5_arch/export_ticks.request                |
//| Output:  MQL5/Files/mt5_arch/ticks/*.csv                         |
//+------------------------------------------------------------------+
#ifndef TICK_COPY_RANGE_EXPORT_MQH
#define TICK_COPY_RANGE_EXPORT_MQH

#ifndef TICK_EXPORT_MIN_HOURS
#define TICK_EXPORT_MIN_HOURS 24
#endif
#ifndef TICK_EXPORT_MAX_HOURS
#define TICK_EXPORT_MAX_HOURS 48
#endif
#ifndef TICK_EXPORT_DEFAULT_HOURS
#define TICK_EXPORT_DEFAULT_HOURS 36
#endif
#ifndef TICK_EXPORT_CHUNK_HOURS
#define TICK_EXPORT_CHUNK_HOURS 4
#endif
#ifndef TICK_EXPORT_MAX_ROWS
#define TICK_EXPORT_MAX_ROWS 2000000
#endif

//+------------------------------------------------------------------+
string TickExportTrim(string s)
  {
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
  }

//+------------------------------------------------------------------+
int TickExportServerUtcOffsetSec()
  {
   long delta = (long)(TimeCurrent() - TimeGMT());
   if(MathAbs(delta) >= 1800)
      return (int)delta;
   MqlDateTime sc, gc;
   TimeToStruct(TimeCurrent(), sc);
   TimeToStruct(TimeGMT(), gc);
   int dh = sc.hour - gc.hour;
   int dd = sc.day - gc.day;
   if(dd > 1)
      dd = -1;
   if(dd < -1)
      dd = 1;
   return (dh + 24 * dd) * 3600;
  }

//+------------------------------------------------------------------+
int TickExportClampHours(const int hours)
  {
   if(hours < TICK_EXPORT_MIN_HOURS)
      return TICK_EXPORT_MIN_HOURS;
   if(hours > TICK_EXPORT_MAX_HOURS)
      return TICK_EXPORT_MAX_HOURS;
   return hours;
  }

//+------------------------------------------------------------------+
bool TickExportReadRequest(string &symbol, string &broker, int &hours,
                           ulong &from_msc, ulong &to_msc)
  {
   symbol = "BTCUSD";
   broker = "fpmarkets";
   hours = TICK_EXPORT_DEFAULT_HOURS;
   from_msc = 0;
   to_msc = 0;
   string req = "mt5_arch\\export_ticks.request";
   if(!FileIsExist(req))
      return false;
   int h = FileOpen(req, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("TickExportReadRequest FileOpen fail err=", GetLastError());
      return false;
     }
   while(!FileIsEnding(h))
     {
      string line = TickExportTrim(FileReadString(h));
      if(StringLen(line) == 0)
         continue;
      int eq = StringFind(line, "=");
      if(eq <= 0)
         continue;
      string key = TickExportTrim(StringSubstr(line, 0, eq));
      string val = TickExportTrim(StringSubstr(line, eq + 1));
      StringToLower(key);
      if(key == "symbol")
         symbol = val;
      else if(key == "broker")
         broker = val;
      else if(key == "hours")
         hours = (int)StringToInteger(val);
      else if(key == "from_msc")
         from_msc = (ulong)StringToInteger(val);
      else if(key == "to_msc")
         to_msc = (ulong)StringToInteger(val);
     }
   FileClose(h);
   hours = TickExportClampHours(hours);
   return true;
  }

//+------------------------------------------------------------------+
void TickExportResolveWindow(const int hours, ulong &from_msc, ulong &to_msc)
  {
   ulong now_msc = (ulong)TimeCurrent() * 1000UL;
   ulong span = (ulong)hours * 3600UL * 1000UL;
   ulong max_span = (ulong)TICK_EXPORT_MAX_HOURS * 3600UL * 1000UL;
   if(to_msc == 0)
      to_msc = now_msc;
   if(from_msc == 0)
      from_msc = (to_msc > span ? to_msc - span : 0);
   if(to_msc <= from_msc)
     {
      to_msc = now_msc;
      from_msc = (to_msc > span ? to_msc - span : 0);
     }
   if(to_msc - from_msc > max_span)
      from_msc = to_msc - max_span;
  }

//+------------------------------------------------------------------+
string TickExportCsvLine(const MqlTick &tick, const int seq, const string symbol,
                         const string broker, const int offset_sec, const int digits)
  {
   string line = IntegerToString((long)tick.time_msc);
   line += "," + IntegerToString(seq);
   line += "," + DoubleToString(tick.bid, digits);
   line += "," + DoubleToString(tick.ask, digits);
   line += "," + DoubleToString(tick.last, digits);
   line += "," + IntegerToString((long)tick.volume);
   line += "," + DoubleToString(tick.volume_real, 8);
   line += "," + IntegerToString((int)tick.flags);
   line += "," + symbol;
   line += "," + broker;
   line += ",copyticks_csv";
   line += "," + IntegerToString(offset_sec);
   return line;
  }

//+------------------------------------------------------------------+
void TickExportWriteDone(const string rel_csv, const string symbol,
                         const string broker, const int n, const ulong from_msc,
                         const ulong to_msc, const int offset_sec, const string err)
  {
   int h = FileOpen("mt5_arch\\export_ticks.done", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("TickExportWriteDone FileOpen fail err=", GetLastError());
      return;
     }
   FileWriteString(h, "path=" + rel_csv + "\n");
   FileWriteString(h, "symbol=" + symbol + "\n");
   FileWriteString(h, "broker=" + broker + "\n");
   FileWriteString(h, "n=" + IntegerToString(n) + "\n");
   FileWriteString(h, "from_msc=" + IntegerToString((long)from_msc) + "\n");
   FileWriteString(h, "to_msc=" + IntegerToString((long)to_msc) + "\n");
   FileWriteString(h, "server_utc_offset_sec=" + IntegerToString(offset_sec) + "\n");
   FileWriteString(h, "source=copyticks_csv\n");
   FileWriteString(h, "error=" + err + "\n");
   FileClose(h);
  }

//+------------------------------------------------------------------+
int TickExportCopyRangeNow()
  {
   string symbol;
   string broker;
   int hours;
   ulong from_msc;
   ulong to_msc;
   bool had_req = TickExportReadRequest(symbol, broker, hours, from_msc, to_msc);
   symbol = TickExportTrim(symbol);
   broker = TickExportTrim(broker);
   if(StringLen(symbol) == 0)
      symbol = "BTCUSD";
   if(StringLen(broker) == 0)
      broker = "fpmarkets";
   hours = TickExportClampHours(hours);
   TickExportResolveWindow(hours, from_msc, to_msc);

   FolderCreate("mt5_arch");
   FolderCreate("mt5_arch\\ticks");

   if(!SymbolSelect(symbol, true))
     {
      Print("TickExportCopyRangeNow SymbolSelect fail ", symbol,
            " err=", GetLastError());
      TickExportWriteDone("", symbol, broker, 0, from_msc, to_msc,
                          TickExportServerUtcOffsetSec(), "symbol_select_failed");
      return 0;
     }

   int offset = TickExportServerUtcOffsetSec();
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(digits < 2)
      digits = 2;
   string rel = "mt5_arch\\ticks\\ticks_" + symbol + "_" + broker + ".csv";
   int hf = FileOpen(rel, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(hf == INVALID_HANDLE)
     {
      Print("TickExportCopyRangeNow FileOpen fail ", rel, " err=", GetLastError());
      TickExportWriteDone(rel, symbol, broker, 0, from_msc, to_msc, offset,
                          "file_open_failed");
      return 0;
     }
   FileWriteString(hf, "time_msc,seq,bid,ask,last,volume,volume_real,flags,symbol,broker,source,server_utc_offset_sec\n");

   ulong chunk = (ulong)TICK_EXPORT_CHUNK_HOURS * 3600UL * 1000UL;
   ulong cursor = from_msc;
   long last_msc = -1;
   int seq = 0;
   int wrote = 0;
   string err = "";
   while(cursor < to_msc && wrote < TICK_EXPORT_MAX_ROWS)
     {
      ulong end = cursor + chunk;
      if(end > to_msc)
         end = to_msc;
      MqlTick ticks[];
      ResetLastError();
      int n = CopyTicksRange(symbol, ticks, COPY_TICKS_ALL, cursor, end);
      if(n < 0)
        {
         err = "copyticks_failed_" + IntegerToString(GetLastError());
         Print("TickExportCopyRangeNow CopyTicksRange fail ", symbol,
               " err=", GetLastError(), " from=", cursor, " to=", end);
         break;
        }
      for(int i = 0; i < n && wrote < TICK_EXPORT_MAX_ROWS; i++)
        {
         if((long)ticks[i].time_msc == last_msc)
            seq++;
         else
           {
            last_msc = (long)ticks[i].time_msc;
            seq = 0;
           }
         FileWriteString(hf, TickExportCsvLine(ticks[i], seq, symbol, broker,
                                               offset, digits) + "\n");
         wrote++;
        }
      if(end == to_msc)
         break;
      cursor = end;
     }
   FileClose(hf);

   if(had_req)
      FileDelete("mt5_arch\\export_ticks.request");
   if(wrote >= TICK_EXPORT_MAX_ROWS)
      err = "truncated_max_rows";
   TickExportWriteDone(rel, symbol, broker, wrote, from_msc, to_msc, offset, err);
   Print("TickExportCopyRangeNow ", symbol, " ticks=", wrote,
         " from_msc=", from_msc, " to_msc=", to_msc,
         " had_request=", (had_req ? "yes" : "no"),
         " NO ORDERS");
   return wrote;
  }

#endif // TICK_COPY_RANGE_EXPORT_MQH
//+------------------------------------------------------------------+

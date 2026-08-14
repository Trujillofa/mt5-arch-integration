//+------------------------------------------------------------------+
//| ExportHtfFibParityFixture.mq5                                    |
//| Read-only dump for MQL5 ↔ Python HTF Fib parity.                 |
//|                                                                  |
//| Writes MQL5/Files/mt5_arch/parity/<tag>/                         |
//|   manifest.json, bars.csv, htf_bars.csv, buffers.csv, pivots.csv |
//|                                                                  |
//| Rules: chronological CopyRates (0=oldest), closed-bar signal,    |
//| fail-closed on short CopyBuffer, Wilder ATR14 via FxAtrSeries,   |
//| pivot confirm = center + right. Never calls OrderSend.           |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.00"
#property description "Export HTF Fib parity fixture — no orders"
#property script_show_inputs
#property strict

#include <ForexUtils.mqh>

input string InpSymbol          = "";                 // empty = chart symbol
input ENUM_TIMEFRAMES InpChartTf = PERIOD_CURRENT;    // bars / iCustom TF
input ENUM_TIMEFRAMES InpHtfTf  = PERIOD_H4;          // pivot scan TF
input int    InpBars            = 256;                // chart bars to copy
input int    InpHtfBars         = FX_HTF_PIVOT_SCAN_BARS; // must match indicator window
input int    InpLeft            = 5;
input int    InpRight           = 5;
input int    InpAtrPeriod       = 14;
input string InpIndicatorName   = "ForexHtfPivotsFib";
input int    InpSignalBuffer    = 8;                  // HTF Fib signal
input int    InpWaitMs          = 30000;              // BarsCalculated wait
input string InpOutDir          = "mt5_arch\\parity";

#define BUF_EMA_FAST   0
#define BUF_EMA_SLOW   1
#define BUF_EMA_BIAS   2
#define BUF_LONG       3
#define BUF_SHORT      4
#define BUF_FIB618     5
#define BUF_FIB786     6
#define BUF_SWING      7
#define BUF_SIGNAL     8
#define BUF_RSI        9
#define BUF_RSI_MA     10
#define BUF_COUNT      11

//+------------------------------------------------------------------+
int CopyRatesChrono(const string sym, const ENUM_TIMEFRAMES tf,
                    const int count, MqlRates &out[])
  {
   MqlRates tmp[];
   ArraySetAsSeries(tmp, true);
   int n = CopyRates(sym, tf, 0, count, tmp);
   if(n <= 0)
      return 0;
   ArrayResize(out, n);
   for(int i = 0; i < n; i++)
      out[i] = tmp[n - 1 - i];
   if(n >= 2 && out[0].time > out[n - 1].time)
     {
      for(int i = 0; i < n / 2; i++)
        {
         MqlRates sw = out[i];
         out[i] = out[n - 1 - i];
         out[n - 1 - i] = sw;
        }
     }
   return n;
  }

//+------------------------------------------------------------------+
bool CopyBufferChrono(const int handle, const int buf, const int count,
                      double &out[])
  {
   double tmp[];
   ArraySetAsSeries(tmp, true);
   ResetLastError();
   int n = CopyBuffer(handle, buf, 0, count, tmp);
   if(n != count)
     {
      Print("ExportHtfFibParity: short CopyBuffer buf=", buf,
            " copied=", n, " requested=", count, " err=", GetLastError());
      return false;
     }
   ArrayResize(out, n);
   for(int i = 0; i < n; i++)
      out[i] = tmp[n - 1 - i];
   return true;
  }

//+------------------------------------------------------------------+
bool IsPivotHighRates(const MqlRates &r[], const int n,
                      const int c, const int left, const int right)
  {
   if(c - left < 0 || c + right >= n)
      return false;
   double v = r[c].high;
   for(int i = c - left; i <= c + right; i++)
     {
      if(i == c) continue;
      if(r[i].high >= v) return false;
     }
   return true;
  }

bool IsPivotLowRates(const MqlRates &r[], const int n,
                     const int c, const int left, const int right)
  {
   if(c - left < 0 || c + right >= n)
      return false;
   double v = r[c].low;
   for(int i = c - left; i <= c + right; i++)
     {
      if(i == c) continue;
      if(r[i].low <= v) return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
string CsvNum(const double v, const int digits)
  {
   if(v == EMPTY_VALUE || v >= 1.0e100)
      return "";
   return DoubleToString(v, digits);
  }

string JsonEsc(const string s)
  {
   string o = s;
   StringReplace(o, "\\", "\\\\");
   StringReplace(o, "\"", "\\\"");
   return o;
  }

string TfName(const ENUM_TIMEFRAMES tf)
  {
   return EnumToString(tf);
  }

// Indicator OnInit writes mt5_arch/htf_fib_effective_<SYMBOL>.txt so this
// dump can pin left/right/fib_source to the iCustom instance (defaults only;
// a full input list returns 4002 on Vantage 6090).
bool ReadEffectiveConfig(const string sym, string &ver,
                         int &left, int &right, int &fib_src)
  {
   string path = "mt5_arch\\htf_fib_effective_" + sym + ".txt";
   int h = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return false;
   ver = "";
   left = right = fib_src = -1;
   while(!FileIsEnding(h))
     {
      string line = FileReadString(h);
      int eq = StringFind(line, "=");
      if(eq < 0)
         continue;
      string key = StringSubstr(line, 0, eq);
      string val = StringSubstr(line, eq + 1);
      if(key == "version")
         ver = val;
      else if(key == "left")
         left = (int)StringToInteger(val);
      else if(key == "right")
         right = (int)StringToInteger(val);
      else if(key == "fib_source")
         fib_src = (int)StringToInteger(val);
     }
   FileClose(h);
   return (left > 0 && right > 0 && (fib_src == 0 || fib_src == 1));
  }

//+------------------------------------------------------------------+
bool WriteBarsCsv(const string path, const MqlRates &r[], const int n)
  {
   int h = FileOpen(path, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(h == INVALID_HANDLE)
     {
      Print("FileOpen fail ", path, " err=", GetLastError());
      return false;
     }
   FileWrite(h, "idx", "time", "open", "high", "low", "close", "tick_volume");
   for(int i = 0; i < n; i++)
     {
      FileWrite(h,
                IntegerToString(i),
                TimeToString(r[i].time, TIME_DATE | TIME_SECONDS),
                DoubleToString(r[i].open, 8),
                DoubleToString(r[i].high, 8),
                DoubleToString(r[i].low, 8),
                DoubleToString(r[i].close, 8),
                IntegerToString((int)r[i].tick_volume));
     }
   FileClose(h);
   return true;
  }

//+------------------------------------------------------------------+
void WriteCopyFail(const string which, const int requested, const int copied)
  {
   FolderCreate("mt5_arch");
   FolderCreate("mt5_arch\\parity");
   string dir = "mt5_arch\\parity\\_failed";
   FolderCreate(dir);
   int h = FileOpen(dir + "\\manifest.json", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("ExportHtfFibParity: cannot write fail manifest err=", GetLastError());
      return;
     }
   FileWriteString(h, "{\n");
   FileWriteString(h, "  \"schema\": \"mql5-python-parity/v1\",\n");
   FileWriteString(h, "  \"source\": \"mql5_export\",\n");
   FileWriteString(h, "  \"export_ok\": false,\n");
   FileWriteString(h, "  \"export_error\": \"short copy " + which + "\",\n");
   FileWriteString(h, "  \"copy\": {\n");
   FileWriteString(h, "    \"" + which + "\": {\"requested\": " +
                  IntegerToString(requested) + ", \"copied\": " +
                  IntegerToString(copied) + "}\n");
   FileWriteString(h, "  }\n");
   FileWriteString(h, "}\n");
   FileClose(h);
   Print("ExportHtfFibParity: wrote fail manifest MQL5/Files/", dir,
         " ", which, " copied=", copied, " requested=", requested);
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   string sym = InpSymbol;
   if(StringLen(sym) == 0)
      sym = _Symbol;
   if(!SymbolSelect(sym, true))
     {
      Print("ExportHtfFibParity: SymbolSelect failed ", sym, " err=", GetLastError());
      return;
     }
   if(InpLeft < 1 || InpRight < 1 || InpBars < InpAtrPeriod + 2 ||
      InpSignalBuffer != BUF_SIGNAL)
     {
      Print("ExportHtfFibParity: refuse — left/right>=1, bars>=ATR+2, ",
            "signal buffer must be ", BUF_SIGNAL, " (got ", InpSignalBuffer, ")");
      return;
     }

   ENUM_TIMEFRAMES chart_tf = (InpChartTf == PERIOD_CURRENT) ? Period() : InpChartTf;
   if(chart_tf != InpHtfTf && InpHtfBars < FX_HTF_PIVOT_SCAN_BARS)
     {
      Print("ExportHtfFibParity: refuse InpHtfBars=", InpHtfBars,
            " < FX_HTF_PIVOT_SCAN_BARS=", FX_HTF_PIVOT_SCAN_BARS,
            " when HTF != chart");
      return;
     }
   FxEnsureHistory(sym, chart_tf, InpBars);
   FxEnsureHistory(sym, InpHtfTf, InpHtfBars);
   Sleep(400);

   MqlRates chart[];
   int n_req = InpBars;
   int n = CopyRatesChrono(sym, chart_tf, n_req, chart);
   if(n < n_req)
     {
      Print("ExportHtfFibParity: FAIL short CopyRates chart copied=", n,
            " requested=", n_req);
      WriteCopyFail("rates", n_req, n);
      return;
     }
   if(n >= 2 && chart[0].time >= chart[n - 1].time)
     {
      Print("ExportHtfFibParity: FAIL chart rates not chronological");
      return;
     }

   MqlRates htf[];
   int hn_req = InpHtfBars;
   int hn = CopyRatesChrono(sym, InpHtfTf, hn_req, htf);
   if(hn < hn_req)
     {
      Print("ExportHtfFibParity: FAIL short CopyRates HTF copied=", hn,
            " requested=", hn_req);
      WriteCopyFail("htf_rates", hn_req, hn);
      return;
     }
   if(chart_tf != InpHtfTf && n == hn)
     {
      Print("ExportHtfFibParity: refuse equal chart/HTF counts (", n,
            ") with different TFs — identity expansion is unsafe");
      return;
     }

   // Defaults only. A full iCustom input list returned 4002 on Vantage 6090
   // (wrong inner parameter) even though the same .ex5 loads on charts.
   // The indicator publishes effective left/right/fib_source; the verifier
   // asserts that sidecar equals this scan. Do not change InpLeft/InpRight
   // unless the chart indicator defaults match.
   int handle = iCustom(sym, chart_tf, InpIndicatorName);
   if(handle == INVALID_HANDLE)
     {
      Print("ExportHtfFibParity: iCustom failed '", InpIndicatorName,
            "' err=", GetLastError());
      return;
     }

   int waited = 0;
   int calc = BarsCalculated(handle);
   while(calc < n && waited < InpWaitMs)
     {
      Sleep(200);
      waited += 200;
      calc = BarsCalculated(handle);
     }
   if(calc < n)
     {
      Print("ExportHtfFibParity: FAIL BarsCalculated=", calc, " need=", n);
      IndicatorRelease(handle);
      return;
     }

   string ind_ver = "";
   int ind_left = -1, ind_right = -1, ind_src = -1;
   bool cfg_ok = ReadEffectiveConfig(sym, ind_ver, ind_left, ind_right, ind_src);
   if(!cfg_ok)
      Print("ExportHtfFibParity: WARN missing indicator sidecar ",
            "mt5_arch\\htf_fib_effective_", sym, ".txt");

   double ema_fast[], ema_slow[], ema_bias[], arrow_l[], arrow_s[];
   double fib618[], fib786[], swing[], signal[], rsi[], rsi_ma[];
   if(!CopyBufferChrono(handle, BUF_EMA_FAST, n, ema_fast) ||
      !CopyBufferChrono(handle, BUF_EMA_SLOW, n, ema_slow) ||
      !CopyBufferChrono(handle, BUF_EMA_BIAS, n, ema_bias) ||
      !CopyBufferChrono(handle, BUF_LONG, n, arrow_l) ||
      !CopyBufferChrono(handle, BUF_SHORT, n, arrow_s) ||
      !CopyBufferChrono(handle, BUF_FIB618, n, fib618) ||
      !CopyBufferChrono(handle, BUF_FIB786, n, fib786) ||
      !CopyBufferChrono(handle, BUF_SWING, n, swing) ||
      !CopyBufferChrono(handle, BUF_SIGNAL, n, signal) ||
      !CopyBufferChrono(handle, BUF_RSI, n, rsi) ||
      !CopyBufferChrono(handle, BUF_RSI_MA, n, rsi_ma))
     {
      IndicatorRelease(handle);
      WriteCopyFail("buffers", n, 0);
      return;
     }
   IndicatorRelease(handle);

   // Forming-bar contract: indicator must leave signal 0 on the last bar.
   if(signal[n - 1] != 0.0 && signal[n - 1] != EMPTY_VALUE)
     {
      Print("ExportHtfFibParity: FAIL forming-bar signal=",
            signal[n - 1], " (closed-bar only)");
      return;
     }

   double highs[], lows[], closes[], atr[];
   ArrayResize(highs, n);
   ArrayResize(lows, n);
   ArrayResize(closes, n);
   for(int i = 0; i < n; i++)
     {
      highs[i]  = chart[i].high;
      lows[i]   = chart[i].low;
      closes[i] = chart[i].close;
     }
   if(!FxAtrSeries(highs, lows, closes, n, InpAtrPeriod, atr))
     {
      Print("ExportHtfFibParity: FAIL FxAtrSeries");
      return;
     }

   string tag = sym + "_" + TfName(chart_tf) + "_" +
                TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + "_" +
                IntegerToString((int)TimeCurrent());
   StringReplace(tag, " ", "_");
   StringReplace(tag, ":", "");
   StringReplace(tag, ".", "");
   string dir = InpOutDir + "\\" + tag;
   FolderCreate("mt5_arch");
   FolderCreate(InpOutDir);
   if(FileIsExist(dir + "\\manifest.json"))
     {
      Print("ExportHtfFibParity: refuse overwrite of completed ", dir);
      return;
     }
   if(!FolderCreate(dir))
      Print("ExportHtfFibParity: FolderCreate ", dir,
            " err=", GetLastError(), " (ok if exists)");
   if(cfg_ok)
      FileCopy("mt5_arch\\htf_fib_effective_" + sym + ".txt", 0,
               dir + "\\htf_fib_effective.txt", FILE_REWRITE);

   if(!WriteBarsCsv(dir + "\\bars.csv", chart, n))
      return;
   if(!WriteBarsCsv(dir + "\\htf_bars.csv", htf, hn))
      return;

   int hb = FileOpen(dir + "\\buffers.csv",
                     FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(hb == INVALID_HANDLE)
     {
      Print("buffers.csv open fail err=", GetLastError());
      return;
     }
   FileWrite(hb, "idx", "time", "atr14", "fib_618", "fib_786",
             "swing_dir", "signal", "ema_fast", "ema_slow", "ema_bias",
             "rsi", "rsi_ma");
   for(int i = 0; i < n; i++)
     {
      FileWrite(hb,
                IntegerToString(i),
                TimeToString(chart[i].time, TIME_DATE | TIME_SECONDS),
                CsvNum(atr[i], 8),
                CsvNum(fib618[i], 8),
                CsvNum(fib786[i], 8),
                CsvNum(swing[i], 8),
                CsvNum(signal[i], 8),
                CsvNum(ema_fast[i], 8),
                CsvNum(ema_slow[i], 8),
                CsvNum(ema_bias[i], 8),
                CsvNum(rsi[i], 8),
                CsvNum(rsi_ma[i], 8));
     }
   FileClose(hb);

   int hp = FileOpen(dir + "\\pivots.csv",
                     FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(hp == INVALID_HANDLE)
     {
      Print("pivots.csv open fail err=", GetLastError());
      return;
     }
   FileWrite(hp, "center_idx", "confirm_idx", "center_time", "confirm_time",
             "ptype", "price");
   int n_pivots = 0;
   int hn_closed = (hn > 0 ? hn - 1 : 0);
   for(int c = InpLeft; c <= hn_closed - 1 - InpRight; c++)
     {
      bool isH = IsPivotHighRates(htf, hn_closed, c, InpLeft, InpRight);
      bool isL = IsPivotLowRates(htf, hn_closed, c, InpLeft, InpRight);
      if(isH && isL)
         continue;
      int confirm = c + InpRight;
      if(isH)
        {
         FileWrite(hp,
                   IntegerToString(c),
                   IntegerToString(confirm),
                   TimeToString(htf[c].time, TIME_DATE | TIME_SECONDS),
                   TimeToString(htf[confirm].time, TIME_DATE | TIME_SECONDS),
                   "1",
                   DoubleToString(htf[c].high, 8));
         n_pivots++;
        }
      else if(isL)
        {
         FileWrite(hp,
                   IntegerToString(c),
                   IntegerToString(confirm),
                   TimeToString(htf[c].time, TIME_DATE | TIME_SECONDS),
                   TimeToString(htf[confirm].time, TIME_DATE | TIME_SECONDS),
                   "-1",
                   DoubleToString(htf[c].low, 8));
         n_pivots++;
        }
     }
   FileClose(hp);

   int cmp0 = 0;
   while(cmp0 < n && chart[cmp0].time < htf[0].time)
      cmp0++;

   string man = dir + "\\manifest.json";
   int hm = FileOpen(man, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(hm == INVALID_HANDLE)
     {
      Print("manifest.json open fail err=", GetLastError());
      return;
     }
   FileWriteString(hm, "{\n");
   FileWriteString(hm, "  \"schema\": \"mql5-python-parity/v1\",\n");
   FileWriteString(hm, "  \"source\": \"mql5_export\",\n");
   FileWriteString(hm, "  \"symbol\": \"" + JsonEsc(sym) + "\",\n");
   FileWriteString(hm, "  \"chart_tf\": \"" + TfName(chart_tf) + "\",\n");
   FileWriteString(hm, "  \"htf_tf\": \"" + TfName(InpHtfTf) + "\",\n");
   FileWriteString(hm, "  \"left\": " + IntegerToString(InpLeft) + ",\n");
   FileWriteString(hm, "  \"right\": " + IntegerToString(InpRight) + ",\n");
   FileWriteString(hm, "  \"atr_period\": " + IntegerToString(InpAtrPeriod) + ",\n");
   FileWriteString(hm, "  \"atr_method\": \"wilder\",\n");
   FileWriteString(hm, "  \"signal_buffer\": " + IntegerToString(BUF_SIGNAL) + ",\n");
   FileWriteString(hm, "  \"signal_shift\": 1,\n");
   FileWriteString(hm, "  \"closed_bar_only\": true,\n");
   FileWriteString(hm, "  \"signal_kind\": \"indicator_buffer\",\n");
   FileWriteString(hm, "  \"export_ok\": true,\n");
   FileWriteString(hm, "  \"htf_scan_bars\": " + IntegerToString(FX_HTF_PIVOT_SCAN_BARS) + ",\n");
   FileWriteString(hm, "  \"compare_from_chart_idx\": " + IntegerToString(cmp0) + ",\n");
   FileWriteString(hm, "  \"indicator\": \"" + JsonEsc(InpIndicatorName) + "\",\n");
   FileWriteString(hm, "  \"indicator_config_ok\": " + (cfg_ok ? "true" : "false") + ",\n");
   FileWriteString(hm, "  \"indicator_version\": \"" + JsonEsc(ind_ver) + "\",\n");
   FileWriteString(hm, "  \"indicator_left\": " + IntegerToString(ind_left) + ",\n");
   FileWriteString(hm, "  \"indicator_right\": " + IntegerToString(ind_right) + ",\n");
   FileWriteString(hm, "  \"indicator_fib_source\": " + IntegerToString(ind_src) + ",\n");
   FileWriteString(hm, "  \"copy\": {\n");
   FileWriteString(hm, "    \"rates\": {\"requested\": " + IntegerToString(n_req) +
                  ", \"copied\": " + IntegerToString(n) + "},\n");
   FileWriteString(hm, "    \"htf_rates\": {\"requested\": " + IntegerToString(hn_req) +
                  ", \"copied\": " + IntegerToString(hn) + "},\n");
   FileWriteString(hm, "    \"buffers\": {\n");
   for(int b = 0; b < BUF_COUNT; b++)
     {
      string comma = (b + 1 < BUF_COUNT) ? "," : "";
      FileWriteString(hm, "      \"" + IntegerToString(b) +
                      "\": {\"requested\": " + IntegerToString(n) +
                      ", \"copied\": " + IntegerToString(n) + "}" + comma + "\n");
     }
   FileWriteString(hm, "    }\n");
   FileWriteString(hm, "  },\n");
   FileWriteString(hm, "  \"buffer_map\": {\n");
   FileWriteString(hm, "    \"0\": \"ema_fast\", \"1\": \"ema_slow\", \"2\": \"ema_bias\",\n");
   FileWriteString(hm, "    \"3\": \"long_arrow\", \"4\": \"short_arrow\",\n");
   FileWriteString(hm, "    \"5\": \"fib_618\", \"6\": \"fib_786\",\n");
   FileWriteString(hm, "    \"7\": \"swing_dir\", \"8\": \"signal\",\n");
   FileWriteString(hm, "    \"9\": \"rsi\", \"10\": \"rsi_ma\"\n");
   FileWriteString(hm, "  },\n");
   FileWriteString(hm, "  \"n_bars\": " + IntegerToString(n) + ",\n");
   FileWriteString(hm, "  \"n_htf_bars\": " + IntegerToString(hn) + ",\n");
   FileWriteString(hm, "  \"n_pivots\": " + IntegerToString(n_pivots) + ",\n");
   FileWriteString(hm, "  \"abs_tol\": 1e-5,\n");
   FileWriteString(hm, "  \"server_time\": \"" +
                  TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + "\"\n");
   FileWriteString(hm, "}\n");
   FileClose(hm);

   Print("ExportHtfFibParity: wrote MQL5/Files/", dir,
         " bars=", n, " htf=", hn, " pivots=", n_pivots,
         " signal_buf=", BUF_SIGNAL, " NO ORDERS");
  }
//+------------------------------------------------------------------+

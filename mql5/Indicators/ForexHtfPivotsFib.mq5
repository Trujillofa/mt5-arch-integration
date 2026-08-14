//+------------------------------------------------------------------+
//| ForexHtfPivotsFib.mq5                                            |
//| Port of manual-trading-agent HTF Pivots + Fib + EMA (TradingView)|
//|                                                                  |
//| Confirmed 4H / Daily pivots (left/right wings, non-repaint)      |
//| Directional Fib retracement + golden zone (61.8–78.6)            |
//| EMA50/200 + optional RSI confluence markers                      |
//|                                                                  |
//| Chart: use at or below H4 (M15/H1 recommended).                  |
//| Fib source falls back to Daily if chart TF > H4.                 |
//|                                                                  |
//| iCustom signal buffer = 8  (+1 long / -1 short / 0)              |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.45"
#property description "HTF pivots + Fib v1.45 (confirm-close fib snaps)"
#property description "Non-repaint pivots. Signal buffer 8. RSI=9 RSI-MA=10."
#property strict

// Single source of truth for the version shown at runtime. The on-chart panel used to
// hardcode "v1.31" while #property/Print said 1.41, so the one thing the panel exists
// to prove -- that the recompile actually took -- was the one thing it got wrong.
// #property takes a literal and cannot read this, so keep the two in step by hand.
// 1.42: skip ObjectsDeleteAll on REASON_CHARTCHANGE (Wine win32u freeze trigger).
// 1.43: S/R levels imported from .tpl templates (yellow/white/blue by relevance).
// 1.44: stamp fib snaps at confirm-bar open; no global FibAt fallback.
// 1.45: stamp at confirm-bar close; FibAt sees chart-bar close (MTF parity).
#define HTF_FIB_VER "1.45"

#property indicator_chart_window
#property indicator_buffers 11
#property indicator_plots   5

#property indicator_label1  "EMA Fast"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDeepSkyBlue
#property indicator_style1  STYLE_SOLID
#property indicator_width1  1

#property indicator_label2  "EMA Slow"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrOrange
#property indicator_style2  STYLE_SOLID
#property indicator_width2  2

#property indicator_label3  "EMA Bias"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrGold
#property indicator_style3  STYLE_SOLID
#property indicator_width3  2

#property indicator_label4  "Long"
#property indicator_type4   DRAW_ARROW
#property indicator_color4  clrLime
#property indicator_width4  2

#property indicator_label5  "Short"
#property indicator_type5   DRAW_ARROW
#property indicator_color5  clrOrangeRed
#property indicator_width5  2

#include <ForexUtils.mqh>
#include <FxSymbolRegistry.mqh>

//+------------------------------------------------------------------+
enum ENUM_FIB_SOURCE
  {
   FIB_SOURCE_H4    = 0, // 4H pivots
   FIB_SOURCE_DAILY = 1  // Daily pivots
  };

//+------------------------------------------------------------------+
input group "=== Trading mode ==="
input ENUM_FX_TRADING_MODE InpTradingMode = FX_MODE_INTRADAY; // INTRADAY=20/50+200 | SWING=50/200
input bool   InpManualOverride   = false; // true = session/fib/EMA from inputs below

input group "=== EMAs (ignored unless Manual override) ==="
input int    InpEmaFast          = 20;     // Fast (manual) — mode 20 or 50
input int    InpEmaSlow          = 50;     // Slow (manual) — mode 50 or 200
input int    InpEmaBias          = 200;    // Bias regime filter
input bool   InpShowEmas         = true;   // Draw fast/slow
input bool   InpShowBiasEma      = true;   // Draw bias when != slow

input group "=== HTF Pivots 4H ==="
input int    InpLeft4h           = 5;      // Left bars
input int    InpRight4h          = 5;      // Right bars (confirm delay)
input bool   InpShow4hLines      = true;
input bool   InpShow4hLabels     = false;
input color  InpCol4hHigh        = clrTomato;
input color  InpCol4hLow         = clrLimeGreen;

input group "=== HTF Pivots Daily ==="
input int    InpLeftDaily        = 5;
input int    InpRightDaily       = 5;
input bool   InpShowDailyLines   = true;
input bool   InpShowDailyLabels  = false;
input color  InpColDailyHigh     = clrMaroon;
input color  InpColDailyLow      = clrLime;

input group "=== Fibonacci ==="
input ENUM_FIB_SOURCE InpFibSource = FIB_SOURCE_H4;
input bool   InpShowFib          = true;
input bool   InpShowFib236       = false;
input bool   InpShowFib382       = false;
input bool   InpShowFib500       = true;
input bool   InpShowFib618       = true;
input bool   InpShowFib786       = true;
input bool   InpShowGoldenZone   = true;
input color  InpColFib500        = clrOrange;
input color  InpColFib618        = clrMediumOrchid;
input color  InpColFib786        = clrTomato;
input color  InpColGolden        = C'40,40,0';  // zone fill (subtle)

input group "=== RSI + RSI MA confluence ==="
input bool           InpShowMarkers    = true;
input int            InpRsiPeriod      = 14;       // RSI period
input int            InpRsiMaPeriod    = 14;       // MA of RSI (signal line)
input ENUM_MA_METHOD InpRsiMaMethod    = MODE_SMA; // MA method on RSI
input int            InpRsiLongMax     = 35;       // Long RSI max (oversold zone)
input int            InpRsiShortMin    = 65;       // Short RSI min (overbought)
input bool           InpUseRsiMaFilter = true;     // Require RSI vs RSI-MA alignment
input bool           InpRequireCandle  = false;    // Require bullish/bearish candle
input bool           InpRequireGoldenZone = true;  // false = research: skip Fib 61.8–78.6
input bool           InpRequireBiasFilter = true;  // false = research: skip EMA200 regime

input group "=== Display ==="
input bool   InpShowPanel        = true;
input double InpArrowOffsetPips  = 4.0;

input group "=== S/R levels (imported from .tpl templates) ==="
// Default OFF under Wine: each HLINE is a GDI object; FP freezes correlated with
// object churn. Enable per chart only when you need the imported zones.
input bool            InpShowSrLevels = false;             // Draw imported S/R levels
input string          InpSrFile       = "forex_sr_levels.csv"; // In MQL5\Files (or Common\Files)
input bool            InpSrShowHigh   = true;              // Show HIGH tier (yellow)
input bool            InpSrShowMed    = true;              // Show MED tier (white)
input bool            InpSrShowLow    = false;             // LOW (M5/M1) — noisy; off by default
input color           InpSrColHigh    = clrYellow;         // HIGH relevance (MN/W1/D1/H4)
input color           InpSrColMed     = clrWhite;          // MED relevance (H1/M30/M15)
input color           InpSrColLow     = clrDodgerBlue;     // LOW relevance (M5/M1)
input ENUM_LINE_STYLE InpSrStyle      = STYLE_DOT;         // Line style (templates use dotted)
input bool            InpSrShowLabels = false;             // Attach tier text to each line
input int             InpSrMaxLevels  = 80;                // Hard cap (Wine GDI guard)

//+------------------------------------------------------------------+
//| Buffers: 0 fast | 1 slow | 2 bias | 3 Long | 4 Short             |
//|          5 fib618 | 6 fib786 | 7 swingDir | 8 signal             |
//|          9 RSI | 10 RSI-MA                                       |
//+------------------------------------------------------------------+
double BufEmaFast[];
double BufEmaSlow[];
double BufEmaBias[];
double BufLong[];
double BufShort[];
double BufFib618[];
double BufFib786[];
double BufSwingDir[];
double BufSignal[];
double BufRsi[];
double BufRsiMa[];

int g_hEmaFast = INVALID_HANDLE;
int g_hEmaSlow = INVALID_HANDLE;
int g_hEmaBias = INVALID_HANDLE;
int g_hRsi     = INVALID_HANDLE;

string g_pfx;
FxModeSettings g_mode;

//--- latest confirmed pivots
double   g_ph4 = 0, g_pl4 = 0, g_phD = 0, g_plD = 0;
datetime g_th4 = 0, g_tl4 = 0, g_thD = 0, g_tlD = 0;
datetime g_seen_h4 = 0, g_seen_l4 = 0, g_seen_hD = 0, g_seen_lD = 0;

//--- swing / fib state (latest)
int      g_lastPivotType = 0;   // 0 unset, 1 high, -1 low
double   g_lastPivotPrice = 0;
datetime g_lastPivotTime  = 0;
double   g_swingHigh = 0, g_swingLow = 0;
datetime g_swingHighTime = 0, g_swingLowTime = 0;
int      g_swingDir = 0;        // 1 bull low->high, -1 bear high->low
double   g_fib236 = 0, g_fib382 = 0, g_fib500 = 0, g_fib618 = 0, g_fib786 = 0;
bool     g_fibValid = false;

//--- historical fib snapshots for correct per-bar signals in tester
struct FibSnap
  {
   datetime t0;    // valid from this time (inclusive)
   int      dir;
   double   f618;
   double   f786;
   bool     valid;
  };
FibSnap g_snaps[];
int     g_nsnaps = 0;

//--- imported S/R levels (static snapshot from hand-drawn .tpl zones)
#define SR_TIER_LOW  0
#define SR_TIER_MED  1
#define SR_TIER_HIGH 2

struct SrLevel
  {
   double price;
   int    tier;   // SR_TIER_*
   string tf;     // template timeframe the line was drawn on
  };
SrLevel g_sr[];
int     g_nsr       = 0;
bool    g_sr_dirty  = true;   // reload/redraw pending

//+------------------------------------------------------------------+
void ApplyTradingMode()
  {
   int man_fib = (InpFibSource == FIB_SOURCE_DAILY) ? 1 : 0;
   FxResolveTradingMode(InpTradingMode,
                        InpManualOverride,
                        true,
                        true, true, true, true,
                        0.0,
                        man_fib,
                        InpManualOverride, // manual EMA when full manual override
                        InpEmaFast, InpEmaSlow, InpEmaBias,
                        g_mode);
  }

int EffectiveFibSource()
  {
   // 0=H4 1=Daily from resolved mode (unless manual override keeps InpFibSource)
   if(InpManualOverride)
      return (InpFibSource == FIB_SOURCE_DAILY) ? 1 : 0;
   return g_mode.fib_source;
  }

bool EffectiveShow4h()
  {
   if(InpManualOverride)
      return InpShow4hLines;
   return g_mode.show_4h_pivots && InpShow4hLines;
  }

datetime BarCloseTime(const datetime bar_open, const ENUM_TIMEFRAMES tf)
  {
   int sec = PeriodSeconds(tf);
   if(sec <= 0)
      sec = PeriodSeconds(_Period);
   return bar_open + (datetime)sec;
  }

datetime ChartBarClose(const datetime bar_open)
  {
   return BarCloseTime(bar_open, PERIOD_CURRENT);
  }

void WriteEffectiveConfig()
  {
   bool use4h = (PeriodSeconds(PERIOD_CURRENT) <= PeriodSeconds(PERIOD_H4));
   bool fib_h4 = (EffectiveFibSource() == 0) && use4h;
   int left  = fib_h4 ? InpLeft4h  : InpLeftDaily;
   int right = fib_h4 ? InpRight4h : InpRightDaily;
   int src   = fib_h4 ? 0 : 1;
   FolderCreate("mt5_arch");
   string path = "mt5_arch\\htf_fib_effective_" + _Symbol + ".txt";
   int h = FileOpen(path, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("ForexHtfPivotsFib: effective-config write fail err=", GetLastError());
      return;
     }
   FileWriteString(h, "version=" + HTF_FIB_VER + "\n");
   FileWriteString(h, "symbol=" + _Symbol + "\n");
   FileWriteString(h, "chart_tf=" + EnumToString(Period()) + "\n");
   FileWriteString(h, "left=" + IntegerToString(left) + "\n");
   FileWriteString(h, "right=" + IntegerToString(right) + "\n");
   FileWriteString(h, "fib_source=" + IntegerToString(src) + "\n");
   FileWriteString(h, "fib_source_name=" + (src == 0 ? "H4" : "D1") + "\n");
   FileClose(h);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpLeft4h < 1 || InpRight4h < 1 || InpLeftDaily < 1 || InpRightDaily < 1 ||
      InpRsiPeriod < 1 || InpRsiMaPeriod < 1)
      return INIT_PARAMETERS_INCORRECT;

   ApplyTradingMode();
   // Strategy Tester often has H1 only until MTF bars are requested
   FxEnsureMtfHistory(_Symbol, 500);
   WriteEffectiveConfig();
   Print("ForexHtfPivotsFib v" + HTF_FIB_VER + " mode=", g_mode.mode_name,
         " EMA ", g_mode.ema_fast, "/", g_mode.ema_slow, " bias=", g_mode.ema_bias,
         " fib=", (EffectiveFibSource() == 1 ? "Daily" : "H4"),
         " show4h=", (EffectiveShow4h() ? "yes" : "no"),
         " hint=", g_mode.chart_hint,
         " zone=", (InpRequireGoldenZone ? "on" : "off"),
         " biasF=", (InpRequireBiasFilter ? "on" : "off"));

   SetIndexBuffer(0, BufEmaFast,  INDICATOR_DATA);
   SetIndexBuffer(1, BufEmaSlow,  INDICATOR_DATA);
   SetIndexBuffer(2, BufEmaBias,  INDICATOR_DATA);
   SetIndexBuffer(3, BufLong,     INDICATOR_DATA);
   SetIndexBuffer(4, BufShort,    INDICATOR_DATA);
   SetIndexBuffer(5, BufFib618,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(6, BufFib786,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(7, BufSwingDir, INDICATOR_CALCULATIONS);
   SetIndexBuffer(8, BufSignal,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(9, BufRsi,      INDICATOR_CALCULATIONS);
   SetIndexBuffer(10, BufRsiMa,   INDICATOR_CALCULATIONS);

   ArraySetAsSeries(BufEmaFast, false);
   ArraySetAsSeries(BufEmaSlow, false);
   ArraySetAsSeries(BufEmaBias, false);
   ArraySetAsSeries(BufLong, false);
   ArraySetAsSeries(BufShort, false);
   ArraySetAsSeries(BufFib618, false);
   ArraySetAsSeries(BufFib786, false);
   ArraySetAsSeries(BufSwingDir, false);
   ArraySetAsSeries(BufSignal, false);
   ArraySetAsSeries(BufRsi, false);
   ArraySetAsSeries(BufRsiMa, false);

   int begin = MathMax(g_mode.ema_slow, g_mode.ema_bias);
   for(int p = 0; p < 5; p++)
     {
      PlotIndexSetInteger(p, PLOT_DRAW_BEGIN, begin);
      PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
     }
   PlotIndexSetInteger(3, PLOT_ARROW, 233);
   PlotIndexSetInteger(4, PLOT_ARROW, 234);

   IndicatorSetInteger(INDICATOR_DIGITS, _Digits);
   IndicatorSetString(INDICATOR_SHORTNAME,
                      StringFormat("HTF Fib %s EMA(%d/%d)+%d",
                                   g_mode.mode_name,
                                   g_mode.ema_fast, g_mode.ema_slow, g_mode.ema_bias));

   g_hEmaFast = iMA(_Symbol, PERIOD_CURRENT, g_mode.ema_fast, 0, MODE_EMA, PRICE_CLOSE);
   g_hEmaSlow = iMA(_Symbol, PERIOD_CURRENT, g_mode.ema_slow, 0, MODE_EMA, PRICE_CLOSE);
   g_hEmaBias = iMA(_Symbol, PERIOD_CURRENT, g_mode.ema_bias, 0, MODE_EMA, PRICE_CLOSE);
   g_hRsi     = iRSI(_Symbol, PERIOD_CURRENT, InpRsiPeriod, PRICE_CLOSE);
   if(g_hEmaFast == INVALID_HANDLE || g_hEmaSlow == INVALID_HANDLE ||
      g_hEmaBias == INVALID_HANDLE || g_hRsi == INVALID_HANDLE)
      return INIT_FAILED;

   g_pfx = "HTFFIB_" + IntegerToString(ChartID()) + "_";
   // Do NOT ObjectsDeleteAll here — param changes call OnInit after OnDeinit(REASON_PARAMETERS).
   // Mass object delete under Wine freezes the UI when tweaking EMAs.

   // OnInit re-runs on both REASON_PARAMETERS and REASON_CHARTCHANGE, so this is
   // also what re-reads the table after a symbol switch or an input tweak.
   LoadSrLevels();
   g_sr_dirty = true;
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_hEmaFast != INVALID_HANDLE) IndicatorRelease(g_hEmaFast);
   if(g_hEmaSlow != INVALID_HANDLE) IndicatorRelease(g_hEmaSlow);
   if(g_hEmaBias != INVALID_HANDLE) IndicatorRelease(g_hEmaBias);
   if(g_hRsi     != INVALID_HANDLE) IndicatorRelease(g_hRsi);

   // Only wipe drawings when really leaving the chart — not on EMA/input tweak,
   // and NOT on REASON_CHARTCHANGE.
   //
   // REASON_CHARTCHANGE fires on every symbol *and timeframe* switch, and g_pfx is
   // keyed on ChartID(), which does not change when the timeframe does. So the old
   // code deleted all ~18 objects and OnInit + the first OnCalculate immediately
   // recreated the same ~18 under the same names -- a pure delete-all/recreate-all
   // cycle, for nothing, on every flip of the timeframe button.
   //
   // That is a mass GDI teardown, which is exactly what the OnInit comment above
   // already warns freezes the UI under Wine. Measured on 2026-08-13: Vantage (65
   // indicator load/remove events) froze at 09:26 and FP Markets (31 events) at
   // 09:56, both with the main thread dead inside win32u.so -- one deadlocked on
   // pthread_mutex_lock under NtUserDispatchMessage/NtGdiSelectBitmap, the other in
   // an endless SEGV_MAPERR loop under NtUserGetMessage. Exness, same host and Wine
   // build but 0 such events, ran 22h clean.
   //
   // Dropping the wipe here is safe because every draw path is idempotent: each
   // object is created only when ObjectFind() misses, then repositioned by name, and
   // every hidden branch deletes its own keys explicitly. A surviving object is
   // adopted and moved by the next instance within one OnCalculate.
   if(reason == REASON_REMOVE || reason == REASON_CHARTCLOSE ||
      reason == REASON_RECOMPILE)
     {
      ObjectsDeleteAll(0, g_pfx);
      Comment("");
     }
   // REASON_PARAMETERS / REASON_CHARTCHANGE / REASON_ACCOUNT: keep objects, just
   // release handles
  }

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   int need = MathMax(g_mode.ema_slow, g_mode.ema_bias) + InpRsiPeriod + InpRsiMaPeriod + 5;
   if(rates_total < need)
      return 0;

   // HTF pivots first (independent of nested iMA). Critical for Strategy Tester iCustom:
   // nested MA CopyBuffer often fails until BarsCalculated catches up — don't block Fib.
   static datetime s_last_htf_bar = 0;
   bool cold = (prev_calculated == 0);
   bool new_bar = cold || (prev_calculated > 0 && rates_total > prev_calculated);
   bool need_htf = cold || (new_bar && time[rates_total - 1] != s_last_htf_bar);
   if(need_htf)
     {
      RebuildHtfAndFib(time[rates_total - 1]);
      s_last_htf_bar = time[rates_total - 1];
      DrawAllLevels(time[rates_total - 1]);
      // Stamp fib/swing buffers immediately (even if nested MA not ready)
      int k0 = MathMax(0, rates_total - 3000);
      // Bars older than the 3000-bar restamp window must not read as price 0.
      if(cold && k0 > 0)
        {
         for(int k = 0; k < k0; k++)
           {
            BufSwingDir[k] = 0.0;
            BufFib618[k]   = EMPTY_VALUE;
            BufFib786[k]   = EMPTY_VALUE;
           }
        }
      for(int k = k0; k < rates_total; k++)
        {
         int sd = 0;
         double a618 = 0.0, a786 = 0.0;
         if(FibAt(ChartBarClose(time[k]), sd, a618, a786))
           {
            BufSwingDir[k] = (double)sd;
            BufFib618[k]   = a618;
            BufFib786[k]   = a786;
           }
         else
           {
            BufSwingDir[k] = 0.0;
            BufFib618[k]   = EMPTY_VALUE;
            BufFib786[k]   = EMPTY_VALUE;
           }
        }
     }

   // Wait for nested indicators (iCustom / tester)
   int bc_fast = BarsCalculated(g_hEmaFast);
   int bc_slow = BarsCalculated(g_hEmaSlow);
   int bc_bias = BarsCalculated(g_hEmaBias);
   int bc_rsi  = BarsCalculated(g_hRsi);
   int bc_min  = MathMin(MathMin(bc_fast, bc_slow), MathMin(bc_bias, bc_rsi));
   if(bc_min <= 0)
      return(rates_total); // HTF stamped; wait for MA/RSI next tick

   int copy_n = MathMin(rates_total, bc_min);
   if(copy_n < need)
      return prev_calculated;

   double ema_fast[], ema_slow[], ema_bias[], rsi[], rsi_ma[];
   ArraySetAsSeries(ema_fast, false);
   ArraySetAsSeries(ema_slow, false);
   ArraySetAsSeries(ema_bias, false);
   ArraySetAsSeries(rsi, false);
   ArraySetAsSeries(rsi_ma, false);
   // Copy from oldest: start pos = rates_total - copy_n when using non-series dest of size copy_n
   // Simpler: request copy_n bars from index 0 (as non-series buffer index 0 = oldest of window)
   if(CopyBuffer(g_hEmaFast, 0, rates_total - copy_n, copy_n, ema_fast) < copy_n) return prev_calculated;
   if(CopyBuffer(g_hEmaSlow, 0, rates_total - copy_n, copy_n, ema_slow) < copy_n) return prev_calculated;
   if(CopyBuffer(g_hEmaBias, 0, rates_total - copy_n, copy_n, ema_bias) < copy_n) return prev_calculated;
   if(CopyBuffer(g_hRsi,     0, rates_total - copy_n, copy_n, rsi)      < copy_n) return prev_calculated;
   if(!FxMaOnSeries(rsi, copy_n, InpRsiMaPeriod, InpRsiMaMethod, rsi_ma))
      return prev_calculated;

   // Map local copy index -> chart bar index: chart_i = (rates_total - copy_n) + local_i
   const int chart0 = rates_total - copy_n;

   // Full history signal scan only once per cold start; after that update tail.
   // Cap first-pass signal work so EMA tweaks don't freeze Wine for minutes.
   const int max_signal_bars = 3000;
   int start = (prev_calculated > 1) ? prev_calculated - 1 : MathMax(need, chart0);
   if(cold && rates_total - start > max_signal_bars)
      start = rates_total - max_signal_bars;
   if(start < chart0)
      start = chart0;
   int fill0 = (prev_calculated > 1) ? prev_calculated - 1 : chart0;
   if(cold && rates_total - fill0 > max_signal_bars)
      fill0 = rates_total - max_signal_bars;
   if(fill0 < chart0)
      fill0 = chart0;

   double aoff = FxPipsToPrice(InpArrowOffsetPips);

   for(int k = fill0; k < rates_total && !IsStopped(); k++)
     {
      int li = k - chart0; // local index into copied arrays
      if(li < 0 || li >= copy_n)
         continue;

      BufRsi[k]   = rsi[li];
      BufRsiMa[k] = rsi_ma[li];

      if(InpShowEmas)
        {
         BufEmaFast[k] = ema_fast[li];
         BufEmaSlow[k] = ema_slow[li];
        }
      else
        {
         BufEmaFast[k] = EMPTY_VALUE;
         BufEmaSlow[k] = EMPTY_VALUE;
        }

      BufEmaBias[k] = ema_bias[li];
      if(!InpShowBiasEma && InpShowEmas)
         BufEmaBias[k] = EMPTY_VALUE;

      int    sd = 0;
      double a618 = 0.0, a786 = 0.0;
      if(FibAt(ChartBarClose(time[k]), sd, a618, a786))
        {
         BufSwingDir[k] = (double)sd;
         BufFib618[k]   = a618;
         BufFib786[k]   = a786;
        }
      else
        {
         BufSwingDir[k] = 0.0;
         BufFib618[k]   = EMPTY_VALUE;
         BufFib786[k]   = EMPTY_VALUE;
        }
     }

   // Signals: ConfluenceSignal needs chart-indexed open/close/ema arrays.
   // Build aligned series over [chart0 .. rates_total) for confluence.
   for(int i = start; i < rates_total && !IsStopped(); i++)
     {
      BufLong[i]   = EMPTY_VALUE;
      BufShort[i]  = EMPTY_VALUE;
      BufSignal[i] = 0.0;

      if(i == rates_total - 1 || i < chart0 + 1)
         continue;

      int li = i - chart0;
      if(li < 1 || li >= copy_n)
         continue;

      // Local confluence using copied series (index li)
      int sig = ConfluenceSignalLocal(li, time[i], open, close, chart0,
                                      ema_bias, rsi, rsi_ma, copy_n);
      BufSignal[i] = (double)sig;
      if(sig > 0 && InpShowMarkers)
         BufLong[i] = low[i] - aoff;
      else if(sig < 0 && InpShowMarkers)
         BufShort[i] = high[i] + aoff;
     }

   if(InpShowPanel && copy_n > 0)
     {
      int last = copy_n - 1;
      DrawPanel(close[rates_total - 1], ema_fast[last],
                ema_slow[last], ema_bias[last],
                rsi[last], rsi_ma[last],
                (rates_total >= 2) ? BufSignal[rates_total - 2] : 0.0);
     }

   return rates_total;
  }

//+------------------------------------------------------------------+
//| Confluence using local (copied) EMA/RSI arrays + chart OHLC      |
//| li = index into ema_bias/rsi arrays; chart bar = chart0 + li     |
//+------------------------------------------------------------------+
int ConfluenceSignalLocal(const int li,
                          const datetime bar_time,
                          const double &open[],
                          const double &close[],
                          const int chart0,
                          const double &ema_bias[],
                          const double &rsi[],
                          const double &rsi_ma[],
                          const int copy_n)
  {
   if(li < 1 || li >= copy_n)
      return 0;
   const int i = chart0 + li;
   const int i1 = i - 1;

   int    dir = 0;
   double f618 = 0.0, f786 = 0.0;
   bool   have = FibAt(ChartBarClose(bar_time), dir, f618, f786);
   if(InpRequireGoldenZone && !have)
      return 0;

   double c  = close[i];
   double eb = ema_bias[li];
   bool bull_zone = true, bear_zone = true;
   if(InpRequireGoldenZone)
     {
      bull_zone = (dir == 1 && c <= f618 && c >= f786);
      bear_zone = (dir == -1 && c >= f618 && c <= f786);
     }
   else if(dir != 0)
     {
      bull_zone = (dir == 1);
      bear_zone = (dir == -1);
     }

   bool rsi_long_ok  = (rsi[li] <= (double)InpRsiLongMax);
   bool rsi_short_ok = (rsi[li] >= (double)InpRsiShortMin);
   if(InpUseRsiMaFilter)
     {
      if(FxRsiMaBias(rsi[li], rsi_ma[li]) < 1)  rsi_long_ok = false;
      if(FxRsiMaBias(rsi[li], rsi_ma[li]) > -1) rsi_short_ok = false;
     }

   bool regime_long  = (!InpRequireBiasFilter || !g_mode.use_bias_ema || c > eb);
   bool regime_short = (!InpRequireBiasFilter || !g_mode.use_bias_ema || c < eb);
   bool bullish_candle = (close[i] > open[i] && close[i] > close[i1]);
   bool bearish_candle = (close[i] < open[i] && close[i] < close[i1]);

   bool long_ok = bull_zone && regime_long && rsi_long_ok
                  && (!InpRequireCandle || bullish_candle);
   bool short_ok = bear_zone && regime_short && rsi_short_ok
                   && (!InpRequireCandle || bearish_candle);

   // previous bar edge
   double c1 = close[i1];
   double eb1 = ema_bias[li - 1];
   bool bz1 = true, ez1 = true;
   if(InpRequireGoldenZone && have)
     {
      bz1 = (dir == 1 && c1 <= f618 && c1 >= f786);
      ez1 = (dir == -1 && c1 >= f618 && c1 <= f786);
     }
   else if(!InpRequireGoldenZone && dir != 0)
     {
      bz1 = (dir == 1);
      ez1 = (dir == -1);
     }
   else if(InpRequireGoldenZone)
     {
      bz1 = false;
      ez1 = false;
     }
   bool pl = (rsi[li - 1] <= (double)InpRsiLongMax);
   bool ps = (rsi[li - 1] >= (double)InpRsiShortMin);
   if(InpUseRsiMaFilter)
     {
      if(FxRsiMaBias(rsi[li - 1], rsi_ma[li - 1]) < 1)  pl = false;
      if(FxRsiMaBias(rsi[li - 1], rsi_ma[li - 1]) > -1) ps = false;
     }
   bool rl = (!InpRequireBiasFilter || !g_mode.use_bias_ema || c1 > eb1);
   bool rs = (!InpRequireBiasFilter || !g_mode.use_bias_ema || c1 < eb1);
   bool prev_long  = bz1 && rl && pl;
   bool prev_short = ez1 && rs && ps;

   if(long_ok && !prev_long)
      return 1;
   if(short_ok && !prev_short)
      return -1;
   return 0;
  }

//+------------------------------------------------------------------+
//| Scan HTF for latest confirmed pivots + update swing/fib state    |
//+------------------------------------------------------------------+
void RebuildHtfAndFib(const datetime chart_now)
  {
   bool use4h = (PeriodSeconds(PERIOD_CURRENT) <= PeriodSeconds(PERIOD_H4));

   // Reset event flags for this rebuild by comparing times after scan
   datetime old_h4 = g_th4, old_l4 = g_tl4, old_hD = g_thD, old_lD = g_tlD;

   if(use4h)
     {
      ScanLatestPivot(PERIOD_H4, InpLeft4h, InpRight4h, true,  g_ph4, g_th4);
      ScanLatestPivot(PERIOD_H4, InpLeft4h, InpRight4h, false, g_pl4, g_tl4);
     }
   ScanLatestPivot(PERIOD_D1, InpLeftDaily, InpRightDaily, true,  g_phD, g_thD);
   ScanLatestPivot(PERIOD_D1, InpLeftDaily, InpRightDaily, false, g_plD, g_tlD);

   // Re-walk all confirmed HTF pivots in time order to rebuild swing/fib
   // (stable vs only reacting to "new" — correct after history load)
   RebuildSwingFromHistory(use4h);
  }

//+------------------------------------------------------------------+
//| Copy rates in true chronological order (0 = oldest).             |
//| Wine/MT5 sometimes ignores ArraySetAsSeries on CopyRates.        |
//+------------------------------------------------------------------+
int CopyRatesChrono(const string sym, const ENUM_TIMEFRAMES tf,
                    const int count, MqlRates &out[])
  {
   MqlRates tmp[];
   ArraySetAsSeries(tmp, true); // request newest-first explicitly
   int n = CopyRates(sym, tf, 0, count, tmp);
   if(n <= 0)
      return 0;
   ArrayResize(out, n);
   // Always reverse series→chrono so out[0] is oldest
   for(int i = 0; i < n; i++)
      out[i] = tmp[n - 1 - i];
   // Sanity: if still reverse-sorted, flip again
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
void PushFibSnap(const datetime t)
  {
   if(!g_fibValid || g_swingDir == 0 || t <= 0)
      return;
   int n = g_nsnaps;
   // Coalesce same-time updates
   if(n > 0 && g_snaps[n - 1].t0 == t)
     {
      g_snaps[n - 1].dir  = g_swingDir;
      g_snaps[n - 1].f618 = g_fib618;
      g_snaps[n - 1].f786 = g_fib786;
      g_snaps[n - 1].valid = true;
      return;
     }
   ArrayResize(g_snaps, n + 1);
   g_snaps[n].t0    = t;
   g_snaps[n].dir   = g_swingDir;
   g_snaps[n].f618  = g_fib618;
   g_snaps[n].f786  = g_fib786;
   g_snaps[n].valid = true;
   g_nsnaps = n + 1;
  }

//+------------------------------------------------------------------+
//| Latest fib snapshot with t0 <= bar_time (pass chart-bar close)   |
//+------------------------------------------------------------------+
bool FibAt(const datetime bar_time, int &dir, double &f618, double &f786)
  {
   if(g_nsnaps <= 0 || bar_time <= 0)
      return false;
   int lo = 0, hi = g_nsnaps - 1, ans = -1;
   while(lo <= hi)
     {
      int mid = (lo + hi) / 2;
      if(g_snaps[mid].t0 <= bar_time)
        {
         ans = mid;
         lo = mid + 1;
        }
      else
         hi = mid - 1;
     }
   if(ans < 0 || !g_snaps[ans].valid)
      return false;
   dir  = g_snaps[ans].dir;
   f618 = g_snaps[ans].f618;
   f786 = g_snaps[ans].f786;
   return (dir != 0 && f618 > 0.0 && f786 > 0.0);
  }

//+------------------------------------------------------------------+
//| Find latest confirmed pivot high or low on a timeframe           |
//+------------------------------------------------------------------+
bool ScanLatestPivot(const ENUM_TIMEFRAMES tf,
                     const int left, const int right,
                     const bool find_high,
                     double &out_price, datetime &out_time)
  {
   int L = MathMax(1, left);
   int R = MathMax(1, right);
   int need = L + R + 200;
   FxEnsureHistory(_Symbol, tf, need);
   MqlRates r[];
   int n = CopyRatesChrono(_Symbol, tf, need, r);
   if(n < L + R + 3)
      return false;

   // Last bar is forming — not a confirmation wing.
   int n_closed = n - 1;
   for(int c = n_closed - 1 - R; c >= L; c--)
     {
      bool ok = find_high
                ? IsPivotHighRates(r, n_closed, c, L, R)
                : IsPivotLowRates(r, n_closed, c, L, R);
      if(ok)
        {
         out_price = find_high ? r[c].high : r[c].low;
         out_time  = r[c].time;
         return true;
        }
     }
   return false;
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
//| Collect confirmed pivots on fib source TF and run swing machine  |
//+------------------------------------------------------------------+
void RebuildSwingFromHistory(const bool use4h)
  {
   ApplyTradingMode();
   bool fib_from_4h = (EffectiveFibSource() == 0) && use4h;
   ENUM_TIMEFRAMES tf = fib_from_4h ? PERIOD_H4 : PERIOD_D1;
   int left  = MathMax(1, fib_from_4h ? InpLeft4h  : InpLeftDaily);
   int right = MathMax(1, fib_from_4h ? InpRight4h : InpRightDaily);

   int want = FX_HTF_PIVOT_SCAN_BARS;
   FxEnsureHistory(_Symbol, tf, want);
   MqlRates r[];
   int n = CopyRatesChrono(_Symbol, tf, want, r);
   ENUM_TIMEFRAMES scan_tf = tf;

   // Fallback: chart / H1 if HTF empty
   if(n < left + right + 3)
     {
      ENUM_TIMEFRAMES fb = PERIOD_H1;
      if(PeriodSeconds(PERIOD_CURRENT) >= PeriodSeconds(PERIOD_H1))
         fb = PERIOD_CURRENT;
      FxEnsureHistory(_Symbol, fb, want);
      n = CopyRatesChrono(_Symbol, fb, want, r);
      scan_tf = fb;
      static bool s_warned_fb = false;
      if(!s_warned_fb)
        {
         Print("ForexHtfPivotsFib: HTF ", EnumToString(tf),
               " bars too few — fallback ", EnumToString(fb), " n=", n);
         s_warned_fb = true;
        }
      if(n < left + right + 3)
        {
         static bool s_warned_fail = false;
         if(!s_warned_fail)
           {
            Print("ForexHtfPivotsFib: no pivot history tf=", EnumToString(tf),
                  " n=", n, " need>=", left + right + 3);
            s_warned_fail = true;
           }
         g_nsnaps = 0;
         ArrayResize(g_snaps, 0);
         return;
        }
     }

   // Chronological pivot events. Snapshots stamp at confirm-bar close
   // (open + PeriodSeconds(scan_tf)), never the center and never the open —
   // a one-shot CopyBuffer must not see fib on [center, confirm_close).
   double   px[];
   datetime t_confirm[];
   datetime t_available[];
   int      ty[];
   int cnt = 0;
   ArrayResize(px, n);
   ArrayResize(t_confirm, n);
   ArrayResize(t_available, n);
   ArrayResize(ty, n);

   // Last copied bar is forming — it must not be a confirmation wing.
   int n_closed = (n > 0 ? n - 1 : 0);
   for(int c = left; c <= n_closed - 1 - right; c++)
     {
      bool isH = IsPivotHighRates(r, n_closed, c, left, right);
      bool isL = IsPivotLowRates(r, n_closed, c, left, right);
      if(isH && isL)
         continue;
      if(isH)
        {
         px[cnt]          = r[c].high;
         t_confirm[cnt]   = r[c + right].time;
         t_available[cnt] = BarCloseTime(r[c + right].time, scan_tf);
         ty[cnt]          = 1;
         cnt++;
        }
      else if(isL)
        {
         px[cnt]          = r[c].low;
         t_confirm[cnt]   = r[c + right].time;
         t_available[cnt] = BarCloseTime(r[c + right].time, scan_tf);
         ty[cnt]          = -1;
         cnt++;
        }
     }

   // Reset and replay — push fib snap after each completed swing
   g_lastPivotType  = 0;
   g_lastPivotPrice = 0;
   g_lastPivotTime  = 0;
   g_swingHigh = g_swingLow = 0;
   g_swingHighTime = g_swingLowTime = 0;
   g_swingDir = 0;
   g_fibValid = false;
   g_nsnaps = 0;
   ArrayResize(g_snaps, 0);

   for(int k = 0; k < cnt; k++)
     {
      ProcessPivotEvent(ty[k], px[k], t_confirm[k]);
      if(g_swingDir != 0 && g_swingHigh > 0 && g_swingLow > 0 &&
         g_swingHigh > g_swingLow)
        {
         ComputeFibLevels();
         if(g_fibValid)
            PushFibSnap(t_available[k]);
        }
     }

   // Fallback: last distinct high + low pivots if state machine left dir=0
   if(g_swingDir == 0 && cnt >= 2)
     {
      double lh = 0, ll = 0;
      datetime th = 0, tl = 0, th_avail = 0, tl_avail = 0;
      for(int k = 0; k < cnt; k++)
        {
         if(ty[k] == 1)  { lh = px[k]; th = t_confirm[k]; th_avail = t_available[k]; }
         if(ty[k] == -1) { ll = px[k]; tl = t_confirm[k]; tl_avail = t_available[k]; }
        }
      if(lh > 0.0 && ll > 0.0 && lh > ll)
        {
         g_swingHigh = lh;
         g_swingLow  = ll;
         g_swingHighTime = th;
         g_swingLowTime  = tl;
         g_swingDir = (th >= tl) ? 1 : -1;
         ComputeFibLevels();
         if(g_fibValid)
            PushFibSnap(MathMax(th_avail, tl_avail));
        }
     }
   else if(g_swingDir != 0 && g_swingHigh > g_swingLow)
     {
      ComputeFibLevels();
     }

   static datetime s_last_swing_log = 0;
   datetime now = TimeCurrent();
   if(s_last_swing_log == 0 || now - s_last_swing_log > 86400)
     {
      Print("ForexHtfPivotsFib rebuild n=", n, " pivots=", cnt,
            " snaps=", g_nsnaps,
            " swingDir=", g_swingDir, " fibValid=", (g_fibValid ? 1 : 0),
            " hi=", g_swingHigh, " lo=", g_swingLow);
      s_last_swing_log = (now > 0 ? now : 1);
     }
  }

//+------------------------------------------------------------------+
//| Same state machine as tradingview_pivot_rsi_ema.pine             |
//+------------------------------------------------------------------+
void ProcessPivotEvent(const int ptype, const double price, const datetime t)
  {
   if(ptype == 1) // high
     {
      if(g_lastPivotType == 0)
        {
         g_lastPivotType = 1;
         g_lastPivotPrice = price;
         g_lastPivotTime = t;
        }
      else if(g_lastPivotType == 1)
        {
         if(price > g_lastPivotPrice)
           {
            g_lastPivotPrice = price;
            g_lastPivotTime = t;
            if(g_swingDir == 1)
              {
               g_swingHigh = price;
               g_swingHighTime = t;
              }
           }
        }
      else // previous was low
        {
         // Always accept alternating high after low (relax extreme filter if needed)
         if(price > g_lastPivotPrice || g_swingDir == 0)
           {
            g_swingLow = g_lastPivotPrice;
            g_swingLowTime = g_lastPivotTime;
            g_swingHigh = price;
            g_swingHighTime = t;
            g_swingDir = 1;
           }
         g_lastPivotType = 1;
         g_lastPivotPrice = price;
         g_lastPivotTime = t;
        }
     }
   else // low
     {
      if(g_lastPivotType == 0)
        {
         g_lastPivotType = -1;
         g_lastPivotPrice = price;
         g_lastPivotTime = t;
        }
      else if(g_lastPivotType == -1)
        {
         if(price < g_lastPivotPrice)
           {
            g_lastPivotPrice = price;
            g_lastPivotTime = t;
            if(g_swingDir == -1)
              {
               g_swingLow = price;
               g_swingLowTime = t;
              }
           }
        }
      else // previous was high
        {
         if(price < g_lastPivotPrice || g_swingDir == 0)
           {
            g_swingHigh = g_lastPivotPrice;
            g_swingHighTime = g_lastPivotTime;
            g_swingLow = price;
            g_swingLowTime = t;
            g_swingDir = -1;
           }
         g_lastPivotType = -1;
         g_lastPivotPrice = price;
         g_lastPivotTime = t;
        }
     }
  }

//+------------------------------------------------------------------+
void ComputeFibLevels()
  {
   double hi = g_swingHigh;
   double lo = g_swingLow;
   if(hi <= lo || g_swingDir == 0)
     {
      g_fibValid = false;
      return;
     }
   g_fib236 = FibLevel(g_swingDir, hi, lo, 0.236);
   g_fib382 = FibLevel(g_swingDir, hi, lo, 0.382);
   g_fib500 = FibLevel(g_swingDir, hi, lo, 0.500);
   g_fib618 = FibLevel(g_swingDir, hi, lo, 0.618);
   g_fib786 = FibLevel(g_swingDir, hi, lo, 0.786);
   g_fibValid = true;
  }

double FibLevel(const int direction, const double hi, const double lo, const double ratio)
  {
   if(direction == 1)
      return hi - (hi - lo) * ratio;
   return lo + (hi - lo) * ratio;
  }

//+------------------------------------------------------------------+
int ConfluenceSignal(const int i,
                     const datetime bar_time,
                     const double &open[],
                     const double &close[],
                     const double &ema_bias[],
                     const double &rsi[],
                     const double &rsi_ma[])
  {
   int    dir = 0;
   double f618 = 0.0, f786 = 0.0;
   bool   have = FibAt(ChartBarClose(bar_time), dir, f618, f786);
   if(InpRequireGoldenZone && !have)
      return 0;

   double c = close[i];
   double eb = ema_bias[i];
   bool bull_zone = true;
   bool bear_zone = true;
   if(InpRequireGoldenZone)
     {
      bull_zone = (dir == 1 && c <= f618 && c >= f786);
      bear_zone = (dir == -1 && c >= f618 && c <= f786);
     }
   else if(dir != 0)
     {
      bull_zone = (dir == 1);
      bear_zone = (dir == -1);
     }

   bool bullish_candle = (close[i] > open[i] && close[i] > close[i - 1]);
   bool bearish_candle = (close[i] < open[i] && close[i] < close[i - 1]);

   bool rsi_long_ok  = (rsi[i] <= (double)InpRsiLongMax);
   bool rsi_short_ok = (rsi[i] >= (double)InpRsiShortMin);

   if(InpUseRsiMaFilter)
     {
      if(FxRsiMaBias(rsi[i], rsi_ma[i]) < 1)
         rsi_long_ok = false;
      if(FxRsiMaBias(rsi[i], rsi_ma[i]) > -1)
         rsi_short_ok = false;
     }

   bool regime_long  = (!InpRequireBiasFilter || !g_mode.use_bias_ema || c > eb);
   bool regime_short = (!InpRequireBiasFilter || !g_mode.use_bias_ema || c < eb);

   bool long_ok = bull_zone && regime_long && rsi_long_ok
                  && (!InpRequireCandle || bullish_candle);
   bool short_ok = bear_zone && regime_short && rsi_short_ok
                   && (!InpRequireCandle || bearish_candle);

   bool prev_long = false, prev_short = false;
   if(i >= 1)
     {
      int    d1 = dir;
      double a1 = f618, b1 = f786;
      // Prefer snap at previous bar time if available via globals only (cheap)
      double c1 = close[i - 1];
      double eb1 = ema_bias[i - 1];
      bool bz1 = true, ez1 = true;
      if(InpRequireGoldenZone && have)
        {
         bz1 = (d1 == 1 && c1 <= a1 && c1 >= b1);
         ez1 = (d1 == -1 && c1 >= a1 && c1 <= b1);
        }
      else if(!InpRequireGoldenZone && d1 != 0)
        {
         bz1 = (d1 == 1);
         ez1 = (d1 == -1);
        }
      else if(InpRequireGoldenZone)
        {
         bz1 = false;
         ez1 = false;
        }
      bool pl = (rsi[i - 1] <= (double)InpRsiLongMax);
      bool ps = (rsi[i - 1] >= (double)InpRsiShortMin);
      if(InpUseRsiMaFilter)
        {
         if(FxRsiMaBias(rsi[i - 1], rsi_ma[i - 1]) < 1)
            pl = false;
         if(FxRsiMaBias(rsi[i - 1], rsi_ma[i - 1]) > -1)
            ps = false;
        }
      bool rl = (!InpRequireBiasFilter || !g_mode.use_bias_ema || c1 > eb1);
      bool rs = (!InpRequireBiasFilter || !g_mode.use_bias_ema || c1 < eb1);
      prev_long  = bz1 && rl && pl;
      prev_short = ez1 && rs && ps;
     }

   if(long_ok && !prev_long)
      return 1;
   if(short_ok && !prev_short)
      return -1;
   return 0;
  }

//+------------------------------------------------------------------+
void DrawAllLevels(const datetime t_now)
  {
   datetime t2 = t_now + PeriodSeconds() * 5;
   bool use4h = (PeriodSeconds(PERIOD_CURRENT) <= PeriodSeconds(PERIOD_H4));

   // Static levels: only touched after a (re)load, never per bar.
   if(g_sr_dirty)
     {
      DrawSrLevels();
      g_sr_dirty = false;
     }

   if(EffectiveShow4h() && use4h)
     {
      if(g_th4 > 0) HLine("P4H", g_ph4, g_th4, t2, InpCol4hHigh, InpShow4hLabels ? "4H H" : "");
      if(g_tl4 > 0) HLine("P4L", g_pl4, g_tl4, t2, InpCol4hLow,  InpShow4hLabels ? "4H L" : "");
     }
   else
     {
      ObjectDelete(0, g_pfx + "P4H");
      ObjectDelete(0, g_pfx + "P4L");
      ObjectDelete(0, g_pfx + "P4H_lbl");
      ObjectDelete(0, g_pfx + "P4L_lbl");
     }

   if(InpShowDailyLines)
     {
      if(g_thD > 0) HLine("PDH", g_phD, g_thD, t2, InpColDailyHigh, InpShowDailyLabels ? "D H" : "");
      if(g_tlD > 0) HLine("PDL", g_plD, g_tlD, t2, InpColDailyLow,  InpShowDailyLabels ? "D L" : "");
     }
   else
     {
      // Mirror the 4H branch. Without this, toggling InpShowDailyLines off orphaned
      // the daily lines for good: REASON_PARAMETERS deliberately does not wipe, so
      // nothing else ever deleted them.
      ObjectDelete(0, g_pfx + "PDH");
      ObjectDelete(0, g_pfx + "PDL");
      ObjectDelete(0, g_pfx + "PDH_lbl");
      ObjectDelete(0, g_pfx + "PDL_lbl");
     }

   // Fib levels
   string fib_keys[] = {"F236","F382","F500","F618","F786"};
   double fib_vals[];
   ArrayResize(fib_vals, 5);
   fib_vals[0] = g_fib236; fib_vals[1] = g_fib382; fib_vals[2] = g_fib500;
   fib_vals[3] = g_fib618; fib_vals[4] = g_fib786;
   bool fib_show[];
   ArrayResize(fib_show, 5);
   fib_show[0] = InpShowFib236; fib_show[1] = InpShowFib382; fib_show[2] = InpShowFib500;
   fib_show[3] = InpShowFib618; fib_show[4] = InpShowFib786;
   color fib_cols[];
   ArrayResize(fib_cols, 5);
   fib_cols[0] = clrCornflowerBlue; fib_cols[1] = clrDodgerBlue; fib_cols[2] = InpColFib500;
   fib_cols[3] = InpColFib618; fib_cols[4] = InpColFib786;
   string fib_labs[] = {"23.6","38.2","50","61.8","78.6"};

   if(InpShowFib && g_fibValid)
     {
      datetime t1 = (g_swingDir == 1) ? g_swingHighTime : g_swingLowTime;
      if(t1 <= 0) t1 = t_now - PeriodSeconds() * 20;
      for(int i = 0; i < 5; i++)
        {
         if(fib_show[i])
            HLine(fib_keys[i], fib_vals[i], t1, t2, fib_cols[i], fib_labs[i]);
         else
           {
            ObjectDelete(0, g_pfx + fib_keys[i]);
            ObjectDelete(0, g_pfx + fib_keys[i] + "_lbl");
           }
        }
      if(InpShowGoldenZone)
         DrawGoldenZone(t1, t2);
      else
         ObjectDelete(0, g_pfx + "GOLD");
     }
   else
     {
      for(int i = 0; i < 5; i++)
        {
         ObjectDelete(0, g_pfx + fib_keys[i]);
         ObjectDelete(0, g_pfx + fib_keys[i] + "_lbl");
        }
      ObjectDelete(0, g_pfx + "GOLD");
     }
  }

//+------------------------------------------------------------------+
void HLine(const string key, const double price,
           const datetime t1, const datetime t2,
           const color clr, const string label)
  {
   string name = g_pfx + key;
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_TREND, 0, t1, price, t2, price);
      ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, true);
      ObjectSetInteger(0, name, OBJPROP_RAY_LEFT, false);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, (key == "F618" || StringFind(key, "P") == 0) ? 2 : 1);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectMove(0, name, 0, t1, price);
   ObjectMove(0, name, 1, t2, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);

   if(StringLen(label) > 0)
     {
      string lname = g_pfx + key + "_lbl";
      if(ObjectFind(0, lname) < 0)
        {
         ObjectCreate(0, lname, OBJ_TEXT, 0, t2, price);
         ObjectSetInteger(0, lname, OBJPROP_FONTSIZE, 8);
         ObjectSetString(0, lname, OBJPROP_FONT, "Arial");
         ObjectSetInteger(0, lname, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, lname, OBJPROP_HIDDEN, true);
         ObjectSetInteger(0, lname, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
        }
      ObjectMove(0, lname, 0, t2, price);
      ObjectSetString(0, lname, OBJPROP_TEXT, " " + label + " " + DoubleToString(price, _Digits));
      ObjectSetInteger(0, lname, OBJPROP_COLOR, clr);
     }
   else
     {
      // Callers pass "" to hide a label (InpShow4hLabels / InpShowDailyLabels). Without
      // this delete the previously drawn label object survived that toggle forever,
      // since REASON_PARAMETERS deliberately keeps objects.
      ObjectDelete(0, g_pfx + key + "_lbl");
     }
  }

//+------------------------------------------------------------------+
//| Imported S/R levels                                              |
//|                                                                  |
//| Levels come from scripts/tpl_to_sr_levels.py, which turns the     |
//| hand-drawn OBJ_HLINE zones of the manual .tpl chart templates     |
//| into MQL5\Files\forex_sr_levels.csv. Reading the table at runtime |
//| (rather than baking it into this source) means re-drawing zones   |
//| needs a regenerate + redeploy, not a MetaEditor recompile.        |
//|                                                                  |
//| The table is a static snapshot: it does not follow price, and it  |
//| only covers the symbols that were exported.                      |
//+------------------------------------------------------------------+

//| Canonical name from the explicit registry. Unmapped symbols stay
//| as-is (uppercased) — no suffix strip, no first-match.
string SrSymbolBase(const string sym)
  {
   string mapped = FxCanonicalFromBrokerSymbolAny(sym);
   if(StringLen(mapped) > 0)
      return mapped;
   string t = sym;
   StringToUpper(t);
   return t;
  }

int SrTierFromText(const string s)
  {
   if(s == "HIGH") return SR_TIER_HIGH;
   if(s == "LOW")  return SR_TIER_LOW;
   return SR_TIER_MED;
  }

color SrTierColor(const int tier)
  {
   if(tier == SR_TIER_HIGH) return InpSrColHigh;
   if(tier == SR_TIER_LOW)  return InpSrColLow;
   return InpSrColMed;
  }

string SrTierName(const int tier)
  {
   if(tier == SR_TIER_HIGH) return "HIGH";
   if(tier == SR_TIER_LOW)  return "LOW";
   return "MED";
  }

//| Filtering here rather than at draw time keeps the object indices dense,
//| so the tail sweep in DrawSrLevels() removes whatever a toggle dropped.
bool SrTierVisible(const int tier)
  {
   if(tier == SR_TIER_HIGH) return InpSrShowHigh;
   if(tier == SR_TIER_LOW)  return InpSrShowLow;
   return InpSrShowMed;
  }

//| Read the CSV, keeping only rows whose symbol matches this chart.
//| Tries MQL5\Files first, then Common\Files (the Strategy Tester agent
//| sandbox only sees the shared Common folder).
void LoadSrLevels()
  {
   g_nsr = 0;
   ArrayResize(g_sr, 0);
   if(!InpShowSrLevels || StringLen(InpSrFile) == 0)
      return;

   int h = FileOpen(InpSrFile, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
      h = FileOpen(InpSrFile, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_COMMON);
   if(h == INVALID_HANDLE)
     {
      Print("ForexHtfPivotsFib: S/R file '", InpSrFile,
            "' not found in MQL5\\Files or Common\\Files (err ", GetLastError(),
            ") — run scripts/tpl_to_sr_levels.py, then scripts/18-install-forex-indicator.sh");
      return;
     }

   string want = SrSymbolBase(_Symbol);
   int skipped = 0;   // rows for other symbols
   int hidden  = 0;   // rows for this symbol dropped by a tier toggle
   while(!FileIsEnding(h) && g_nsr < InpSrMaxLevels)
     {
      string line = FileReadString(h);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) == 0 || StringGetCharacter(line, 0) == '#')
         continue;

      string parts[];
      if(StringSplit(line, ',', parts) < 3)
         continue;
      if(SrSymbolBase(parts[0]) != want)
        { skipped++; continue; }

      double price = StringToDouble(parts[1]);
      if(price <= 0.0)
         continue;
      int tier = SrTierFromText(parts[2]);
      if(!SrTierVisible(tier))
        { hidden++; continue; }

      ArrayResize(g_sr, g_nsr + 1);
      g_sr[g_nsr].price = price;
      g_sr[g_nsr].tier  = tier;
      g_sr[g_nsr].tf    = (ArraySize(parts) > 3) ? parts[3] : "?";
      g_nsr++;
     }
   FileClose(h);

   int n_high = 0, n_med = 0, n_low = 0;
   for(int i = 0; i < g_nsr; i++)
     {
      if(g_sr[i].tier == SR_TIER_HIGH)      n_high++;
      else if(g_sr[i].tier == SR_TIER_MED)  n_med++;
      else                                  n_low++;
     }
   Print("ForexHtfPivotsFib: S/R levels for ", _Symbol, " (base ", want, "): ",
         g_nsr, " drawn (high=", n_high, " med=", n_med, " low=", n_low,
         "), ", hidden, " hidden by tier toggles, ",
         skipped, " rows for other symbols");
   if(g_nsr == 0 && hidden == 0 && skipped > 0)
      Print("ForexHtfPivotsFib: no S/R rows matched ", want,
            " — re-export a template for this symbol");
  }

//| Idempotent like every other draw path here: create on miss, then move
//| by name. Only runs when g_sr_dirty is set, so a chart tick never
//| touches ~100 objects (mass GDI work is what freezes MT5 under Wine).
void DrawSrLevels()
  {
   for(int i = 0; i < g_nsr; i++)
     {
      string name = g_pfx + "SR" + IntegerToString(i);
      if(ObjectFind(0, name) < 0)
        {
         ObjectCreate(0, name, OBJ_HLINE, 0, 0, g_sr[i].price);
         ObjectSetInteger(0, name, OBJPROP_BACK, true);
         ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, name, OBJPROP_SELECTED, false);
         ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
        }
      ObjectSetDouble(0, name, OBJPROP_PRICE, 0, g_sr[i].price);
      ObjectSetInteger(0, name, OBJPROP_COLOR, SrTierColor(g_sr[i].tier));
      ObjectSetInteger(0, name, OBJPROP_STYLE, InpSrStyle);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, (g_sr[i].tier == SR_TIER_HIGH) ? 2 : 1);

      string tag = SrTierName(g_sr[i].tier) + " " + g_sr[i].tf + " " +
                   DoubleToString(g_sr[i].price, _Digits);
      ObjectSetString(0, name, OBJPROP_TOOLTIP, tag);
      ObjectSetString(0, name, OBJPROP_TEXT, InpSrShowLabels ? tag : "");
     }

   // Sweep the tail: toggling InpShowSrLevels off, switching to a symbol with
   // fewer levels, or regenerating a shorter CSV must not leave orphans behind.
   // ObjectDelete on a missing name is a cheap no-op, so the bounded sweep is
   // safe to run on every (rare) reload.
   for(int i = g_nsr; i < InpSrMaxLevels; i++)
      ObjectDelete(0, g_pfx + "SR" + IntegerToString(i));
  }

//+------------------------------------------------------------------+
void DrawGoldenZone(const datetime t1, const datetime t2)
  {
   string name = g_pfx + "GOLD";
   double top = MathMax(g_fib618, g_fib786);
   double bot = MathMin(g_fib618, g_fib786);
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, top, t2, bot);
      ObjectSetInteger(0, name, OBJPROP_FILL, true);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
     }
   ObjectMove(0, name, 0, t1, top);
   ObjectMove(0, name, 1, t2, bot);
   ObjectSetInteger(0, name, OBJPROP_COLOR, InpColGolden);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, InpColGolden);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
  }

//+------------------------------------------------------------------+
//| Comment() panel only — Wine breaks stacked OBJ_LABEL (garble)    |
//| Header includes version so you can confirm recompile worked.     |
//+------------------------------------------------------------------+
void DrawPanel(const double close_px,
               const double e_fast, const double e_slow, const double e_bias,
               const double rsi_v, const double rsi_ma_v, const double last_sig)
  {
   static int clean_ticks = 0;
   if(clean_ticks < 5)
     {
      for(int r = 0; r < 16; r++)
        {
         ObjectDelete(0, g_pfx + "p" + IntegerToString(r));
         ObjectDelete(0, "HTFFIB_" + IntegerToString(ChartID()) + "_p" + IntegerToString(r));
        }
      clean_ticks++;
     }

   if(!InpShowPanel)
     {
      Comment("");
      return;
     }

   string dir = (g_swingDir == 1) ? "BULL"
                : (g_swingDir == -1 ? "BEAR" : "none");
   string gz = g_fibValid
               ? StringFormat("%s - %s",
                              DoubleToString(MathMin(g_fib618, g_fib786), _Digits),
                              DoubleToString(MathMax(g_fib618, g_fib786), _Digits))
               : "(need swing)";

   int rb = FxRsiMaBias(rsi_v, rsi_ma_v);
   string rsi_rel = (rb > 0) ? "above MA" : (rb < 0 ? "below MA" : "flat");

   ApplyTradingMode();
   string fib_src = (EffectiveFibSource() == 1) ? "Daily" : "4H";

   string panel =
      "HTF Fib v" + HTF_FIB_VER + "\n" +
      StringFormat("Mode   %s  (%s)\n", g_mode.mode_name, g_mode.chart_hint) +
      StringFormat("EMAs   %d/%d bias %d\n",
                   g_mode.ema_fast, g_mode.ema_slow, g_mode.ema_bias) +
      StringFormat("Fib src %s\n", fib_src) +
      StringFormat("Swing  %s\n", dir) +
      StringFormat("Golden %s\n", gz) +
      StringFormat("RSI    %.1f\n", rsi_v) +
      StringFormat("RSI MA %.1f  (%s)\n", rsi_ma_v, rsi_rel) +
      StringFormat("EMA%d  %s\n", g_mode.ema_fast, DoubleToString(e_fast, _Digits)) +
      StringFormat("EMA%d  %s\n", g_mode.ema_slow, DoubleToString(e_slow, _Digits)) +
      StringFormat("EMA%d  %s\n", g_mode.ema_bias, DoubleToString(e_bias, _Digits)) +
      StringFormat("Signal %+.0f", last_sig);

   Comment(panel);
  }

//+------------------------------------------------------------------+
//| EA: CopyBuffer(h, 8, 1, 1, sig)   signal                         |
//|     CopyBuffer(h, 9, 0, 1, rsi)   RSI                            |
//|     CopyBuffer(h, 10, 0, 1, rma)  RSI-MA                         |
//|     CopyBuffer(h, 5, 0, 1, f618)  fib 61.8                       |
//+------------------------------------------------------------------+

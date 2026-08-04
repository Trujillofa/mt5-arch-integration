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
//| iCustom signal buffer = 7  (+1 long / -1 short / 0)              |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.00"
#property description "HTF confirmed pivots + directional Fib + EMA50/200 (TV port)"
#property description "Non-repaint pivots. Signal buffer 7. Visual/manual first."
#property strict

#property indicator_chart_window
#property indicator_buffers 8
#property indicator_plots   4

#property indicator_label1  "EMA50"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDeepSkyBlue
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

#property indicator_label2  "EMA200"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrGold
#property indicator_style2  STYLE_SOLID
#property indicator_width2  2

#property indicator_label3  "Long"
#property indicator_type3   DRAW_ARROW
#property indicator_color3  clrLime
#property indicator_width3  2

#property indicator_label4  "Short"
#property indicator_type4   DRAW_ARROW
#property indicator_color4  clrOrangeRed
#property indicator_width4  2

#include <ForexUtils.mqh>

//+------------------------------------------------------------------+
enum ENUM_FIB_SOURCE
  {
   FIB_SOURCE_H4    = 0, // 4H pivots
   FIB_SOURCE_DAILY = 1  // Daily pivots
  };

//+------------------------------------------------------------------+
input group "=== EMAs ==="
input int    InpEma50            = 50;
input int    InpEma200           = 200;
input bool   InpShowEmas         = true;

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

input group "=== Confluence markers ==="
input bool   InpShowMarkers      = true;
input int    InpRsiPeriod        = 14;
input int    InpRsiLongMax       = 35;
input int    InpRsiShortMin      = 65;
input bool   InpRequireCandle    = false;  // Require bullish/bearish candle

input group "=== Display ==="
input bool   InpShowPanel        = true;
input double InpArrowOffsetPips  = 4.0;

//+------------------------------------------------------------------+
//| Buffers: 0 EMA50 | 1 EMA200 | 2 Long | 3 Short                   |
//|          4 fib618 | 5 fib786 | 6 swingDir | 7 signal             |
//+------------------------------------------------------------------+
double BufEma50[];
double BufEma200[];
double BufLong[];
double BufShort[];
double BufFib618[];
double BufFib786[];
double BufSwingDir[];
double BufSignal[];

int g_hEma50  = INVALID_HANDLE;
int g_hEma200 = INVALID_HANDLE;
int g_hRsi    = INVALID_HANDLE;

string g_pfx;

//--- latest confirmed pivots
double   g_ph4 = 0, g_pl4 = 0, g_phD = 0, g_plD = 0;
datetime g_th4 = 0, g_tl4 = 0, g_thD = 0, g_tlD = 0;
datetime g_seen_h4 = 0, g_seen_l4 = 0, g_seen_hD = 0, g_seen_lD = 0;

//--- swing / fib state
int      g_lastPivotType = 0;   // 0 unset, 1 high, -1 low
double   g_lastPivotPrice = 0;
datetime g_lastPivotTime  = 0;
double   g_swingHigh = 0, g_swingLow = 0;
datetime g_swingHighTime = 0, g_swingLowTime = 0;
int      g_swingDir = 0;        // 1 bull low->high, -1 bear high->low
double   g_fib236 = 0, g_fib382 = 0, g_fib500 = 0, g_fib618 = 0, g_fib786 = 0;
bool     g_fibValid = false;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpLeft4h < 1 || InpRight4h < 1 || InpLeftDaily < 1 || InpRightDaily < 1)
      return INIT_PARAMETERS_INCORRECT;

   SetIndexBuffer(0, BufEma50,    INDICATOR_DATA);
   SetIndexBuffer(1, BufEma200,   INDICATOR_DATA);
   SetIndexBuffer(2, BufLong,     INDICATOR_DATA);
   SetIndexBuffer(3, BufShort,    INDICATOR_DATA);
   SetIndexBuffer(4, BufFib618,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(5, BufFib786,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(6, BufSwingDir, INDICATOR_CALCULATIONS);
   SetIndexBuffer(7, BufSignal,   INDICATOR_CALCULATIONS);

   ArraySetAsSeries(BufEma50, false);
   ArraySetAsSeries(BufEma200, false);
   ArraySetAsSeries(BufLong, false);
   ArraySetAsSeries(BufShort, false);
   ArraySetAsSeries(BufFib618, false);
   ArraySetAsSeries(BufFib786, false);
   ArraySetAsSeries(BufSwingDir, false);
   ArraySetAsSeries(BufSignal, false);

   PlotIndexSetInteger(0, PLOT_DRAW_BEGIN, InpEma50);
   PlotIndexSetInteger(1, PLOT_DRAW_BEGIN, InpEma200);
   PlotIndexSetInteger(2, PLOT_DRAW_BEGIN, InpEma200);
   PlotIndexSetInteger(3, PLOT_DRAW_BEGIN, InpEma200);
   PlotIndexSetInteger(2, PLOT_ARROW, 233);
   PlotIndexSetInteger(3, PLOT_ARROW, 234);
   for(int p = 0; p < 4; p++)
      PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);

   IndicatorSetInteger(INDICATOR_DIGITS, _Digits);
   IndicatorSetString(INDICATOR_SHORTNAME, "HTF Pivots+Fib");

   g_hEma50  = iMA(_Symbol, PERIOD_CURRENT, InpEma50,  0, MODE_EMA, PRICE_CLOSE);
   g_hEma200 = iMA(_Symbol, PERIOD_CURRENT, InpEma200, 0, MODE_EMA, PRICE_CLOSE);
   g_hRsi    = iRSI(_Symbol, PERIOD_CURRENT, InpRsiPeriod, PRICE_CLOSE);
   if(g_hEma50 == INVALID_HANDLE || g_hEma200 == INVALID_HANDLE || g_hRsi == INVALID_HANDLE)
      return INIT_FAILED;

   g_pfx = "HTFFIB_" + IntegerToString(ChartID()) + "_";
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_hEma50  != INVALID_HANDLE) IndicatorRelease(g_hEma50);
   if(g_hEma200 != INVALID_HANDLE) IndicatorRelease(g_hEma200);
   if(g_hRsi    != INVALID_HANDLE) IndicatorRelease(g_hRsi);
   ObjectsDeleteAll(0, g_pfx);
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
   int need = MathMax(InpEma200, InpRsiPeriod) + 5;
   if(rates_total < need)
      return 0;

   double ema50[], ema200[], rsi[];
   ArraySetAsSeries(ema50, false);
   ArraySetAsSeries(ema200, false);
   ArraySetAsSeries(rsi, false);
   if(CopyBuffer(g_hEma50,  0, 0, rates_total, ema50)  < rates_total) return prev_calculated;
   if(CopyBuffer(g_hEma200, 0, 0, rates_total, ema200) < rates_total) return prev_calculated;
   if(CopyBuffer(g_hRsi,    0, 0, rates_total, rsi)    < rates_total) return prev_calculated;

   // Rebuild HTF pivots + fib when new bar or first run
   bool new_bar = (prev_calculated == 0) ||
                  (prev_calculated > 0 && rates_total > prev_calculated);
   if(new_bar || prev_calculated == 0)
      RebuildHtfAndFib(time[rates_total - 1]);

   int start = (prev_calculated > 1) ? prev_calculated - 1 : need;
   double aoff = FxPipsToPrice(InpArrowOffsetPips);

   for(int i = start; i < rates_total && !IsStopped(); i++)
     {
      if(InpShowEmas)
        {
         BufEma50[i]  = ema50[i];
         BufEma200[i] = ema200[i];
        }
      else
        {
         BufEma50[i]  = EMPTY_VALUE;
         BufEma200[i] = EMPTY_VALUE;
        }

      BufFib618[i]   = g_fibValid ? g_fib618 : EMPTY_VALUE;
      BufFib786[i]   = g_fibValid ? g_fib786 : EMPTY_VALUE;
      BufSwingDir[i] = (double)g_swingDir;
      BufLong[i]     = EMPTY_VALUE;
      BufShort[i]    = EMPTY_VALUE;
      BufSignal[i]   = 0.0;

      // signals only on closed bars
      if(i == rates_total - 1 || i < 1)
         continue;

      int sig = ConfluenceSignal(i, open, close, ema200, rsi);
      BufSignal[i] = (double)sig;
      if(sig > 0 && InpShowMarkers)
         BufLong[i] = low[i] - aoff;
      else if(sig < 0 && InpShowMarkers)
         BufShort[i] = high[i] + aoff;
     }

   DrawAllLevels(time[rates_total - 1]);

   if(InpShowPanel)
      DrawPanel(close[rates_total - 1], ema50[rates_total - 1],
                ema200[rates_total - 1], rsi[rates_total - 1],
                (rates_total >= 2) ? BufSignal[rates_total - 2] : 0.0);

   return rates_total;
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
//| Find latest confirmed pivot high or low on a timeframe           |
//+------------------------------------------------------------------+
bool ScanLatestPivot(const ENUM_TIMEFRAMES tf,
                     const int left, const int right,
                     const bool find_high,
                     double &out_price, datetime &out_time)
  {
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int need = left + right + 50;
   int n = CopyRates(_Symbol, tf, 0, need, r);
   if(n < left + right + 2)
      return false;

   // series false: 0 = oldest. Confirmed centers: left .. n-1-right
   // Prefer most recent center (highest index)
   for(int c = n - 1 - right; c >= left; c--)
     {
      bool ok = find_high
                ? IsPivotHighRates(r, n, c, left, right)
                : IsPivotLowRates(r, n, c, left, right);
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
   bool fib_from_4h = (InpFibSource == FIB_SOURCE_H4) && use4h;
   ENUM_TIMEFRAMES tf = fib_from_4h ? PERIOD_H4 : PERIOD_D1;
   int left  = fib_from_4h ? InpLeft4h  : InpLeftDaily;
   int right = fib_from_4h ? InpRight4h : InpRightDaily;

   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, tf, 0, 200, r);
   if(n < left + right + 3)
      return;

   // Chronological list of pivot events (price, time, type ±1)
   double  px[];
   datetime tm[];
   int     ty[];
   int cnt = 0;
   ArrayResize(px, n);
   ArrayResize(tm, n);
   ArrayResize(ty, n);

   for(int c = left; c <= n - 1 - right; c++)
     {
      bool isH = IsPivotHighRates(r, n, c, left, right);
      bool isL = IsPivotLowRates(r, n, c, left, right);
      // Ambiguous same bar: skip (matches Pine)
      if(isH && isL)
         continue;
      if(isH)
        {
         px[cnt] = r[c].high;
         tm[cnt] = r[c].time;
         ty[cnt] = 1;
         cnt++;
        }
      else if(isL)
        {
         px[cnt] = r[c].low;
         tm[cnt] = r[c].time;
         ty[cnt] = -1;
         cnt++;
        }
     }

   // Reset swing state and replay
   g_lastPivotType  = 0;
   g_lastPivotPrice = 0;
   g_lastPivotTime  = 0;
   g_swingHigh = g_swingLow = 0;
   g_swingHighTime = g_swingLowTime = 0;
   g_swingDir = 0;
   g_fibValid = false;

   for(int k = 0; k < cnt; k++)
      ProcessPivotEvent(ty[k], px[k], tm[k]);

   if(g_swingDir != 0 && g_swingHigh > 0 && g_swingLow > 0)
      ComputeFibLevels();
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
         if(price > g_lastPivotPrice)
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
         if(price < g_lastPivotPrice)
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
   // Bullish: retrace down from high; bearish: retrace up from low
   double hi = g_swingHigh;
   double lo = g_swingLow;
   if(hi <= lo)
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
                     const double &open[],
                     const double &close[],
                     const double &ema200[],
                     const double &rsi[])
  {
   if(!g_fibValid || g_swingDir == 0)
      return 0;

   double c = close[i];
   bool bull_zone = (g_swingDir == 1 && c <= g_fib618 && c >= g_fib786);
   bool bear_zone = (g_swingDir == -1 && c >= g_fib618 && c <= g_fib786);

   bool bullish_candle = (close[i] > open[i] && close[i] > close[i - 1]);
   bool bearish_candle = (close[i] < open[i] && close[i] < close[i - 1]);

   bool long_ok = bull_zone && (c > ema200[i]) && (rsi[i] <= (double)InpRsiLongMax)
                  && (!InpRequireCandle || bullish_candle);
   bool short_ok = bear_zone && (c < ema200[i]) && (rsi[i] >= (double)InpRsiShortMin)
                   && (!InpRequireCandle || bearish_candle);

   // Edge trigger: condition true now, false previous closed bar
   // (approximate: only mark when in zone — continuous; use edge for cleanliness)
   // Pine uses barstate.isconfirmed && condition && not condition[1]
   // We approximate with in-zone + RSI side without requiring prior false
   // to avoid missing holds; markers on every bar in zone would spam.
   // Edge: check previous bar not already in setup.
   bool prev_long = false, prev_short = false;
   if(i >= 1)
     {
      double c1 = close[i - 1];
      bool bz1 = (g_swingDir == 1 && c1 <= g_fib618 && c1 >= g_fib786);
      bool ez1 = (g_swingDir == -1 && c1 >= g_fib618 && c1 <= g_fib786);
      prev_long  = bz1 && (c1 > ema200[i - 1]) && (rsi[i - 1] <= (double)InpRsiLongMax);
      prev_short = ez1 && (c1 < ema200[i - 1]) && (rsi[i - 1] >= (double)InpRsiShortMin);
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

   if(InpShow4hLines && use4h)
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
void DrawPanel(const double close_px, const double e50, const double e200,
               const double rsi_v, const double last_sig)
  {
   string dir = (g_swingDir == 1) ? "BULL swing" : (g_swingDir == -1 ? "BEAR swing" : "—");
   color  dcol = (g_swingDir == 1) ? clrLime : (g_swingDir == -1 ? clrOrangeRed : clrWhite);

   string lines[7];
   color  cols[7];
   lines[0] = "HTF Pivots + Fib";          cols[0] = clrWhite;
   lines[1] = StringFormat("Swing  %s", dir); cols[1] = dcol;
   lines[2] = g_fibValid
              ? StringFormat("GZ  %.5f – %.5f", MathMin(g_fib618, g_fib786), MathMax(g_fib618, g_fib786))
              : "GZ  (need swing)";
   cols[2] = clrGold;
   lines[3] = StringFormat("RSI    %.1f", rsi_v); cols[3] = clrViolet;
   lines[4] = StringFormat("EMA50  %s", DoubleToString(e50, _Digits));  cols[4] = clrDeepSkyBlue;
   lines[5] = StringFormat("EMA200 %s", DoubleToString(e200, _Digits)); cols[5] = clrGold;
   lines[6] = StringFormat("Signal %+.0f", last_sig);
   cols[6] = (last_sig > 0) ? clrLime : (last_sig < 0 ? clrOrangeRed : clrWhite);

   for(int row = 0; row < 7; row++)
     {
      string name = g_pfx + "p" + IntegerToString(row);
      if(ObjectFind(0, name) < 0)
        {
         ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
         ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
         ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 10);
         ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 18 + row * 14);
         ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
         ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
         ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
        }
      ObjectSetString(0, name, OBJPROP_TEXT, lines[row]);
      ObjectSetInteger(0, name, OBJPROP_COLOR, cols[row]);
     }
  }

//+------------------------------------------------------------------+
//| EA: CopyBuffer(h, 7, 1, 1, sig)  // last closed signal           |
//|     CopyBuffer(h, 4, 0, 1, f618) // fib 61.8                     |
//|     CopyBuffer(h, 5, 0, 1, f786) // fib 78.6                     |
//|     CopyBuffer(h, 6, 0, 1, dir)  // swing direction              |
//+------------------------------------------------------------------+

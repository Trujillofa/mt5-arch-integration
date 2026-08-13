//+------------------------------------------------------------------+
//| ForexIndicatorTemplate.mq5                                       |
//| Forex overlay: EMA cloud + prior-day levels + RSI signals        |
//| v1.10 — useful levels instead of noisy ATR bands                 |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.42"
#property description "EMA cloud (bull/bear) + PDH/PDL/PDO + RSI signals + session/spread panel"
#property description "iCustom buffer 8 = signal (+1/-1/0). Closed-bar signals only."
#property strict

#property indicator_chart_window
#property indicator_buffers 12
#property indicator_plots   7

//--- plot 0+1: bull cloud (DRAW_FILLING needs 2 consecutive buffers)
#property indicator_label1  "Bull cloud"
#property indicator_type1   DRAW_FILLING
#property indicator_color1  clrMediumSeaGreen,clrMediumSeaGreen
#property indicator_style1  STYLE_SOLID
#property indicator_width1  1

//--- plot 2+3: bear cloud
#property indicator_label2  "Bear cloud"
#property indicator_type2   DRAW_FILLING
#property indicator_color2  clrIndianRed,clrIndianRed
#property indicator_style2  STYLE_SOLID
#property indicator_width2  1

//--- plot 4: EMA fast (20 or 50)
#property indicator_label3  "EMA Fast"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrDeepSkyBlue
#property indicator_style3  STYLE_SOLID
#property indicator_width3  1

//--- plot 5: EMA slow (50 or 200)
#property indicator_label4  "EMA Slow"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrOrange
#property indicator_style4  STYLE_SOLID
#property indicator_width4  2

//--- plot 6: EMA bias (200 regime)
#property indicator_label5  "EMA Bias"
#property indicator_type5   DRAW_LINE
#property indicator_color5  clrGold
#property indicator_style5  STYLE_SOLID
#property indicator_width5  2

//--- plot 7: Long arrows
#property indicator_label6  "Long"
#property indicator_type6   DRAW_ARROW
#property indicator_color6  clrLime
#property indicator_width6  2

//--- plot 8: Short arrows
#property indicator_label7  "Short"
#property indicator_type7   DRAW_ARROW
#property indicator_color7  clrOrangeRed
#property indicator_width7  2

#include <ForexUtils.mqh>

//+------------------------------------------------------------------+
//| Inputs                                                           |
//+------------------------------------------------------------------+
input group "=== Trading mode ==="
input ENUM_FX_TRADING_MODE InpTradingMode = FX_MODE_INTRADAY; // INTRADAY=20/50+200 | SWING=50/200
input bool   InpManualSessionOverride = false; // true = use session/spread inputs below instead of mode
input bool   InpManualEmaOverride = false;     // true = use EMA periods below instead of mode

input group "=== EMAs / cloud (ignored unless Manual EMA override) ==="
input int    InpEmaFastPeriod    = 20;     // Fast EMA (manual) — mode default 20 or 50
input int    InpEmaSlowPeriod    = 50;     // Slow EMA (manual) — mode default 50 or 200
input int    InpEmaBiasPeriod    = 200;    // Bias EMA (manual) — regime filter
input bool   InpShowCloud        = true;   // Trend cloud between fast/slow EMAs
input bool   InpShowEmaLines     = false;  // Draw fast/slow EMA strokes
input bool   InpShowBiasEma      = true;   // Draw EMA bias (200) when different from slow
input color  InpColorBullCloud   = clrMediumSeaGreen; // Bull cloud (fast > slow)
input color  InpColorBearCloud   = clrIndianRed;      // Bear cloud (fast < slow)
input color  InpColorEmaFast     = clrDeepSkyBlue;    // Fast EMA line
input color  InpColorEmaSlow     = clrOrange;         // Slow EMA line
input color  InpColorEmaBias     = clrGold;           // Bias EMA line

input group "=== Prior-day levels (forex S/R) ==="
input bool   InpShowPriorDay     = true;   // Show PDH / PDL / PDO
input color  InpColorPDH         = clrCrimson;     // Prior day high
input color  InpColorPDL         = clrLimeGreen;   // Prior day low
input color  InpColorPDO         = clrGold;        // Prior day open (not gray)
input int    InpLevelWidth       = 1;      // Level line width
input bool   InpLevelExtendRight = true;   // Extend levels to the right

input group "=== RSI + RSI MA ==="
input int            InpRsiPeriod     = 14;       // RSI period
input int            InpRsiMaPeriod   = 14;       // MA of RSI period (signal line)
input ENUM_MA_METHOD InpRsiMaMethod   = MODE_SMA; // MA method on RSI (SMA/EMA)
input int            InpRsiLongMax    = 35;       // Long: RSI level (cross up / max)
input int            InpRsiShortMin   = 65;       // Short: RSI level (cross down / min)
input bool           InpUseRsiMaFilter= true;     // Require RSI vs RSI-MA alignment
input bool           InpRsiMaCross    = false;    // Also allow RSI×MA cross as RSI trigger

input group "=== Signal rules ==="
input bool   InpRequireTrend     = true;   // Require EMA alignment
input bool   InpUseSessionFilter = true;   // Session filter
input bool   InpAllowAsian       = false;
input bool   InpAllowLondon      = true;
input bool   InpAllowNY          = true;
input bool   InpAllowOverlap     = true;
input double InpMaxSpreadPips    = 2.5;    // Max spread pips (0 = off)
input bool   InpSignalOnClose    = true;   // Closed bar only

input group "=== Session hours (broker SERVER time) ==="
input int    InpAsianStart       = 0;
input int    InpAsianEnd         = 8;
input int    InpLondonStart      = 7;
input int    InpLondonEnd        = 16;
input int    InpNyStart          = 12;
input int    InpNyEnd            = 21;

input group "=== Display / alerts ==="
input bool   InpShowDashboard    = true;   // Info panel (Comment — Wine-safe)
input bool   InpShowArrows       = true;
input double InpArrowOffsetPips  = 5.0;
input bool   InpAlertPopup       = false;
input bool   InpAlertPush        = false;
input bool   InpAlertSound       = false;
input string InpAlertSoundFile   = "alert.wav";

// ATR kept only for dashboard pips (not plotted)
input group "=== ATR (dashboard only) ==="
input int    InpAtrPeriod        = 14;

//+------------------------------------------------------------------+
//| Buffers                                                          |
//| 0-1 bull | 2-3 bear | 4 fast | 5 slow | 6 bias                   |
//| 7 long | 8 short | 9 signal | 10 RSI | 11 RSI-MA                 |
//+------------------------------------------------------------------+
double BufBullHi[];
double BufBullLo[];
double BufBearHi[];
double BufBearLo[];
double BufEmaFast[];
double BufEmaSlow[];
double BufEmaBias[];
double BufLong[];
double BufShort[];
double BufSignal[];
double BufRsi[];
double BufRsiMa[];

int g_hEmaFast = INVALID_HANDLE;
int g_hEmaSlow = INVALID_HANDLE;
int g_hEmaBias = INVALID_HANDLE;
int g_hAtr     = INVALID_HANDLE;
int g_hRsi     = INVALID_HANDLE;

string   g_prefix;
datetime g_last_alert_bar = 0;
FxModeSettings g_mode;

// Prior-day values
double   g_pdh = 0.0, g_pdl = 0.0, g_pdo = 0.0;
datetime g_pd_day = 0;

//+------------------------------------------------------------------+
void ApplyTradingMode()
  {
   FxResolveTradingMode(InpTradingMode,
                        InpManualSessionOverride,
                        InpUseSessionFilter,
                        InpAllowAsian, InpAllowLondon, InpAllowNY, InpAllowOverlap,
                        InpMaxSpreadPips,
                        0, // fib unused here
                        InpManualEmaOverride,
                        InpEmaFastPeriod, InpEmaSlowPeriod, InpEmaBiasPeriod,
                        g_mode);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpEmaFastPeriod < 1 || InpEmaSlowPeriod < 1 || InpEmaBiasPeriod < 1 ||
      InpRsiPeriod < 1 || InpRsiMaPeriod < 1)
      return INIT_PARAMETERS_INCORRECT;

   ApplyTradingMode();
   Print("ForexIndicatorTemplate mode=", g_mode.mode_name,
         " EMA ", g_mode.ema_fast, "/", g_mode.ema_slow, " bias=", g_mode.ema_bias,
         " sessions=", (g_mode.use_session_filter ? "on" : "off"),
         " max_spread=", DoubleToString(g_mode.max_spread_pips, 1),
         " chart_hint=", g_mode.chart_hint);

   SetIndexBuffer(0, BufBullHi,  INDICATOR_DATA);
   SetIndexBuffer(1, BufBullLo,  INDICATOR_DATA);
   SetIndexBuffer(2, BufBearHi,  INDICATOR_DATA);
   SetIndexBuffer(3, BufBearLo,  INDICATOR_DATA);
   SetIndexBuffer(4, BufEmaFast, INDICATOR_DATA);
   SetIndexBuffer(5, BufEmaSlow, INDICATOR_DATA);
   SetIndexBuffer(6, BufEmaBias, INDICATOR_DATA);
   SetIndexBuffer(7, BufLong,    INDICATOR_DATA);
   SetIndexBuffer(8, BufShort,   INDICATOR_DATA);
   SetIndexBuffer(9, BufSignal,  INDICATOR_CALCULATIONS);
   SetIndexBuffer(10, BufRsi,    INDICATOR_CALCULATIONS);
   SetIndexBuffer(11, BufRsiMa,  INDICATOR_CALCULATIONS);

   ArraySetAsSeries(BufBullHi,  false);
   ArraySetAsSeries(BufBullLo,  false);
   ArraySetAsSeries(BufBearHi,  false);
   ArraySetAsSeries(BufBearLo,  false);
   ArraySetAsSeries(BufEmaFast, false);
   ArraySetAsSeries(BufEmaSlow, false);
   ArraySetAsSeries(BufEmaBias, false);
   ArraySetAsSeries(BufLong,    false);
   ArraySetAsSeries(BufShort,   false);
   ArraySetAsSeries(BufSignal,  false);
   ArraySetAsSeries(BufRsi,     false);
   ArraySetAsSeries(BufRsiMa,   false);

   int begin = MathMax(g_mode.ema_slow, g_mode.ema_bias);
   for(int p = 0; p < 7; p++)
     {
      PlotIndexSetInteger(p, PLOT_DRAW_BEGIN, begin);
      PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
     }

   PlotIndexSetInteger(0, PLOT_LINE_COLOR, 0, InpColorBullCloud);
   PlotIndexSetInteger(0, PLOT_LINE_COLOR, 1, InpColorBullCloud);
   PlotIndexSetInteger(1, PLOT_LINE_COLOR, 0, InpColorBearCloud);
   PlotIndexSetInteger(1, PLOT_LINE_COLOR, 1, InpColorBearCloud);
   PlotIndexSetInteger(2, PLOT_LINE_COLOR, InpColorEmaFast);
   PlotIndexSetInteger(3, PLOT_LINE_COLOR, InpColorEmaSlow);
   PlotIndexSetInteger(4, PLOT_LINE_COLOR, InpColorEmaBias);
   PlotIndexSetInteger(5, PLOT_ARROW, 233);
   PlotIndexSetInteger(6, PLOT_ARROW, 234);
   PlotIndexSetInteger(5, PLOT_LINE_COLOR, clrLime);
   PlotIndexSetInteger(6, PLOT_LINE_COLOR, clrOrangeRed);

   IndicatorSetInteger(INDICATOR_DIGITS, _Digits);
   IndicatorSetString(INDICATOR_SHORTNAME,
                      StringFormat("FX %s EMA(%d/%d)+%d",
                                   g_mode.mode_name,
                                   g_mode.ema_fast, g_mode.ema_slow, g_mode.ema_bias));

   g_hEmaFast = iMA(_Symbol, PERIOD_CURRENT, g_mode.ema_fast, 0, MODE_EMA, PRICE_CLOSE);
   g_hEmaSlow = iMA(_Symbol, PERIOD_CURRENT, g_mode.ema_slow, 0, MODE_EMA, PRICE_CLOSE);
   g_hEmaBias = iMA(_Symbol, PERIOD_CURRENT, g_mode.ema_bias, 0, MODE_EMA, PRICE_CLOSE);
   g_hAtr     = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   g_hRsi     = iRSI(_Symbol, PERIOD_CURRENT, InpRsiPeriod, PRICE_CLOSE);

   if(g_hEmaFast == INVALID_HANDLE || g_hEmaSlow == INVALID_HANDLE ||
      g_hEmaBias == INVALID_HANDLE || g_hAtr == INVALID_HANDLE || g_hRsi == INVALID_HANDLE)
     {
      Print("ForexIndicatorTemplate: handle fail err=", GetLastError());
      return INIT_FAILED;
     }

   g_prefix = "FXIT_" + IntegerToString(ChartID()) + "_";
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_hEmaFast != INVALID_HANDLE) IndicatorRelease(g_hEmaFast);
   if(g_hEmaSlow != INVALID_HANDLE) IndicatorRelease(g_hEmaSlow);
   if(g_hEmaBias != INVALID_HANDLE) IndicatorRelease(g_hEmaBias);
   if(g_hAtr     != INVALID_HANDLE) IndicatorRelease(g_hAtr);
   if(g_hRsi     != INVALID_HANDLE) IndicatorRelease(g_hRsi);
   // Skip object wipe on REASON_PARAMETERS (EMA tweak) and REASON_CHARTCHANGE
   // (timeframe/symbol switch) — mass GDI delete is what freezes Wine, and on a
   // timeframe flip it deletes objects that the next instance immediately recreates
   // under the same ChartID-keyed names. Safe to skip: every draw is ObjectFind
   // guarded and repositioned by name. See ForexHtfPivotsFib.mq5 OnDeinit for the
   // captured stacks behind this.
   if(reason == REASON_REMOVE || reason == REASON_CHARTCLOSE ||
      reason == REASON_RECOMPILE)
     {
      ObjectsDeleteAll(0, g_prefix);
      Comment("");
     }
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
   int min_bars = MathMax(g_mode.ema_slow, g_mode.ema_bias) + InpRsiPeriod + InpRsiMaPeriod + 5;
   if(rates_total < min_bars)
      return 0;

   double ema_fast[], ema_slow[], ema_bias[], atr[], rsi[], rsi_ma[];
   ArraySetAsSeries(ema_fast, false);
   ArraySetAsSeries(ema_slow, false);
   ArraySetAsSeries(ema_bias, false);
   ArraySetAsSeries(atr, false);
   ArraySetAsSeries(rsi, false);
   ArraySetAsSeries(rsi_ma, false);

   if(CopyBuffer(g_hEmaFast, 0, 0, rates_total, ema_fast) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hEmaSlow, 0, 0, rates_total, ema_slow) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hEmaBias, 0, 0, rates_total, ema_bias) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hAtr, 0, 0, rates_total, atr) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hRsi, 0, 0, rates_total, rsi) < rates_total)
      return prev_calculated;

   // Full-series RSI MA (needed for correct seed); cheap vs HTF work
   if(!FxMaOnSeries(rsi, rates_total, InpRsiMaPeriod, InpRsiMaMethod, rsi_ma))
      return prev_calculated;

   // Store RSI / RSI-MA for iCustom (always full fill from start when cold)
   int copy_start = (prev_calculated > 1) ? prev_calculated - 1 : 0;
   for(int k = copy_start; k < rates_total; k++)
     {
      BufRsi[k]   = rsi[k];
      BufRsiMa[k] = rsi_ma[k];
     }

   int start = (prev_calculated > 1) ? prev_calculated - 1 : min_bars;
   double arrow_off = FxPipsToPrice(InpArrowOffsetPips);

   for(int i = start; i < rates_total && !IsStopped(); i++)
     {
      double ef = ema_fast[i];
      double es = ema_slow[i];

      double eb = ema_bias[i];

      //--- trend cloud: between timing EMAs (20/50 or 50/200)
      if(InpShowCloud && i >= g_mode.ema_slow - 1)
        {
         if(ef > es)
           {
            BufBullHi[i] = ef;
            BufBullLo[i] = es;
            BufBearHi[i] = EMPTY_VALUE;
            BufBearLo[i] = EMPTY_VALUE;
           }
         else if(ef < es)
           {
            BufBearHi[i] = es;
            BufBearLo[i] = ef;
            BufBullHi[i] = EMPTY_VALUE;
            BufBullLo[i] = EMPTY_VALUE;
           }
         else
           {
            BufBullHi[i] = EMPTY_VALUE;
            BufBullLo[i] = EMPTY_VALUE;
            BufBearHi[i] = EMPTY_VALUE;
            BufBearLo[i] = EMPTY_VALUE;
           }
        }
      else
        {
         BufBullHi[i] = EMPTY_VALUE;
         BufBullLo[i] = EMPTY_VALUE;
         BufBearHi[i] = EMPTY_VALUE;
         BufBearLo[i] = EMPTY_VALUE;
        }

      if(InpShowEmaLines)
        {
         BufEmaFast[i] = ef;
         BufEmaSlow[i] = es;
        }
      else
        {
         BufEmaFast[i] = EMPTY_VALUE;
         BufEmaSlow[i] = EMPTY_VALUE;
        }

      // Bias line: show when enabled and period differs from slow (intraday 200 vs 50)
      if(InpShowBiasEma && g_mode.ema_bias != g_mode.ema_slow)
         BufEmaBias[i] = eb;
      else if(InpShowBiasEma && InpShowEmaLines)
         BufEmaBias[i] = EMPTY_VALUE; // same as slow stroke — skip double
      else if(InpShowBiasEma && g_mode.ema_bias == g_mode.ema_slow && !InpShowEmaLines)
         BufEmaBias[i] = eb; // swing: show 200 as bias if strokes off
      else
         BufEmaBias[i] = EMPTY_VALUE;

      BufLong[i]   = EMPTY_VALUE;
      BufShort[i]  = EMPTY_VALUE;
      BufSignal[i] = 0.0;

      if(InpSignalOnClose && i == rates_total - 1)
         continue;
      if(i < 1)
         continue;

      int sig = CalculateSignal(i, time[i], close, ema_fast, ema_slow, ema_bias, rsi, rsi_ma);
      BufSignal[i] = (double)sig;

      if(sig > 0 && InpShowArrows)
         BufLong[i] = low[i] - arrow_off;
      else if(sig < 0 && InpShowArrows)
         BufShort[i] = high[i] + arrow_off;

      if(sig != 0 && i == rates_total - 2)
         MaybeAlert(time[i], sig, close[i], rsi[i], rsi_ma[i]);
     }

   if(InpShowPriorDay)
      UpdatePriorDayLevels(time, open, high, low, rates_total);

   if(InpShowDashboard)
      UpdateDashboard(time, close, ema_fast, ema_slow, ema_bias, atr, rsi, rsi_ma, rates_total);

   return rates_total;
  }

//+------------------------------------------------------------------+
//| Prior day high / low / open — real S/R for forex                 |
//+------------------------------------------------------------------+
void UpdatePriorDayLevels(const datetime &time[],
                          const double &open[],
                          const double &high[],
                          const double &low[],
                          const int rates_total)
  {
   // Broker daily bar via CopyRates is cleanest
   MqlRates day[];
   ArraySetAsSeries(day, true);
   int n = CopyRates(_Symbol, PERIOD_D1, 0, 3, day);
   if(n < 2)
      return;

   // day[0] = current (forming) day, day[1] = completed prior day
   double pdh = day[1].high;
   double pdl = day[1].low;
   double pdo = day[1].open;
   datetime day_start = day[1].time;

   // Only rebuild objects when the prior day changes
   if(day_start == g_pd_day && g_pdh == pdh && g_pdl == pdl && g_pdo == pdo)
     {
      // still refresh right endpoint so lines track the chart edge
      datetime t_right = time[rates_total - 1] + PeriodSeconds();
      MoveHLine("PDH", pdh, day_start, t_right, InpColorPDH, "PDH");
      MoveHLine("PDL", pdl, day_start, t_right, InpColorPDL, "PDL");
      MoveHLine("PDO", pdo, day_start, t_right, InpColorPDO, "PDO");
      return;
     }

   g_pd_day = day_start;
   g_pdh = pdh;
   g_pdl = pdl;
   g_pdo = pdo;

   datetime t_right = time[rates_total - 1] + PeriodSeconds();
   MoveHLine("PDH", pdh, day_start, t_right, InpColorPDH, "PDH " + DoubleToString(pdh, _Digits));
   MoveHLine("PDL", pdl, day_start, t_right, InpColorPDL, "PDL " + DoubleToString(pdl, _Digits));
   MoveHLine("PDO", pdo, day_start, t_right, InpColorPDO, "PDO " + DoubleToString(pdo, _Digits));
  }

//+------------------------------------------------------------------+
void MoveHLine(const string key, const double price,
               const datetime t1, const datetime t2,
               const color clr, const string label)
  {
   string name = g_prefix + key;
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_TREND, 0, t1, price, t2, price);
      ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, InpLevelExtendRight);
      ObjectSetInteger(0, name, OBJPROP_RAY_LEFT, false);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, InpLevelWidth);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectMove(0, name, 0, t1, price);
   ObjectMove(0, name, 1, t2, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, InpLevelExtendRight);

   string lname = g_prefix + key + "_lbl";
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
   ObjectSetString(0, lname, OBJPROP_TEXT, " " + label);
   ObjectSetInteger(0, lname, OBJPROP_COLOR, clr);
  }

//+------------------------------------------------------------------+
int CalculateSignal(const int i,
                    const datetime bar_time,
                    const double &close[],
                    const double &ema_fast[],
                    const double &ema_slow[],
                    const double &ema_bias[],
                    const double &rsi[],
                    const double &rsi_ma[])
  {
   if(g_mode.max_spread_pips > 0.0 && FxSpreadPips(_Symbol) > g_mode.max_spread_pips)
      return 0;

   if(g_mode.use_session_filter)
     {
      ENUM_FX_SESSION sess = FxDetectSession(bar_time,
                                             InpAsianStart, InpAsianEnd,
                                             InpLondonStart, InpLondonEnd,
                                             InpNyStart, InpNyEnd);
      if(!SessionAllowedMode(sess))
         return 0;
     }

   double c  = close[i];
   double ef = ema_fast[i];
   double es = ema_slow[i];
   double eb = ema_bias[i];
   double r0 = rsi[i];
   double r1 = rsi[i - 1];
   double m0 = rsi_ma[i];
   double m1 = rsi_ma[i - 1];

   // Timing: fast vs slow. Regime: close vs bias EMA (200).
   bool bull_timing = (ef > es);
   bool bear_timing = (ef < es);
   bool bull_regime = (!g_mode.use_bias_ema || c > eb);
   bool bear_regime = (!g_mode.use_bias_ema || c < eb);

   bool bull_trend = bull_regime && (!InpRequireTrend || bull_timing);
   bool bear_trend = bear_regime && (!InpRequireTrend || bear_timing);

   // Level crosses (classic)
   bool rsi_cross_up   = (r1 <= (double)InpRsiLongMax)  && (r0 >  (double)InpRsiLongMax);
   bool rsi_cross_down = (r1 >= (double)InpRsiShortMin) && (r0 <  (double)InpRsiShortMin);

   // RSI × RSI-MA crosses (optional extra trigger)
   if(InpRsiMaCross)
     {
      if(FxRsiMaCrossUp(r1, m1, r0, m0))
         rsi_cross_up = true;
      if(FxRsiMaCrossDown(r1, m1, r0, m0))
         rsi_cross_down = true;
     }

   // RSI above/below its MA filter
   if(InpUseRsiMaFilter)
     {
      if(FxRsiMaBias(r0, m0) < 1)
         rsi_cross_up = false;    // need RSI > MA for long
      if(FxRsiMaBias(r0, m0) > -1)
         rsi_cross_down = false;  // need RSI < MA for short
     }

   if(bull_trend && rsi_cross_up)
      return 1;
   if(bear_trend && rsi_cross_down)
      return -1;
   return 0;
  }

//+------------------------------------------------------------------+
bool SessionAllowedMode(const ENUM_FX_SESSION s)
  {
   switch(s)
     {
      case FX_SESSION_ASIAN:   return g_mode.allow_asian;
      case FX_SESSION_LONDON:  return g_mode.allow_london;
      case FX_SESSION_NY:      return g_mode.allow_ny;
      case FX_SESSION_OVERLAP: return g_mode.allow_overlap;
      default:                 return false;
     }
  }

//+------------------------------------------------------------------+
void MaybeAlert(const datetime bar_time, const int sig,
                const double price, const double rsi_val, const double rsi_ma_val)
  {
   if(bar_time == g_last_alert_bar)
      return;
   g_last_alert_bar = bar_time;

   string side = (sig > 0) ? "LONG" : "SHORT";
   string msg = StringFormat("%s %s %s | %s RSI=%.1f MA=%.1f spr=%.1fp",
                             _Symbol, EnumToString(Period()), side,
                             DoubleToString(price, _Digits),
                             rsi_val, rsi_ma_val, FxSpreadPips(_Symbol));
   if(InpAlertPopup)
      Alert(msg);
   if(InpAlertPush)
      SendNotification(msg);
   if(InpAlertSound)
      PlaySound(InpAlertSoundFile);
   Print("ForexIndicatorTemplate: ", msg);
  }

//+------------------------------------------------------------------+
//| Info panel via Comment() — only reliable multi-line under Wine   |
//| (stacked OBJ_LABEL overlap / garble on Wine MT5)                 |
//+------------------------------------------------------------------+
string TfShortName()
  {
   // PERIOD_H1 -> H1
   string s = EnumToString(Period());
   string p = "PERIOD_";
   if(StringFind(s, p) == 0)
      s = StringSubstr(s, StringLen(p));
   return s;
  }

void UpdateDashboard(const datetime &time[],
                     const double &close[],
                     const double &ema_fast[],
                     const double &ema_slow[],
                     const double &ema_bias[],
                     const double &atr[],
                     const double &rsi[],
                     const double &rsi_ma[],
                     const int rates_total)
  {
   int i = rates_total - 1;
   if(i < 1)
      return;

   static bool cleaned = false;
   if(!cleaned)
     {
      for(int r = 0; r < 16; r++)
         ObjectDelete(0, g_prefix + "d" + IntegerToString(r));
      cleaned = true;
     }

   if(!InpShowDashboard)
     {
      Comment("");
      return;
     }

   ENUM_FX_SESSION sess = FxDetectSession(time[i],
                                          InpAsianStart, InpAsianEnd,
                                          InpLondonStart, InpLondonEnd,
                                          InpNyStart, InpNyEnd);

   double atr_pips = (atr[i] > 0.0) ? FxPriceToPips(atr[i]) : 0.0;
   double sp = FxSpreadPips(_Symbol);

   string bias = "FLAT";
   if(close[i] > ema_bias[i] && ema_fast[i] > ema_slow[i])
      bias = "BULL";
   else if(close[i] < ema_bias[i] && ema_fast[i] < ema_slow[i])
      bias = "BEAR";

   int closed = rates_total - 2;
   double last_sig = (closed >= 0) ? BufSignal[closed] : 0.0;
   double dist_bias = FxPriceToPips(close[i] - ema_bias[i]);

   int rsi_ma_bias = FxRsiMaBias(rsi[i], rsi_ma[i]);
   string rsi_rel = (rsi_ma_bias > 0) ? "above MA" : (rsi_ma_bias < 0 ? "below MA" : "flat");

   ApplyTradingMode();

   string panel =
      "=== FX Template v1.41 ===\n" +
      StringFormat("Mode    : %s  (%s)\n", g_mode.mode_name, g_mode.chart_hint) +
      StringFormat("EMAs    : %d / %d  bias %d\n",
                   g_mode.ema_fast, g_mode.ema_slow, g_mode.ema_bias) +
      StringFormat("%s | %s\n", _Symbol, TfShortName()) +
      StringFormat("Session : %s%s\n", FxSessionName(sess),
                   g_mode.use_session_filter ? "" : " (filter off)") +
      StringFormat("Spread  : %.1f p  (max %s)\n", sp,
                   (g_mode.max_spread_pips > 0.0
                    ? DoubleToString(g_mode.max_spread_pips, 1)
                    : "off")) +
      StringFormat("ATR(%d) : %.1f p\n", InpAtrPeriod, atr_pips) +
      StringFormat("RSI(%d) : %.1f\n", InpRsiPeriod, rsi[i]) +
      StringFormat("RSI MA(%d): %.1f  (%s)\n", InpRsiMaPeriod, rsi_ma[i], rsi_rel) +
      StringFormat("vs EMA%d: %+.1f p\n", g_mode.ema_bias, dist_bias) +
      StringFormat("Bias    : %s\n", bias) +
      StringFormat("Signal  : %+.0f", last_sig);

   Comment(panel);
  }

//+------------------------------------------------------------------+
//| EA: CopyBuffer(h, 9, 1, 1, sig)   signal                         |
//|     CopyBuffer(h, 10, 0, 1, rsi)  RSI                            |
//|     CopyBuffer(h, 11, 0, 1, rma)  RSI-MA                         |
//| Note: signal buffer index moved 8 → 9 after EMA bias plot.       |
//+------------------------------------------------------------------+

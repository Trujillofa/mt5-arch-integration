//+------------------------------------------------------------------+
//| ForexIndicatorTemplate.mq5                                       |
//| Forex overlay: EMA cloud + prior-day levels + RSI signals        |
//| v1.10 — useful levels instead of noisy ATR bands                 |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.11"
#property description "EMA cloud (bull/bear) + PDH/PDL/PDO + RSI signals + session/spread panel"
#property description "iCustom buffer 8 = signal (+1/-1/0). Closed-bar signals only."
#property strict

#property indicator_chart_window
#property indicator_buffers 9
#property indicator_plots   6

//--- plot 0+1: bull cloud (DRAW_FILLING needs 2 consecutive buffers)
//    Bright teal-green — readable on black (no DimGray / mud)
#property indicator_label1  "Bull cloud"
#property indicator_type1   DRAW_FILLING
#property indicator_color1  clrMediumSeaGreen,clrMediumSeaGreen
#property indicator_style1  STYLE_SOLID
#property indicator_width1  1

//--- plot 2+3: bear cloud — clear coral red
#property indicator_label2  "Bear cloud"
#property indicator_type2   DRAW_FILLING
#property indicator_color2  clrIndianRed,clrIndianRed
#property indicator_style2  STYLE_SOLID
#property indicator_width2  1

//--- plot 4: EMA fast
#property indicator_label3  "EMA Fast"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrDeepSkyBlue
#property indicator_style3  STYLE_SOLID
#property indicator_width3  1

//--- plot 5: EMA slow
#property indicator_label4  "EMA Slow"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrGold
#property indicator_style4  STYLE_SOLID
#property indicator_width4  2

//--- plot 6: Long arrows
#property indicator_label5  "Long"
#property indicator_type5   DRAW_ARROW
#property indicator_color5  clrLime
#property indicator_width5  2

//--- plot 7: Short arrows
#property indicator_label6  "Short"
#property indicator_type6   DRAW_ARROW
#property indicator_color6  clrOrangeRed
#property indicator_width6  2

#include <ForexUtils.mqh>

//+------------------------------------------------------------------+
//| Inputs                                                           |
//+------------------------------------------------------------------+
input group "=== EMAs / cloud ==="
input int    InpEmaFastPeriod    = 50;     // Fast EMA
input int    InpEmaSlowPeriod    = 200;    // Slow EMA
input bool   InpShowCloud        = true;   // Trend cloud between EMAs (main visual)
input bool   InpShowEmaLines     = false;  // Also draw EMA line strokes (off = cleaner)
input color  InpColorBullCloud   = clrMediumSeaGreen; // Bull cloud (fast > slow)
input color  InpColorBearCloud   = clrIndianRed;      // Bear cloud (fast < slow)
input color  InpColorEmaFast     = clrDeepSkyBlue;    // Fast EMA line
input color  InpColorEmaSlow     = clrGold;           // Slow EMA line

input group "=== Prior-day levels (forex S/R) ==="
input bool   InpShowPriorDay     = true;   // Show PDH / PDL / PDO
input color  InpColorPDH         = clrCrimson;     // Prior day high
input color  InpColorPDL         = clrLimeGreen;   // Prior day low
input color  InpColorPDO         = clrGold;        // Prior day open (not gray)
input int    InpLevelWidth       = 1;      // Level line width
input bool   InpLevelExtendRight = true;   // Extend levels to the right

input group "=== RSI confluence ==="
input int    InpRsiPeriod        = 14;     // RSI period
input int    InpRsiLongMax       = 35;     // Long: RSI cross up through
input int    InpRsiShortMin      = 65;     // Short: RSI cross down through

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
input bool   InpShowDashboard    = true;
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
//| 0-1 bull fill | 2-3 bear fill | 4 EMA fast | 5 EMA slow          |
//| 6 long arrow | 7 short arrow | 8 signal (+1/-1/0)                |
//+------------------------------------------------------------------+
double BufBullHi[];
double BufBullLo[];
double BufBearHi[];
double BufBearLo[];
double BufEmaFast[];
double BufEmaSlow[];
double BufLong[];
double BufShort[];
double BufSignal[];

int g_hEmaFast = INVALID_HANDLE;
int g_hEmaSlow = INVALID_HANDLE;
int g_hAtr     = INVALID_HANDLE;
int g_hRsi     = INVALID_HANDLE;

string   g_prefix;
datetime g_last_alert_bar = 0;

// Prior-day values
double   g_pdh = 0.0, g_pdl = 0.0, g_pdo = 0.0;
datetime g_pd_day = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpEmaFastPeriod < 1 || InpEmaSlowPeriod < 1 || InpRsiPeriod < 1)
      return INIT_PARAMETERS_INCORRECT;

   // DRAW_FILLING plots: each "plot" consumes 2 buffers in order
   SetIndexBuffer(0, BufBullHi,  INDICATOR_DATA);
   SetIndexBuffer(1, BufBullLo,  INDICATOR_DATA);
   SetIndexBuffer(2, BufBearHi,  INDICATOR_DATA);
   SetIndexBuffer(3, BufBearLo,  INDICATOR_DATA);
   SetIndexBuffer(4, BufEmaFast, INDICATOR_DATA);
   SetIndexBuffer(5, BufEmaSlow, INDICATOR_DATA);
   SetIndexBuffer(6, BufLong,    INDICATOR_DATA);
   SetIndexBuffer(7, BufShort,   INDICATOR_DATA);
   SetIndexBuffer(8, BufSignal,  INDICATOR_CALCULATIONS);

   ArraySetAsSeries(BufBullHi,  false);
   ArraySetAsSeries(BufBullLo,  false);
   ArraySetAsSeries(BufBearHi,  false);
   ArraySetAsSeries(BufBearLo,  false);
   ArraySetAsSeries(BufEmaFast, false);
   ArraySetAsSeries(BufEmaSlow, false);
   ArraySetAsSeries(BufLong,    false);
   ArraySetAsSeries(BufShort,   false);
   ArraySetAsSeries(BufSignal,  false);

   int begin = InpEmaSlowPeriod;
   for(int p = 0; p < 6; p++)
     {
      PlotIndexSetInteger(p, PLOT_DRAW_BEGIN, begin);
      PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
     }

   // Apply input colors at runtime (overrides muddy #property defaults if changed)
   PlotIndexSetInteger(0, PLOT_LINE_COLOR, 0, InpColorBullCloud);
   PlotIndexSetInteger(0, PLOT_LINE_COLOR, 1, InpColorBullCloud);
   PlotIndexSetInteger(1, PLOT_LINE_COLOR, 0, InpColorBearCloud);
   PlotIndexSetInteger(1, PLOT_LINE_COLOR, 1, InpColorBearCloud);
   PlotIndexSetInteger(2, PLOT_LINE_COLOR, InpColorEmaFast);
   PlotIndexSetInteger(3, PLOT_LINE_COLOR, InpColorEmaSlow);
   PlotIndexSetInteger(4, PLOT_ARROW, 233);
   PlotIndexSetInteger(5, PLOT_ARROW, 234);
   PlotIndexSetInteger(4, PLOT_LINE_COLOR, clrLime);
   PlotIndexSetInteger(5, PLOT_LINE_COLOR, clrOrangeRed);

   IndicatorSetInteger(INDICATOR_DIGITS, _Digits);
   IndicatorSetString(INDICATOR_SHORTNAME,
                      StringFormat("FX EMA(%d/%d) cloud", InpEmaFastPeriod, InpEmaSlowPeriod));

   g_hEmaFast = iMA(_Symbol, PERIOD_CURRENT, InpEmaFastPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_hEmaSlow = iMA(_Symbol, PERIOD_CURRENT, InpEmaSlowPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_hAtr     = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   g_hRsi     = iRSI(_Symbol, PERIOD_CURRENT, InpRsiPeriod, PRICE_CLOSE);

   if(g_hEmaFast == INVALID_HANDLE || g_hEmaSlow == INVALID_HANDLE ||
      g_hAtr == INVALID_HANDLE || g_hRsi == INVALID_HANDLE)
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
   if(g_hAtr     != INVALID_HANDLE) IndicatorRelease(g_hAtr);
   if(g_hRsi     != INVALID_HANDLE) IndicatorRelease(g_hRsi);
   ObjectsDeleteAll(0, g_prefix);
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
   int min_bars = InpEmaSlowPeriod + InpRsiPeriod + 5;
   if(rates_total < min_bars)
      return 0;

   double ema_fast[], ema_slow[], atr[], rsi[];
   ArraySetAsSeries(ema_fast, false);
   ArraySetAsSeries(ema_slow, false);
   ArraySetAsSeries(atr, false);
   ArraySetAsSeries(rsi, false);

   if(CopyBuffer(g_hEmaFast, 0, 0, rates_total, ema_fast) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hEmaSlow, 0, 0, rates_total, ema_slow) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hAtr, 0, 0, rates_total, atr) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hRsi, 0, 0, rates_total, rsi) < rates_total)
      return prev_calculated;

   int start = (prev_calculated > 1) ? prev_calculated - 1 : min_bars;
   double arrow_off = FxPipsToPrice(InpArrowOffsetPips);

   for(int i = start; i < rates_total && !IsStopped(); i++)
     {
      double ef = ema_fast[i];
      double es = ema_slow[i];

      //--- trend cloud: soft fill only on the side that matches bias
      if(InpShowCloud && i >= InpEmaSlowPeriod - 1)
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

      //--- EMA strokes optional (off by default — cloud is enough)
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

      BufLong[i]   = EMPTY_VALUE;
      BufShort[i]  = EMPTY_VALUE;
      BufSignal[i] = 0.0;

      if(InpSignalOnClose && i == rates_total - 1)
         continue;
      if(i < 1)
         continue;

      int sig = CalculateSignal(i, time[i], close, ema_fast, ema_slow, rsi);
      BufSignal[i] = (double)sig;

      if(sig > 0 && InpShowArrows)
         BufLong[i] = low[i] - arrow_off;
      else if(sig < 0 && InpShowArrows)
         BufShort[i] = high[i] + arrow_off;

      if(sig != 0 && i == rates_total - 2)
         MaybeAlert(time[i], sig, close[i], rsi[i]);
     }

   if(InpShowPriorDay)
      UpdatePriorDayLevels(time, open, high, low, rates_total);

   if(InpShowDashboard)
      UpdateDashboard(time, close, ema_fast, ema_slow, atr, rsi, rates_total);

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
                    const double &rsi[])
  {
   if(InpMaxSpreadPips > 0.0 && FxSpreadPips(_Symbol) > InpMaxSpreadPips)
      return 0;

   if(InpUseSessionFilter)
     {
      ENUM_FX_SESSION sess = FxDetectSession(bar_time,
                                             InpAsianStart, InpAsianEnd,
                                             InpLondonStart, InpLondonEnd,
                                             InpNyStart, InpNyEnd);
      if(!SessionAllowed(sess))
         return 0;
     }

   double c  = close[i];
   double ef = ema_fast[i];
   double es = ema_slow[i];
   double r0 = rsi[i];
   double r1 = rsi[i - 1];

   bool bull_trend = (c > es) && (!InpRequireTrend || ef > es);
   bool bear_trend = (c < es) && (!InpRequireTrend || ef < es);
   bool rsi_cross_up   = (r1 <= (double)InpRsiLongMax)  && (r0 >  (double)InpRsiLongMax);
   bool rsi_cross_down = (r1 >= (double)InpRsiShortMin) && (r0 <  (double)InpRsiShortMin);

   if(bull_trend && rsi_cross_up)
      return 1;
   if(bear_trend && rsi_cross_down)
      return -1;
   return 0;
  }

//+------------------------------------------------------------------+
bool SessionAllowed(const ENUM_FX_SESSION s)
  {
   switch(s)
     {
      case FX_SESSION_ASIAN:   return InpAllowAsian;
      case FX_SESSION_LONDON:  return InpAllowLondon;
      case FX_SESSION_NY:      return InpAllowNY;
      case FX_SESSION_OVERLAP: return InpAllowOverlap;
      default:                 return false;
     }
  }

//+------------------------------------------------------------------+
void MaybeAlert(const datetime bar_time, const int sig,
                const double price, const double rsi_val)
  {
   if(bar_time == g_last_alert_bar)
      return;
   g_last_alert_bar = bar_time;

   string side = (sig > 0) ? "LONG" : "SHORT";
   string msg = StringFormat("%s %s %s | %s RSI=%.1f spr=%.1fp",
                             _Symbol, EnumToString(Period()), side,
                             DoubleToString(price, _Digits),
                             rsi_val, FxSpreadPips(_Symbol));
   if(InpAlertPopup)
      Alert(msg);
   if(InpAlertPush)
      SendNotification(msg);
   if(InpAlertSound)
      PlaySound(InpAlertSoundFile);
   Print("ForexIndicatorTemplate: ", msg);
  }

//+------------------------------------------------------------------+
//| Multi-line panel via stacked labels (Wine-safe — no \\n)         |
//+------------------------------------------------------------------+
void UpdateDashboard(const datetime &time[],
                     const double &close[],
                     const double &ema_fast[],
                     const double &ema_slow[],
                     const double &atr[],
                     const double &rsi[],
                     const int rates_total)
  {
   int i = rates_total - 1;
   if(i < 1)
      return;

   ENUM_FX_SESSION sess = FxDetectSession(time[i],
                                          InpAsianStart, InpAsianEnd,
                                          InpLondonStart, InpLondonEnd,
                                          InpNyStart, InpNyEnd);

   double atr_pips = (atr[i] > 0.0) ? FxPriceToPips(atr[i]) : 0.0;
   double sp = FxSpreadPips(_Symbol);

   string bias = "FLAT";
   color  bias_col = clrWhite;
   if(close[i] > ema_slow[i] && ema_fast[i] > ema_slow[i])
     { bias = "BULL"; bias_col = clrLime; }
   else if(close[i] < ema_slow[i] && ema_fast[i] < ema_slow[i])
     { bias = "BEAR"; bias_col = clrOrangeRed; }

   int closed = rates_total - 2;
   double last_sig = (closed >= 0) ? BufSignal[closed] : 0.0;

   // Distance of price to EMA200 in pips (actionable)
   double dist_slow = FxPriceToPips(close[i] - ema_slow[i]);

   string lines[];
   ArrayResize(lines, 8);
   lines[0] = StringFormat("%s  %s", _Symbol, EnumToString(Period()));
   lines[1] = StringFormat("Session  %s", FxSessionName(sess));
   lines[2] = StringFormat("Spread   %.1f p  (max %.1f)", sp, InpMaxSpreadPips);
   lines[3] = StringFormat("ATR(%d)   %.1f p", InpAtrPeriod, atr_pips);
   lines[4] = StringFormat("RSI(%d)   %.1f", InpRsiPeriod, rsi[i]);
   lines[5] = StringFormat("vs EMA%d  %+.1f p", InpEmaSlowPeriod, dist_slow);
   lines[6] = StringFormat("Bias     %s", bias);
   lines[7] = StringFormat("Signal   %+.0f", last_sig);

   // No DimGray / Silver — high-contrast on black charts
   color cols[];
   ArrayResize(cols, 8);
   cols[0] = clrWhite;
   cols[1] = clrAqua;
   cols[2] = (InpMaxSpreadPips > 0.0 && sp > InpMaxSpreadPips) ? clrOrangeRed : clrKhaki;
   cols[3] = clrKhaki;
   cols[4] = clrViolet;
   cols[5] = (dist_slow >= 0.0) ? clrLimeGreen : clrOrangeRed;
   cols[6] = bias_col;
   cols[7] = (last_sig > 0) ? clrLime : (last_sig < 0 ? clrOrangeRed : clrWhite);

   const int x0 = 10;
   const int y0 = 18;
   const int dy = 14;

   for(int row = 0; row < 8; row++)
     {
      string name = g_prefix + "d" + IntegerToString(row);
      if(ObjectFind(0, name) < 0)
        {
         ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
         ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
         ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x0);
         ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y0 + row * dy);
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
//| EA: CopyBuffer(handle, 8, 1, 1, sig)  // buffer 8, last closed   |
//+------------------------------------------------------------------+

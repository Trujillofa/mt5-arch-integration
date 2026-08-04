//+------------------------------------------------------------------+
//| BtcTrendPullback.mq5                                             |
//| BTCUSD CFD visual indicator (Wave B observe)                     |
//|                                                                  |
//| H4 completed-bar EMA50/200 bias + H1 closed-bar pullback reclaim |
//| ATR% liveliness, ATR price stop-guides, optional continuation.   |
//| DNA: crypto-agent TrendPullback — NOT Forex Fib pivots.          |
//|                                                                  |
//| Chart: BTCUSD H1 recommended. Signal buffer 7 = +1/−1/0.         |
//| Logger: ForexSignalLogger InpIndicatorName=BtcTrendPullback      |
//|         InpSignalBuffer=7 InpMaxSpreadPips=0                     |
//| Never OrderSend.                                                 |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.00"
#property description "BTC trend pullback: H4 bias + H1 reclaim. Signal buffer 7 (+1/−1/0)."
#property description "Closed bars only. ATR guides — not FX pips. Visual/iCustom only."
#property strict

#property indicator_chart_window
#property indicator_buffers 8
#property indicator_plots   6

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

#property indicator_label3  "ATR Lower"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrDimGray
#property indicator_style3  STYLE_DOT
#property indicator_width3  1

#property indicator_label4  "ATR Upper"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrDimGray
#property indicator_style4  STYLE_DOT
#property indicator_width4  1

#property indicator_label5  "Long"
#property indicator_type5   DRAW_ARROW
#property indicator_color5  clrLime
#property indicator_width5  2

#property indicator_label6  "Short"
#property indicator_type6   DRAW_ARROW
#property indicator_color6  clrOrangeRed
#property indicator_width6  2

//+------------------------------------------------------------------+
enum ENUM_ATR_BAND_MID
  {
   ATR_MID_EMA50 = 0, // EMA50
   ATR_MID_CLOSE = 1  // Close
  };

//+------------------------------------------------------------------+
input group "=== EMAs (chart TF) ==="
input int    InpEmaFast                 = 50;
input int    InpEmaSlow                 = 200;
input bool   InpShowEmas                = true;

input group "=== HTF bias ==="
input ENUM_TIMEFRAMES InpHtfPeriod      = PERIOD_H4;
input double InpMinTrendStrengthPct     = 0.01;   // 1.0%
input double InpStrongTrendStrengthPct  = 0.015;  // 1.5%

input group "=== RSI ==="
input int    InpRsiPeriod               = 14;
input double InpRsiReclaim              = 50.0;
input double InpContinuationRsi         = 54.0;

input group "=== MACD ==="
input int    InpMacdFast                = 12;
input int    InpMacdSlow                = 26;
input int    InpMacdSignal              = 9;
input double InpMinMacdHist             = 0.0;

input group "=== ATR / liveliness / bands ==="
input int    InpAtrPeriod               = 14;
input double InpMinAtrPct               = 0.01;   // 1% of price
input double InpAtrBandMult             = 2.0;
input ENUM_ATR_BAND_MID InpAtrBandMid   = ATR_MID_EMA50;
input bool   InpShowAtrBands            = true;

input group "=== Pullback / extension ==="
input double InpMaxPullbackPct          = 0.015;  // 1.5%
input double InpMaxEma50ExtensionPct    = 0.03;   // 3%

input group "=== VWAP (optional; OFF by default) ==="
input bool   InpUseVwap                 = false;
input double InpVwapPullbackPct         = 0.01;
input int    InpVwapLookback            = 24;     // bars for rolling VWAP if enabled

input group "=== Modes ==="
input bool   InpAllowContinuation       = true;
input bool   InpDeepReclaimEnabled      = false;
input int    InpDeepReclaimArmBars      = 3;
input double InpDeepReclaimArmMaxPct    = 0.03;
input bool   InpAllowShorts             = true;
input bool   InpPanicBlock              = true;
input double InpPanicRsi                = 35.0;
input double InpPanicAtrPct             = 0.08;
input bool   InpEdgeTrigger             = true;

input group "=== Display ==="
input bool   InpShowMarkers             = true;
input bool   InpShowPanel               = true;
input double InpArrowOffsetAtrFrac      = 0.15;   // price offset = frac × ATR

//+------------------------------------------------------------------+
//| Buffers: 0 EMA50 | 1 EMA200 | 2 ATR lo | 3 ATR hi                |
//|          4 Long  | 5 Short  | 6 HTF bias | 7 signal              |
//+------------------------------------------------------------------+
double BufEma50[];
double BufEma200[];
double BufAtrLower[];
double BufAtrUpper[];
double BufLong[];
double BufShort[];
double BufHtfBias[];
double BufSignal[];

int g_hEma50    = INVALID_HANDLE;
int g_hEma200   = INVALID_HANDLE;
int g_hRsi      = INVALID_HANDLE;
int g_hMacd     = INVALID_HANDLE;
int g_hAtr      = INVALID_HANDLE;
int g_hHtfEma50 = INVALID_HANDLE;
int g_hHtfEma200= INVALID_HANDLE;

string g_pfx;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpEmaFast < 1 || InpEmaSlow < InpEmaFast)
      return INIT_PARAMETERS_INCORRECT;
   if(InpRsiPeriod < 2 || InpAtrPeriod < 1)
      return INIT_PARAMETERS_INCORRECT;
   if(InpMacdSlow <= InpMacdFast)
      return INIT_PARAMETERS_INCORRECT;

   SetIndexBuffer(0, BufEma50,    INDICATOR_DATA);
   SetIndexBuffer(1, BufEma200,   INDICATOR_DATA);
   SetIndexBuffer(2, BufAtrLower, INDICATOR_DATA);
   SetIndexBuffer(3, BufAtrUpper, INDICATOR_DATA);
   SetIndexBuffer(4, BufLong,     INDICATOR_DATA);
   SetIndexBuffer(5, BufShort,    INDICATOR_DATA);
   SetIndexBuffer(6, BufHtfBias,  INDICATOR_CALCULATIONS);
   SetIndexBuffer(7, BufSignal,   INDICATOR_CALCULATIONS);

   ArraySetAsSeries(BufEma50, false);
   ArraySetAsSeries(BufEma200, false);
   ArraySetAsSeries(BufAtrLower, false);
   ArraySetAsSeries(BufAtrUpper, false);
   ArraySetAsSeries(BufLong, false);
   ArraySetAsSeries(BufShort, false);
   ArraySetAsSeries(BufHtfBias, false);
   ArraySetAsSeries(BufSignal, false);

   int begin = MathMax(InpEmaSlow, MathMax(InpMacdSlow + InpMacdSignal, InpAtrPeriod)) + 5;
   for(int p = 0; p < 6; p++)
     {
      PlotIndexSetInteger(p, PLOT_DRAW_BEGIN, begin);
      PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
     }
   PlotIndexSetInteger(4, PLOT_ARROW, 233);
   PlotIndexSetInteger(5, PLOT_ARROW, 234);

   IndicatorSetInteger(INDICATOR_DIGITS, _Digits);
   IndicatorSetString(INDICATOR_SHORTNAME,
                      "BtcTrendPullback | sig@7 closed-bar");

   g_hEma50  = iMA(_Symbol, PERIOD_CURRENT, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   g_hEma200 = iMA(_Symbol, PERIOD_CURRENT, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   g_hRsi    = iRSI(_Symbol, PERIOD_CURRENT, InpRsiPeriod, PRICE_CLOSE);
   g_hMacd   = iMACD(_Symbol, PERIOD_CURRENT, InpMacdFast, InpMacdSlow, InpMacdSignal, PRICE_CLOSE);
   g_hAtr    = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   g_hHtfEma50  = iMA(_Symbol, InpHtfPeriod, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   g_hHtfEma200 = iMA(_Symbol, InpHtfPeriod, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);

   if(g_hEma50 == INVALID_HANDLE || g_hEma200 == INVALID_HANDLE ||
      g_hRsi == INVALID_HANDLE || g_hMacd == INVALID_HANDLE ||
      g_hAtr == INVALID_HANDLE || g_hHtfEma50 == INVALID_HANDLE ||
      g_hHtfEma200 == INVALID_HANDLE)
      return INIT_FAILED;

   g_pfx = "BTCTP_" + IntegerToString(ChartID()) + "_";
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_hEma50     != INVALID_HANDLE) IndicatorRelease(g_hEma50);
   if(g_hEma200    != INVALID_HANDLE) IndicatorRelease(g_hEma200);
   if(g_hRsi       != INVALID_HANDLE) IndicatorRelease(g_hRsi);
   if(g_hMacd      != INVALID_HANDLE) IndicatorRelease(g_hMacd);
   if(g_hAtr       != INVALID_HANDLE) IndicatorRelease(g_hAtr);
   if(g_hHtfEma50  != INVALID_HANDLE) IndicatorRelease(g_hHtfEma50);
   if(g_hHtfEma200 != INVALID_HANDLE) IndicatorRelease(g_hHtfEma200);
   ObjectsDeleteAll(0, g_pfx);
  }

//+------------------------------------------------------------------+
//| Last fully completed HTF bar shift (as-of chart_time, no lookfwd)|
//+------------------------------------------------------------------+
int CompletedHtfShift(const datetime chart_time)
  {
   int sh = iBarShift(_Symbol, InpHtfPeriod, chart_time, false);
   if(sh < 0)
      return -1;
   datetime open_t = iTime(_Symbol, InpHtfPeriod, sh);
   if(open_t <= 0)
      return -1;
   int sec = PeriodSeconds(InpHtfPeriod);
   // Still inside this HTF bar at chart_time → use previous completed bar
   if((long)open_t + (long)sec > (long)chart_time)
      sh += 1;
   return sh;
  }

//+------------------------------------------------------------------+
bool CopyHtfEma(const int shift, double &ema50, double &ema200, double &htf_close)
  {
   if(shift < 0)
      return false;
   double a50[1], a200[1];
   if(CopyBuffer(g_hHtfEma50,  0, shift, 1, a50)  != 1) return false;
   if(CopyBuffer(g_hHtfEma200, 0, shift, 1, a200) != 1) return false;
   htf_close = iClose(_Symbol, InpHtfPeriod, shift);
   if(htf_close <= 0.0)
      return false;
   ema50  = a50[0];
   ema200 = a200[0];
   return (ema50 > 0.0 && ema200 > 0.0);
  }

//+------------------------------------------------------------------+
int HtfBiasAt(const datetime chart_time, double &out_strength)
  {
   out_strength = 0.0;
   int sh = CompletedHtfShift(chart_time);
   double e50, e200, c;
   if(!CopyHtfEma(sh, e50, e200, c))
      return 0;
   out_strength = (e50 - e200) / e200;
   if(c > e200 && e50 > e200 && out_strength >= InpMinTrendStrengthPct)
      return +1;
   if(c < e200 && e50 < e200 && (-out_strength) >= InpMinTrendStrengthPct)
      return -1;
   return 0;
  }

//+------------------------------------------------------------------+
double RollingVwap(const int i,
                   const double &high[],
                   const double &low[],
                   const double &close[],
                   const long &tick_volume[])
  {
   int n = MathMax(1, InpVwapLookback);
   int from = MathMax(0, i - n + 1);
   double num = 0.0, den = 0.0;
   for(int k = from; k <= i; k++)
     {
      double typ = (high[k] + low[k] + close[k]) / 3.0;
      double vol = (double)MathMax(tick_volume[k], 1);
      num += typ * vol;
      den += vol;
     }
   if(den <= 0.0)
      return close[i];
   return num / den;
  }

//+------------------------------------------------------------------+
bool PanicLongVeto(const double rsi, const double atr_pct,
                   const double close_px, const double ema200)
  {
   if(!InpPanicBlock)
      return false;
   bool stress = (rsi <= InpPanicRsi) || (atr_pct >= InpPanicAtrPct);
   return stress && (close_px < ema200);
  }

//+------------------------------------------------------------------+
bool PanicShortVeto(const double rsi, const double atr_pct,
                    const double close_px, const double ema200)
  {
   if(!InpPanicBlock)
      return false;
   // Mirror: extreme high RSI or ATR spike while above slow MA
   bool stress = (rsi >= (100.0 - InpPanicRsi)) || (atr_pct >= InpPanicAtrPct);
   return stress && (close_px > ema200);
  }

//+------------------------------------------------------------------+
bool DeepReclaimLong(const int i,
                     const double &close[],
                     const double &ema50[],
                     const double &rsi[],
                     const double &macd_hist[])
  {
   if(!InpDeepReclaimEnabled || i < InpDeepReclaimArmBars + 1)
      return false;
   // Count consecutive closed bars under EMA50 within arm distance
   int under = 0;
   for(int k = i - 1; k >= 0 && under < InpDeepReclaimArmBars; k--)
     {
      if(ema50[k] <= 0.0) break;
      double dist = (ema50[k] - close[k]) / ema50[k];
      if(close[k] < ema50[k] && dist >= 0.0 && dist <= InpDeepReclaimArmMaxPct)
         under++;
      else
         break;
     }
   if(under < InpDeepReclaimArmBars)
      return false;
   // Fire: reclaim EMA50 with momentum, not extended
   if(close[i] < ema50[i])
      return false;
   double ext = (close[i] - ema50[i]) / ema50[i];
   if(ext < 0.0 || ext > InpMaxEma50ExtensionPct)
      return false;
   if(rsi[i] < InpRsiReclaim || rsi[i] <= rsi[i - 1])
      return false;
   if(macd_hist[i] < InpMinMacdHist || macd_hist[i] <= macd_hist[i - 1])
      return false;
   return true;
  }

//+------------------------------------------------------------------+
bool DeepReclaimShort(const int i,
                      const double &close[],
                      const double &ema50[],
                      const double &rsi[],
                      const double &macd_hist[])
  {
   if(!InpDeepReclaimEnabled || i < InpDeepReclaimArmBars + 1)
      return false;
   int over = 0;
   for(int k = i - 1; k >= 0 && over < InpDeepReclaimArmBars; k--)
     {
      if(ema50[k] <= 0.0) break;
      double dist = (close[k] - ema50[k]) / ema50[k];
      if(close[k] > ema50[k] && dist >= 0.0 && dist <= InpDeepReclaimArmMaxPct)
         over++;
      else
         break;
     }
   if(over < InpDeepReclaimArmBars)
      return false;
   if(close[i] > ema50[i])
      return false;
   double ext = (ema50[i] - close[i]) / ema50[i];
   if(ext < 0.0 || ext > InpMaxEma50ExtensionPct)
      return false;
   if(rsi[i] > (100.0 - InpRsiReclaim) || rsi[i] >= rsi[i - 1])
      return false;
   if(macd_hist[i] > -InpMinMacdHist || macd_hist[i] >= macd_hist[i - 1])
      return false;
   return true;
  }

//+------------------------------------------------------------------+
//| Evaluate long setup on closed bar i (needs i>=1)                 |
//+------------------------------------------------------------------+
bool LongSetup(const int i,
               const int htf_bias,
               const double htf_strength,
               const double &close[],
               const double &ema50[],
               const double &ema200[],
               const double &rsi[],
               const double &macd_hist[],
               const double atr_pct,
               const double vwap)
  {
   if(htf_bias != +1)
      return false;
   if(PanicLongVeto(rsi[i], atr_pct, close[i], ema200[i]))
      return false;
   if(ema50[i] <= 0.0)
      return false;

   double dist_e50 = MathAbs(close[i] - ema50[i]) / ema50[i];
   bool near_ema50 = (dist_e50 <= InpMaxPullbackPct);
   bool near_vwap  = true;
   if(InpUseVwap && vwap > 0.0)
      near_vwap = (MathAbs(close[i] - vwap) / vwap <= InpVwapPullbackPct);

   bool recovery_ok =
      (rsi[i] >= InpRsiReclaim && rsi[i] > rsi[i - 1]) &&
      (macd_hist[i] >= InpMinMacdHist && macd_hist[i] > macd_hist[i - 1]) &&
      (close[i] > close[i - 1]);

   bool setup_pullback = near_ema50 && near_vwap && recovery_ok;

   bool setup_cont = false;
   if(InpAllowContinuation)
     {
      bool strong = (htf_strength >= InpStrongTrendStrengthPct);
      double ext  = (close[i] - ema50[i]) / ema50[i];
      bool not_ext = (ext >= 0.0 && ext <= InpMaxEma50ExtensionPct);
      bool mom = (rsi[i] >= InpContinuationRsi) &&
                 (rsi[i] > rsi[i - 1] || macd_hist[i] > macd_hist[i - 1]);
      setup_cont = strong && (close[i] >= ema50[i]) && not_ext && mom;
     }

   bool setup_deep = DeepReclaimLong(i, close, ema50, rsi, macd_hist);
   return setup_pullback || setup_cont || setup_deep;
  }

//+------------------------------------------------------------------+
bool ShortSetup(const int i,
                const int htf_bias,
                const double htf_strength,
                const double &close[],
                const double &ema50[],
                const double &ema200[],
                const double &rsi[],
                const double &macd_hist[],
                const double atr_pct,
                const double vwap)
  {
   if(!InpAllowShorts || htf_bias != -1)
      return false;
   if(PanicShortVeto(rsi[i], atr_pct, close[i], ema200[i]))
      return false;
   if(ema50[i] <= 0.0)
      return false;

   double dist_e50 = MathAbs(close[i] - ema50[i]) / ema50[i];
   bool near_ema50 = (dist_e50 <= InpMaxPullbackPct);
   bool near_vwap  = true;
   if(InpUseVwap && vwap > 0.0)
      near_vwap = (MathAbs(close[i] - vwap) / vwap <= InpVwapPullbackPct);

   bool recovery_ok =
      (rsi[i] <= (100.0 - InpRsiReclaim) && rsi[i] < rsi[i - 1]) &&
      (macd_hist[i] <= -InpMinMacdHist && macd_hist[i] < macd_hist[i - 1]) &&
      (close[i] < close[i - 1]);

   bool setup_pullback = near_ema50 && near_vwap && recovery_ok;

   bool setup_cont = false;
   if(InpAllowContinuation)
     {
      bool strong = ((-htf_strength) >= InpStrongTrendStrengthPct);
      double ext  = (ema50[i] - close[i]) / ema50[i];
      bool not_ext = (ext >= 0.0 && ext <= InpMaxEma50ExtensionPct);
      bool mom = (rsi[i] <= (100.0 - InpContinuationRsi)) &&
                 (rsi[i] < rsi[i - 1] || macd_hist[i] < macd_hist[i - 1]);
      setup_cont = strong && (close[i] <= ema50[i]) && not_ext && mom;
     }

   bool setup_deep = DeepReclaimShort(i, close, ema50, rsi, macd_hist);
   return setup_pullback || setup_cont || setup_deep;
  }

//+------------------------------------------------------------------+
void DrawPanel(const double close_px,
               const double ema50,
               const double ema200,
               const double atr_pct,
               const int htf_bias,
               const double htf_strength,
               const double last_sig)
  {
   string name = g_pfx + "panel";
   string bias = (htf_bias > 0) ? "BULL" : (htf_bias < 0) ? "BEAR" : "CHOP";
   string sigs = (last_sig > 0.5) ? "LONG" : (last_sig < -0.5) ? "SHORT" : "flat";
   string txt =
      "BtcTrendPullback\n" +
      "HTF " + EnumToString(InpHtfPeriod) + ": " + bias +
      "  str=" + DoubleToString(htf_strength * 100.0, 2) + "%\n" +
      "Close " + DoubleToString(close_px, _Digits) +
      "  EMA50 " + DoubleToString(ema50, _Digits) +
      "  EMA200 " + DoubleToString(ema200, _Digits) + "\n" +
      "ATR% " + DoubleToString(atr_pct * 100.0, 2) +
      "  VWAP " + (InpUseVwap ? "ON" : "OFF") +
      "  last_sig " + sigs + "\n" +
      "sig@7 closed-bar | no orders";

   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 8);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 20);
      ObjectSetInteger(0, name, OBJPROP_COLOR, clrWhite);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
      ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
     }
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
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
   int need = MathMax(InpEmaSlow, MathMax(InpMacdSlow + InpMacdSignal, InpAtrPeriod)) + 5;
   if(rates_total < need + 2)
      return 0;

   double ema50[], ema200[], rsi[], macd_main[], macd_sig[], atr[];
   ArraySetAsSeries(ema50, false);
   ArraySetAsSeries(ema200, false);
   ArraySetAsSeries(rsi, false);
   ArraySetAsSeries(macd_main, false);
   ArraySetAsSeries(macd_sig, false);
   ArraySetAsSeries(atr, false);

   if(CopyBuffer(g_hEma50,  0, 0, rates_total, ema50)     < rates_total) return prev_calculated;
   if(CopyBuffer(g_hEma200, 0, 0, rates_total, ema200)    < rates_total) return prev_calculated;
   if(CopyBuffer(g_hRsi,    0, 0, rates_total, rsi)       < rates_total) return prev_calculated;
   if(CopyBuffer(g_hMacd,   0, 0, rates_total, macd_main) < rates_total) return prev_calculated;
   if(CopyBuffer(g_hMacd,   1, 0, rates_total, macd_sig)  < rates_total) return prev_calculated;
   if(CopyBuffer(g_hAtr,    0, 0, rates_total, atr)       < rates_total) return prev_calculated;

   double macd_hist[];
   ArrayResize(macd_hist, rates_total);
   ArraySetAsSeries(macd_hist, false);
   for(int j = 0; j < rates_total; j++)
      macd_hist[j] = macd_main[j] - macd_sig[j];

   int start = (prev_calculated > 2) ? prev_calculated - 2 : need;

   for(int i = start; i < rates_total && !IsStopped(); i++)
     {
      // --- always paint structure ---
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

      double mid = (InpAtrBandMid == ATR_MID_EMA50) ? ema50[i] : close[i];
      if(InpShowAtrBands && atr[i] > 0.0 && mid > 0.0)
        {
         BufAtrLower[i] = mid - InpAtrBandMult * atr[i];
         BufAtrUpper[i] = mid + InpAtrBandMult * atr[i];
        }
      else
        {
         BufAtrLower[i] = EMPTY_VALUE;
         BufAtrUpper[i] = EMPTY_VALUE;
        }

      double htf_strength = 0.0;
      int htf_bias = HtfBiasAt(time[i], htf_strength);
      BufHtfBias[i] = (double)htf_bias;

      BufLong[i]   = EMPTY_VALUE;
      BufShort[i]  = EMPTY_VALUE;
      BufSignal[i] = 0.0;

      // Forming bar: no signal
      if(i == rates_total - 1 || i < 1)
         continue;

      if(close[i] <= 0.0 || atr[i] <= 0.0)
         continue;

      double atr_pct = atr[i] / close[i];
      if(atr_pct < InpMinAtrPct)
         continue;

      double vwap = 0.0;
      if(InpUseVwap)
         vwap = RollingVwap(i, high, low, close, tick_volume);

      bool long_now  = LongSetup(i, htf_bias, htf_strength, close, ema50, ema200,
                                 rsi, macd_hist, atr_pct, vwap);
      bool short_now = ShortSetup(i, htf_bias, htf_strength, close, ema50, ema200,
                                  rsi, macd_hist, atr_pct, vwap);

      bool long_fire  = long_now;
      bool short_fire = short_now;

      if(InpEdgeTrigger && i >= 2)
        {
         double prev_strength = 0.0;
         int prev_bias = HtfBiasAt(time[i - 1], prev_strength);
         double prev_atr_pct = (close[i - 1] > 0.0) ? atr[i - 1] / close[i - 1] : 0.0;
         double prev_vwap = 0.0;
         if(InpUseVwap)
            prev_vwap = RollingVwap(i - 1, high, low, close, tick_volume);

         bool long_prev = false;
         bool short_prev = false;
         if(prev_atr_pct >= InpMinAtrPct)
           {
            long_prev = LongSetup(i - 1, prev_bias, prev_strength, close, ema50, ema200,
                                  rsi, macd_hist, prev_atr_pct, prev_vwap);
            short_prev = ShortSetup(i - 1, prev_bias, prev_strength, close, ema50, ema200,
                                    rsi, macd_hist, prev_atr_pct, prev_vwap);
           }
         long_fire  = long_now  && !long_prev;
         short_fire = short_now && !short_prev;
        }

      int sig = 0;
      if(long_fire)
         sig = +1;
      else if(short_fire)
         sig = -1;

      BufSignal[i] = (double)sig;
      if(sig > 0 && InpShowMarkers)
         BufLong[i] = low[i] - InpArrowOffsetAtrFrac * atr[i];
      else if(sig < 0 && InpShowMarkers)
         BufShort[i] = high[i] + InpArrowOffsetAtrFrac * atr[i];
     }

   if(InpShowPanel && rates_total >= 2)
     {
      int i = rates_total - 1;
      double str = 0.0;
      int bias = HtfBiasAt(time[i], str);
      double ap = (close[i] > 0.0 && atr[i] > 0.0) ? atr[i] / close[i] : 0.0;
      DrawPanel(close[i], ema50[i], ema200[i], ap, bias, str, BufSignal[rates_total - 2]);
     }

   return rates_total;
  }

//+------------------------------------------------------------------+

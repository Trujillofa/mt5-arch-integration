//+------------------------------------------------------------------+
//| BtcNySessionScalp.mq5                                            |
//| BTCUSD NY-desk overlap overlay (Wave B observe)                  |
//|                                                                  |
//| Frozen a-priori family: btc_ny_overlap_vwap_ema_flat             |
//|   [08:00, 11:30) ET + session VWAP + EMA 9/21 + ATR% floor       |
//|   Closed-bar AND. Flatten visual 11:30 ET. No overnight.         |
//|                                                                  |
//| SCREEN_FAIL 2026-09-11 (0/96 develop-eligible). observe-only.    |
//| Not a trading signal. Never OrderSend.                           |
//| Not the US-index cash overlay. Not the gold London overlay.     |
//| Logger: ForexSignalLogger InpIndicatorName=BtcNySessionScalp     |
//|         InpSignalBuffer=8 InpMaxSpreadPips=0                     |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.00"
#property description "BTC NY-desk overlap v1.00 — SCREEN_FAIL observe-only"
#property description "Default VWAP+EMA. Signal buffer 8. Not a trading signal."
#property strict

#define BNS_VERSION "1.00"

#property indicator_chart_window
#property indicator_buffers 10
#property indicator_plots   7

#property indicator_label1  "EMA9"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDeepSkyBlue
#property indicator_style1  STYLE_SOLID
#property indicator_width1  1

#property indicator_label2  "EMA21"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrOrange
#property indicator_style2  STYLE_SOLID
#property indicator_width2  2

#property indicator_label3  "NY VWAP"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrWhite
#property indicator_style3  STYLE_SOLID
#property indicator_width3  2

#property indicator_label4  "OR High"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrAqua
#property indicator_style4  STYLE_DOT
#property indicator_width4  1

#property indicator_label5  "OR Low"
#property indicator_type5   DRAW_LINE
#property indicator_color5  clrAqua
#property indicator_style5  STYLE_DOT
#property indicator_width5  1

#property indicator_label6  "Long"
#property indicator_type6   DRAW_ARROW
#property indicator_color6  clrLime
#property indicator_width6  2

#property indicator_label7  "Short"
#property indicator_type7   DRAW_ARROW
#property indicator_color7  clrOrangeRed
#property indicator_width7  2

#include <BtcSessionUtils.mqh>

enum ENUM_BTC_FAMILY
  {
   BTC_FAM_VWAP_EMA     = 0, // a-priori default (SCREEN_FAIL)
   BTC_FAM_ATR_DRIVE    = 1, // 30m NY-desk range + 0.10 ATR
   BTC_FAM_HTF_PULLBACK = 2  // completed H1 EMA50/200 bias + M5 reclaim vs chart EMA-slow (mirrors htf_pullback_signals)
  };

input group "=== Family (observe only) ==="
input ENUM_BTC_FAMILY InpFamily      = BTC_FAM_VWAP_EMA;

input group "=== Session / signal ==="
input int    InpEmaFast              = 9;
input int    InpEmaSlow              = 21;
input int    InpAtrPeriod            = 14;
input double InpMinAtrPct            = 0.00015;
input int    InpOrMinutes            = 30;
input double InpOrBufferAtrFrac      = 0.10;
input bool   InpOnePerDay            = true;
input bool   InpSignalOnClose        = true;
input bool   InpEdgeTrigger          = true;
input bool   InpNfpBlackout          = false;

input group "=== HTF pullback ==="
input int    InpHtfFast              = 50;
input int    InpHtfSlow              = 200;
input double InpPullbackPct          = 0.003;
input double InpExtensionPct         = 0.005;

input group "=== Display ==="
input bool   InpShowEmas             = true;
input bool   InpShowVwap             = true;
input bool   InpShowOr               = true;
input bool   InpShowMarkers          = true;
input bool   InpShowPanel            = true;
input bool   InpShowFlattenLine      = true;
input double InpArrowOffsetAtrFrac   = 0.15;
input color  InpColFlat              = clrDarkOrange;
input color  InpColNy                = clrGold;

double BufEmaFast[];
double BufEmaSlow[];
double BufVwap[];
double BufOrHigh[];
double BufOrLow[];
double BufLong[];
double BufShort[];
double BufSession[];
double BufSignal[];
double BufAtr[];

int    g_hEmaFast = INVALID_HANDLE;
int    g_hEmaSlow = INVALID_HANDLE;
int    g_hAtr     = INVALID_HANDLE;
int    g_hHtfFast = INVALID_HANDLE;
int    g_hHtfSlow = INVALID_HANDLE;
string g_pfx;
string g_last_reason = "SCREEN_FAIL observe-only";

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpEmaFast < 1 || InpEmaSlow < InpEmaFast || InpAtrPeriod < 1)
      return INIT_PARAMETERS_INCORRECT;
   SetIndexBuffer(0, BufEmaFast,  INDICATOR_DATA);
   SetIndexBuffer(1, BufEmaSlow,  INDICATOR_DATA);
   SetIndexBuffer(2, BufVwap,     INDICATOR_DATA);
   SetIndexBuffer(3, BufOrHigh,   INDICATOR_DATA);
   SetIndexBuffer(4, BufOrLow,    INDICATOR_DATA);
   SetIndexBuffer(5, BufLong,     INDICATOR_DATA);
   SetIndexBuffer(6, BufShort,    INDICATOR_DATA);
   SetIndexBuffer(7, BufSession,  INDICATOR_CALCULATIONS);
   SetIndexBuffer(8, BufSignal,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(9, BufAtr,      INDICATOR_CALCULATIONS);
   ArraySetAsSeries(BufEmaFast, false);
   ArraySetAsSeries(BufEmaSlow, false);
   ArraySetAsSeries(BufVwap,    false);
   ArraySetAsSeries(BufOrHigh,  false);
   ArraySetAsSeries(BufOrLow,   false);
   ArraySetAsSeries(BufLong,    false);
   ArraySetAsSeries(BufShort,   false);
   ArraySetAsSeries(BufSession, false);
   ArraySetAsSeries(BufSignal,  false);
   ArraySetAsSeries(BufAtr,     false);
   PlotIndexSetInteger(5, PLOT_ARROW, 233);
   PlotIndexSetInteger(6, PLOT_ARROW, 234);
   for(int p=0; p<7; p++)
      PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   if(InpEmaFast < 1 || InpEmaSlow <= InpEmaFast || InpAtrPeriod < 1 ||
      InpOrMinutes < 1 || InpHtfFast < 1 || InpHtfSlow <= InpHtfFast)
      return INIT_PARAMETERS_INCORRECT;
   g_hEmaFast = iMA(_Symbol, PERIOD_CURRENT, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   g_hEmaSlow = iMA(_Symbol, PERIOD_CURRENT, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   g_hAtr     = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   g_hHtfFast = iMA(_Symbol, PERIOD_H1, InpHtfFast, 0, MODE_EMA, PRICE_CLOSE);
   g_hHtfSlow = iMA(_Symbol, PERIOD_H1, InpHtfSlow, 0, MODE_EMA, PRICE_CLOSE);
   if(g_hEmaFast == INVALID_HANDLE || g_hEmaSlow == INVALID_HANDLE ||
      g_hAtr == INVALID_HANDLE || g_hHtfFast == INVALID_HANDLE ||
      g_hHtfSlow == INVALID_HANDLE)
      return INIT_FAILED;
   g_pfx = StringFormat("BNS_%I64d_", ChartID());
   IndicatorSetString(INDICATOR_SHORTNAME,
                      "BtcNySessionScalp v" + BNS_VERSION + " buf8 SCREEN_FAIL");
   if(!BtcLooksLikeBtc(_Symbol))
      Print("BtcNySessionScalp: '", _Symbol, "' does not look like BTC");
   Print("BtcNySessionScalp v" + BNS_VERSION + " ", _Symbol,
         " observe-only SCREEN_FAIL. Not a trading signal.");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_hEmaFast != INVALID_HANDLE) IndicatorRelease(g_hEmaFast);
   if(g_hEmaSlow != INVALID_HANDLE) IndicatorRelease(g_hEmaSlow);
   if(g_hAtr     != INVALID_HANDLE) IndicatorRelease(g_hAtr);
   if(g_hHtfFast != INVALID_HANDLE) IndicatorRelease(g_hHtfFast);
   if(g_hHtfSlow != INVALID_HANDLE) IndicatorRelease(g_hHtfSlow);
   // HTF Fib lesson: never ObjectsDeleteAll on CHARTCHANGE / PARAMETERS.
   if(reason == REASON_REMOVE || reason == REASON_CHARTCLOSE ||
      reason == REASON_RECOMPILE)
     {
      ObjectsDeleteAll(0, g_pfx);
      Comment("");
     }
  }

//+------------------------------------------------------------------+
void BnsPanel()
  {
   if(!InpShowPanel)
      return;
   string fam = (InpFamily == BTC_FAM_ATR_DRIVE ? "atr_drive" :
                 InpFamily == BTC_FAM_HTF_PULLBACK ? "htf_pullback" :
                 "vwap_ema");
   Comment(
      "BtcNySessionScalp v" + BNS_VERSION + "  SCREEN_FAIL / observe-only\n" +
      "Not a trading signal. NY desk [08:00, 11:30) ET. Flatten 11:30.\n" +
      "Family " + fam + "  last: " + g_last_reason + "\n"
   );
  }

//+------------------------------------------------------------------+
void BnsDrawFlat(const datetime et_day_start)
  {
   if(!InpShowFlattenLine)
      return;
   datetime et_flat = et_day_start + BTC_FLAT_MIN * 60;
   datetime server_flat = et_flat + BTC_SERVER_MINUS_SEC;
   string name = g_pfx + "FLAT";
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_VLINE, 0, server_flat, 0);
   ObjectSetInteger(0, name, OBJPROP_TIME, server_flat);
   ObjectSetInteger(0, name, OBJPROP_COLOR, InpColFlat);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DOT);
   ObjectSetString(0, name, OBJPROP_TEXT, "FLAT 11:30 ET");
   {
      datetime et_open = et_day_start + BTC_SESSION_START_MIN * 60;
      datetime server_open = et_open + BTC_SERVER_MINUS_SEC;
      string n2 = g_pfx + "NY08";
      if(ObjectFind(0, n2) < 0)
         ObjectCreate(0, n2, OBJ_VLINE, 0, server_open, 0);
      ObjectSetInteger(0, n2, OBJPROP_TIME, server_open);
      ObjectSetInteger(0, n2, OBJPROP_COLOR, InpColNy);
      ObjectSetString(0, n2, OBJPROP_TEXT, "NY desk 08:00");
   }
  }

//+------------------------------------------------------------------+
int BnsHtfBias(const datetime bar_time)
  {
   if(g_hHtfFast == INVALID_HANDLE || g_hHtfSlow == INVALID_HANDLE)
      return 0;
   int sh = iBarShift(_Symbol, PERIOD_H1, bar_time, true);
   if(sh < 0)
      return 0;
   int completed = sh + 1;
   double e50[], e200[], c[];
   if(CopyBuffer(g_hHtfFast, 0, completed, 1, e50) != 1)
      return 0;
   if(CopyBuffer(g_hHtfSlow, 0, completed, 1, e200) != 1)
      return 0;
   if(CopyClose(_Symbol, PERIOD_H1, completed, 1, c) != 1)
      return 0;
   if(c[0] > e200[0] && e50[0] > e200[0])
      return 1;
   if(c[0] < e200[0] && e50[0] < e200[0])
      return -1;
   return 0;
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
   if(rates_total < InpEmaSlow + 5)
      return 0;
   double ema_f[], ema_s[], atr[];
   ArraySetAsSeries(ema_f, false);
   ArraySetAsSeries(ema_s, false);
   ArraySetAsSeries(atr, false);
   if(CopyBuffer(g_hEmaFast, 0, 0, rates_total, ema_f) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hEmaSlow, 0, 0, rates_total, ema_s) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hAtr, 0, 0, rates_total, atr) < rates_total)
      return prev_calculated;

   int start = (prev_calculated > 2 ? prev_calculated - 2 : 0);
   for(int z=start; z<rates_total; z++)
     {
      BufEmaFast[z] = (InpShowEmas ? ema_f[z] : EMPTY_VALUE);
      BufEmaSlow[z] = (InpShowEmas ? ema_s[z] : EMPTY_VALUE);
      BufVwap[z]    = EMPTY_VALUE;
      BufOrHigh[z]  = EMPTY_VALUE;
      BufOrLow[z]   = EMPTY_VALUE;
      BufLong[z]    = EMPTY_VALUE;
      BufShort[z]   = EMPTY_VALUE;
      BufSession[z] = 0.0;
      BufSignal[z]  = 0.0;
      BufAtr[z]     = atr[z];
     }

   double vnum = 0.0, vden = 0.0;
   double or_h = EMPTY_VALUE, or_l = EMPTY_VALUE;
   bool or_ready = false;
   int last_key = -1;
   int fired_key = -1;
   datetime last_et_day = 0;

   for(int i=0; i<rates_total; i++)
     {
      datetime et = BtcEtFromServer(time[i]);
      int key = BtcEtKey(et);
      int emin = BtcEtMinuteOfDay(et);
      if(key != last_key)
        {
         last_key = key;
         vnum = vden = 0.0;
         or_h = or_l = EMPTY_VALUE;
         or_ready = false;
         last_et_day = et - emin * 60;
        }
      bool in_box = BtcInOverlap(et);
      BufSession[i] = in_box ? 1.0 : 0.0;
      if(in_box)
        {
         double typ = (high[i] + low[i] + close[i]) / 3.0;
         double vol = (double)MathMax(tick_volume[i], 1);
         vnum += typ * vol;
         vden += vol;
         if(vden > 0.0 && InpShowVwap)
            BufVwap[i] = vnum / vden;
         int or_end = BTC_SESSION_START_MIN + InpOrMinutes;
         if(emin >= BTC_SESSION_START_MIN && emin < or_end)
           {
            if(or_h == EMPTY_VALUE)
              {
               or_h = high[i];
               or_l = low[i];
              }
            else
              {
               or_h = MathMax(or_h, high[i]);
               or_l = MathMin(or_l, low[i]);
              }
           }
         if(emin >= or_end && or_h != EMPTY_VALUE)
            or_ready = true;
         if(InpShowOr && or_ready)
           {
            BufOrHigh[i] = or_h;
            BufOrLow[i]  = or_l;
           }
        }

      bool forming = (i == rates_total - 1);
      if(InpSignalOnClose && forming)
        {
         BufSignal[i] = 0.0;
         continue;
        }
      int sig = 0;
      g_last_reason = "no_setup";
      if(!BtcEntryOk(et, InpNfpBlackout))
         g_last_reason = "outside_window";
      else if(close[i] <= 0.0 || atr[i] <= 0.0 || atr[i] / close[i] < InpMinAtrPct)
         g_last_reason = "dead_atr";
      else if(vden <= 0.0)
         g_last_reason = "no_vwap";
      else
        {
         double vw = vnum / vden;
         double ef = ema_f[i];
         double es = ema_s[i];
         double px = close[i];
         if(InpFamily == BTC_FAM_VWAP_EMA)
           {
            if(px > vw && ef > es)
               sig = 1;
            else if(px < vw && ef < es)
               sig = -1;
           }
         else if(InpFamily == BTC_FAM_ATR_DRIVE)
           {
            if(!or_ready)
               g_last_reason = "or_incomplete";
            else
              {
               double buf = InpOrBufferAtrFrac * atr[i];
               if(px > or_h + buf && px > vw && ef > es)
                  sig = 1;
               else if(px < or_l - buf && px < vw && ef < es)
                  sig = -1;
              }
           }
         else if(InpFamily == BTC_FAM_HTF_PULLBACK)
           {
            int bias = BnsHtfBias(time[i]);
            if(es > 0.0)
              {
               double dist = (px - es) / px;
               if(bias == 1 && MathAbs(dist) <= InpPullbackPct &&
                  px > es && i > 0 && px > close[i - 1] && dist <= InpExtensionPct)
                  sig = 1;
               else if(bias == -1 && MathAbs(dist) <= InpPullbackPct &&
                       px < es && i > 0 && px < close[i - 1] && -dist <= InpExtensionPct)
                  sig = -1;
              }
           }
        }
      if(InpOnePerDay && sig != 0 && key == fired_key)
         sig = 0;
      if(InpEdgeTrigger && i > 0 && sig != 0 && BufSignal[i - 1] == (double)sig)
         sig = 0;
      BufSignal[i] = (double)sig;
      if(sig != 0)
        {
         fired_key = key;
         g_last_reason = (sig > 0 ? "long" : "short");
         if(InpShowMarkers)
           {
            double off = InpArrowOffsetAtrFrac * atr[i];
            if(sig > 0)
               BufLong[i] = low[i] - off;
            else
               BufShort[i] = high[i] + off;
           }
        }
     }
   if(last_et_day > 0)
      BnsDrawFlat(last_et_day);
   BnsPanel();
   return rates_total;
  }
//+------------------------------------------------------------------+

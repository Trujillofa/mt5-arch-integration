//+------------------------------------------------------------------+
//| OilSessionScalp.mq5                                              |
//| XTIUSD / USOUSD London+NY energy overlay (observe only)          |
//|                                                                  |
//| Frozen a-priori family: oil_london_orb_vwap_ema_flat             |
//|   London 30m OR + London-date VWAP + EMA 9/21 + ATR% + OR-width  |
//|   Closed-bar AND. Flatten visual 11:00 London / 11:30 ET.        |
//|                                                                  |
//| promote=no. observe-only SCREEN_FAIL. Not a trading signal. Never OrderSend. |
//| Not the US-index cash overlay. Not the gold London overlay.      |
//| Logger: ForexSignalLogger InpIndicatorName=OilSessionScalp       |
//|         InpSignalBuffer=8 InpMaxSpreadPips=0                     |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.00"
#property description "Oil session scalp v1.00 — SCREEN_FAIL observe-only"
#property description "Default London OR+VWAP+EMA. Signal buffer 8. Not a trading signal."
#property strict

#define OSS_VERSION "1.00"

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

#property indicator_label3  "Session VWAP"
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

#include <OilSessionUtils.mqh>
#include <OilM5Export.mqh>

enum ENUM_OIL_FAMILY
  {
   OIL_FAM_LONDON  = 0, // a-priori default oil_london_orb_vwap_ema_flat
   OIL_FAM_NY      = 1, // oil_ny_inventory_drive
   OIL_FAM_RECLAIM = 2  // oil_prior_day_reclaim
  };

input group "=== Family (observe only) ==="
input ENUM_OIL_FAMILY InpFamily      = OIL_FAM_LONDON;

input group "=== Session / signal ==="
input int    InpEmaFast              = 9;
input int    InpEmaSlow              = 21;
input int    InpAtrPeriod            = 14;
input double InpMinAtrPct            = 0.00015;
input int    InpOrMinutes            = 30;
input double InpOrBufferAtrFrac      = 0.10;
input double InpOrWidthLo            = 0.35;
input double InpOrWidthHi            = 2.5;
input bool   InpOnePerDay            = true;
input bool   InpSignalOnClose        = true;
input bool   InpEdgeTrigger          = true;
input bool   InpEiaBlackout          = false;

input group "=== Display ==="
input bool   InpShowEmas             = true;
input bool   InpShowVwap             = true;
input bool   InpShowOr               = true;
input bool   InpShowMarkers          = true;
input bool   InpShowPanel            = true;
input bool   InpShowFlattenLine      = true;
input double InpArrowOffsetAtrFrac   = 0.15;
input color  InpColFlat              = clrDarkOrange;
input color  InpColLon               = clrDodgerBlue;
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
   g_hEmaFast = iMA(_Symbol, PERIOD_CURRENT, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   g_hEmaSlow = iMA(_Symbol, PERIOD_CURRENT, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   g_hAtr     = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   if(g_hEmaFast == INVALID_HANDLE || g_hEmaSlow == INVALID_HANDLE ||
      g_hAtr == INVALID_HANDLE)
      return INIT_FAILED;
   g_pfx = StringFormat("OSS_%I64d_", ChartID());
   IndicatorSetString(INDICATOR_SHORTNAME,
                      "OilSessionScalp v" + OSS_VERSION + " buf8 observe");
   if(!OilLooksLikeOil(_Symbol))
      Print("OilSessionScalp: '", _Symbol, "' does not look like oil");
   Print("OilSessionScalp v" + OSS_VERSION + " ", _Symbol,
         " observe-only SCREEN_FAIL. Not a trading signal.");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_hEmaFast != INVALID_HANDLE) IndicatorRelease(g_hEmaFast);
   if(g_hEmaSlow != INVALID_HANDLE) IndicatorRelease(g_hEmaSlow);
   if(g_hAtr     != INVALID_HANDLE) IndicatorRelease(g_hAtr);
   ObjectsDeleteAll(0, g_pfx);
  }

//+------------------------------------------------------------------+
void OssPanel()
  {
   if(!InpShowPanel)
      return;
   string fam = (InpFamily == OIL_FAM_NY ? "ny_inventory" :
                 InpFamily == OIL_FAM_RECLAIM ? "prior_day_reclaim" :
                 "london_orb");
   Comment(
      "OilSessionScalp v" + OSS_VERSION + "  SCREEN_FAIL / observe-only\n" +
      "Not a trading signal. London 08:30-11:00 / NY [08:00, 11:30) ET.\n" +
      "Family " + fam + "  last: " + g_last_reason + "\n"
   );
  }

//+------------------------------------------------------------------+
void OssDrawGuides(const datetime et_day_start)
  {
   if(!InpShowFlattenLine)
      return;
   datetime et_ny_flat = et_day_start + OIL_NY_FLAT_MIN * 60;
   datetime server_ny = et_ny_flat + OIL_SERVER_MINUS_SEC;
   string n1 = g_pfx + "FLAT_NY";
   if(ObjectFind(0, n1) < 0)
      ObjectCreate(0, n1, OBJ_VLINE, 0, server_ny, 0);
   ObjectSetInteger(0, n1, OBJPROP_TIME, server_ny);
   ObjectSetInteger(0, n1, OBJPROP_COLOR, InpColFlat);
   ObjectSetInteger(0, n1, OBJPROP_STYLE, STYLE_DOT);
   ObjectSetString(0, n1, OBJPROP_TEXT, "FLAT 11:30 ET");

   datetime et_lon_open = et_day_start + (3 * 3600); // ~03:00 ET = 08:00 London visual
   datetime server_lon = et_lon_open + OIL_SERVER_MINUS_SEC;
   string n2 = g_pfx + "LON08";
   if(ObjectFind(0, n2) < 0)
      ObjectCreate(0, n2, OBJ_VLINE, 0, server_lon, 0);
   ObjectSetInteger(0, n2, OBJPROP_TIME, server_lon);
   ObjectSetInteger(0, n2, OBJPROP_COLOR, InpColLon);
   ObjectSetString(0, n2, OBJPROP_TEXT, "London 08:00");

   datetime et_ny_open = et_day_start + OIL_NY_START_MIN * 60;
   datetime server_nyo = et_ny_open + OIL_SERVER_MINUS_SEC;
   string n3 = g_pfx + "NY08";
   if(ObjectFind(0, n3) < 0)
      ObjectCreate(0, n3, OBJ_VLINE, 0, server_nyo, 0);
   ObjectSetInteger(0, n3, OBJPROP_TIME, server_nyo);
   ObjectSetInteger(0, n3, OBJPROP_COLOR, InpColNy);
   ObjectSetString(0, n3, OBJPROP_TEXT, "NY energy 08:00");
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
   OilExportM5IfRequested();
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
   double pri_h = EMPTY_VALUE, pri_l = EMPTY_VALUE;
   double day_h = -1.0, day_l = 1.0e300;
   int session_mode = (InpFamily == OIL_FAM_NY ? 2 :
                       InpFamily == OIL_FAM_RECLAIM ? 0 : 1);

   for(int i=0; i<rates_total; i++)
     {
      datetime et = OilEtFromServer(time[i]);
      datetime lon = OilLonFromEt(et);
      int key = OilDateKey(et);
      int emin = OilMinuteOfDay(et);
      int lmin = OilMinuteOfDay(lon);
      if(key != last_key)
        {
         if(last_key > 0)
           {
            pri_h = day_h;
            pri_l = day_l;
           }
         last_key = key;
         vnum = vden = 0.0;
         or_h = or_l = EMPTY_VALUE;
         or_ready = false;
         day_h = high[i];
         day_l = low[i];
         last_et_day = et - emin * 60;
        }
      else
        {
         day_h = MathMax(day_h, high[i]);
         day_l = MathMin(day_l, low[i]);
        }

      bool in_box = (session_mode == 1 ? OilInLondonEntry(et) :
                     session_mode == 2 ? OilInNyEntry(et) :
                     (OilInLondonEntry(et) || OilInNyEntry(et)));
      BufSession[i] = in_box ? 1.0 : 0.0;

      bool in_vwap = false;
      int or_start = OIL_LONDON_START_MIN;
      int or_end = OIL_LONDON_START_MIN + InpOrMinutes;
      int clock_min = lmin;
      if(InpFamily == OIL_FAM_NY)
        {
         in_vwap = OilInNyEntry(et) || (emin >= OIL_NY_START_MIN && emin < OIL_NY_END_MIN);
         or_start = OIL_NY_START_MIN;
         or_end = OIL_NY_START_MIN + InpOrMinutes;
         clock_min = emin;
        }
      else
        {
         in_vwap = (lmin >= OIL_LONDON_START_MIN && lmin < OIL_LONDON_END_MIN);
        }
      if(in_vwap)
        {
         double typ = (high[i] + low[i] + close[i]) / 3.0;
         double vol = (double)MathMax(tick_volume[i], 1);
         vnum += typ * vol;
         vden += vol;
         if(vden > 0.0 && InpShowVwap)
            BufVwap[i] = vnum / vden;
        }
      if(clock_min >= or_start && clock_min < or_end)
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
      if(clock_min >= or_end && or_h != EMPTY_VALUE)
         or_ready = true;
      if(InpShowOr && or_ready)
        {
         BufOrHigh[i] = or_h;
         BufOrLow[i]  = or_l;
        }

      bool forming = (i == rates_total - 1);
      if(InpSignalOnClose && forming)
        {
         BufSignal[i] = 0.0;
         continue;
        }
      int sig = 0;
      g_last_reason = "no_setup";
      if(!OilEntryOk(et, time[i], InpEiaBlackout, session_mode))
         g_last_reason = "outside_window";
      else if(close[i] <= 0.0 || atr[i] <= 0.0 || atr[i] / close[i] < InpMinAtrPct)
         g_last_reason = "dead_atr";
      else if(InpFamily != OIL_FAM_RECLAIM && vden <= 0.0)
         g_last_reason = "no_vwap";
      else
        {
         double vw = (vden > 0.0 ? vnum / vden : EMPTY_VALUE);
         double ef = ema_f[i];
         double es = ema_s[i];
         double px = close[i];
         if(InpFamily == OIL_FAM_LONDON)
           {
            if(!or_ready)
               g_last_reason = "or_incomplete";
            else
              {
               double or_w = or_h - or_l;
               if(atr[i] > 0.0 && or_w > 0.0)
                 {
                  double w = or_w / atr[i];
                  if(w < InpOrWidthLo || w > InpOrWidthHi)
                     g_last_reason = "or_width";
                  else
                    {
                     double buf = InpOrBufferAtrFrac * atr[i];
                     if(px > or_h + buf && px > vw && ef > es)
                        sig = 1;
                     else if(px < or_l - buf && px < vw && ef < es)
                        sig = -1;
                    }
                 }
              }
           }
         else if(InpFamily == OIL_FAM_NY)
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
         else if(InpFamily == OIL_FAM_RECLAIM)
           {
            if(pri_h == EMPTY_VALUE || pri_l == EMPTY_VALUE)
               g_last_reason = "no_prior_day";
            else if(low[i] < pri_l && px > pri_l)
               sig = 1;
            else if(high[i] > pri_h && px < pri_h)
               sig = -1;
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
      OssDrawGuides(last_et_day);
   OssPanel();
   return rates_total;
  }
//+------------------------------------------------------------------+

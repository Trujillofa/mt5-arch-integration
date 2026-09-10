//+------------------------------------------------------------------+
//| GoldSessionScalp.mq5                                             |
//| XAUUSD session-scalp overlay — CLOSED / observe-only             |
//|                                                                  |
//| Disposition: promote=no, live_go=false. Not a trading signal.    |
//| Family: xau_london_defined_r_be_flat_v1 (do not retune).         |
//| M5 session-OR scalp is structurally cost-killed on this tape.    |
//| Do not attach as a live entry host. Never OrderSend.             |
//|                                                                  |
//| Frozen combo: London 30m OR + London VWAP + EMA 9/21             |
//|   NY metals 08:00 ET is a second box — not US cash 09:30.        |
//|                                                                  |
//| Logger: ForexSignalLogger (observe). Buffer 8.                   |
//|   InpIndicatorName=GoldSessionScalp InpSignalBuffer=8            |
//|   InpMaxSpreadPips=0                                             |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.10"
#property description "XAUUSD session scalp v1.10 — CLOSED observe-only"
#property description "Not a trading signal. Buffer 8. No orders."
#property strict

#define GSS_VERSION "1.10"

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

#property indicator_label3  "London VWAP"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrWhite
#property indicator_style3  STYLE_SOLID
#property indicator_width3  2

#property indicator_label4  "London OR High"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrGold
#property indicator_style4  STYLE_DOT
#property indicator_width4  1

#property indicator_label5  "London OR Low"
#property indicator_type5   DRAW_LINE
#property indicator_color5  clrGold
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

#include <GoldSessionUtils.mqh>

#define GSS_MAX_BOXES 12

input group "=== Clock ==="
input int    InpServerUtcOffsetHours = -99; // -99 = auto (TimeCurrent-TimeGMT)

input group "=== Opening range / signal (frozen combo) ==="
input int    InpOrMinutes            = 30;     // London OR length
input int    InpEmaFast              = 9;
input int    InpEmaSlow              = 21;
input int    InpAtrPeriod            = 14;
input double InpMinAtrPct            = 0.00015;
input double InpOrBufferAtrFrac      = 0.10;
input bool   InpAllowNyBox           = true;
input int    InpLonEntryEndHour      = 11;
input int    InpLonEntryEndMinute    = 0;
input int    InpNyEntryStartHour     = 8;
input int    InpNyEntryEndHour       = 11;
input bool   InpOnePerBox            = true;
input bool   InpSignalOnClose        = true;
input bool   InpShowAtrStops         = false;
input double InpSlAtr                = 1.0;
input double InpTpAtr                = 1.2;    // legacy ATR TP (unused if InpTpR>0)
input double InpTpR                  = 1.0;    // defined-R TP (family v1.10)
input double InpBeR                  = 0.0;    // 0 = no breakeven
input int    InpTimeStopBars         = 6;      // 0 = flatten only
input double InpOrWidthAtrMin        = 0.35;
input double InpOrWidthAtrMax        = 2.5;
input double InpMaxCostToTp          = 0.35;

input group "=== Spread (gold points, 0.01 quote) ==="
input double InpMaxSpreadPoints      = 0;      // 0 = auto 40

input group "=== Session drawings ==="
input int    InpDrawDays             = 2;
input bool   InpShowTokyo            = false;
input bool   InpShowLondon           = true;
input bool   InpShowNyMetals         = true;
input bool   InpShowSessionBoxes     = false;
input bool   InpShowOrBox            = true;
input bool   InpShowFlattenLines     = true;
input color  InpColTokyo             = clrMediumPurple;
input color  InpColLondon            = clrDodgerBlue;
input color  InpColNy                = clrGoldenrod;
input color  InpColOr                = clrGold;
input color  InpColFlat              = clrDarkOrange;

input group "=== Display ==="
input bool   InpShowEmas             = true;
input bool   InpShowVwap             = true;
input bool   InpShowMarkers          = true;
input bool   InpShowPanel            = true;
input double InpArrowOffsetAtrFrac   = 0.15;

// Buffers: 0 EMA9 | 1 EMA21 | 2 VWAP | 3 ORH | 4 ORL
//          5 Long | 6 Short | 7 session | 8 signal | 9 ATR
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
int    g_offset   = 0;
string g_last_reason = "";

struct GldBox
  {
   int      key;
   datetime t0;
   datetime t1;
   double   hi;
   double   lo;
  };

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpEmaFast < 1 || InpEmaSlow < InpEmaFast)
      return INIT_PARAMETERS_INCORRECT;
   if(InpOrMinutes < 1 || InpAtrPeriod < 1)
      return INIT_PARAMETERS_INCORRECT;
   if(InpDrawDays < 1 || InpDrawDays > GSS_MAX_BOXES)
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

   int begin = InpEmaSlow + InpAtrPeriod + 2;
   for(int p = 0; p < 7; p++)
     {
      PlotIndexSetInteger(p, PLOT_DRAW_BEGIN, begin);
      PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
     }
   PlotIndexSetInteger(5, PLOT_ARROW, 233);
   PlotIndexSetInteger(6, PLOT_ARROW, 234);

   IndicatorSetInteger(INDICATOR_DIGITS, _Digits);
   IndicatorSetString(INDICATOR_SHORTNAME,
                      StringFormat("GoldScalp EMA(%d/%d) LonOR%d sig@8",
                                   InpEmaFast, InpEmaSlow, InpOrMinutes));

   g_hEmaFast = iMA(_Symbol, PERIOD_CURRENT, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   g_hEmaSlow = iMA(_Symbol, PERIOD_CURRENT, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   g_hAtr     = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   if(g_hEmaFast == INVALID_HANDLE || g_hEmaSlow == INVALID_HANDLE ||
      g_hAtr == INVALID_HANDLE)
      return INIT_FAILED;

   g_pfx    = "GSS_" + IntegerToString(ChartID()) + "_";
   g_offset = GldDetectServerUtcOffsetSec(InpServerUtcOffsetHours);

   if(PeriodSeconds() > 15 * 60)
      Print("GoldSessionScalp: chart TF > M15 — OR of ", InpOrMinutes,
            "m is coarse. Prefer M5 (or M15).");
   if(!GldLooksLikeGold(_Symbol))
      Print("GoldSessionScalp: '", _Symbol,
            "' does not look like XAU/GOLD — still running.");

   Print("GoldSessionScalp v" + GSS_VERSION + " CLOSED observe-only ", _Symbol,
         " offset_h=", g_offset / 3600,
         " LonOR=", InpOrMinutes, "m sig@8 NO ORDERS");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_hEmaFast != INVALID_HANDLE) IndicatorRelease(g_hEmaFast);
   if(g_hEmaSlow != INVALID_HANDLE) IndicatorRelease(g_hEmaSlow);
   if(g_hAtr     != INVALID_HANDLE) IndicatorRelease(g_hAtr);
   if(reason == REASON_REMOVE || reason == REASON_CHARTCLOSE ||
      reason == REASON_RECOMPILE)
      ObjectsDeleteAll(0, g_pfx);
   Comment("");
  }

//+------------------------------------------------------------------+
void GldUpsertVline(const string name, const datetime t, const color col)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_VLINE, 0, t, 0);
   ObjectSetInteger(0, name, OBJPROP_TIME, t);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

//+------------------------------------------------------------------+
void GldUpsertHline(const string name, const double px, const color col,
                    const ENUM_LINE_STYLE style)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, px);
   ObjectSetDouble(0, name, OBJPROP_PRICE, px);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

//+------------------------------------------------------------------+
void GldUpsertText(const string name, const datetime t, const double px,
                   const string txt, const color col)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_TEXT, 0, t, px);
   ObjectSetInteger(0, name, OBJPROP_TIME, t);
   ObjectSetDouble(0, name, OBJPROP_PRICE, px);
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

//+------------------------------------------------------------------+
void GldUpsertRect(const string name, const datetime t0, const double hi,
                   const datetime t1, const double lo, const color col)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t0, hi, t1, lo);
   ObjectSetInteger(0, name, OBJPROP_TIME, 0, t0);
   ObjectSetInteger(0, name, OBJPROP_TIME, 1, t1);
   ObjectSetDouble(0, name, OBJPROP_PRICE, 0, hi);
   ObjectSetDouble(0, name, OBJPROP_PRICE, 1, lo);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_FILL, false);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

//+------------------------------------------------------------------+
void GldAccBox(GldBox &boxes[], int &n, const int key, const datetime t,
               const double hi, const double lo, const int psec)
  {
   if(n > 0 && boxes[n - 1].key == key)
     {
      if(hi > boxes[n - 1].hi)
         boxes[n - 1].hi = hi;
      if(lo < boxes[n - 1].lo)
         boxes[n - 1].lo = lo;
      boxes[n - 1].t1 = t + psec;
      return;
     }
   if(n >= GSS_MAX_BOXES)
     {
      for(int i = 1; i < n; i++)
         boxes[i - 1] = boxes[i];
      n--;
     }
   boxes[n].key = key;
   boxes[n].t0  = t;
   boxes[n].t1  = t + psec;
   boxes[n].hi  = hi;
   boxes[n].lo  = lo;
   n++;
  }

//+------------------------------------------------------------------+
void GldDrawBoxSet(const string tag, const string label,
                   const GldBox &boxes[], const int n,
                   const color col, const bool show)
  {
   for(int i = 0; i < GSS_MAX_BOXES; i++)
     {
      string vk = g_pfx + tag + "V" + IntegerToString(i);
      string tk = g_pfx + tag + "T" + IntegerToString(i);
      string rk = g_pfx + tag + "R" + IntegerToString(i);
      if(!show || i >= n)
        {
         ObjectDelete(0, vk);
         ObjectDelete(0, tk);
         ObjectDelete(0, rk);
         continue;
        }
      GldUpsertVline(vk, boxes[i].t0, col);
      GldUpsertText(tk, boxes[i].t0, boxes[i].hi, label, col);
      if(InpShowSessionBoxes)
         GldUpsertRect(rk, boxes[i].t0, boxes[i].hi, boxes[i].t1, boxes[i].lo, col);
      else
         ObjectDelete(0, rk);
     }
  }

//+------------------------------------------------------------------+
void DrawSessionGeometry(const datetime &time[],
                         const double &high[],
                         const double &low[],
                         const int rates_total,
                         const int first,
                         const double today_or_h,
                         const double today_or_l,
                         const bool today_or_ok,
                         const datetime today_or_t0,
                         const datetime today_or_t1)
  {
   GldBox tokyo[], london[], ny[];
   ArrayResize(tokyo, GSS_MAX_BOXES);
   ArrayResize(london, GSS_MAX_BOXES);
   ArrayResize(ny, GSS_MAX_BOXES);
   int nt = 0, nl = 0, nn = 0;
   int psec = PeriodSeconds();
   if(psec <= 0)
      psec = 60;

   for(int i = first; i < rates_total && !IsStopped(); i++)
     {
      MqlDateTime et, lon, tyo;
      GldEtOfBar(time[i], g_offset, et);
      GldLondonOfBar(time[i], g_offset, lon);
      GldTokyoOfBar(time[i], g_offset, tyo);
      if(GldIsTokyoOpen(tyo))
         GldAccBox(tokyo, nt, GldYmdKey(tyo), time[i], high[i], low[i], psec);
      if(GldIsLondonOpen(lon))
         GldAccBox(london, nl, GldYmdKey(lon), time[i], high[i], low[i], psec);
      if(GldIsNyMetals(et))
         GldAccBox(ny, nn, GldYmdKey(et), time[i], high[i], low[i], psec);
     }

   GldDrawBoxSet("TYO", "Tokyo",  tokyo,  nt, InpColTokyo,  InpShowTokyo);
   GldDrawBoxSet("LDN", "London", london, nl, InpColLondon, InpShowLondon);
   GldDrawBoxSet("NY",  "NY 08:00", ny,  nn, InpColNy,     InpShowNyMetals);

   string ork = g_pfx + "OR";
   string orh = g_pfx + "ORH";
   string orl = g_pfx + "ORL";
   if(InpShowOrBox && today_or_ok && today_or_t0 > 0)
     {
      GldUpsertRect(ork, today_or_t0, today_or_h, today_or_t1, today_or_l, InpColOr);
      GldUpsertHline(orh, today_or_h, InpColOr, STYLE_DOT);
      GldUpsertHline(orl, today_or_l, InpColOr, STYLE_DOT);
      if(rates_total > 1)
        {
         GldUpsertText(g_pfx + "ORHT", time[rates_total - 1], today_or_h, "ORH", InpColOr);
         GldUpsertText(g_pfx + "ORLT", time[rates_total - 1], today_or_l, "ORL", InpColOr);
        }
     }
   else
     {
      ObjectDelete(0, ork);
      ObjectDelete(0, orh);
      ObjectDelete(0, orl);
      ObjectDelete(0, g_pfx + "ORHT");
      ObjectDelete(0, g_pfx + "ORLT");
     }

   if(InpShowFlattenLines && rates_total > 1)
     {
      MqlDateTime et_now, lon_now;
      GldEtOfBar(time[rates_total - 1], g_offset, et_now);
      GldLondonOfBar(time[rates_total - 1], g_offset, lon_now);
      datetime flat_l = GldLondonWallToServer(lon_now.year, lon_now.mon, lon_now.day,
                                             11, 0, g_offset);
      datetime flat_n = GldEtWallToServer(et_now.year, et_now.mon, et_now.day,
                                          11, 0, g_offset);
      GldUpsertVline(g_pfx + "FLATL", flat_l, InpColFlat);
      GldUpsertText(g_pfx + "FLATLT", flat_l, today_or_h, "FLAT 11:00 LDN", InpColFlat);
      GldUpsertVline(g_pfx + "FLATN", flat_n, InpColFlat);
      GldUpsertText(g_pfx + "FLATNT", flat_n, today_or_l, "FLAT 11:00 ET", InpColFlat);
     }
   else
     {
      ObjectDelete(0, g_pfx + "FLATL");
      ObjectDelete(0, g_pfx + "FLATLT");
      ObjectDelete(0, g_pfx + "FLATN");
      ObjectDelete(0, g_pfx + "FLATNT");
     }
  }

//+------------------------------------------------------------------+
void DrawAtrGuides(const datetime &time[],
                   const int rates_total,
                   const int last_sig_side,
                   const double last_sig_px,
                   const double last_sig_atr)
  {
   string slk = g_pfx + "ATRSL";
   string tpk = g_pfx + "ATRTP";
   if(!InpShowAtrStops || last_sig_atr <= 0.0 || last_sig_px <= 0.0 ||
      last_sig_side == 0)
     {
      ObjectDelete(0, slk);
      ObjectDelete(0, tpk);
      return;
     }
   double sl_dist = InpSlAtr * last_sig_atr;
   double tp_dist = (InpTpR > 0.0) ? (InpTpR * sl_dist) : (InpTpAtr * last_sig_atr);
   double sl = last_sig_px - last_sig_side * sl_dist;
   double tp = last_sig_px + last_sig_side * tp_dist;
   GldUpsertHline(slk, sl, clrOrangeRed, STYLE_DASH);
   GldUpsertHline(tpk, tp, clrLime, STYLE_DASH);
  }

//+------------------------------------------------------------------+
void DrawPanel(const double close_px,
               const ENUM_GLD_SESSION sess,
               const double vwap,
               const double or_h,
               const double or_l,
               const double last_sig,
               const double spread_pts)
  {
   if(!InpShowPanel)
     {
      Comment("");
      return;
     }
   string sigs = (last_sig > 0.5) ? "LONG" : (last_sig < -0.5) ? "SHORT" : "flat";
   string warn = GldLooksLikeGold(_Symbol) ? "" : "  (not XAU/GOLD name)\n";
   string tfw  = (PeriodSeconds() > 15 * 60) ? "  TF>M15: prefer M5\n" : "";
   MqlDateTime et_now, lon_now;
   GldEtOfBar(TimeCurrent(), g_offset, et_now);
   GldLondonOfBar(TimeCurrent(), g_offset, lon_now);
   double cap = GldEffectiveMaxSpread(InpMaxSpreadPoints);
   Comment(
      "GoldSessionScalp v" + GSS_VERSION + "\n" +
      StringFormat("Symbol %s%s%s", _Symbol, warn, tfw) +
      StringFormat("LDN %02d:%02d  ET %02d:%02d  %s  srv %+dh\n",
                   lon_now.hour, lon_now.min, et_now.hour, et_now.min,
                   GldSessionName(sess), g_offset / 3600) +
      "CLOSED observe-only  Family xau_london_defined_r_be_flat_v1\n" +
      StringFormat("Combo  Lon OR%d + VWAP + EMA %d/%d  buf %.2f ATR\n",
                   InpOrMinutes, InpEmaFast, InpEmaSlow, InpOrBufferAtrFrac) +
      StringFormat("Risk   SL %.1f ATR  TP %.2fR  BE %.2fR  tstop %d\n",
                   InpSlAtr, InpTpR, InpBeR, InpTimeStopBars) +
      StringFormat("Close  %s   VWAP %s\n",
                   DoubleToString(close_px, _Digits),
                   (vwap == EMPTY_VALUE ? "—" : DoubleToString(vwap, _Digits))) +
      StringFormat("OR     %s / %s\n",
                   (or_h == EMPTY_VALUE ? "—" : DoubleToString(or_h, _Digits)),
                   (or_l == EMPTY_VALUE ? "—" : DoubleToString(or_l, _Digits))) +
      StringFormat("Spread %.0f pt  (cap %.0f%s)\n",
                   spread_pts, cap, (InpMaxSpreadPoints <= 0.0 ? " auto" : "")) +
      StringFormat("Signal %s  | %s | no orders", sigs,
                   (g_last_reason == "" ? "sig@8" : g_last_reason))
   );
  }

//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
bool _GldCostToTpBlocked(const double atr_i)
  {
   double sl_dist = InpSlAtr * atr_i;
   double tp_dist = InpTpR * sl_dist;
   double pt = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double cs = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(pt <= 0.0)
      pt = 0.01;
   if(cs <= 0.0)
      cs = 100.0;
   double rt = (GldSpreadPoints(_Symbol) + 20.0) * pt * cs;
   double tp_cash = tp_dist * cs;
   return (tp_cash <= 0.0 || rt > InpMaxCostToTp * tp_cash);
  }

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
   int need = InpEmaSlow + InpAtrPeriod + 2;
   if(rates_total < need + 2)
      return 0;

   g_offset = GldDetectServerUtcOffsetSec(InpServerUtcOffsetHours);

   double ema_fast[], ema_slow[], atr[];
   ArraySetAsSeries(ema_fast, false);
   ArraySetAsSeries(ema_slow, false);
   ArraySetAsSeries(atr, false);
   if(CopyBuffer(g_hEmaFast, 0, 0, rates_total, ema_fast) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hEmaSlow, 0, 0, rates_total, ema_slow) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hAtr, 0, 0, rates_total, atr) < rates_total)
      return prev_calculated;

   int psec = PeriodSeconds();
   if(psec <= 0)
      psec = 60;
   int bars_per_day = MathMax(12, (24 * 3600) / psec);
   int first = MathMax(0, rates_total - InpDrawDays * bars_per_day - 4);
   bool cold = (prev_calculated == 0);
   if(!cold)
     {
      MqlDateTime lon_now;
      GldLondonOfBar(time[rates_total - 1], g_offset, lon_now);
      int today = GldYmdKey(lon_now);
      first = rates_total - 1;
      for(int k = rates_total - 1; k >= 0; k--)
        {
         MqlDateTime lonk;
         GldLondonOfBar(time[k], g_offset, lonk);
         if(GldYmdKey(lonk) != today)
           {
            first = k + 1;
            break;
           }
         first = k;
        }
      first = MathMax(0, first - bars_per_day);
     }

   double vnum = 0.0, vden = 0.0;
   int    vday = -1;
   double or_h = 0.0, or_l = 0.0;
   bool   or_set = false;
   int    fired_box = 0;
   double today_or_h = 0.0, today_or_l = 0.0;
   bool   today_or_ok = false;
   datetime today_or_t0 = 0, today_or_t1 = 0;
   int today_lon = 0;
   int last_sig_side = 0;
   double last_sig_px = 0.0;
   double last_sig_atr = 0.0;
   if(rates_total > 0)
     {
      MqlDateTime lon_last;
      GldLondonOfBar(time[rates_total - 1], g_offset, lon_last);
      today_lon = GldYmdKey(lon_last);
     }

   int paint0 = first;
   if(cold)
     {
      for(int z = 0; z < first; z++)
        {
         BufEmaFast[z]  = EMPTY_VALUE;
         BufEmaSlow[z]  = EMPTY_VALUE;
         BufVwap[z]     = EMPTY_VALUE;
         BufOrHigh[z]   = EMPTY_VALUE;
         BufOrLow[z]    = EMPTY_VALUE;
         BufLong[z]     = EMPTY_VALUE;
         BufShort[z]    = EMPTY_VALUE;
         BufSession[z]  = 0.0;
         BufSignal[z]   = 0.0;
         BufAtr[z]      = EMPTY_VALUE;
        }
     }

   for(int i = paint0; i < rates_total && !IsStopped(); i++)
     {
      BufEmaFast[i] = InpShowEmas ? ema_fast[i] : EMPTY_VALUE;
      BufEmaSlow[i] = InpShowEmas ? ema_slow[i] : EMPTY_VALUE;
      BufAtr[i]     = atr[i];
      BufLong[i]    = EMPTY_VALUE;
      BufShort[i]   = EMPTY_VALUE;
      BufSignal[i]  = 0.0;

      MqlDateTime et, lon;
      GldEtOfBar(time[i], g_offset, et);
      GldLondonOfBar(time[i], g_offset, lon);
      int lday = GldYmdKey(lon);
      ENUM_GLD_SESSION sess = GldDetectSession(time[i], g_offset);
      BufSession[i] = (double)sess;

      if(lday != vday)
        {
         vday  = lday;
         vnum  = 0.0;
         vden  = 0.0;
         or_h  = 0.0;
         or_l  = 0.0;
         or_set = false;
        }

      if(GldIsLondonOpen(lon))
        {
         double typ = (high[i] + low[i] + close[i]) / 3.0;
         double vol = (double)MathMax(tick_volume[i], 1);
         vnum += typ * vol;
         vden += vol;
         BufVwap[i] = (InpShowVwap && vden > 0.0) ? (vnum / vden) : EMPTY_VALUE;
        }
      else
         BufVwap[i] = EMPTY_VALUE;

      if(GldInLondonOrWindow(lon, InpOrMinutes))
        {
         if(!or_set)
           {
            or_h = high[i];
            or_l = low[i];
            or_set = true;
            if(lday == today_lon)
               today_or_t0 = time[i];
           }
         else
           {
            if(high[i] > or_h)
               or_h = high[i];
            if(low[i] < or_l)
               or_l = low[i];
           }
         if(lday == today_lon)
            today_or_t1 = time[i] + psec;
        }

      bool or_ready = or_set && GldLondonOrComplete(lon, InpOrMinutes);
      if(or_ready)
        {
         BufOrHigh[i] = or_h;
         BufOrLow[i]  = or_l;
         if(lday == today_lon)
           {
            today_or_h  = or_h;
            today_or_l  = or_l;
            today_or_ok = true;
           }
        }
      else
        {
         BufOrHigh[i] = EMPTY_VALUE;
         BufOrLow[i]  = EMPTY_VALUE;
        }

      if(InpSignalOnClose && i == rates_total - 1)
         continue;
      if(i < need)
         continue;

      ENUM_GLD_BOX box = GldSessionBox(lon, et, InpOrMinutes, InpAllowNyBox);
      int bkey = GldBoxKey(box, lon, et);
      double vwap = BufVwap[i];
      double ef   = ema_fast[i];
      double es   = ema_slow[i];
      double at   = atr[i];
      double px   = close[i];
      double cap  = GldEffectiveMaxSpread(InpMaxSpreadPoints);
      bool live_spread_ok = true;
      if(cap > 0.0 && i == rates_total - 2)
         live_spread_ok = (GldSpreadPoints(_Symbol) <= cap);

      int sig = 0;
      string why = "no_confluence";
      if(GldFridayCutoff(et))
         why = "friday_cutoff";
      else if(box == GLD_BOX_NONE)
         why = "outside_entry_window";
      else if(!or_ready)
         why = "or_incomplete";
      else if(!live_spread_ok)
         why = "spread";
      else if(vwap == EMPTY_VALUE)
         why = "no_vwap";
      else if(at <= 0.0 || ef <= 0.0 || es <= 0.0)
         why = "ema_atr_warmup";
      else if(px > 0.0 && (at / px) < InpMinAtrPct)
         why = "dead_atr";
      else if(or_ready && at > 0.0 &&
              ((or_h - or_l) / at < InpOrWidthAtrMin ||
               (or_h - or_l) / at > InpOrWidthAtrMax))
         why = "or_width";
      else if(InpMaxCostToTp > 0.0 && at > 0.0 && InpTpR > 0.0 &&
              _GldCostToTpBlocked(at))
         why = "cost_to_tp";
      else if(InpOnePerBox && fired_box == bkey)
         why = "already_signaled_box";
      else
        {
         double buf = InpOrBufferAtrFrac * at;
         if(px > or_h + buf && px > vwap && ef > es)
           {
            sig = +1;
            why = "london_orb_vwap_ema_long";
           }
         else if(px < or_l - buf && px < vwap && ef < es)
           {
            sig = -1;
            why = "london_orb_vwap_ema_short";
           }
        }

      BufSignal[i] = (double)sig;
      if(sig != 0)
        {
         fired_box = bkey;
         last_sig_side = sig;
         last_sig_px = px;
         last_sig_atr = at;
         if(InpShowMarkers)
           {
            double off = InpArrowOffsetAtrFrac * at;
            if(sig > 0)
               BufLong[i] = low[i] - off;
            else
               BufShort[i] = high[i] + off;
           }
        }
      if(i == rates_total - 2)
         g_last_reason = why;
     }

   DrawSessionGeometry(time, high, low, rates_total, first,
                       today_or_h, today_or_l, today_or_ok,
                       today_or_t0, today_or_t1);
   DrawAtrGuides(time, rates_total, last_sig_side, last_sig_px, last_sig_atr);
   double last_close = (rates_total > 0) ? close[rates_total - 1] : 0.0;
   ENUM_GLD_SESSION nows = (rates_total > 0)
                           ? GldDetectSession(time[rates_total - 1], g_offset)
                           : GLD_SESSION_NONE;
   double last_sig = (rates_total > 1) ? BufSignal[rates_total - 2] : 0.0;
   DrawPanel(last_close, nows,
             (rates_total > 0 ? BufVwap[rates_total - 1] : EMPTY_VALUE),
             (today_or_ok ? today_or_h : EMPTY_VALUE),
             (today_or_ok ? today_or_l : EMPTY_VALUE),
             last_sig, GldSpreadPoints(_Symbol));
   return rates_total;
  }
//+------------------------------------------------------------------+

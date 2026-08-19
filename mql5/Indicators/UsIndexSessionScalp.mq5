//+------------------------------------------------------------------+
//| UsIndexSessionScalp.mq5                                          |
//| US30 / US100 session-scalp overlay (Wave B observe)              |
//|                                                                  |
//| Frozen combo: ny_cash_orb_vwap_ema_flat                          |
//|   NY cash 15m opening range + session VWAP + EMA 9/21            |
//|   Closed-bar AND confluence. Scalp only. No overnight.           |
//|                                                                  |
//| Draws London / NY open vlines (Tokyo off) + persistent OR levels.|
//| Signal buffer 8 = +1 / −1 / 0. Never OrderSend.                  |
//| Logger: ForexSignalLogger InpIndicatorName=UsIndexSessionScalp   |
//|         InpSignalBuffer=8 InpMaxSpreadPips=0                     |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.40"
#property description "US30/US100 session scalp v1.40 — optional playbook families"
#property description "Default family still frozen ORB. Signal buffer 8."
#property strict

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

#include <ForexUtils.mqh>
#include <IndexSessionUtils.mqh>
#include <IndexM5Export.mqh>

#define IDX_MAX_BOXES 12

enum ENUM_IDX_FAMILY
  {
   IDX_FAM_ORB         = 0, // frozen ORB+VWAP+EMA
   IDX_FAM_VWAP_BOUNCE = 1, // playbook VWAP fade + RSI
   IDX_FAM_EMA_MACD    = 2  // playbook EMA cross + MACD
  };

input group "=== Clock ==="
input int    InpServerUtcOffsetHours = -99; // -99 = auto (TimeCurrent-TimeGMT)

input group "=== Opening range / signal (frozen combo) ==="
input int    InpOrMinutes            = 15;     // NY cash OR length
input int    InpEmaFast              = 9;
input int    InpEmaSlow              = 21;
input int    InpAtrPeriod            = 14;
input double InpMinAtrPct            = 0.00015; // dead-lunch floor
input int    InpEntryEndHour         = 11;     // frozen window ends 11:30 ET
input int    InpEntryEndMinute       = 30;
input bool   InpOnePerDay            = true;
input bool   InpSignalOnClose        = true;
input bool   InpEdgeTrigger          = true;
input bool   InpShowAtrStops         = false;  // research candidate SL/TP guides
input double InpSlAtr                = 1.0;
input double InpTpAtr                = 1.5;

input group "=== Playbook families (observe only; default = frozen ORB) ==="
input ENUM_IDX_FAMILY InpFamily      = IDX_FAM_ORB;
input int    InpRsiPeriod            = 14;
input double InpRsiOb                = 75.0;
input double InpRsiOs                = 25.0;
input double InpAtrDev               = 1.0;    // |close-VWAP| / ATR
input int    InpMacdFast             = 12;
input int    InpMacdSlow             = 26;
input int    InpMacdSignal           = 9;
input bool   InpCrossOnly            = true;

input group "=== Spread (points, not pips) ==="
input double InpMaxSpreadPoints      = 0;      // 0 = auto (US100 200 / US30 80)

input group "=== Session drawings ==="
input int    InpDrawDays             = 2;      // open vlines to keep (today+yesterday)
input bool   InpShowTokyo            = false;  // off: NY-scalp chart, Asia is noise
input bool   InpShowLondon           = true;
input bool   InpShowNyCash           = true;
input bool   InpShowSessionBoxes     = false;  // filled range boxes hide candles
input bool   InpShowOrBox            = true;
input bool   InpShowPriorDay         = true;
input bool   InpShowFlattenLine      = true;
input color  InpColTokyo             = clrMediumPurple;
input color  InpColLondon            = clrDodgerBlue;
input color  InpColNy                = clrGold;
input color  InpColOr                = clrAqua;
input color  InpColPdh               = clrCrimson;
input color  InpColPdl               = clrLimeGreen;
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
int    g_hRsi     = INVALID_HANDLE;
int    g_hMacd    = INVALID_HANDLE;
string g_pfx;
int    g_offset   = 0;
int    g_drawn_days = 0;
string g_last_reason = "";

struct IdxBox
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
   if(InpRsiPeriod < 2 || InpMacdFast < 1 || InpMacdSlow <= InpMacdFast ||
      InpMacdSignal < 1 || InpAtrDev < 0.0)
      return INIT_PARAMETERS_INCORRECT;
   if(InpDrawDays < 1 || InpDrawDays > IDX_MAX_BOXES)
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
                      StringFormat("USIdxScalp EMA(%d/%d) OR%d sig@8",
                                   InpEmaFast, InpEmaSlow, InpOrMinutes));

   g_hEmaFast = iMA(_Symbol, PERIOD_CURRENT, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   g_hEmaSlow = iMA(_Symbol, PERIOD_CURRENT, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   g_hAtr     = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   g_hRsi     = iRSI(_Symbol, PERIOD_CURRENT, InpRsiPeriod, PRICE_CLOSE);
   g_hMacd    = iMACD(_Symbol, PERIOD_CURRENT, InpMacdFast, InpMacdSlow,
                      InpMacdSignal, PRICE_CLOSE);
   if(g_hEmaFast == INVALID_HANDLE || g_hEmaSlow == INVALID_HANDLE ||
      g_hAtr == INVALID_HANDLE || g_hRsi == INVALID_HANDLE ||
      g_hMacd == INVALID_HANDLE)
      return INIT_FAILED;

   g_pfx    = "UIS_" + IntegerToString(ChartID()) + "_";
   g_offset = IdxDetectServerUtcOffsetSec(InpServerUtcOffsetHours);

   if(PeriodSeconds() > 15 * 60)
      Print("UsIndexSessionScalp: chart TF > M15 — OR of ", InpOrMinutes,
            "m is coarse. Prefer M5 (or M1 / M15).");
   if(!IdxLooksLikeUsIndex(_Symbol))
      Print("UsIndexSessionScalp: '", _Symbol,
            "' does not look like US30/US100 — still running.");

   Print("UsIndexSessionScalp v1.40 ", _Symbol,
         " offset_h=", g_offset / 3600,
         " OR=", InpOrMinutes, "m sig@8 NO ORDERS");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_hEmaFast != INVALID_HANDLE) IndicatorRelease(g_hEmaFast);
   if(g_hEmaSlow != INVALID_HANDLE) IndicatorRelease(g_hEmaSlow);
   if(g_hAtr     != INVALID_HANDLE) IndicatorRelease(g_hAtr);
   if(g_hRsi     != INVALID_HANDLE) IndicatorRelease(g_hRsi);
   if(g_hMacd    != INVALID_HANDLE) IndicatorRelease(g_hMacd);
   // HTF Fib lesson: never ObjectsDeleteAll on CHARTCHANGE / PARAMETERS.
   if(reason == REASON_REMOVE || reason == REASON_CHARTCLOSE ||
      reason == REASON_RECOMPILE)
     {
      ObjectsDeleteAll(0, g_pfx);
      Comment("");
     }
  }

//+------------------------------------------------------------------+
void IdxAccBox(IdxBox &boxes[], int &n, const int key,
               const datetime t, const double h, const double l,
               const int period_sec)
  {
   for(int i = 0; i < n; i++)
     {
      if(boxes[i].key != key)
         continue;
      boxes[i].t1 = t + period_sec;
      if(h > boxes[i].hi)
         boxes[i].hi = h;
      if(l < boxes[i].lo)
         boxes[i].lo = l;
      return;
     }
   if(n >= IDX_MAX_BOXES)
      return;
   boxes[n].key = key;
   boxes[n].t0  = t;
   boxes[n].t1  = t + period_sec;
   boxes[n].hi  = h;
   boxes[n].lo  = l;
   n++;
  }

//+------------------------------------------------------------------+
double IdxEffectiveMaxSpread()
  {
   if(InpMaxSpreadPoints > 0.0)
      return InpMaxSpreadPoints;
   string u = _Symbol;
   StringToUpper(u);
   if(StringFind(u, "US100") >= 0 || StringFind(u, "NAS") >= 0 ||
      StringFind(u, "USTEC") >= 0 || StringFind(u, "NDX") >= 0)
      return 200.0;
   if(StringFind(u, "US30") >= 0 || StringFind(u, "DJ30") >= 0)
      return 80.0;
   return 120.0;
  }

//+------------------------------------------------------------------+
string IdxOrWidthText(const double or_h, const double or_l)
  {
   if(or_h == EMPTY_VALUE || or_l == EMPTY_VALUE || or_h <= 0.0 || or_l <= 0.0)
      return "";
   // Price width, not MT5 points (US100 point=0.01 → a 137 handle OR is 13725 pt).
   return StringFormat("  (%.2f)", or_h - or_l);
  }

//+------------------------------------------------------------------+
double IdxLabelPrice(const int slot)
  {
   double mx = ChartGetDouble(0, CHART_PRICE_MAX);
   double mn = ChartGetDouble(0, CHART_PRICE_MIN);
   double span = mx - mn;
   if(span <= 0.0)
      return mx;
   return mx - (0.025 + 0.04 * slot) * span;
  }

//+------------------------------------------------------------------+
void IdxUpsertRect(const string key, const datetime t1, const double p1,
                   const datetime t2, const double p2, const color col,
                   const bool fill)
  {
   if(ObjectFind(0, key) < 0)
     {
      ObjectCreate(0, key, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
      ObjectSetInteger(0, key, OBJPROP_BACK, true);
      ObjectSetInteger(0, key, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, key, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, key, OBJPROP_BORDER_TYPE, BORDER_FLAT);
     }
   ObjectMove(0, key, 0, t1, p1);
   ObjectMove(0, key, 1, t2, p2);
   ObjectSetInteger(0, key, OBJPROP_FILL, fill);
   ObjectSetInteger(0, key, OBJPROP_COLOR, col);
   ObjectSetInteger(0, key, OBJPROP_BGCOLOR, col);
   ObjectSetInteger(0, key, OBJPROP_STYLE, fill ? STYLE_SOLID : STYLE_DOT);
   ObjectSetInteger(0, key, OBJPROP_WIDTH, 1);
  }

//+------------------------------------------------------------------+
void IdxUpsertVline(const string key, const datetime t, const color col,
                    const ENUM_LINE_STYLE style = STYLE_SOLID)
  {
   if(ObjectFind(0, key) < 0)
     {
      ObjectCreate(0, key, OBJ_VLINE, 0, t, 0);
      ObjectSetInteger(0, key, OBJPROP_BACK, true);
      ObjectSetInteger(0, key, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, key, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, key, OBJPROP_WIDTH, 1);
     }
   ObjectMove(0, key, 0, t, 0);
   ObjectSetInteger(0, key, OBJPROP_COLOR, col);
   ObjectSetInteger(0, key, OBJPROP_STYLE, style);
  }

//+------------------------------------------------------------------+
void IdxUpsertHline(const string key, const double price, const color col,
                    const ENUM_LINE_STYLE style)
  {
   if(ObjectFind(0, key) < 0)
     {
      ObjectCreate(0, key, OBJ_HLINE, 0, 0, price);
      ObjectSetInteger(0, key, OBJPROP_BACK, true);
      ObjectSetInteger(0, key, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, key, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, key, OBJPROP_WIDTH, 1);
     }
   ObjectSetDouble(0, key, OBJPROP_PRICE, 0, price);
   ObjectSetInteger(0, key, OBJPROP_COLOR, col);
   ObjectSetInteger(0, key, OBJPROP_STYLE, style);
  }

//+------------------------------------------------------------------+
void IdxUpsertText(const string key, const datetime t, const double price,
                   const string text, const color col)
  {
   if(ObjectFind(0, key) < 0)
     {
      ObjectCreate(0, key, OBJ_TEXT, 0, t, price);
      ObjectSetInteger(0, key, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, key, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, key, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
     }
   ObjectMove(0, key, 0, t, price);
   ObjectSetString(0, key, OBJPROP_TEXT, text);
   ObjectSetInteger(0, key, OBJPROP_COLOR, col);
   ObjectSetInteger(0, key, OBJPROP_FONTSIZE, 11);
  }

//+------------------------------------------------------------------+
void IdxDrawBoxSet(const string tag, const string label,
                   const IdxBox &boxes[], const int n,
                   const color col, const bool show, const int slot)
  {
   double y = IdxLabelPrice(slot);
   for(int i = 0; i < IDX_MAX_BOXES; i++)
     {
      string rk = g_pfx + tag + "R" + IntegerToString(i);
      string vk = g_pfx + tag + "V" + IntegerToString(i);
      string tk = g_pfx + tag + "T" + IntegerToString(i);
      if(!show || i >= n)
        {
         ObjectDelete(0, rk);
         ObjectDelete(0, vk);
         ObjectDelete(0, tk);
         continue;
        }
      if(InpShowSessionBoxes)
         IdxUpsertRect(rk, boxes[i].t0, boxes[i].hi, boxes[i].t1, boxes[i].lo,
                       col, false);
      else
         ObjectDelete(0, rk);
      IdxUpsertVline(vk, boxes[i].t0, col, STYLE_SOLID);
      IdxUpsertText(tk, boxes[i].t0, y, label, col);
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
                         const datetime today_or_t1,
                         const double pdh,
                         const double pdl)
  {
   IdxBox tokyo[];
   IdxBox london[];
   IdxBox ny[];
   ArrayResize(tokyo, IDX_MAX_BOXES);
   ArrayResize(london, IDX_MAX_BOXES);
   ArrayResize(ny, IDX_MAX_BOXES);
   int nt = 0, nl = 0, nn = 0;
   int psec = PeriodSeconds();
   if(psec <= 0)
      psec = 60;

   for(int i = first; i < rates_total && !IsStopped(); i++)
     {
      MqlDateTime et, lon, tyo;
      IdxEtOfBar(time[i], g_offset, et);
      IdxLondonOfBar(time[i], g_offset, lon);
      IdxTokyoOfBar(time[i], g_offset, tyo);

      if(IdxIsTokyoOpen(tyo))
         IdxAccBox(tokyo, nt, tyo.year * 10000 + tyo.mon * 100 + tyo.day,
                   time[i], high[i], low[i], psec);
      if(IdxIsLondonOpen(lon))
         IdxAccBox(london, nl, lon.year * 10000 + lon.mon * 100 + lon.day,
                   time[i], high[i], low[i], psec);
      if(IdxIsNyCash(et))
         IdxAccBox(ny, nn, IdxEtDateKey(et),
                   time[i], high[i], low[i], psec);
     }

   IdxDrawBoxSet("TYO", "Tokyo",  tokyo,  nt, InpColTokyo,  InpShowTokyo,  0);
   IdxDrawBoxSet("LDN", "London", london, nl, InpColLondon, InpShowLondon, 1);
   IdxDrawBoxSet("NY",  "NY 09:30", ny,   nn, InpColNy,     InpShowNyCash, 2);

   string ork = g_pfx + "OR";
   string ort = g_pfx + "ORT";
   string orh = g_pfx + "ORH";
   string orl = g_pfx + "ORL";
   string orht = g_pfx + "ORHT";
   string orlt = g_pfx + "ORLT";
   if(InpShowOrBox && today_or_ok && today_or_t0 > 0)
     {
      IdxUpsertRect(ork, today_or_t0, today_or_h, today_or_t1, today_or_l,
                    InpColOr, false);
      IdxUpsertText(ort, today_or_t0, today_or_h,
                    "OR " + IntegerToString(InpOrMinutes) + "m", InpColOr);
      // Full-width levels so afternoon zoom still shows the range.
      IdxUpsertHline(orh, today_or_h, InpColOr, STYLE_DOT);
      IdxUpsertHline(orl, today_or_l, InpColOr, STYLE_DOT);
      if(rates_total > 1)
        {
         IdxUpsertText(orht, time[rates_total - 1], today_or_h, "ORH", InpColOr);
         IdxUpsertText(orlt, time[rates_total - 1], today_or_l, "ORL", InpColOr);
        }
     }
   else
     {
      ObjectDelete(0, ork);
      ObjectDelete(0, ort);
      ObjectDelete(0, orh);
      ObjectDelete(0, orl);
      ObjectDelete(0, orht);
      ObjectDelete(0, orlt);
     }

   string pdhk = g_pfx + "PDH";
   string pdlk = g_pfx + "PDL";
   if(InpShowPriorDay && pdh > 0.0 && pdl > 0.0)
     {
      IdxUpsertHline(pdhk, pdh, InpColPdh, STYLE_DASH);
      IdxUpsertHline(pdlk, pdl, InpColPdl, STYLE_DASH);
      if(rates_total > 1)
        {
         IdxUpsertText(g_pfx + "PDHT", time[rates_total - 1], pdh, "PDH", InpColPdh);
         IdxUpsertText(g_pfx + "PDLT", time[rates_total - 1], pdl, "PDL", InpColPdl);
        }
     }
   else
     {
      ObjectDelete(0, pdhk);
      ObjectDelete(0, pdlk);
      ObjectDelete(0, g_pfx + "PDHT");
      ObjectDelete(0, g_pfx + "PDLT");
     }

   string flk = g_pfx + "FLAT";
   string flt = g_pfx + "FLATT";
   if(InpShowFlattenLine && rates_total > 1)
     {
      MqlDateTime et_now;
      IdxEtOfBar(time[rates_total - 1], g_offset, et_now);
      datetime flat_t = IdxEtWallToServer(et_now.year, et_now.mon, et_now.day,
                                          15, 45, g_offset);
      IdxUpsertVline(flk, flat_t, InpColFlat, STYLE_DASH);
      IdxUpsertText(flt, flat_t, IdxLabelPrice(3), "FLAT 15:45 ET", InpColFlat);
     }
   else
     {
      ObjectDelete(0, flk);
      ObjectDelete(0, flt);
     }

   g_drawn_days = InpDrawDays;
  }

//+------------------------------------------------------------------+
void DrawAtrGuides(const datetime &time[],
                   const int rates_total,
                   const int last_sig_i,
                   const int last_sig_side,
                   const double last_sig_px,
                   const double last_sig_atr)
  {
   string slk = g_pfx + "ATRSL";
   string tpk = g_pfx + "ATRTP";
   string slt = g_pfx + "ATRSLT";
   string tpt = g_pfx + "ATRTPT";
   if(!InpShowAtrStops || last_sig_i < 0 || last_sig_atr <= 0.0 ||
      last_sig_px <= 0.0 || last_sig_side == 0)
     {
      ObjectDelete(0, slk);
      ObjectDelete(0, tpk);
      ObjectDelete(0, slt);
      ObjectDelete(0, tpt);
      return;
     }
   double sl = last_sig_px - last_sig_side * InpSlAtr * last_sig_atr;
   double tp = last_sig_px + last_sig_side * InpTpAtr * last_sig_atr;
   IdxUpsertHline(slk, sl, clrOrangeRed, STYLE_DASH);
   IdxUpsertHline(tpk, tp, clrLime, STYLE_DASH);
   if(rates_total > 1)
     {
      datetime t = time[rates_total - 1];
      IdxUpsertText(slt, t, sl, "SL ATR", clrOrangeRed);
      IdxUpsertText(tpt, t, tp, "TP ATR", clrLime);
     }
  }

//+------------------------------------------------------------------+
void DrawPanel(const double close_px,
               const ENUM_IDX_SESSION sess,
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
   string warn = IdxLooksLikeUsIndex(_Symbol) ? "" : "  (not US30/US100 name)\n";
   string tfw  = (PeriodSeconds() > 15 * 60) ? "  TF>M15: prefer M5\n" : "";
   MqlDateTime et_now;
   IdxEtOfBar(TimeCurrent(), g_offset, et_now);
   double cap = IdxEffectiveMaxSpread();
   Comment(
      "UsIndexSessionScalp v1.40\n" +
      StringFormat("Symbol %s%s%s", _Symbol, warn, tfw) +
      StringFormat("ET     %02d:%02d   session %s   srv %+dh\n",
                   et_now.hour, et_now.min, IdxSessionName(sess), g_offset / 3600) +
      "Lines  blue=London  gold=NY  aqua=OR  orange=FLAT\n" +
      StringFormat("Family %s  window-to %02d:%02d%s\n",
                   (InpFamily == IDX_FAM_VWAP_BOUNCE ? "VWAP bounce+RSI" :
                    InpFamily == IDX_FAM_EMA_MACD ? "EMA+MACD" :
                    "ORB+VWAP+EMA"),
                   InpEntryEndHour, InpEntryEndMinute,
                   (InpShowAtrStops ? "  ATR guides on" : "")) +
      StringFormat("Combo  NY OR%d + VWAP + EMA %d/%d\n",
                   InpOrMinutes, InpEmaFast, InpEmaSlow) +
      StringFormat("Close  %s   VWAP %s\n",
                   DoubleToString(close_px, _Digits),
                   (vwap == EMPTY_VALUE ? "—" : DoubleToString(vwap, _Digits))) +
      StringFormat("OR     %s / %s%s\n",
                   (or_h == EMPTY_VALUE ? "—" : DoubleToString(or_h, _Digits)),
                   (or_l == EMPTY_VALUE ? "—" : DoubleToString(or_l, _Digits)),
                   IdxOrWidthText(or_h, or_l)) +
      StringFormat("Spread %.0f pt  (cap %.0f%s)\n",
                   spread_pts, cap, (InpMaxSpreadPoints <= 0.0 ? " auto" : "")) +
      StringFormat("Signal %s  | %s | no orders", sigs,
                   (g_last_reason == "" ? "sig@8" : g_last_reason))
   );
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
   int need = InpEmaSlow + InpAtrPeriod + 2;
   need = MathMax(need, InpRsiPeriod + 2);
   need = MathMax(need, InpMacdSlow + InpMacdSignal + 2);
   if(rates_total < need + 2)
      return 0;

   g_offset = IdxDetectServerUtcOffsetSec(InpServerUtcOffsetHours);

   double ema_fast[], ema_slow[], atr[], rsi[], macd_main[], macd_sig[];
   ArraySetAsSeries(ema_fast, false);
   ArraySetAsSeries(ema_slow, false);
   ArraySetAsSeries(atr, false);
   ArraySetAsSeries(rsi, false);
   ArraySetAsSeries(macd_main, false);
   ArraySetAsSeries(macd_sig, false);
   if(CopyBuffer(g_hEmaFast, 0, 0, rates_total, ema_fast) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hEmaSlow, 0, 0, rates_total, ema_slow) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hAtr, 0, 0, rates_total, atr) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hRsi, 0, 0, rates_total, rsi) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hMacd, 0, 0, rates_total, macd_main) < rates_total)
      return prev_calculated;
   if(CopyBuffer(g_hMacd, 1, 0, rates_total, macd_sig) < rates_total)
      return prev_calculated;

   IdxExportUsIndexM5IfRequested();

   int psec = PeriodSeconds();
   if(psec <= 0)
      psec = 60;
   int bars_per_day = MathMax(12, (24 * 3600) / psec);
   int first = MathMax(0, rates_total - InpDrawDays * bars_per_day - 4);
   bool cold = (prev_calculated == 0);
   if(!cold)
     {
      MqlDateTime et_now;
      IdxEtOfBar(time[rates_total - 1], g_offset, et_now);
      int today = IdxEtDateKey(et_now);
      first = rates_total - 1;
      for(int k = rates_total - 1; k >= 0; k--)
        {
         MqlDateTime etk;
         IdxEtOfBar(time[k], g_offset, etk);
         if(IdxEtDateKey(etk) != today)
           {
            first = k + 1;
            break;
           }
         first = k;
        }
      // need previous ET day for PDH when incremental
      first = MathMax(0, first - bars_per_day);
     }

   double vnum = 0.0, vden = 0.0;
   int    vday = -1;
   double or_h = 0.0, or_l = 0.0;
   bool   or_set = false;
   int    or_day = -1;
   int    fired_day = -1;
   double pdh = 0.0, pdl = 0.0;
   int    pdh_day = -1;
   bool   pdh_set = false;
   double today_or_h = 0.0, today_or_l = 0.0;
   bool   today_or_ok = false;
   datetime today_or_t0 = 0, today_or_t1 = 0;
   int today_key = 0;
   int last_sig_i = -1;
   int last_sig_side = 0;
   double last_sig_px = 0.0;
   double last_sig_atr = 0.0;
   if(rates_total > 0)
     {
      MqlDateTime et_last;
      IdxEtOfBar(time[rates_total - 1], g_offset, et_last);
      today_key = IdxEtDateKey(et_last);
     }

   // Always replay from `first`. Starting at prev_calculated-2 with
   // or_set=false wiped today's OR / VWAP / one-per-day on every tick
   // (live panel showed OR — / — after 09:45 ET).
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

      MqlDateTime et;
      IdxEtOfBar(time[i], g_offset, et);
      int day = IdxEtDateKey(et);
      ENUM_IDX_SESSION sess = IdxDetectSession(time[i], g_offset);
      BufSession[i] = (double)sess;

      if(day != vday)
        {
         if(vday > 0 && vday != today_key)
           {
            // previous completed ET day becomes PDH/PDL
            pdh_day = vday;
           }
         vday  = day;
         vnum  = 0.0;
         vden  = 0.0;
         or_h  = 0.0;
         or_l  = 0.0;
         or_set = false;
         or_day = day;
        }

      // Prior-day range: all bars of the last fully finished ET date
      if(day != today_key)
        {
         if(!pdh_set || day != pdh_day)
           {
            if(day != pdh_day)
              {
               pdh = high[i];
               pdl = low[i];
               pdh_day = day;
               pdh_set = true;
              }
           }
         if(day == pdh_day)
           {
            if(high[i] > pdh)
               pdh = high[i];
            if(low[i] < pdl)
               pdl = low[i];
           }
        }

      if(IdxIsNyCash(et))
        {
         double typ = (high[i] + low[i] + close[i]) / 3.0;
         double vol = (double)MathMax(tick_volume[i], 1);
         vnum += typ * vol;
         vden += vol;
         BufVwap[i] = (InpShowVwap && vden > 0.0) ? (vnum / vden) : EMPTY_VALUE;
        }
      else
         BufVwap[i] = EMPTY_VALUE;

      if(IdxInOrWindow(et, InpOrMinutes))
        {
         if(!or_set)
           {
            or_h = high[i];
            or_l = low[i];
            or_set = true;
            if(day == today_key)
               today_or_t0 = time[i];
           }
         else
           {
            if(high[i] > or_h)
               or_h = high[i];
            if(low[i] < or_l)
               or_l = low[i];
           }
         if(day == today_key)
            today_or_t1 = time[i] + psec;
        }

      bool or_ready = or_set && IdxOrComplete(et, InpOrMinutes);
      if(or_ready)
        {
         BufOrHigh[i] = or_h;
         BufOrLow[i]  = or_l;
         if(day == today_key)
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

      bool friday = IdxFridayCutoff(et);
      int  win_or = (InpFamily == IDX_FAM_ORB) ? InpOrMinutes : 5;
      bool window = IdxInEntryWindow(et, win_or,
                                    InpEntryEndHour, InpEntryEndMinute);
      double vwap = BufVwap[i];
      double ef   = ema_fast[i];
      double es   = ema_slow[i];
      double at   = atr[i];
      double px   = close[i];
      double rv   = rsi[i];
      double hist = macd_main[i] - macd_sig[i];

      double cap = IdxEffectiveMaxSpread();
      bool live_spread_ok = true;
      if(cap > 0.0 && i == rates_total - 2)
         live_spread_ok = (IdxSpreadPoints(_Symbol) <= cap);

      int sig = 0;
      string why = "no_confluence";
      if(friday)
         why = "friday_cutoff";
      else if(!window)
         why = (et.hour * 60 + et.min < 9 * 60 + 30 + win_or)
               ? "before_or_end" : "outside_entry_window";
      else if(InpFamily == IDX_FAM_ORB && !or_ready)
         why = "or_incomplete";
      else if(!live_spread_ok)
         why = "spread";
      else if(InpFamily != IDX_FAM_EMA_MACD && vwap == EMPTY_VALUE)
         why = "no_vwap";
      else if(at <= 0.0)
         why = "atr_warmup";
      else if(InpFamily == IDX_FAM_ORB && (ef <= 0.0 || es <= 0.0))
         why = "ema_atr_warmup";
      else if(px > 0.0 && (at / px) < InpMinAtrPct)
         why = "dead_atr";
      else if(InpOnePerDay && fired_day == day)
         why = "already_today";
      else if(InpFamily == IDX_FAM_VWAP_BOUNCE)
        {
         if(rv == EMPTY_VALUE || rv <= 0.0)
            why = "rsi_warmup";
         else
           {
            double ext = (px - vwap) / at;
            if(ext <= -InpAtrDev && rv <= InpRsiOs)
              {
               sig = +1;
               why = "vwap_bounce_long";
              }
            else if(ext >= InpAtrDev && rv >= InpRsiOb)
              {
               sig = -1;
               why = "vwap_bounce_short";
              }
           }
        }
      else if(InpFamily == IDX_FAM_EMA_MACD)
        {
         if(ef <= 0.0 || es <= 0.0 ||
            macd_main[i] == EMPTY_VALUE || macd_sig[i] == EMPTY_VALUE)
            why = "macd_warmup";
         else
           {
            bool long_ok  = (ef > es && hist > 0.0);
            bool short_ok = (ef < es && hist < 0.0);
            if(InpCrossOnly)
              {
               if(i < 1)
                 {
                  long_ok  = false;
                  short_ok = false;
                 }
               else
                 {
                  long_ok  = long_ok && ema_fast[i - 1] <= ema_slow[i - 1];
                  short_ok = short_ok && ema_fast[i - 1] >= ema_slow[i - 1];
                 }
              }
            if(long_ok)
              {
               sig = +1;
               why = "ema_macd_long";
              }
            else if(short_ok)
              {
               sig = -1;
               why = "ema_macd_short";
              }
           }
        }
      else if(px > or_h && px > vwap && ef > es)
        {
         sig = +1;
         why = "orb_vwap_ema_long";
        }
      else if(px < or_l && px < vwap && ef < es)
        {
         sig = -1;
         why = "orb_vwap_ema_short";
        }

      if(InpEdgeTrigger && i > 0 && sig != 0 && BufSignal[i - 1] == (double)sig)
        {
         sig = 0;
         why = "edge_hold";
        }

      BufSignal[i] = (double)sig;
      if(sig != 0)
        {
         fired_day = day;
         if(day == today_key)
           {
            last_sig_i = i;
            last_sig_side = sig;
            last_sig_px = px;
            last_sig_atr = at;
           }
        }
      if(i == rates_total - 2)
         g_last_reason = why;

      if(InpShowMarkers && sig > 0 && at > 0.0)
         BufLong[i] = low[i] - InpArrowOffsetAtrFrac * at;
      if(InpShowMarkers && sig < 0 && at > 0.0)
         BufShort[i] = high[i] + InpArrowOffsetAtrFrac * at;
     }

   DrawSessionGeometry(time, high, low, rates_total, first,
                       today_or_h, today_or_l, today_or_ok,
                       today_or_t0, today_or_t1, pdh, pdl);
   DrawAtrGuides(time, rates_total, last_sig_i, last_sig_side,
                 last_sig_px, last_sig_atr);

   int last_closed = rates_total - 2;
   if(last_closed < 0)
      last_closed = 0;
   ENUM_IDX_SESSION now_sess = IdxDetectSession(time[rates_total - 1], g_offset);
   DrawPanel(close[rates_total - 1], now_sess,
             BufVwap[last_closed], BufOrHigh[last_closed], BufOrLow[last_closed],
             BufSignal[last_closed], IdxSpreadPoints(_Symbol));

   return rates_total;
  }
//+------------------------------------------------------------------+

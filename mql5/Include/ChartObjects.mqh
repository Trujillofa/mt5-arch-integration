//+------------------------------------------------------------------+
//| ChartObjects.mqh                                                 |
//| Prefix-scoped chart-object upsert + one OnDeinit wipe policy.    |
//|                                                                  |
//| In-scope: UIS, BNS, HTFFIB, BTP, FXIT. GoldSessionScalp excluded.|
//| Do not change prices, times, colors, or when callers draw.       |
//| RAY_RIGHT / width / style are per-call so visual quirks stay.    |
//|                                                                  |
//| OnDeinit: wipe ObjectsDeleteAll(prefix) ONLY on REMOVE /         |
//| CHARTCLOSE / RECOMPILE. Never PARAMETERS / CHARTCHANGE — that    |
//| mass GDI teardown freezes Wine (win32u.so, measured 2026-08-13). |
//| Always Comment("") on those wipe reasons. Callers still own      |
//| IndicatorRelease. Draw paths stay idempotent (create on miss).   |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef CHART_OBJECTS_MQH
#define CHART_OBJECTS_MQH

#define CHART_OBJECTS_VER "1.00"

//+------------------------------------------------------------------+
bool CoShouldWipe(const int reason)
  {
   return (reason == REASON_REMOVE ||
           reason == REASON_CHARTCLOSE ||
           reason == REASON_RECOMPILE);
  }

//+------------------------------------------------------------------+
void CoWipePrefix(const int reason, const string prefix)
  {
   if(!CoShouldWipe(reason))
      return;
   ObjectsDeleteAll(0, prefix);
   Comment("");
  }

//+------------------------------------------------------------------+
void CoHline(const string name, const double price, const color col,
             const ENUM_LINE_STYLE style, const int width)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetDouble(0, name, OBJPROP_PRICE, 0, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
  }

//+------------------------------------------------------------------+
void CoVline(const string name, const datetime t, const color col,
             const ENUM_LINE_STYLE style, const int width,
             const bool back=true, const bool hidden=true,
             const string text="")
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_VLINE, 0, t, 0);
   ObjectMove(0, name, 0, t, 0);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(0, name, OBJPROP_BACK, back);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, hidden);
   if(StringLen(text) > 0)
      ObjectSetString(0, name, OBJPROP_TEXT, text);
  }

//+------------------------------------------------------------------+
void CoRect(const string name,
            const datetime t1, const double p1,
            const datetime t2, const double p2,
            const color col, const bool fill,
            const ENUM_LINE_STYLE style, const int width)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
     }
   ObjectMove(0, name, 0, t1, p1);
   ObjectMove(0, name, 1, t2, p2);
   ObjectSetInteger(0, name, OBJPROP_FILL, fill);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, col);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
  }

//+------------------------------------------------------------------+
void CoText(const string name, const datetime t, const double price,
            const string text, const color col,
            const int fontsize, const ENUM_ANCHOR_POINT anchor,
            const string font="")
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_TEXT, 0, t, price);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectMove(0, name, 0, t, price);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, fontsize);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, anchor);
   if(StringLen(font) > 0)
      ObjectSetString(0, name, OBJPROP_FONT, font);
  }

//+------------------------------------------------------------------+
//| OBJ_TREND used as a horizontal level (HTFFIB HLine / FXIT        |
//| MoveHLine). ray_right is per-call: HTFFIB always true, FXIT      |
//| follows InpLevelExtendRight.                                     |
//+------------------------------------------------------------------+
void CoTrend(const string name,
             const datetime t1, const double price,
             const datetime t2,
             const color col, const ENUM_LINE_STYLE style, const int width,
             const bool ray_right)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_TREND, 0, t1, price, t2, price);
      ObjectSetInteger(0, name, OBJPROP_RAY_LEFT, false);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectMove(0, name, 0, t1, price);
   ObjectMove(0, name, 1, t2, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, ray_right);
  }

#endif

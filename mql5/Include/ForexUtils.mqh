//+------------------------------------------------------------------+
//| ForexUtils.mqh                                                   |
//| Shared forex helpers for MT5 indicators / EAs                    |
//| Pips, sessions (broker server time), spread, symbol specs        |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef FOREX_UTILS_MQH
#define FOREX_UTILS_MQH

//--- Session IDs (broker SERVER time — adjust offsets in inputs)
enum ENUM_FX_SESSION
  {
   FX_SESSION_NONE   = 0,
   FX_SESSION_ASIAN  = 1,
   FX_SESSION_LONDON = 2,
   FX_SESSION_NY     = 3,
   FX_SESSION_OVERLAP= 4   // London+NY overlap
  };

//+------------------------------------------------------------------+
//| Pip size for common FX / metals / indices                        |
//| JPY pairs: 0.01; most FX: 0.0001; gold often 0.01                |
//+------------------------------------------------------------------+
double FxPipSize(const string symbol = NULL)
  {
   string sym = (symbol == NULL || symbol == "") ? _Symbol : symbol;
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   if(point <= 0.0)
      point = _Point;

   // 3/5-digit brokers: pip = 10 * point; 2/4-digit: pip = point
   if(digits == 3 || digits == 5)
      return point * 10.0;
   if(digits == 2 || digits == 4)
      return point;

   // Metals / CFDs fallback
   string upper = sym;
   StringToUpper(upper);
   if(StringFind(upper, "XAU") >= 0 || StringFind(upper, "GOLD") >= 0)
      return (digits >= 2) ? point * 10.0 : point;
   if(StringFind(upper, "XAG") >= 0 || StringFind(upper, "SILVER") >= 0)
      return (digits >= 3) ? point * 10.0 : point;

   return (digits == 3 || digits == 5) ? point * 10.0 : point;
  }

//+------------------------------------------------------------------+
//| Price distance in pips                                           |
//+------------------------------------------------------------------+
double FxPriceToPips(const double price_delta, const string symbol = NULL)
  {
   double pip = FxPipSize(symbol);
   if(pip <= 0.0)
      return 0.0;
   return price_delta / pip;
  }

//+------------------------------------------------------------------+
//| Pips to price                                                    |
//+------------------------------------------------------------------+
double FxPipsToPrice(const double pips, const string symbol = NULL)
  {
   return pips * FxPipSize(symbol);
  }

//+------------------------------------------------------------------+
//| Current spread in pips (bid/ask)                                 |
//+------------------------------------------------------------------+
double FxSpreadPips(const string symbol = NULL)
  {
   string sym = (symbol == NULL || symbol == "") ? _Symbol : symbol;
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   if(ask <= 0.0 || bid <= 0.0)
      return 0.0;
   return FxPriceToPips(ask - bid, sym);
  }

//+------------------------------------------------------------------+
//| Hour of day from a datetime (broker server time)                 |
//+------------------------------------------------------------------+
int FxHourOf(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.hour;
  }

//+------------------------------------------------------------------+
//| Session detection using inclusive start, exclusive end (0-23)    |
//| Times are broker SERVER hours (not local / not UTC unless set).  |
//| Default approximates UTC if broker is GMT+0/+2 winter/summer.    |
//+------------------------------------------------------------------+
bool FxInHourWindow(const int hour, const int start_h, const int end_h)
  {
   if(start_h == end_h)
      return true; // full day
   if(start_h < end_h)
      return (hour >= start_h && hour < end_h);
   // wraps midnight
   return (hour >= start_h || hour < end_h);
  }

ENUM_FX_SESSION FxDetectSession(const datetime bar_time,
                                const int asian_start  = 0,
                                const int asian_end    = 8,
                                const int london_start = 7,
                                const int london_end   = 16,
                                const int ny_start     = 12,
                                const int ny_end       = 21)
  {
   int h = FxHourOf(bar_time);
   bool asian  = FxInHourWindow(h, asian_start,  asian_end);
   bool london = FxInHourWindow(h, london_start, london_end);
   bool ny     = FxInHourWindow(h, ny_start,     ny_end);

   if(london && ny)
      return FX_SESSION_OVERLAP;
   if(london)
      return FX_SESSION_LONDON;
   if(ny)
      return FX_SESSION_NY;
   if(asian)
      return FX_SESSION_ASIAN;
   return FX_SESSION_NONE;
  }

string FxSessionName(const ENUM_FX_SESSION s)
  {
   switch(s)
     {
      case FX_SESSION_ASIAN:   return "Asian";
      case FX_SESSION_LONDON:  return "London";
      case FX_SESSION_NY:      return "NewYork";
      case FX_SESSION_OVERLAP: return "LDN+NY";
      default:                 return "Off";
     }
  }

//+------------------------------------------------------------------+
//| Wilder-style True Range (single bar i, needs previous close)     |
//+------------------------------------------------------------------+
double FxTrueRange(const double high, const double low,
                   const double prev_close)
  {
   double hl = high - low;
   double hc = MathAbs(high - prev_close);
   double lc = MathAbs(low  - prev_close);
   return MathMax(hl, MathMax(hc, lc));
  }

//+------------------------------------------------------------------+
//| Seed SMA then recursive EMA — series index 0 = oldest bar        |
//| Returns false if rates_total < period                            |
//+------------------------------------------------------------------+
bool FxEmaSeries(const double &price[],
                 const int rates_total,
                 const int period,
                 double &out_ema[])
  {
   if(period < 1 || rates_total < period)
      return false;

   ArrayResize(out_ema, rates_total);
   ArrayInitialize(out_ema, EMPTY_VALUE);

   double sum = 0.0;
   for(int i = 0; i < period; i++)
      sum += price[i];

   out_ema[period - 1] = sum / period;
   double mult = 2.0 / (period + 1.0);
   for(int i = period; i < rates_total; i++)
      out_ema[i] = price[i] * mult + out_ema[i - 1] * (1.0 - mult);

   return true;
  }

//+------------------------------------------------------------------+
//| Wilder ATR series — index 0 = oldest                             |
//+------------------------------------------------------------------+
bool FxAtrSeries(const double &high[],
                 const double &low[],
                 const double &close[],
                 const int rates_total,
                 const int period,
                 double &out_atr[])
  {
   if(period < 1 || rates_total < period + 1)
      return false;

   ArrayResize(out_atr, rates_total);
   ArrayInitialize(out_atr, EMPTY_VALUE);

   double tr_sum = 0.0;
   for(int i = 1; i <= period; i++)
     {
      double tr = FxTrueRange(high[i], low[i], close[i - 1]);
      tr_sum += tr;
     }
   out_atr[period] = tr_sum / period;

   for(int i = period + 1; i < rates_total; i++)
     {
      double tr = FxTrueRange(high[i], low[i], close[i - 1]);
      out_atr[i] = (out_atr[i - 1] * (period - 1) + tr) / period;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Classic RSI (Wilder) — index 0 = oldest                          |
//+------------------------------------------------------------------+
bool FxRsiSeries(const double &price[],
                 const int rates_total,
                 const int period,
                 double &out_rsi[])
  {
   if(period < 1 || rates_total <= period)
      return false;

   ArrayResize(out_rsi, rates_total);
   ArrayInitialize(out_rsi, EMPTY_VALUE);

   double sum_pos = 0.0, sum_neg = 0.0;
   for(int i = 1; i <= period; i++)
     {
      double d = price[i] - price[i - 1];
      if(d > 0.0) sum_pos += d;
      else        sum_neg -= d;
     }

   double avg_pos = sum_pos / period;
   double avg_neg = sum_neg / period;
   if(avg_neg == 0.0)
      out_rsi[period] = (avg_pos == 0.0) ? 50.0 : 100.0;
   else
      out_rsi[period] = 100.0 - (100.0 / (1.0 + avg_pos / avg_neg));

   for(int i = period + 1; i < rates_total; i++)
     {
      double d = price[i] - price[i - 1];
      double pos = (d > 0.0) ? d : 0.0;
      double neg = (d < 0.0) ? -d : 0.0;
      avg_pos = (avg_pos * (period - 1) + pos) / period;
      avg_neg = (avg_neg * (period - 1) + neg) / period;
      if(avg_neg == 0.0)
         out_rsi[i] = (avg_pos == 0.0) ? 50.0 : 100.0;
      else
         out_rsi[i] = 100.0 - (100.0 / (1.0 + avg_pos / avg_neg));
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Confirmed pivot high at bar center (left/right wings).           |
//| Non-repainting: only true after `right` bars have closed.        |
//| Call with i = rates_total-1-right for latest candidate.          |
//+------------------------------------------------------------------+
bool FxIsPivotHigh(const double &high[],
                   const int rates_total,
                   const int center,
                   const int left,
                   const int right)
  {
   if(center - left < 0 || center + right >= rates_total)
      return false;
   double v = high[center];
   for(int i = center - left; i <= center + right; i++)
     {
      if(i == center)
         continue;
      if(high[i] >= v)
         return false;
     }
   return true;
  }

bool FxIsPivotLow(const double &low[],
                  const int rates_total,
                  const int center,
                  const int left,
                  const int right)
  {
   if(center - left < 0 || center + right >= rates_total)
      return false;
   double v = low[center];
   for(int i = center - left; i <= center + right; i++)
     {
      if(i == center)
         continue;
      if(low[i] <= v)
         return false;
     }
   return true;
  }

#endif // FOREX_UTILS_MQH
//+------------------------------------------------------------------+

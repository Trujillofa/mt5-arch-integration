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

//--- Trading style presets (apply session / spread / structure defaults)
enum ENUM_FX_TRADING_MODE
  {
   FX_MODE_INTRADAY = 0, // M15–H1 execution, session filter on, tighter spread
   FX_MODE_SWING    = 1  // H4–D1 structure, sessions off, looser / no spread gate
  };

//+------------------------------------------------------------------+
//| Effective runtime settings resolved from mode + manual overrides |
//+------------------------------------------------------------------+
struct FxModeSettings
  {
   bool   use_session_filter;
   bool   allow_asian;
   bool   allow_london;
   bool   allow_ny;
   bool   allow_overlap;
   double max_spread_pips;   // 0 = off
   int    fib_source;        // 0=H4, 1=Daily (HTF Fib)
   bool   show_4h_pivots;
   // EMAs: cloud/timing pair + separate regime bias
   int    ema_fast;          // INTRADAY 20 | SWING 50
   int    ema_slow;          // INTRADAY 50 | SWING 200
   int    ema_bias;          // always 200 (hard regime filter)
   bool   use_bias_ema;      // require close vs EMA bias for signals
   string mode_name;
   string chart_hint;        // recommended chart TF text
  };

//+------------------------------------------------------------------+
//| Resolve mode. manual_override=true keeps the bool/double inputs. |
//| When override=false, mode fully owns session/spread/fib/EMA.     |
//+------------------------------------------------------------------+
void FxResolveTradingMode(const ENUM_FX_TRADING_MODE mode,
                          const bool use_manual_session,
                          const bool man_use_session,
                          const bool man_asian,
                          const bool man_london,
                          const bool man_ny,
                          const bool man_overlap,
                          const double man_max_spread,
                          const int man_fib_source, // 0 H4 / 1 Daily
                          const bool use_manual_ema,
                          const int man_ema_fast,
                          const int man_ema_slow,
                          const int man_ema_bias,
                          FxModeSettings &out)
  {
   if(mode == FX_MODE_SWING)
     {
      out.mode_name         = "SWING";
      out.chart_hint        = "H4-D1 (or H1 for entries)";
      out.use_session_filter= false;
      out.allow_asian       = true;
      out.allow_london      = true;
      out.allow_ny          = true;
      out.allow_overlap     = true;
      out.max_spread_pips   = 0.0;      // ignore live spread for swing holds
      out.fib_source        = 1;        // Daily pivots
      out.show_4h_pivots    = false;    // Daily-focused
      out.ema_fast          = 50;
      out.ema_slow          = 200;
      out.ema_bias          = 200;      // same as slow — regime line
      out.use_bias_ema      = true;
     }
   else // INTRADAY
     {
      out.mode_name         = "INTRADAY";
      out.chart_hint        = "M15-H1 (structure from 4H/D)";
      out.use_session_filter= true;
      out.allow_asian       = false;
      out.allow_london      = true;
      out.allow_ny          = true;
      out.allow_overlap     = true;
      out.max_spread_pips   = 2.5;
      out.fib_source        = 0;        // 4H pivots
      out.show_4h_pivots    = true;
      out.ema_fast          = 20;       // timing
      out.ema_slow          = 50;       // short structure
      out.ema_bias          = 200;      // hard regime filter
      out.use_bias_ema      = true;
     }

   // Optional: user still overrides session/spread via dedicated inputs
   if(use_manual_session)
     {
      out.use_session_filter = man_use_session;
      out.allow_asian        = man_asian;
      out.allow_london       = man_london;
      out.allow_ny           = man_ny;
      out.allow_overlap      = man_overlap;
      out.max_spread_pips    = man_max_spread;
      out.fib_source         = man_fib_source;
     }

   // Optional: lock EMA periods to inputs instead of mode presets
   if(use_manual_ema)
     {
      out.ema_fast = MathMax(1, man_ema_fast);
      out.ema_slow = MathMax(1, man_ema_slow);
      out.ema_bias = MathMax(1, man_ema_bias);
     }
  }

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

//+------------------------------------------------------------------+
//| Moving average of any series (index 0 = oldest).                 |
//| Used for RSI signal line (RSI-based MA).                         |
//| method: MODE_SMA or MODE_EMA (others fall back to SMA).          |
//+------------------------------------------------------------------+
bool FxMaOnSeries(const double &src[],
                  const int rates_total,
                  const int period,
                  const ENUM_MA_METHOD method,
                  double &out_ma[])
  {
   if(period < 1 || rates_total < period)
      return false;

   ArrayResize(out_ma, rates_total);
   ArrayInitialize(out_ma, EMPTY_VALUE);

   // Seed: SMA of first `period` non-empty values
   double sum = 0.0;
   int    got = 0;
   int    seed_end = -1;
   for(int i = 0; i < rates_total; i++)
     {
      if(src[i] == EMPTY_VALUE)
         continue;
      sum += src[i];
      got++;
      if(got == period)
        {
         seed_end = i;
         break;
        }
     }
   if(seed_end < 0)
      return false;

   out_ma[seed_end] = sum / period;

   if(method == MODE_EMA)
     {
      double mult = 2.0 / (period + 1.0);
      double ema = out_ma[seed_end];
      for(int i = seed_end + 1; i < rates_total; i++)
        {
         if(src[i] == EMPTY_VALUE)
           {
            out_ma[i] = EMPTY_VALUE;
            continue;
           }
         ema = src[i] * mult + ema * (1.0 - mult);
         out_ma[i] = ema;
        }
     }
   else // SMA O(n) rolling window (was O(n*period) — froze Wine on full recalc)
     {
      double window = sum; // already sum of first `period` values ending at seed_end
      // Track indices of values in the window for EMPTY_VALUE gaps is hard;
      // for RSI series EMPTY_VALUE only appears before first RSI — contiguous after seed.
      for(int i = seed_end + 1; i < rates_total; i++)
        {
         if(src[i] == EMPTY_VALUE || src[i - period] == EMPTY_VALUE)
           {
            // fallback rare path
            double s = 0.0;
            int    n = 0;
            for(int j = i; j >= 0 && n < period; j--)
              {
               if(src[j] == EMPTY_VALUE)
                  continue;
               s += src[j];
               n++;
              }
            out_ma[i] = (n == period) ? s / period : EMPTY_VALUE;
            if(n == period)
               window = s;
            continue;
           }
         window += src[i] - src[i - period];
         out_ma[i] = window / period;
        }
     }
   return true;
  }

//+------------------------------------------------------------------+
//| RSI + MA-of-RSI convenience (index 0 = oldest).                  |
//+------------------------------------------------------------------+
bool FxRsiWithMa(const double &price[],
                 const int rates_total,
                 const int rsi_period,
                 const int ma_period,
                 const ENUM_MA_METHOD ma_method,
                 double &out_rsi[],
                 double &out_rsi_ma[])
  {
   if(!FxRsiSeries(price, rates_total, rsi_period, out_rsi))
      return false;
   return FxMaOnSeries(out_rsi, rates_total, ma_period, ma_method, out_rsi_ma);
  }

//+------------------------------------------------------------------+
//| RSI vs its MA state                                              |
//| +1 RSI above MA | -1 below | 0 flat/unknown                      |
//| Cross up/down: previous vs current                               |
//+------------------------------------------------------------------+
int FxRsiMaBias(const double rsi_now, const double ma_now)
  {
   if(rsi_now == EMPTY_VALUE || ma_now == EMPTY_VALUE)
      return 0;
   if(rsi_now > ma_now)
      return 1;
   if(rsi_now < ma_now)
      return -1;
   return 0;
  }

bool FxRsiMaCrossUp(const double rsi_prev, const double ma_prev,
                    const double rsi_now, const double ma_now)
  {
   if(rsi_prev == EMPTY_VALUE || ma_prev == EMPTY_VALUE ||
      rsi_now == EMPTY_VALUE || ma_now == EMPTY_VALUE)
      return false;
   return (rsi_prev <= ma_prev && rsi_now > ma_now);
  }

bool FxRsiMaCrossDown(const double rsi_prev, const double ma_prev,
                      const double rsi_now, const double ma_now)
  {
   if(rsi_prev == EMPTY_VALUE || ma_prev == EMPTY_VALUE ||
      rsi_now == EMPTY_VALUE || ma_now == EMPTY_VALUE)
      return false;
   return (rsi_prev >= ma_prev && rsi_now < ma_now);
  }

//+------------------------------------------------------------------+
//| Force-load history for a TF (critical in Strategy Tester for MTF)|
//| Returns number of bars available after load attempt.             |
//+------------------------------------------------------------------+
int FxEnsureHistory(const string symbol, const ENUM_TIMEFRAMES tf, const int min_bars = 300)
  {
   string sym = (symbol == NULL || symbol == "") ? _Symbol : symbol;
   if(!SymbolSelect(sym, true))
     {
      // still try CopyRates — tester may already have the symbol
     }

   MqlRates r[];
   ArraySetAsSeries(r, true);
   int n = CopyRates(sym, tf, 0, min_bars, r);
   if(n >= min_bars)
      return n;

   // Second try: wider window by time (≈ min_bars * period seconds * 1.5)
   int sec = PeriodSeconds(tf);
   if(sec <= 0)
      sec = 3600;
   datetime to   = TimeCurrent();
   if(to <= 0)
      to = TimeTradeServer();
   datetime from = to - (datetime)(sec * min_bars * 2);
   n = CopyRates(sym, tf, from, to, r);
   if(n < 0)
      n = 0;

   // Third: request via terminal terminal history depth
   datetime t[];
   ArraySetAsSeries(t, true);
   int nt = CopyTime(sym, tf, 0, min_bars, t);
   if(nt > n)
      n = nt;

   return n;
  }

//+------------------------------------------------------------------+
//| Ensure H1 + H4 + D1 (and current) for multi-TF Fib indicators    |
//+------------------------------------------------------------------+
void FxEnsureMtfHistory(const string symbol = NULL, const int min_bars = 400)
  {
   string sym = (symbol == NULL || symbol == "") ? _Symbol : symbol;
   int h1 = FxEnsureHistory(sym, PERIOD_H1, min_bars);
   int h4 = FxEnsureHistory(sym, PERIOD_H4, MathMax(150, min_bars / 4));
   int d1 = FxEnsureHistory(sym, PERIOD_D1, MathMax(80,  min_bars / 20));
   int cur = FxEnsureHistory(sym, PERIOD_CURRENT, min_bars);
   Print("FxEnsureMtfHistory ", sym,
         " H1=", h1, " H4=", h4, " D1=", d1, " CUR=", cur);
  }

#endif // FOREX_UTILS_MQH
//+------------------------------------------------------------------+

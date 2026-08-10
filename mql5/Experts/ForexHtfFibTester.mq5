//+------------------------------------------------------------------+
//| ForexHtfFibTester.mq5                                            |
//| Strategy Tester EA: HTF Fib golden-zone + RSI + EMA200           |
//|                                                                  |
//| v1.40: EA-native Fib engine (no iCustom buffer dependency).      |
//| Chart indicator ForexHtfPivotsFib remains for visual only.       |
//| Recommended: XAUUSD H1. BTC → BtcTrendPullback path.             |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.40"
#property description "Backtest EA: EA-native HTF Fib + ATR exits v1.40"
#property strict

#include <Trade\Trade.mqh>
#include <ForexUtils.mqh>

input group "=== Signal ==="
input int    InpSignalShift       = 1;     // 1 = last closed bar
input bool   InpAllowLiveTrading  = false; // false = tester only
input bool   InpUseEaFibEngine    = true;  // recommended: true (reliable in tester)

input group "=== Fib / mode ==="
input ENUM_FX_TRADING_MODE InpTradingMode = FX_MODE_INTRADAY;
input int    InpPivotLeft         = 5;
input int    InpPivotRight        = 5;
input int    InpHtfBars           = 800;   // H4 bars to scan

input group "=== RSI + filters ==="
input int    InpRsiPeriod         = 14;
input int    InpRsiLongMax        = 40;
input int    InpRsiShortMin       = 60;
input bool   InpRequireGoldenZone = true;  // Fib 61.8–78.6
input bool   InpRequireBiasFilter = true;  // close vs EMA200
input bool   InpResearchFallback  = false; // RSI-only if no Fib sig

input group "=== Risk / exits ==="
input double InpLots              = 0.01;
input double InpRiskPercent       = 0.5;
input int    InpAtrPeriod         = 14;
input double InpSlAtrMult         = 2.0;
input double InpTpAtrMult         = 3.0;
input double InpMaxSpreadPips     = 0.0;
input int    InpMagic             = 26080505;
input int    InpSlippagePoints    = 50;
input bool   InpReverseOnOpp      = true;
input bool   InpOneTradePerBar    = true;

input group "=== Diagnostics ==="
input bool   InpDiagVerbose       = true;

//---
CTrade   g_trade;
int      g_hAtr  = INVALID_HANDLE;
int      g_hRsi  = INVALID_HANDLE;
int      g_hBias = INVALID_HANDLE;
datetime g_last_bar = 0;
datetime g_last_trade_bar = 0;
bool     g_trade_enabled = true;

// Engine state (latest)
int      g_swing_dir = 0;
double   g_fib618 = 0, g_fib786 = 0;
bool     g_fib_ok = false;
int      g_pivot_count = 0;
int      g_htf_bars = 0;

// Funnel
ulong g_bars_eval = 0, g_spread_block = 0;
ulong g_fib_valid = 0, g_swing_non0 = 0;
ulong g_in_zone_long = 0, g_in_zone_short = 0;
ulong g_rsi_long = 0, g_rsi_short = 0;
ulong g_sig_long = 0, g_sig_short = 0;
ulong g_entries_ok = 0, g_entries_fail = 0;
ulong g_research_hits = 0;
double g_rsi_min = 1000, g_rsi_max = -1000;

//+------------------------------------------------------------------+
int OnInit()
  {
   g_trade_enabled = true;
   if(!MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_OPTIMIZATION))
     {
      if(!InpAllowLiveTrading)
        {
         g_trade_enabled = false;
         Print("ForexHtfFibTester: LIVE — no orders (InpAllowLiveTrading=false). Use Strategy Tester.");
        }
     }

   if(MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_OPTIMIZATION))
      FxEnsureMtfHistory(_Symbol, 600);

   g_hAtr  = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   g_hRsi  = iRSI(_Symbol, PERIOD_CURRENT, InpRsiPeriod, PRICE_CLOSE);
   g_hBias = iMA(_Symbol, PERIOD_CURRENT, 200, 0, MODE_EMA, PRICE_CLOSE);
   if(g_hAtr == INVALID_HANDLE || g_hRsi == INVALID_HANDLE || g_hBias == INVALID_HANDLE)
     {
      Print("ForexHtfFibTester: indicator handle fail err=", GetLastError());
      return INIT_FAILED;
     }

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpSlippagePoints);
   g_trade.SetTypeFillingBySymbol(_Symbol);

   // Warm Fib once
   RebuildEaFib();

   Print("ForexHtfFibTester v1.40 ON ", _Symbol, " ", EnumToString(Period()),
         " eaFib=", (InpUseEaFibEngine ? "yes" : "no"),
         " zone=", (InpRequireGoldenZone ? "ON" : "off"),
         " bias=", (InpRequireBiasFilter ? "on" : "off"),
         " RSI<=", InpRsiLongMax, "/>=", InpRsiShortMin,
         " htfBars=", g_htf_bars, " pivots=", g_pivot_count,
         " swing=", g_swing_dir, " fib=", (g_fib_ok ? 1 : 0),
         " liveTrade=", (g_trade_enabled ? "yes" : "NO"),
         " lots=", InpLots, " SL=", InpSlAtrMult, "x TP=", InpTpAtrMult, "x");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(InpDiagVerbose)
      PrintDiag("OnDeinit");
   if(g_hAtr  != INVALID_HANDLE) IndicatorRelease(g_hAtr);
   if(g_hRsi  != INVALID_HANDLE) IndicatorRelease(g_hRsi);
   if(g_hBias != INVALID_HANDLE) IndicatorRelease(g_hBias);
  }

//+------------------------------------------------------------------+
void PrintDiag(const string tag)
  {
   Print("DIAG[", tag, "] bars=", g_bars_eval,
         " spreadBlock=", g_spread_block,
         " htfBars=", g_htf_bars, " pivots=", g_pivot_count,
         " fibValid=", g_fib_valid, " swing!=0=", g_swing_non0,
         " zoneL/S=", g_in_zone_long, "/", g_in_zone_short,
         " rsiL/S=", g_rsi_long, "/", g_rsi_short,
         " sigL/S=", g_sig_long, "/", g_sig_short,
         " researchHits=", g_research_hits,
         " rsiMinMax=", g_rsi_min, "/", g_rsi_max,
         " entryOK/fail=", g_entries_ok, "/", g_entries_fail,
         " flags zone=", (InpRequireGoldenZone ? 1 : 0),
         " bias=", (InpRequireBiasFilter ? 1 : 0));
  }

//+------------------------------------------------------------------+
int CopyRatesChrono(const ENUM_TIMEFRAMES tf, const int count, MqlRates &out[])
  {
   MqlRates tmp[];
   ArraySetAsSeries(tmp, true);
   int n = CopyRates(_Symbol, tf, 0, count, tmp);
   if(n <= 0)
      return 0;
   ArrayResize(out, n);
   for(int i = 0; i < n; i++)
      out[i] = tmp[n - 1 - i];
   if(n >= 2 && out[0].time > out[n - 1].time)
     {
      for(int i = 0; i < n / 2; i++)
        {
         MqlRates sw = out[i];
         out[i] = out[n - 1 - i];
         out[n - 1 - i] = sw;
        }
     }
   return n;
  }

//+------------------------------------------------------------------+
bool IsPivotHigh(const MqlRates &r[], const int n, const int c,
                 const int left, const int right)
  {
   if(c - left < 0 || c + right >= n)
      return false;
   double v = r[c].high;
   for(int i = c - left; i <= c + right; i++)
     {
      if(i == c) continue;
      if(r[i].high >= v)
         return false;
     }
   return true;
  }

bool IsPivotLow(const MqlRates &r[], const int n, const int c,
                const int left, const int right)
  {
   if(c - left < 0 || c + right >= n)
      return false;
   double v = r[c].low;
   for(int i = c - left; i <= c + right; i++)
     {
      if(i == c) continue;
      if(r[i].low <= v)
         return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
void ProcessPivot(const int ptype, const double price, const datetime t,
                  int &last_type, double &last_px, datetime &last_t,
                  double &sh, double &sl, datetime &sht, datetime &slt, int &dir)
  {
   if(ptype == 1)
     {
      if(last_type == 0)
        {
         last_type = 1;
         last_px = price;
         last_t = t;
        }
      else if(last_type == 1)
        {
         if(price > last_px)
           {
            last_px = price;
            last_t = t;
            if(dir == 1)
              {
               sh = price;
               sht = t;
              }
           }
        }
      else
        {
         if(price > last_px || dir == 0)
           {
            sl = last_px;
            slt = last_t;
            sh = price;
            sht = t;
            dir = 1;
           }
         last_type = 1;
         last_px = price;
         last_t = t;
        }
     }
   else
     {
      if(last_type == 0)
        {
         last_type = -1;
         last_px = price;
         last_t = t;
        }
      else if(last_type == -1)
        {
         if(price < last_px)
           {
            last_px = price;
            last_t = t;
            if(dir == -1)
              {
               sl = price;
               slt = t;
              }
           }
        }
      else
        {
         if(price < last_px || dir == 0)
           {
            sh = last_px;
            sht = last_t;
            sl = price;
            slt = t;
            dir = -1;
           }
         last_type = -1;
         last_px = price;
         last_t = t;
        }
     }
  }

//+------------------------------------------------------------------+
void RebuildEaFib()
  {
   g_swing_dir = 0;
   g_fib_ok = false;
   g_fib618 = g_fib786 = 0;
   g_pivot_count = 0;
   g_htf_bars = 0;

   ENUM_TIMEFRAMES tf = PERIOD_H4;
   if(InpTradingMode == FX_MODE_SWING)
      tf = PERIOD_D1;

   int left  = MathMax(1, InpPivotLeft);
   int right = MathMax(1, InpPivotRight);
   int want  = MathMax(50, InpHtfBars);

   FxEnsureHistory(_Symbol, tf, want);
   MqlRates r[];
   int n = CopyRatesChrono(tf, want, r);
   if(n < left + right + 3)
     {
      // fallback H1
      FxEnsureHistory(_Symbol, PERIOD_H1, want);
      n = CopyRatesChrono(PERIOD_H1, want, r);
     }
   g_htf_bars = n;
   if(n < left + right + 3)
     {
      static bool once = false;
      if(!once)
        {
         Print("EaFib: not enough HTF bars n=", n);
         once = true;
        }
      return;
     }

   int last_type = 0;
   double last_px = 0;
   datetime last_t = 0;
   double sh = 0, sl = 0;
   datetime sht = 0, slt = 0;
   int dir = 0;
   int cnt = 0;
   double last_hi = 0, last_lo = 0;
   datetime th = 0, tl = 0;

   for(int c = left; c <= n - 1 - right; c++)
     {
      bool isH = IsPivotHigh(r, n, c, left, right);
      bool isL = IsPivotLow(r, n, c, left, right);
      if(isH && isL)
         continue;
      if(isH)
        {
         ProcessPivot(1, r[c].high, r[c].time,
                      last_type, last_px, last_t, sh, sl, sht, slt, dir);
         last_hi = r[c].high;
         th = r[c].time;
         cnt++;
        }
      else if(isL)
        {
         ProcessPivot(-1, r[c].low, r[c].time,
                      last_type, last_px, last_t, sh, sl, sht, slt, dir);
         last_lo = r[c].low;
         tl = r[c].time;
         cnt++;
        }
     }
   g_pivot_count = cnt;

   if(dir == 0 && last_hi > 0 && last_lo > 0 && last_hi > last_lo)
     {
      sh = last_hi;
      sl = last_lo;
      sht = th;
      slt = tl;
      dir = (th >= tl) ? 1 : -1;
     }

   g_swing_dir = dir;
   if(dir != 0 && sh > sl)
     {
      if(dir == 1)
        {
         g_fib618 = sh - (sh - sl) * 0.618;
         g_fib786 = sh - (sh - sl) * 0.786;
        }
      else
        {
         g_fib618 = sl + (sh - sl) * 0.618;
         g_fib786 = sl + (sh - sl) * 0.786;
        }
      g_fib_ok = true;
     }

   static datetime s_log = 0;
   datetime now = TimeCurrent();
   if(s_log == 0 || now - s_log > 86400)
     {
      Print("EaFib rebuild tf=", EnumToString(tf),
            " n=", n, " pivots=", cnt, " swing=", dir,
            " fib=", (g_fib_ok ? 1 : 0),
            " f618=", g_fib618, " f786=", g_fib786,
            " hi=", sh, " lo=", sl);
      s_log = (now > 0 ? now : 1);
     }
  }

//+------------------------------------------------------------------+
//| +1 long / -1 short / 0 none on closed bar (shift)                |
//+------------------------------------------------------------------+
int EaFibSignal(const int shift)
  {
   // Rebuild on each new bar evaluation (cheap enough for H4 scan)
   RebuildEaFib();

   if(g_swing_dir != 0)
      g_swing_non0++;
   if(g_fib_ok)
      g_fib_valid++;

   double close[], rsi[], bias[];
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(bias, true);
   if(CopyClose(_Symbol, PERIOD_CURRENT, shift, 2, close) < 2)
      return 0;
   if(CopyBuffer(g_hRsi, 0, shift, 2, rsi) < 2)
      return 0;
   if(rsi[0] <= 0.0 || rsi[0] > 100.0)
      return 0;

   if(rsi[0] < g_rsi_min) g_rsi_min = rsi[0];
   if(rsi[0] > g_rsi_max) g_rsi_max = rsi[0];
   if(rsi[0] <= InpRsiLongMax)  g_rsi_long++;
   if(rsi[0] >= InpRsiShortMin) g_rsi_short++;

   double c = close[0];
   bool bull_zone = true, bear_zone = true;
   if(InpRequireGoldenZone)
     {
      if(!g_fib_ok || g_swing_dir == 0)
         return 0;
      bull_zone = (g_swing_dir == 1 && c <= g_fib618 && c >= g_fib786);
      bear_zone = (g_swing_dir == -1 && c >= g_fib618 && c <= g_fib786);
     }
   else if(g_swing_dir != 0)
     {
      bull_zone = (g_swing_dir == 1);
      bear_zone = (g_swing_dir == -1);
     }

   if(bull_zone && g_swing_dir == 1) g_in_zone_long++;
   if(bear_zone && g_swing_dir == -1) g_in_zone_short++;

   bool long_now  = bull_zone && (rsi[0] <= InpRsiLongMax);
   bool short_now = bear_zone && (rsi[0] >= InpRsiShortMin);
   bool long_prev  = (rsi[1] <= InpRsiLongMax);
   bool short_prev = (rsi[1] >= InpRsiShortMin);
   // previous zone approx same fib (latest) — edge on RSI entry into band
   if(InpRequireGoldenZone)
     {
      bool bz1 = (g_swing_dir == 1 && close[1] <= g_fib618 && close[1] >= g_fib786);
      bool ez1 = (g_swing_dir == -1 && close[1] >= g_fib618 && close[1] <= g_fib786);
      long_prev  = bz1 && long_prev;
      short_prev = ez1 && short_prev;
     }

   if(InpRequireBiasFilter)
     {
      if(CopyBuffer(g_hBias, 0, shift, 1, bias) < 1 || bias[0] <= 0.0)
         return 0;
      if(c <= bias[0]) long_now = false;
      if(c >= bias[0]) short_now = false;
     }

   int s = 0;
   if(long_now && !long_prev)
      s = 1;
   else if(short_now && !short_prev)
      s = -1;

   if(s > 0) g_sig_long++;
   if(s < 0) g_sig_short++;
   return s;
  }

//+------------------------------------------------------------------+
int ResearchRsiOnly(const int shift)
  {
   double close[], rsi[], bias[];
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(bias, true);
   if(CopyClose(_Symbol, PERIOD_CURRENT, shift, 2, close) < 2)
      return 0;
   if(CopyBuffer(g_hRsi, 0, shift, 2, rsi) < 2)
      return 0;
   if(rsi[0] <= 0.0 || rsi[0] > 100.0)
      return 0;

   bool long_now  = (rsi[0] <= InpRsiLongMax);
   bool short_now = (rsi[0] >= InpRsiShortMin);
   bool long_prev  = (rsi[1] <= InpRsiLongMax);
   bool short_prev = (rsi[1] >= InpRsiShortMin);

   if(InpRequireBiasFilter)
     {
      if(CopyBuffer(g_hBias, 0, shift, 1, bias) < 1)
         return 0;
      if(close[0] <= bias[0]) long_now = false;
      if(close[0] >= bias[0]) short_now = false;
     }

   int s = 0;
   if(long_now && !long_prev) s = 1;
   else if(short_now && !short_prev) s = -1;
   if(s != 0) g_research_hits++;
   return s;
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   datetime t[];
   if(CopyTime(_Symbol, PERIOD_CURRENT, 0, 1, t) < 1)
      return;
   if(t[0] == g_last_bar)
      return;
   g_last_bar = t[0];
   g_bars_eval++;

   if(InpMaxSpreadPips > 0.0 && FxSpreadPips(_Symbol) > InpMaxSpreadPips)
     {
      g_spread_block++;
      return;
     }

   int s = 0;
   if(InpUseEaFibEngine)
      s = EaFibSignal(InpSignalShift);
   if(s == 0 && InpResearchFallback)
      s = ResearchRsiOnly(InpSignalShift);
   if(s == 0)
      return;
   if(!g_trade_enabled)
      return;
   if(InpOneTradePerBar && g_last_trade_bar == t[0])
      return;

   int pos = PositionDir();
   if(pos == s)
      return;
   if(pos != 0)
     {
      if(!InpReverseOnOpp)
         return;
      if(!CloseOurPosition())
         return;
     }

   if(OpenBySignal(s))
     {
      g_last_trade_bar = t[0];
      g_entries_ok++;
     }
   else
      g_entries_fail++;
  }

//+------------------------------------------------------------------+
int PositionDir()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      long type = PositionGetInteger(POSITION_TYPE);
      if(type == POSITION_TYPE_BUY)  return 1;
      if(type == POSITION_TYPE_SELL) return -1;
     }
   return 0;
  }

//+------------------------------------------------------------------+
bool CloseOurPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(!g_trade.PositionClose(ticket))
        {
         Print("Close fail ", g_trade.ResultRetcodeDescription());
         return false;
        }
     }
   return true;
  }

//+------------------------------------------------------------------+
bool OpenBySignal(const int s)
  {
   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(g_hAtr, 0, 1, 1, atr) < 1 || atr[0] <= 0.0)
     {
      Print("ATR missing");
      return false;
     }

   double sl_dist = atr[0] * InpSlAtrMult;
   double tp_dist = atr[0] * InpTpAtrMult;
   double lot = LotsForStop(sl_dist);
   if(lot <= 0.0)
      return false;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   long stops_level = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double min_dist = (stops_level > 0) ? stops_level * _Point : 0.0;
   if(sl_dist < min_dist) sl_dist = min_dist;
   if(tp_dist < min_dist) tp_dist = min_dist;

   bool ok = false;
   if(s > 0)
     {
      double sl = NormalizeDouble(ask - sl_dist, digits);
      double tp = NormalizeDouble(ask + tp_dist, digits);
      ok = g_trade.Buy(lot, _Symbol, ask, sl, tp, "HTF Fib long");
     }
   else
     {
      double sl = NormalizeDouble(bid + sl_dist, digits);
      double tp = NormalizeDouble(bid - tp_dist, digits);
      ok = g_trade.Sell(lot, _Symbol, bid, sl, tp, "HTF Fib short");
     }

   if(!ok)
      Print("Open fail s=", s, " ", g_trade.ResultRetcodeDescription());
   else
      Print("Open s=", s, " lot=", lot, " atr=", atr[0],
            " fib618=", g_fib618, " fib786=", g_fib786, " swing=", g_swing_dir);
   return ok;
  }

//+------------------------------------------------------------------+
double LotsForStop(const double sl_price_dist)
  {
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minv = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxv = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0) step = 0.01;

   double lot = InpLots;
   if(lot <= 0.0)
     {
      double tick_size  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      if(tick_size <= 0.0 || tick_value <= 0.0 || sl_price_dist <= 0.0)
         return minv;
      double money_risk = AccountInfoDouble(ACCOUNT_EQUITY) * (InpRiskPercent / 100.0);
      double ticks = sl_price_dist / tick_size;
      double money_per_lot = ticks * tick_value;
      if(money_per_lot <= 0.0)
         return minv;
      lot = money_risk / money_per_lot;
     }
   lot = MathFloor(lot / step) * step;
   if(lot < minv) lot = minv;
   if(lot > maxv) lot = maxv;
   return NormalizeDouble(lot, 2);
  }

//+------------------------------------------------------------------+
double OnTester()
  {
   if(InpDiagVerbose)
      PrintDiag("OnTester");
   double trades = TesterStatistics(STAT_TRADES);
   double pf     = TesterStatistics(STAT_PROFIT_FACTOR);
   double profit = TesterStatistics(STAT_PROFIT);
   double dd     = TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
   Print("OnTester summary trades=", trades,
         " profit=", profit, " pf=", pf, " maxDD%=", dd);
   if(trades > 0.0 && pf > 0.0 && pf < 1000.0)
      return pf;
   if(trades > 0.0)
      return profit;
   return -1.0;
  }
//+------------------------------------------------------------------+

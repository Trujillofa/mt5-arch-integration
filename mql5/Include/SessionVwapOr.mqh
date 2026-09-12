//+------------------------------------------------------------------+
//| SessionVwapOr.mqh                                                |
//| ET-day-keyed session VWAP (vnum/vden) + opening-range hi/lo.     |
//|                                                                  |
//| In-scope: UIS, BNS. BtcTrendPullback RollingVwap stays separate  |
//| (lookback, not ET-day). GoldSessionScalp excluded.               |
//| Callers own the clock (IdxEtOfBar / BtcEtFromServer) and pass    |
//| their existing day key. Do not change clocks here.               |
//| Buffer writes (BufVwap, ORH/ORL) stay in the indicators.         |
//| Never OrderSend. Signal math stays in the overlays.              |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef SESSION_VWAP_OR_MQH
#define SESSION_VWAP_OR_MQH

#define SESSION_VWAP_OR_VER "1.00"

struct SessionVwapOr
  {
   double vnum;
   double vden;
   double or_hi;
   double or_lo;
   int    day_key;
   bool   or_set;
  };

//+------------------------------------------------------------------+
void SvoInit(SessionVwapOr &s)
  {
   s.vnum    = 0.0;
   s.vden    = 0.0;
   s.or_hi   = 0.0;
   s.or_lo   = 0.0;
   s.day_key = -1;
   s.or_set  = false;
  }

//+------------------------------------------------------------------+
void SvoReset(SessionVwapOr &s, const int day_key, const double or_unset)
  {
   s.vnum    = 0.0;
   s.vden    = 0.0;
   s.or_hi   = or_unset;
   s.or_lo   = or_unset;
   s.day_key = day_key;
   s.or_set  = false;
  }

//+------------------------------------------------------------------+
bool SvoOnDayChange(SessionVwapOr &s, const int day_key, const double or_unset)
  {
   if(day_key == s.day_key)
      return false;
   SvoReset(s, day_key, or_unset);
   return true;
  }

//+------------------------------------------------------------------+
void SvoAccumulate(SessionVwapOr &s,
                   const double high, const double low, const double close,
                   const long tick_volume)
  {
   double typ = (high + low + close) / 3.0;
   double vol = (double)MathMax(tick_volume, 1);
   s.vnum += typ * vol;
   s.vden += vol;
  }

//+------------------------------------------------------------------+
double SvoVwap(const SessionVwapOr &s)
  {
   if(s.vden > 0.0)
      return s.vnum / s.vden;
   return EMPTY_VALUE;
  }

//+------------------------------------------------------------------+
void SvoOrBar(SessionVwapOr &s, const double high, const double low)
  {
   if(!s.or_set)
     {
      s.or_hi  = high;
      s.or_lo  = low;
      s.or_set = true;
     }
   else
     {
      if(high > s.or_hi)
         s.or_hi = high;
      if(low < s.or_lo)
         s.or_lo = low;
     }
  }

#endif

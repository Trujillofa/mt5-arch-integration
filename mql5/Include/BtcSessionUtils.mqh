//+------------------------------------------------------------------+
//| BtcSessionUtils.mqh                                              |
//| BTC NY-desk overlap clock (ET+7). Mirror of                     |
//| scripts/btc_ny_session_scalp_core.py                             |
//|                                                                  |
//| Server wall = America/New_York + 7h (tracks US DST).             |
//| ET = server - 7 hours. Never a constant UTC offset of 10800.     |
//| Session is [08:00, 11:30) ET — not cash 09:30, not London gold.  |
//| SCREEN_FAIL / observe-only. Never OrderSend.                     |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef BTC_SESSION_UTILS_MQH
#define BTC_SESSION_UTILS_MQH

#define BTC_SESSION_START_MIN  (8 * 60)
#define BTC_SESSION_END_MIN    (11 * 60 + 30)
#define BTC_FLAT_MIN           (11 * 60 + 30)
#define BTC_FRIDAY_CUTOFF_MIN  (14 * 60)
#define BTC_NFP_LO_MIN         (8 * 60 + 25)
#define BTC_NFP_HI_MIN         (8 * 60 + 40)
#define BTC_SERVER_MINUS_SEC   (7 * 3600)

//+------------------------------------------------------------------+
bool BtcLooksLikeBtc(const string symbol)
  {
   string u = symbol;
   StringToUpper(u);
   StringReplace(u, " ", "");
   StringReplace(u, "-", "");
   StringReplace(u, "/", "");
   return (StringFind(u, "BTC") >= 0);
  }

//+------------------------------------------------------------------+
datetime BtcEtFromServer(const datetime server)
  {
   return server - BTC_SERVER_MINUS_SEC;
  }

//+------------------------------------------------------------------+
int BtcEtMinuteOfDay(const datetime et)
  {
   MqlDateTime dt;
   TimeToStruct(et, dt);
   return dt.hour * 60 + dt.min;
  }

//+------------------------------------------------------------------+
int BtcEtDow(const datetime et)
  {
   MqlDateTime dt;
   TimeToStruct(et, dt);
   return dt.day_of_week; // 0=Sun ... 5=Fri
  }

//+------------------------------------------------------------------+
int BtcEtKey(const datetime et)
  {
   MqlDateTime dt;
   TimeToStruct(et, dt);
   return dt.year * 10000 + dt.mon * 100 + dt.day;
  }

//+------------------------------------------------------------------+
bool BtcInOverlap(const datetime et)
  {
   int m = BtcEtMinuteOfDay(et);
   return (m >= BTC_SESSION_START_MIN && m < BTC_SESSION_END_MIN);
  }

//+------------------------------------------------------------------+
bool BtcFridayCutoff(const datetime et)
  {
   return (BtcEtDow(et) == 5 && BtcEtMinuteOfDay(et) >= BTC_FRIDAY_CUTOFF_MIN);
  }

//+------------------------------------------------------------------+
bool BtcEntryOk(const datetime et, const bool nfp_blackout)
  {
   if(!BtcInOverlap(et))
      return false;
   if(BtcFridayCutoff(et))
      return false;
   if(nfp_blackout)
     {
      int m = BtcEtMinuteOfDay(et);
      if(m >= BTC_NFP_LO_MIN && m < BTC_NFP_HI_MIN)
         return false;
     }
   return true;
  }

#endif

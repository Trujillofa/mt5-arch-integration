//+------------------------------------------------------------------+
//| OilSessionUtils.mqh                                              |
//| XTIUSD / USOUSD London+NY energy clock (ET+7). Mirror of        |
//| scripts/oil_session_scalp_core.py                                |
//|                                                                  |
//| Server wall = America/New_York + 7h (tracks US DST).             |
//| ET = server - 7 hours. Never a constant UTC offset of 10800.     |
//| London visual = ET + 5h (Python ZoneInfo is authoritative).      |
//| NY energy [08:00, 11:30) ET. EIA Wed [10:25, 10:40) ET.          |
//| Never OrderSend.                                                 |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef OIL_SESSION_UTILS_MQH
#define OIL_SESSION_UTILS_MQH

#define OIL_LONDON_START_MIN   (8 * 60)
#define OIL_LONDON_OR_END_MIN  (8 * 60 + 30)
#define OIL_LONDON_END_MIN     (11 * 60)
#define OIL_NY_START_MIN       (8 * 60)
#define OIL_NY_END_MIN         (11 * 60 + 30)
#define OIL_NY_FLAT_MIN        (11 * 60 + 30)
#define OIL_FRIDAY_CUTOFF_MIN  (14 * 60)
#define OIL_EIA_LO_MIN         (10 * 60 + 25)
#define OIL_EIA_HI_MIN         (10 * 60 + 40)
#define OIL_SERVER_MINUS_SEC   (7 * 3600)
#define OIL_ET_TO_LON_SEC      (5 * 3600)
#define OIL_GLOBEX_UTC_HOUR    21

//+------------------------------------------------------------------+
bool OilLooksLikeOil(const string symbol)
  {
   string u = symbol;
   StringToUpper(u);
   StringReplace(u, " ", "");
   StringReplace(u, "-", "");
   StringReplace(u, "/", "");
   StringReplace(u, ".", "");
   if(StringFind(u, "UKOIL") >= 0) return false;
   if(StringFind(u, "UKOUSD") >= 0) return false;
   if(StringFind(u, "XBR") >= 0) return false;
   if(StringFind(u, "BRENT") >= 0) return false;
   if(StringFind(u, "XTI") >= 0) return true;
   if(StringFind(u, "USOIL") >= 0) return true;
   if(StringFind(u, "USOUSD") >= 0) return true;
   if(StringFind(u, "WTI") >= 0) return true;
   if(StringFind(u, "CLOIL") >= 0) return true;
   return (StringFind(u, "USO") == 0);
  }

//+------------------------------------------------------------------+
datetime OilEtFromServer(const datetime server)
  {
   return server - OIL_SERVER_MINUS_SEC;
  }

//+------------------------------------------------------------------+
datetime OilLonFromEt(const datetime et)
  {
   return et + OIL_ET_TO_LON_SEC;
  }

//+------------------------------------------------------------------+
int OilMinuteOfDay(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.hour * 60 + dt.min;
  }

//+------------------------------------------------------------------+
int OilDow(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.day_of_week; // 0=Sun ... 5=Fri
  }

//+------------------------------------------------------------------+
int OilDateKey(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.year * 10000 + dt.mon * 100 + dt.day;
  }

//+------------------------------------------------------------------+
int OilUtcHourFromServer(const datetime server)
  {
   datetime et = OilEtFromServer(server);
   datetime utc = et + (datetime)(TimeGMT() - TimeLocal());
   // Fallback: treat server as ET+7 so UTC = ET + (5 winter / 4 summer).
   // Overlay uses server hour - 2 as a visual-only Globex gate
   // (21:00-22:00 UTC ≈ server 04:00 / 05:00). Python is authoritative.
   MqlDateTime dt;
   TimeToStruct(server, dt);
   int guess = dt.hour - 2;
   if(guess < 0)
      guess += 24;
   return guess;
  }

//+------------------------------------------------------------------+
bool OilInLondonEntry(const datetime et)
  {
   datetime lon = OilLonFromEt(et);
   int m = OilMinuteOfDay(lon);
   return (m >= OIL_LONDON_OR_END_MIN && m < OIL_LONDON_END_MIN);
  }

//+------------------------------------------------------------------+
bool OilInNyEntry(const datetime et)
  {
   int m = OilMinuteOfDay(et);
   return (m >= OIL_NY_START_MIN && m < OIL_NY_END_MIN);
  }

//+------------------------------------------------------------------+
bool OilFridayCutoff(const datetime et)
  {
   return (OilDow(et) == 5 && OilMinuteOfDay(et) >= OIL_FRIDAY_CUTOFF_MIN);
  }

//+------------------------------------------------------------------+
bool OilEiaBlackout(const datetime et)
  {
   // Wednesday = 3
   return (OilDow(et) == 3 &&
           OilMinuteOfDay(et) >= OIL_EIA_LO_MIN &&
           OilMinuteOfDay(et) < OIL_EIA_HI_MIN);
  }

//+------------------------------------------------------------------+
bool OilEntryOk(const datetime et, const datetime server,
                const bool eia_blackout, const int session)
  {
   if(OilFridayCutoff(et))
      return false;
   if(OilUtcHourFromServer(server) == OIL_GLOBEX_UTC_HOUR)
      return false;
   if(eia_blackout && OilEiaBlackout(et))
      return false;
   if(session == 1)
      return OilInLondonEntry(et);
   if(session == 2)
      return OilInNyEntry(et);
   return (OilInLondonEntry(et) || OilInNyEntry(et));
  }

#endif

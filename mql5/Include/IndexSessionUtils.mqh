//+------------------------------------------------------------------+
//| IndexSessionUtils.mqh                                            |
//| US-index session clock (DST-safe ET / London / Tokyo)            |
//| Mirror of scripts/us_index_session_core.py                       |
//|                                                                  |
//| Bar times are broker SERVER wall clocks. Convert via             |
//| TimeCurrent()-TimeGMT() (override with InpServerUtcOffsetHours). |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef INDEX_SESSION_UTILS_MQH
#define INDEX_SESSION_UTILS_MQH

enum ENUM_IDX_SESSION
  {
   IDX_SESSION_NONE    = 0,
   IDX_SESSION_TOKYO   = 1,
   IDX_SESSION_LONDON  = 2,
   IDX_SESSION_NY_CASH = 3,
   IDX_SESSION_OVERLAP = 4
  };

//+------------------------------------------------------------------+
int IdxDaysInMonth(const int year, const int month)
  {
   if(month == 2)
     {
      bool leap = ((year % 4 == 0 && year % 100 != 0) || (year % 400 == 0));
      return leap ? 29 : 28;
     }
   if(month == 4 || month == 6 || month == 9 || month == 11)
      return 30;
   return 31;
  }

//+------------------------------------------------------------------+
int IdxNthSunday(const int year, const int month, const int n)
  {
   MqlDateTime dt;
   ZeroMemory(dt);
   dt.year = year;
   dt.mon  = month;
   dt.day  = 1;
   dt.hour = 12;
   datetime t = StructToTime(dt);
   TimeToStruct(t, dt);
   int wd = dt.day_of_week; // 0 = Sunday
   int first_sun = (wd == 0) ? 1 : (8 - wd);
   return first_sun + (n - 1) * 7;
  }

//+------------------------------------------------------------------+
int IdxLastSunday(const int year, const int month)
  {
   MqlDateTime dt;
   ZeroMemory(dt);
   dt.year = year;
   dt.mon  = month;
   dt.day  = IdxDaysInMonth(year, month);
   dt.hour = 12;
   datetime t = StructToTime(dt);
   TimeToStruct(t, dt);
   return dt.day - dt.day_of_week;
  }

//+------------------------------------------------------------------+
//| US Eastern DST from UTC wall (2nd Sun Mar 07:00 → 1st Sun Nov 06:00)
//+------------------------------------------------------------------+
bool IdxUsEasternDstUtc(const int y, const int m, const int d,
                        const int h, const int mi)
  {
   if(m < 3 || m > 11)
      return false;
   if(m > 3 && m < 11)
      return true;
   if(m == 3)
     {
      int start_d = IdxNthSunday(y, 3, 2);
      if(d < start_d)
         return false;
      if(d > start_d)
         return true;
      return (h > 7 || (h == 7 && mi >= 0));
     }
   int end_d = IdxNthSunday(y, 11, 1);
   if(d < end_d)
      return true;
   if(d > end_d)
      return false;
   return (h < 6);
  }

//+------------------------------------------------------------------+
//| UK DST from UTC wall (last Sun Mar 01:00 → last Sun Oct 01:00)   |
//+------------------------------------------------------------------+
bool IdxUkDstUtc(const int y, const int m, const int d,
                 const int h, const int mi)
  {
   if(m < 3 || m > 10)
      return false;
   if(m > 3 && m < 10)
      return true;
   if(m == 3)
     {
      int start_d = IdxLastSunday(y, 3);
      if(d < start_d)
         return false;
      if(d > start_d)
         return true;
      return (h >= 1);
     }
   int end_d = IdxLastSunday(y, 10);
   if(d < end_d)
      return true;
   if(d > end_d)
      return false;
   return (h < 1);
  }

//+------------------------------------------------------------------+
int IdxDetectServerUtcOffsetSec(const int override_hours)
  {
   if(override_hours != -99)
      return override_hours * 3600;

   long delta = (long)(TimeCurrent() - TimeGMT());
   if(MathAbs(delta) >= 1800)
      return (int)delta;

   MqlDateTime sc, gc;
   TimeToStruct(TimeCurrent(), sc);
   TimeToStruct(TimeGMT(), gc);
   int dh = sc.hour - gc.hour;
   int dd = sc.day - gc.day;
   if(dd > 1)
      dd = -1;
   if(dd < -1)
      dd = 1;
   return (dh + 24 * dd) * 3600;
  }

//+------------------------------------------------------------------+
void IdxUtcWallOfBar(const datetime bar_server, const int server_utc_offset_sec,
                     int &y, int &m, int &d, int &h, int &mi)
  {
   datetime utc_as_dt = bar_server - server_utc_offset_sec;
   MqlDateTime u;
   TimeToStruct(utc_as_dt, u);
   y  = u.year;
   m  = u.mon;
   d  = u.day;
   h  = u.hour;
   mi = u.min;
  }

//+------------------------------------------------------------------+
void IdxEtOfBar(const datetime bar_server, const int server_utc_offset_sec,
                MqlDateTime &et)
  {
   int y, m, d, h, mi;
   IdxUtcWallOfBar(bar_server, server_utc_offset_sec, y, m, d, h, mi);
   int et_off_h = IdxUsEasternDstUtc(y, m, d, h, mi) ? -4 : -5;
   datetime utc_as_dt = bar_server - server_utc_offset_sec;
   datetime et_as_dt  = utc_as_dt + et_off_h * 3600;
   TimeToStruct(et_as_dt, et);
  }

//+------------------------------------------------------------------+
void IdxLondonOfBar(const datetime bar_server, const int server_utc_offset_sec,
                    MqlDateTime &lon)
  {
   int y, m, d, h, mi;
   IdxUtcWallOfBar(bar_server, server_utc_offset_sec, y, m, d, h, mi);
   int lon_off_h = IdxUkDstUtc(y, m, d, h, mi) ? 1 : 0;
   datetime utc_as_dt = bar_server - server_utc_offset_sec;
   datetime lon_as_dt = utc_as_dt + lon_off_h * 3600;
   TimeToStruct(lon_as_dt, lon);
  }

//+------------------------------------------------------------------+
void IdxTokyoOfBar(const datetime bar_server, const int server_utc_offset_sec,
                   MqlDateTime &tyo)
  {
   datetime utc_as_dt = bar_server - server_utc_offset_sec;
   datetime tyo_as_dt = utc_as_dt + 9 * 3600;
   TimeToStruct(tyo_as_dt, tyo);
  }

//+------------------------------------------------------------------+
bool IdxInHm(const int hour, const int minute,
             const int start_h, const int start_m,
             const int end_h, const int end_m)
  {
   int t   = hour * 60 + minute;
   int a   = start_h * 60 + start_m;
   int b   = end_h * 60 + end_m;
   if(a < b)
      return (t >= a && t < b);
   return (t >= a || t < b);
  }

//+------------------------------------------------------------------+
bool IdxIsNyCash(const MqlDateTime &et)
  {
   return IdxInHm(et.hour, et.min, 9, 30, 16, 0);
  }

//+------------------------------------------------------------------+
bool IdxIsLondonOpen(const MqlDateTime &lon)
  {
   return IdxInHm(lon.hour, lon.min, 8, 0, 17, 0);
  }

//+------------------------------------------------------------------+
bool IdxIsTokyoOpen(const MqlDateTime &tyo)
  {
   return IdxInHm(tyo.hour, tyo.min, 9, 0, 18, 0);
  }

//+------------------------------------------------------------------+
ENUM_IDX_SESSION IdxDetectSession(const datetime bar_server,
                                  const int server_utc_offset_sec)
  {
   MqlDateTime et, lon, tyo;
   IdxEtOfBar(bar_server, server_utc_offset_sec, et);
   IdxLondonOfBar(bar_server, server_utc_offset_sec, lon);
   IdxTokyoOfBar(bar_server, server_utc_offset_sec, tyo);
   bool ny  = IdxIsNyCash(et);
   bool ldn = IdxIsLondonOpen(lon);
   if(ny && ldn)
      return IDX_SESSION_OVERLAP;
   if(ny)
      return IDX_SESSION_NY_CASH;
   if(ldn)
      return IDX_SESSION_LONDON;
   if(IdxIsTokyoOpen(tyo))
      return IDX_SESSION_TOKYO;
   return IDX_SESSION_NONE;
  }

//+------------------------------------------------------------------+
string IdxSessionName(const ENUM_IDX_SESSION s)
  {
   switch(s)
     {
      case IDX_SESSION_TOKYO:   return "Tokyo";
      case IDX_SESSION_LONDON:  return "London";
      case IDX_SESSION_NY_CASH: return "NY cash";
      case IDX_SESSION_OVERLAP: return "LDN+NY";
      default:                  return "Off";
     }
  }

//+------------------------------------------------------------------+
bool IdxInOrWindow(const MqlDateTime &et, const int or_minutes)
  {
   int start = 9 * 60 + 30;
   int end   = start + or_minutes;
   int t     = et.hour * 60 + et.min;
   return (t >= start && t < end);
  }

//+------------------------------------------------------------------+
bool IdxOrComplete(const MqlDateTime &et, const int or_minutes)
  {
   int t   = et.hour * 60 + et.min;
   int end = 9 * 60 + 30 + or_minutes;
   return (t >= end);
  }

//+------------------------------------------------------------------+
bool IdxInEntryWindow(const MqlDateTime &et, const int or_minutes,
                      const int end_h = 11, const int end_m = 30)
  {
   int t     = et.hour * 60 + et.min;
   int start = 9 * 60 + 30 + or_minutes;
   int end   = end_h * 60 + end_m;
   return (t >= start && t < end);
  }

//+------------------------------------------------------------------+
bool IdxFridayCutoff(const MqlDateTime &et)
  {
   // day_of_week: 0 Sunday … 5 Friday
   if(et.day_of_week != 5)
      return false;
   return (et.hour * 60 + et.min) >= (14 * 60);
  }

//+------------------------------------------------------------------+
int IdxEtDateKey(const MqlDateTime &et)
  {
   return et.year * 10000 + et.mon * 100 + et.day;
  }

//+------------------------------------------------------------------+
void IdxAddHoursToYmdhm(int &y, int &m, int &d, int &h, const int add_h)
  {
   h += add_h;
   while(h >= 24)
     {
      h -= 24;
      d += 1;
      if(d > IdxDaysInMonth(y, m))
        {
         d = 1;
         m += 1;
         if(m > 12)
           {
            m = 1;
            y += 1;
           }
        }
     }
  }

//+------------------------------------------------------------------+
datetime IdxEtWallToServer(const int y0, const int m0, const int d0,
                           const int h0, const int mi,
                           const int server_utc_offset_sec)
  {
   // Assume EST (UTC-5) to decide DST, then emit UTC wall + server offset.
   int uy = y0, um = m0, ud = d0, uh = h0;
   IdxAddHoursToYmdhm(uy, um, ud, uh, 5);
   bool dst = IdxUsEasternDstUtc(uy, um, ud, uh, mi);
   int add_h = dst ? 4 : 5;
   int y = y0, m = m0, d = d0, h = h0;
   IdxAddHoursToYmdhm(y, m, d, h, add_h);
   MqlDateTime dt;
   ZeroMemory(dt);
   dt.year = y;
   dt.mon  = m;
   dt.day  = d;
   dt.hour = h;
   dt.min  = mi;
   return StructToTime(dt) + server_utc_offset_sec;
  }

//+------------------------------------------------------------------+
bool IdxLooksLikeUsIndex(const string symbol)
  {
   string u = symbol;
   StringToUpper(u);
   StringReplace(u, " ", "");
   StringReplace(u, "-", "");
   StringReplace(u, "/", "");
   return (StringFind(u, "US30")   >= 0 ||
           StringFind(u, "DJ30")   >= 0 ||
           StringFind(u, "DJIA")   >= 0 ||
           StringFind(u, "US100")  >= 0 ||
           StringFind(u, "NAS100") >= 0 ||
           StringFind(u, "USTEC")  >= 0 ||
           StringFind(u, "NASDAQ") >= 0 ||
           StringFind(u, "NDX")    >= 0 ||
           StringFind(u, "US500")  >= 0 ||
           StringFind(u, "SPX")    >= 0 ||
           StringFind(u, "SP500")  >= 0 ||
           StringFind(u, "US2000") >= 0);
  }

//+------------------------------------------------------------------+
double IdxSpreadPoints(const string symbol = NULL)
  {
   string sym = (symbol == NULL || symbol == "") ? _Symbol : symbol;
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double pt  = SymbolInfoDouble(sym, SYMBOL_POINT);
   if(ask <= 0.0 || bid <= 0.0 || pt <= 0.0)
      return 0.0;
   return (ask - bid) / pt;
  }

#endif // INDEX_SESSION_UTILS_MQH
//+------------------------------------------------------------------+

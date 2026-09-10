//+------------------------------------------------------------------+
//| GoldSessionUtils.mqh                                             |
//| Gold session clock (DST-safe London / NY metals / Tokyo)         |
//| Mirror of scripts/xau_session_scalp_core.py                      |
//|                                                                  |
//| NY metals is 08:00-17:00 ET — not US cash-index 09:30.           |
//| London OR starts 08:00 Europe/London.                            |
//| Risk family: xau_london_defined_r_be_flat_v1 — CLOSED / observe-only |
//| OR-width gate lives in GoldSessionScalp (not in this clock).     |
//| Not a live signal source. Do not retune the M5 scalp family.     |
//| Bar times are broker SERVER wall clocks. Convert via             |
//| TimeCurrent()-TimeGMT() (override with InpServerUtcOffsetHours). |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef GOLD_SESSION_UTILS_MQH
#define GOLD_SESSION_UTILS_MQH

enum ENUM_GLD_SESSION
  {
   GLD_SESSION_NONE      = 0,
   GLD_SESSION_TOKYO     = 1,
   GLD_SESSION_LONDON    = 2,
   GLD_SESSION_NY_METALS = 3,
   GLD_SESSION_OVERLAP   = 4
  };

enum ENUM_GLD_BOX
  {
   GLD_BOX_NONE   = 0,
   GLD_BOX_LONDON = 1,
   GLD_BOX_NY     = 2
  };

//+------------------------------------------------------------------+
int GldDaysInMonth(const int year, const int month)
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
int GldNthSunday(const int year, const int month, const int n)
  {
   MqlDateTime dt;
   ZeroMemory(dt);
   dt.year = year;
   dt.mon  = month;
   dt.day  = 1;
   dt.hour = 12;
   datetime t = StructToTime(dt);
   TimeToStruct(t, dt);
   int wd = dt.day_of_week;
   int first_sun = (wd == 0) ? 1 : (8 - wd);
   return first_sun + (n - 1) * 7;
  }

//+------------------------------------------------------------------+
int GldLastSunday(const int year, const int month)
  {
   MqlDateTime dt;
   ZeroMemory(dt);
   dt.year = year;
   dt.mon  = month;
   dt.day  = GldDaysInMonth(year, month);
   dt.hour = 12;
   datetime t = StructToTime(dt);
   TimeToStruct(t, dt);
   return dt.day - dt.day_of_week;
  }

//+------------------------------------------------------------------+
bool GldUsEasternDstUtc(const int y, const int m, const int d,
                        const int h, const int mi)
  {
   if(m < 3 || m > 11)
      return false;
   if(m > 3 && m < 11)
      return true;
   if(m == 3)
     {
      int start_d = GldNthSunday(y, 3, 2);
      if(d < start_d)
         return false;
      if(d > start_d)
         return true;
      return (h > 7 || (h == 7 && mi >= 0));
     }
   int end_d = GldNthSunday(y, 11, 1);
   if(d < end_d)
      return true;
   if(d > end_d)
      return false;
   return (h < 6);
  }

//+------------------------------------------------------------------+
bool GldUkDstUtc(const int y, const int m, const int d,
                 const int h, const int mi)
  {
   if(m < 3 || m > 10)
      return false;
   if(m > 3 && m < 10)
      return true;
   if(m == 3)
     {
      int start_d = GldLastSunday(y, 3);
      if(d < start_d)
         return false;
      if(d > start_d)
         return true;
      return (h >= 1);
     }
   int end_d = GldLastSunday(y, 10);
   if(d < end_d)
      return true;
   if(d > end_d)
      return false;
   return (h < 1);
  }

//+------------------------------------------------------------------+
int GldDetectServerUtcOffsetSec(const int override_hours)
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
void GldUtcWallOfBar(const datetime bar_server, const int server_utc_offset_sec,
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
void GldEtOfBar(const datetime bar_server, const int server_utc_offset_sec,
                MqlDateTime &et)
  {
   int y, m, d, h, mi;
   GldUtcWallOfBar(bar_server, server_utc_offset_sec, y, m, d, h, mi);
   int et_off_h = GldUsEasternDstUtc(y, m, d, h, mi) ? -4 : -5;
   datetime utc_as_dt = bar_server - server_utc_offset_sec;
   datetime et_as_dt  = utc_as_dt + et_off_h * 3600;
   TimeToStruct(et_as_dt, et);
  }

//+------------------------------------------------------------------+
void GldLondonOfBar(const datetime bar_server, const int server_utc_offset_sec,
                    MqlDateTime &lon)
  {
   int y, m, d, h, mi;
   GldUtcWallOfBar(bar_server, server_utc_offset_sec, y, m, d, h, mi);
   int lon_off_h = GldUkDstUtc(y, m, d, h, mi) ? 1 : 0;
   datetime utc_as_dt = bar_server - server_utc_offset_sec;
   datetime lon_as_dt = utc_as_dt + lon_off_h * 3600;
   TimeToStruct(lon_as_dt, lon);
  }

//+------------------------------------------------------------------+
void GldTokyoOfBar(const datetime bar_server, const int server_utc_offset_sec,
                   MqlDateTime &tyo)
  {
   datetime utc_as_dt = bar_server - server_utc_offset_sec;
   datetime tyo_as_dt = utc_as_dt + 9 * 3600;
   TimeToStruct(tyo_as_dt, tyo);
  }

//+------------------------------------------------------------------+
bool GldInHm(const int hour, const int minute,
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
bool GldIsNyMetals(const MqlDateTime &et)
  {
   return GldInHm(et.hour, et.min, 8, 0, 17, 0);
  }

//+------------------------------------------------------------------+
bool GldIsLondonOpen(const MqlDateTime &lon)
  {
   return GldInHm(lon.hour, lon.min, 8, 0, 17, 0);
  }

//+------------------------------------------------------------------+
bool GldIsTokyoOpen(const MqlDateTime &tyo)
  {
   return GldInHm(tyo.hour, tyo.min, 9, 0, 18, 0);
  }

//+------------------------------------------------------------------+
ENUM_GLD_SESSION GldDetectSession(const datetime bar_server,
                                  const int server_utc_offset_sec)
  {
   MqlDateTime et, lon, tyo;
   GldEtOfBar(bar_server, server_utc_offset_sec, et);
   GldLondonOfBar(bar_server, server_utc_offset_sec, lon);
   GldTokyoOfBar(bar_server, server_utc_offset_sec, tyo);
   bool ny  = GldIsNyMetals(et);
   bool ldn = GldIsLondonOpen(lon);
   if(ny && ldn)
      return GLD_SESSION_OVERLAP;
   if(ny)
      return GLD_SESSION_NY_METALS;
   if(ldn)
      return GLD_SESSION_LONDON;
   if(GldIsTokyoOpen(tyo))
      return GLD_SESSION_TOKYO;
   return GLD_SESSION_NONE;
  }

//+------------------------------------------------------------------+
string GldSessionName(const ENUM_GLD_SESSION s)
  {
   switch(s)
     {
      case GLD_SESSION_TOKYO:     return "Tokyo";
      case GLD_SESSION_LONDON:    return "London";
      case GLD_SESSION_NY_METALS: return "NY metals";
      case GLD_SESSION_OVERLAP:   return "LDN+NY";
      default:                    return "Off";
     }
  }

//+------------------------------------------------------------------+
bool GldInLondonOrWindow(const MqlDateTime &lon, const int or_minutes)
  {
   int start = 8 * 60;
   int end   = start + or_minutes;
   int t     = lon.hour * 60 + lon.min;
   return (t >= start && t < end);
  }

//+------------------------------------------------------------------+
bool GldLondonOrComplete(const MqlDateTime &lon, const int or_minutes)
  {
   int t   = lon.hour * 60 + lon.min;
   int end = 8 * 60 + or_minutes;
   return (t >= end);
  }

//+------------------------------------------------------------------+
bool GldInLondonEntry(const MqlDateTime &lon, const int or_minutes,
                      const int end_h = 11, const int end_m = 0)
  {
   int t     = lon.hour * 60 + lon.min;
   int start = 8 * 60 + or_minutes;
   int end   = end_h * 60 + end_m;
   return (t >= start && t < end);
  }

//+------------------------------------------------------------------+
bool GldInNyEntry(const MqlDateTime &et,
                  const int start_h = 8, const int start_m = 0,
                  const int end_h = 11, const int end_m = 0)
  {
   return GldInHm(et.hour, et.min, start_h, start_m, end_h, end_m);
  }

//+------------------------------------------------------------------+
ENUM_GLD_BOX GldSessionBox(const MqlDateTime &lon, const MqlDateTime &et,
                           const int or_minutes, const bool allow_ny)
  {
   if(GldInLondonEntry(lon, or_minutes))
      return GLD_BOX_LONDON;
   if(allow_ny && GldInNyEntry(et))
      return GLD_BOX_NY;
   return GLD_BOX_NONE;
  }

//+------------------------------------------------------------------+
bool GldFridayCutoff(const MqlDateTime &et)
  {
   if(et.day_of_week != 5)
      return false;
   return (et.hour * 60 + et.min) >= (14 * 60);
  }

//+------------------------------------------------------------------+
int GldYmdKey(const MqlDateTime &dt)
  {
   return dt.year * 10000 + dt.mon * 100 + dt.day;
  }

//+------------------------------------------------------------------+
int GldBoxKey(const ENUM_GLD_BOX box, const MqlDateTime &lon, const MqlDateTime &et)
  {
   if(box == GLD_BOX_LONDON)
      return 100000000 + GldYmdKey(lon);
   if(box == GLD_BOX_NY)
      return 200000000 + GldYmdKey(et);
   return 0;
  }

//+------------------------------------------------------------------+
void GldAddHoursToYmdhm(int &y, int &m, int &d, int &h, const int add_h)
  {
   h += add_h;
   while(h >= 24)
     {
      h -= 24;
      d += 1;
      if(d > GldDaysInMonth(y, m))
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
datetime GldEtWallToServer(const int y0, const int m0, const int d0,
                           const int h0, const int mi,
                           const int server_utc_offset_sec)
  {
   int uy = y0, um = m0, ud = d0, uh = h0;
   GldAddHoursToYmdhm(uy, um, ud, uh, 5);
   bool dst = GldUsEasternDstUtc(uy, um, ud, uh, mi);
   int add_h = dst ? 4 : 5;
   int y = y0, m = m0, d = d0, h = h0;
   GldAddHoursToYmdhm(y, m, d, h, add_h);
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
datetime GldLondonWallToServer(const int y0, const int m0, const int d0,
                               const int h0, const int mi,
                               const int server_utc_offset_sec)
  {
   // Probe GMT (UTC+0) then apply UK DST.
   bool dst = GldUkDstUtc(y0, m0, d0, h0, mi);
   int add_h = dst ? -1 : 0;
   int y = y0, m = m0, d = d0, h = h0;
   GldAddHoursToYmdhm(y, m, d, h, add_h);
   // If we crossed the spring-forward hour, re-evaluate.
   if(!dst && GldUkDstUtc(y, m, d, h, mi))
      GldAddHoursToYmdhm(y, m, d, h, -1);
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
bool GldLooksLikeGold(const string symbol)
  {
   string u = symbol;
   StringToUpper(u);
   StringReplace(u, " ", "");
   StringReplace(u, "-", "");
   StringReplace(u, "/", "");
   StringReplace(u, ".", "");
   StringReplace(u, "_", "");
   return (StringFind(u, "XAU") >= 0 || StringFind(u, "GOLD") >= 0);
  }

//+------------------------------------------------------------------+
double GldSpreadPoints(const string symbol = NULL)
  {
   string sym = (symbol == NULL || symbol == "") ? _Symbol : symbol;
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double pt  = SymbolInfoDouble(sym, SYMBOL_POINT);
   if(ask <= 0.0 || bid <= 0.0 || pt <= 0.0)
      return 0.0;
   return (ask - bid) / pt;
  }

//+------------------------------------------------------------------+
double GldEffectiveMaxSpread(const double inp_max)
  {
   if(inp_max > 0.0)
      return inp_max;
   return 40.0; // gold points (0.01 quote); hostile vs typical 16-21 STP
  }

#endif // GOLD_SESSION_UTILS_MQH
//+------------------------------------------------------------------+

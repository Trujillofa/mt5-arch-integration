//+------------------------------------------------------------------+
//| ExportSymbolSyncAudit.mq5                                        |
//| Read-only H1 calendar / spread sync audit. No OrderSend.         |
//|                                                                  |
//| Writes MQL5/Files/mt5_arch/sync_audit/<broker>_<epoch>/          |
//|   manifest.json                                                  |
//|                                                                  |
//| InpBroker is required (vantage|fpmarkets|exness|wsf).            |
//| Resolution is the explicit registry — no suffix walk.            |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property version     "1.00"
#property description "Export H1 symbol sync audit — no orders"
#property script_show_inputs
#property strict

#include <FxSymbolRegistry.mqh>

input string InpBroker  = "";
input string InpSymbols = "EURUSD,GBPUSD,USDJPY,USDCHF,XAUUSD,BTCUSD";
input int    InpMaxBars = 50000;
input string InpOutDir  = "mt5_arch\\sync_audit";

#define AUDIT_MAX_SYM 16

datetime g_all[];
int      g_start[AUDIT_MAX_SYM];
int      g_count[AUDIT_MAX_SYM];
int      g_nsym = 0;

string JsonEsc(const string s)
  {
   string o = s;
   StringReplace(o, "\\", "\\\\");
   StringReplace(o, "\"", "\\\"");
   return o;
  }

bool SortedHas(const datetime &arr[], const int start, const int n, const datetime t)
  {
   int lo = 0;
   int hi = n - 1;
   while(lo <= hi)
     {
      int mid = (lo + hi) / 2;
      datetime v = arr[start + mid];
      if(v == t)
         return true;
      if(v < t)
         lo = mid + 1;
      else
         hi = mid - 1;
     }
   return false;
  }

void OnStart()
  {
   string broker = InpBroker;
   StringTrimLeft(broker);
   StringTrimRight(broker);
   StringToLower(broker);
   if(StringLen(broker) == 0)
     {
      Print("ExportSymbolSyncAudit: FAIL InpBroker is required");
      return;
     }

   string parts[];
   int n = StringSplit(InpSymbols, ',', parts);
   if(n <= 0)
     {
      Print("ExportSymbolSyncAudit: FAIL empty InpSymbols");
      return;
     }

   datetime now = TimeCurrent();
   string tag = broker + "_" + IntegerToString((int)now);
   string dir = InpOutDir + "\\" + tag;
   FolderCreate("mt5_arch");
   FolderCreate(InpOutDir);
   if(!FolderCreate(dir))
      Print("ExportSymbolSyncAudit: FolderCreate ", dir,
            " err=", GetLastError(), " (ok if exists)");

   string man = dir + "\\manifest.json";
   int hm = FileOpen(man, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(hm == INVALID_HANDLE)
     {
      Print("manifest.json open fail err=", GetLastError());
      return;
     }

   FileWriteString(hm, "{\n");
   FileWriteString(hm, "  \"schema\": \"mt5-symbol-sync-audit/v1\",\n");
   FileWriteString(hm, "  \"source\": \"mql5_export\",\n");
   FileWriteString(hm, "  \"export_ok\": true,\n");
   FileWriteString(hm, "  \"broker\": \"" + JsonEsc(broker) + "\",\n");
   FileWriteString(hm, "  \"registry_schema\": \"" + FX_SYMBOL_REGISTRY_SCHEMA + "\",\n");
   FileWriteString(hm, "  \"timeframe\": \"H1\",\n");
   FileWriteString(hm, "  \"server_time\": \"" +
                  TimeToString(now, TIME_DATE | TIME_SECONDS) + "\",\n");
   FileWriteString(hm, "  \"time_current\": " + IntegerToString((long)now) + ",\n");
   FileWriteString(hm, "  \"symbols\": [\n");

   int wrote = 0;
   datetime window_first = 0;
   datetime window_last = 0;
   bool have_window = false;
   int max_bars = MathMax(1, InpMaxBars);

   for(int i = 0; i < n; i++)
     {
      string requested = parts[i];
      StringTrimLeft(requested);
      StringTrimRight(requested);
      if(StringLen(requested) == 0)
         continue;
      string canonical = "";
      string mapped = "";
      bool in_reg = FxRegistryLookup(broker, requested, canonical, mapped);
      string resolved = "";
      if(in_reg)
         resolved = FxResolveSymbol(broker, requested);

      MqlRates rates[];
      ArraySetAsSeries(rates, false);
      int bars = 0;
      datetime first_t = 0, last_t = 0;
      int n_spread = 0;
      int n_missing = 0;
      string miss_sample = "";
      int miss_kept = 0;
      bool last_forming = false;
      if(StringLen(resolved) > 0)
        {
         bars = CopyRates(resolved, PERIOD_H1, 0, max_bars, rates);
         if(bars > 0)
           {
            first_t = rates[0].time;
            last_t  = rates[bars - 1].time;
            last_forming = ((long)last_t + PeriodSeconds(PERIOD_H1) > (long)now);
            for(int k = 0; k < bars; k++)
              {
               if(rates[k].spread > 0)
                  n_spread++;
              }
            for(datetime t = first_t; t <= last_t; t += 3600)
              {
               bool found = false;
               int lo = 0, hi = bars - 1;
               while(lo <= hi)
                 {
                  int mid = (lo + hi) / 2;
                  if(rates[mid].time == t)
                    {
                     found = true;
                     break;
                    }
                  if(rates[mid].time < t)
                     lo = mid + 1;
                  else
                     hi = mid - 1;
                 }
               if(!found)
                 {
                  n_missing++;
                  if(miss_kept < 8)
                    {
                     if(miss_kept > 0)
                        miss_sample += ", ";
                     miss_sample += "\"" + TimeToString(t, TIME_DATE | TIME_SECONDS) + "\"";
                     miss_kept++;
                    }
                 }
              }
            if(g_nsym < AUDIT_MAX_SYM)
              {
               int closed = bars;
               if(last_forming && closed > 0)
                  closed--;
               int base = ArraySize(g_all);
               if(ArrayResize(g_all, base + closed) >= 0)
                 {
                  for(int k = 0; k < closed; k++)
                     g_all[base + k] = rates[k].time;
                  g_start[g_nsym] = base;
                  g_count[g_nsym] = closed;
                  g_nsym++;
                 }
              }
            if(!have_window)
              {
               window_first = first_t;
               window_last = last_t;
               have_window = true;
              }
            else
              {
               if(first_t > window_first)
                  window_first = first_t;
               if(last_t < window_last)
                  window_last = last_t;
              }
           }
        }

      bool selected = (StringLen(resolved) > 0);
      bool ok = in_reg && selected && bars >= 1;
      string err = "";
      if(!in_reg)
         err = "not_in_registry";
      else if(!selected)
         err = "symbol_select_failed";
      else if(!ok)
         err = "history_incomplete";

      if(wrote > 0)
         FileWriteString(hm, ",\n");
      FileWriteString(hm, "    {\n");
      FileWriteString(hm, "      \"canonical\": \"" + JsonEsc(in_reg ? canonical : requested) + "\",\n");
      FileWriteString(hm, "      \"requested\": \"" + JsonEsc(requested) + "\",\n");
      FileWriteString(hm, "      \"broker_symbol\": \"" + JsonEsc(mapped) + "\",\n");
      FileWriteString(hm, "      \"resolved\": \"" + JsonEsc(resolved) + "\",\n");
      FileWriteString(hm, "      \"selected\": " + (selected ? "true" : "false") + ",\n");
      FileWriteString(hm, "      \"sync_mode\": " +
                     IntegerToString(selected ? (int)SymbolInfoInteger(resolved, SYMBOL_SELECT) : 0) + ",\n");
      FileWriteString(hm, "      \"bars_h1\": " + IntegerToString(MathMax(0, bars)) + ",\n");
      FileWriteString(hm, "      \"closed_bars_h1\": " +
                     IntegerToString(MathMax(0, bars - (last_forming ? 1 : 0))) + ",\n");
      FileWriteString(hm, "      \"first_time\": \"" +
                     (first_t > 0 ? TimeToString(first_t, TIME_DATE | TIME_SECONDS) : "") + "\",\n");
      FileWriteString(hm, "      \"last_time\": \"" +
                     (last_t > 0 ? TimeToString(last_t, TIME_DATE | TIME_SECONDS) : "") + "\",\n");
      FileWriteString(hm, "      \"last_forming\": " + (last_forming ? "true" : "false") + ",\n");
      FileWriteString(hm, "      \"n_spread_positive\": " + IntegerToString(n_spread) + ",\n");
      FileWriteString(hm, "      \"n_missing_vs_hourly\": " + IntegerToString(n_missing) + ",\n");
      FileWriteString(hm, "      \"missing_sample\": [" + miss_sample + "],\n");
      FileWriteString(hm, "      \"timestamps\": [");
      for(int k = 0; k < bars; k++)
        {
         if(k > 0)
            FileWriteString(hm, ",");
         FileWriteString(hm, IntegerToString((long)rates[k].time));
        }
      FileWriteString(hm, "],\n");
      FileWriteString(hm, "      \"ok\": " + (ok ? "true" : "false") + ",\n");
      FileWriteString(hm, "      \"error\": \"" + JsonEsc(err) + "\"\n");
      FileWriteString(hm, "    }");
      wrote++;
     }

   int n_inter = 0;
   datetime inter_first = 0, inter_last = 0;
   if(g_nsym > 0)
     {
      int short_i = 0;
      for(int s = 1; s < g_nsym; s++)
        {
         if(g_count[s] < g_count[short_i])
            short_i = s;
        }
      for(int k = 0; k < g_count[short_i]; k++)
        {
         datetime t = g_all[g_start[short_i] + k];
         bool all_have = true;
         for(int s = 0; s < g_nsym; s++)
           {
            if(s == short_i)
               continue;
            if(!SortedHas(g_all, g_start[s], g_count[s], t))
              {
               all_have = false;
               break;
              }
           }
         if(all_have)
           {
            if(n_inter == 0)
               inter_first = t;
            inter_last = t;
            n_inter++;
           }
        }
     }

   FileWriteString(hm, "\n  ],\n");
   FileWriteString(hm, "  \"joint\": {\n");
   FileWriteString(hm, "    \"window_first\": \"" +
                  (have_window ? TimeToString(window_first, TIME_DATE | TIME_SECONDS) : "") + "\",\n");
   FileWriteString(hm, "    \"window_last\": \"" +
                  (have_window ? TimeToString(window_last, TIME_DATE | TIME_SECONDS) : "") + "\",\n");
   FileWriteString(hm, "    \"first_time\": \"" +
                  (n_inter > 0 ? TimeToString(inter_first, TIME_DATE | TIME_SECONDS) : "") + "\",\n");
   FileWriteString(hm, "    \"last_time\": \"" +
                  (n_inter > 0 ? TimeToString(inter_last, TIME_DATE | TIME_SECONDS) : "") + "\",\n");
   FileWriteString(hm, "    \"n_intersection_timestamps\": " + IntegerToString(n_inter) + "\n");
   FileWriteString(hm, "  }\n");
   FileWriteString(hm, "}\n");
   FileClose(hm);
   Print("ExportSymbolSyncAudit: wrote MQL5/Files/", dir,
         " broker=", broker, " symbols=", wrote,
         " intersection=", n_inter, " NO ORDERS");
  }
//+------------------------------------------------------------------+

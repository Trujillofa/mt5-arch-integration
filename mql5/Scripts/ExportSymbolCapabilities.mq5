//+------------------------------------------------------------------+
//| ExportSymbolCapabilities.mq5                                     |
//| Read-only broker-symbol capability dump. No OrderSend.           |
//|                                                                  |
//| Writes MQL5/Files/mt5_arch/capabilities/<broker>_<epoch>/        |
//|   manifest.json                                                  |
//|                                                                  |
//| InpBroker is required (vantage|fpmarkets|exness|wsf).            |
//| Resolution is the explicit registry — no suffix walk.            |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property version     "1.00"
#property description "Export symbol capabilities — no orders"
#property script_show_inputs
#property strict

#include <FxSymbolRegistry.mqh>

input string InpBroker  = "";
input string InpSymbols = "EURUSD,GBPUSD,USDJPY,USDCHF,XAUUSD,BTCUSD";
input int    InpMinBars = 1;
input string InpOutDir  = "mt5_arch\\capabilities";

string JsonEsc(const string s)
  {
   string o = s;
   StringReplace(o, "\\", "\\\\");
   StringReplace(o, "\"", "\\\"");
   return o;
  }

string TradeModeName(const long mode)
  {
   if(mode == SYMBOL_TRADE_MODE_DISABLED)  return "DISABLED";
   if(mode == SYMBOL_TRADE_MODE_LONGONLY)  return "LONGONLY";
   if(mode == SYMBOL_TRADE_MODE_SHORTONLY) return "SHORTONLY";
   if(mode == SYMBOL_TRADE_MODE_CLOSEONLY) return "CLOSEONLY";
   if(mode == SYMBOL_TRADE_MODE_FULL)      return "FULL";
   return "UNKNOWN";
  }

void OnStart()
  {
   string broker = InpBroker;
   StringTrimLeft(broker);
   StringTrimRight(broker);
   StringToLower(broker);
   if(StringLen(broker) == 0)
     {
      Print("ExportSymbolCapabilities: FAIL InpBroker is required");
      return;
     }

   string parts[];
   int n = StringSplit(InpSymbols, ',', parts);
   if(n <= 0)
     {
      Print("ExportSymbolCapabilities: FAIL empty InpSymbols");
      return;
     }

   string tag = broker + "_" + IntegerToString((int)TimeCurrent());
   string dir = InpOutDir + "\\" + tag;
   FolderCreate("mt5_arch");
   FolderCreate(InpOutDir);
   if(!FolderCreate(dir))
      Print("ExportSymbolCapabilities: FolderCreate ", dir,
            " err=", GetLastError(), " (ok if exists)");

   string man = dir + "\\manifest.json";
   int hm = FileOpen(man, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(hm == INVALID_HANDLE)
     {
      Print("manifest.json open fail err=", GetLastError());
      return;
     }

   FileWriteString(hm, "{\n");
   FileWriteString(hm, "  \"schema\": \"mt5-symbol-capabilities/v1\",\n");
   FileWriteString(hm, "  \"source\": \"mql5_export\",\n");
   FileWriteString(hm, "  \"export_ok\": true,\n");
   FileWriteString(hm, "  \"broker\": \"" + JsonEsc(broker) + "\",\n");
   FileWriteString(hm, "  \"registry_schema\": \"" + FX_SYMBOL_REGISTRY_SCHEMA + "\",\n");
   FileWriteString(hm, "  \"server_time\": \"" +
                  TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + "\",\n");
   FileWriteString(hm, "  \"symbols\": [\n");

   int wrote = 0;
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
      if(StringLen(resolved) > 0)
        {
         bars = CopyRates(resolved, PERIOD_H1, 0, 32, rates);
         if(bars > 0)
           {
            first_t = rates[0].time;
            last_t  = rates[bars - 1].time;
           }
        }

      bool selected = (StringLen(resolved) > 0);
      int digits = selected ? (int)SymbolInfoInteger(resolved, SYMBOL_DIGITS) : 0;
      double point = selected ? SymbolInfoDouble(resolved, SYMBOL_POINT) : 0.0;
      double contract = selected ? SymbolInfoDouble(resolved, SYMBOL_TRADE_CONTRACT_SIZE) : 0.0;
      long mode = selected ? SymbolInfoInteger(resolved, SYMBOL_TRADE_MODE) : -1;
      bool ok = in_reg && selected && digits > 0 && point > 0.0 &&
                contract > 0.0 && bars >= InpMinBars;
      string err = "";
      if(!in_reg)
         err = "not_in_registry";
      else if(!selected)
         err = "symbol_select_failed";
      else if(!ok)
         err = "capability_incomplete";

      if(wrote > 0)
         FileWriteString(hm, ",\n");
      FileWriteString(hm, "    {\n");
      FileWriteString(hm, "      \"canonical\": \"" + JsonEsc(in_reg ? canonical : requested) + "\",\n");
      FileWriteString(hm, "      \"requested\": \"" + JsonEsc(requested) + "\",\n");
      FileWriteString(hm, "      \"broker_symbol\": \"" + JsonEsc(mapped) + "\",\n");
      FileWriteString(hm, "      \"resolved\": \"" + JsonEsc(resolved) + "\",\n");
      FileWriteString(hm, "      \"selected\": " + (selected ? "true" : "false") + ",\n");
      FileWriteString(hm, "      \"digits\": " + IntegerToString(digits) + ",\n");
      FileWriteString(hm, "      \"point\": " + DoubleToString(point, 8) + ",\n");
      FileWriteString(hm, "      \"contract_size\": " + DoubleToString(contract, 2) + ",\n");
      FileWriteString(hm, "      \"min_lot\": " +
                     DoubleToString(selected ? SymbolInfoDouble(resolved, SYMBOL_VOLUME_MIN) : 0, 4) + ",\n");
      FileWriteString(hm, "      \"max_lot\": " +
                     DoubleToString(selected ? SymbolInfoDouble(resolved, SYMBOL_VOLUME_MAX) : 0, 4) + ",\n");
      FileWriteString(hm, "      \"lot_step\": " +
                     DoubleToString(selected ? SymbolInfoDouble(resolved, SYMBOL_VOLUME_STEP) : 0, 4) + ",\n");
      FileWriteString(hm, "      \"trade_mode\": " + IntegerToString((int)mode) + ",\n");
      FileWriteString(hm, "      \"trade_mode_name\": \"" + TradeModeName(mode) + "\",\n");
      FileWriteString(hm, "      \"bars_h1\": " + IntegerToString(MathMax(0, bars)) + ",\n");
      FileWriteString(hm, "      \"first_time\": \"" +
                     (first_t > 0 ? TimeToString(first_t, TIME_DATE | TIME_SECONDS) : "") + "\",\n");
      FileWriteString(hm, "      \"last_time\": \"" +
                     (last_t > 0 ? TimeToString(last_t, TIME_DATE | TIME_SECONDS) : "") + "\",\n");
      FileWriteString(hm, "      \"ok\": " + (ok ? "true" : "false") + ",\n");
      FileWriteString(hm, "      \"error\": \"" + JsonEsc(err) + "\"\n");
      FileWriteString(hm, "    }");
      wrote++;
     }

   FileWriteString(hm, "\n  ]\n");
   FileWriteString(hm, "}\n");
   FileClose(hm);
   Print("ExportSymbolCapabilities: wrote MQL5/Files/", dir,
         " broker=", broker, " symbols=", wrote, " NO ORDERS");
  }
//+------------------------------------------------------------------+

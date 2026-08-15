//+------------------------------------------------------------------+
//| FxSymbolRegistry.mqh                                             |
//| GENERATED from config/symbols/registry.json — do not hand-edit.  |
//| python3 -c "from mt5_arch.symbol_registry import write_mql5_include; write_mql5_include()"
//| Explicit maps only. No suffix walk. No first-match. No OrderSend.|
//+------------------------------------------------------------------+
#ifndef FX_SYMBOL_REGISTRY_MQH
#define FX_SYMBOL_REGISTRY_MQH

#define FX_SYMBOL_REGISTRY_SCHEMA "mt5-symbol-registry/v1"

void FxRegNormBroker(string &s)
  {
   StringTrimLeft(s);
   StringTrimRight(s);
   StringToLower(s);
  }

void FxRegNormSymbol(string &s)
  {
   StringTrimLeft(s);
   StringTrimRight(s);
   StringToUpper(s);
  }

bool FxRegistryLookup(const string broker, const string requested,
                      string &canonical, string &broker_symbol)
  {
   string b = broker;
   string r = requested;
   FxRegNormBroker(b);
   FxRegNormSymbol(r);
   if(StringLen(b) == 0 || StringLen(r) == 0)
      return false;
   if(b == "exness")
     {
      if(r == "XAUUSD" || r == "XAUUSDM")
        {
         canonical = "XAUUSD";
         broker_symbol = "XAUUSDm";
         return true;
        }
      return false;
     }
   if(b == "fpmarkets")
     {
      if(r == "EURUSD" || r == "EURUSD")
        {
         canonical = "EURUSD";
         broker_symbol = "EURUSD";
         return true;
        }
      if(r == "GBPUSD" || r == "GBPUSD")
        {
         canonical = "GBPUSD";
         broker_symbol = "GBPUSD";
         return true;
        }
      if(r == "USDJPY" || r == "USDJPY")
        {
         canonical = "USDJPY";
         broker_symbol = "USDJPY";
         return true;
        }
      if(r == "USDCHF" || r == "USDCHF")
        {
         canonical = "USDCHF";
         broker_symbol = "USDCHF";
         return true;
        }
      if(r == "XAUUSD" || r == "XAUUSD.R")
        {
         canonical = "XAUUSD";
         broker_symbol = "XAUUSD.r";
         return true;
        }
      if(r == "BTCUSD" || r == "BTCUSD")
        {
         canonical = "BTCUSD";
         broker_symbol = "BTCUSD";
         return true;
        }
      return false;
     }
   if(b == "vantage")
     {
      if(r == "EURUSD" || r == "EURUSD")
        {
         canonical = "EURUSD";
         broker_symbol = "EURUSD";
         return true;
        }
      if(r == "GBPUSD" || r == "GBPUSD")
        {
         canonical = "GBPUSD";
         broker_symbol = "GBPUSD";
         return true;
        }
      if(r == "USDJPY" || r == "USDJPY")
        {
         canonical = "USDJPY";
         broker_symbol = "USDJPY";
         return true;
        }
      if(r == "USDCHF" || r == "USDCHF")
        {
         canonical = "USDCHF";
         broker_symbol = "USDCHF";
         return true;
        }
      if(r == "XAUUSD" || r == "XAUUSD")
        {
         canonical = "XAUUSD";
         broker_symbol = "XAUUSD";
         return true;
        }
      if(r == "BTCUSD" || r == "BTCUSD")
        {
         canonical = "BTCUSD";
         broker_symbol = "BTCUSD";
         return true;
        }
      return false;
     }
   return false;
  }

string FxResolveSymbol(const string broker, const string requested)
  {
   string canonical = "";
   string broker_symbol = "";
   if(!FxRegistryLookup(broker, requested, canonical, broker_symbol))
      return "";
   if(!SymbolSelect(broker_symbol, true))
      return "";
   return broker_symbol;
  }

string FxCanonicalFromBrokerSymbol(const string broker, const string broker_symbol)
  {
   string canonical = "";
   string mapped = "";
   if(!FxRegistryLookup(broker, broker_symbol, canonical, mapped))
      return "";
   return canonical;
  }

string FxCanonicalFromBrokerSymbolAny(const string broker_symbol)
  {
   string r = broker_symbol;
   FxRegNormSymbol(r);
   string hit = "";
   int n = 0;
   if(r == "BTCUSD")
     {
      hit = "BTCUSD";
      n++;
     }
   if(r == "EURUSD")
     {
      hit = "EURUSD";
      n++;
     }
   if(r == "GBPUSD")
     {
      hit = "GBPUSD";
      n++;
     }
   if(r == "USDCHF")
     {
      hit = "USDCHF";
      n++;
     }
   if(r == "USDJPY")
     {
      hit = "USDJPY";
      n++;
     }
   if(r == "XAUUSD")
     {
      hit = "XAUUSD";
      n++;
     }
   if(r == "XAUUSD.R")
     {
      hit = "XAUUSD";
      n++;
     }
   if(r == "XAUUSDM")
     {
      hit = "XAUUSD";
      n++;
     }
   if(n != 1)
      return "";
   return hit;
  }

#endif // FX_SYMBOL_REGISTRY_MQH

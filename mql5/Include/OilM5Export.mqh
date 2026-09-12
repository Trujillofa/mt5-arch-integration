//+------------------------------------------------------------------+
//| OilM5Export.mqh                                                  |
//| Dump XTIUSD / USOUSD M5 + spread for the offline oil scalp.      |
//| Trigger: MQL5/Files/mt5_arch/export_oil.request                  |
//| Reuses IdxExportSymbolM5 (same CSV schema). Never OrderSend.     |
//| Does not kill the terminal.                                      |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef OIL_M5_EXPORT_MQH
#define OIL_M5_EXPORT_MQH

#include <IndexM5Export.mqh>
#include <OilSessionUtils.mqh>

//+------------------------------------------------------------------+
int OilExportM5Now()
  {
   int offset = IdxDetectServerUtcOffsetSec(-99);
   string want = "CL-OIL,USOUSD,XTIUSD,USOIL,USOIL.pro";
   string parts[];
   int n = StringSplit(want, ',', parts);
   int done = 0;
   for(int i = 0; i < n; i++)
     {
      string req = parts[i];
      StringTrimLeft(req);
      StringTrimRight(req);
      if(StringLen(req) == 0)
         continue;
      if(!SymbolSelect(req, true) && req != _Symbol)
         continue;
      string resolved = SymbolSelect(req, true) ? req : _Symbol;
      if(IdxExportSymbolM5(resolved, "XTIUSD", offset))
         done++;
     }
   if(OilLooksLikeOil(_Symbol) && done == 0)
     {
      if(IdxExportSymbolM5(_Symbol, "XTIUSD", offset))
         done++;
     }
   return done;
  }

//+------------------------------------------------------------------+
void OilExportM5IfRequested()
  {
   string req = "mt5_arch\\export_oil.request";
   if(!FileIsExist(req))
      return;
   Print("OilExportM5IfRequested: request seen");
   int done = OilExportM5Now();
   FileDelete(req);
   int h = FileOpen("mt5_arch\\export_oil.done", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h != INVALID_HANDLE)
     {
      FileWriteString(h, IntegerToString(done) + "\n");
      FileClose(h);
     }
   Print("OilExportM5IfRequested: done=", done);
  }

#endif

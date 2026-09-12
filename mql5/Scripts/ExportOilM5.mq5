//+------------------------------------------------------------------+
//| ExportOilM5.mq5                                                  |
//| Live-safe USOUSD / XTIUSD M5 dump. Does not shut the terminal.   |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property version   "1.00"
#property script_show_inputs false
#property script_show_confirm false

#include <OilM5Export.mqh>

void OnStart()
  {
   int done = OilExportM5Now();
   Print("ExportOilM5 finished symbols=", done);
  }
//+------------------------------------------------------------------+

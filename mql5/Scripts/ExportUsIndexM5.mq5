//+------------------------------------------------------------------+
//| ExportUsIndexM5.mq5                                              |
//| Live-safe US100/US30 M5 dump. Does not shut the terminal down.   |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property version   "1.00"
#property script_show_inputs false
#property script_show_confirm false

#include <IndexM5Export.mqh>

void OnStart()
  {
   int done = IdxExportUsIndexM5Now();
   Print("ExportUsIndexM5 finished symbols=", done);
  }
//+------------------------------------------------------------------+

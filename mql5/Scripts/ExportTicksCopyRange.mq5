//+------------------------------------------------------------------+
//| ExportTicksCopyRange.mq5                                         |
//| Live-safe CopyTicksRange dump. Does not shut the terminal down.  |
//| Never OrderSend. Not a tester EA.                                |
//|                                                                  |
//| Request (optional): MQL5/Files/mt5_arch/export_ticks.request     |
//|   symbol=BTCUSD                                                  |
//|   hours=36                                                       |
//|   broker=fpmarkets                                               |
//| Window is clamped to 24–48h. CSV columns match tick_cvd_core.py. |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property version   "1.00"
#property description "CopyTicksRange dump — no orders, does not kill terminal"
#property script_show_inputs false
#property script_show_confirm false

#include <TickCopyRangeExport.mqh>

void OnStart()
  {
   int n = TickExportCopyRangeNow();
   Print("ExportTicksCopyRange finished ticks=", n);
  }
//+------------------------------------------------------------------+

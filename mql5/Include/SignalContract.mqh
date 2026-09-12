//+------------------------------------------------------------------+
//| SignalContract.mqh                                               |
//| Single source of truth for overlay iCustom SIGNAL buffer indices |
//|                                                                  |
//| In-scope: UIS, BNS, HTFFIB, BTP, FXIT. GoldSessionScalp excluded.|
//| Do not change a define without moving that file's SetIndexBuffer.|
//| MQL5 has no #if/#error — overlays pin *_SIGNAL_BUFFER in OnInit.|
//| ForexSignalLogger keeps InpSignalBuffer as an input so existing  |
//| .set files keep working (default stays HTFFIB=8).                |
//+------------------------------------------------------------------+
#property copyright "mt5-arch-integration"
#property strict

#ifndef SIGNAL_CONTRACT_MQH
#define SIGNAL_CONTRACT_MQH

#define UIS_SHORTNAME     "UsIndexSessionScalp"
#define BNS_SHORTNAME     "BtcNySessionScalp"
#define HTFFIB_SHORTNAME  "ForexHtfPivotsFib"
#define BTP_SHORTNAME     "BtcTrendPullback"
#define FXIT_SHORTNAME    "ForexIndicatorTemplate"

#define UIS_SIGNAL_BUFFER     8
#define BNS_SIGNAL_BUFFER     8
#define HTFFIB_SIGNAL_BUFFER  8
#define BTP_SIGNAL_BUFFER     7
#define FXIT_SIGNAL_BUFFER    9

//+------------------------------------------------------------------+
int SignalContractBufferFor(const string name)
  {
   if(name == UIS_SHORTNAME)
      return UIS_SIGNAL_BUFFER;
   if(name == BNS_SHORTNAME)
      return BNS_SIGNAL_BUFFER;
   if(name == HTFFIB_SHORTNAME)
      return HTFFIB_SIGNAL_BUFFER;
   if(name == BTP_SHORTNAME)
      return BTP_SIGNAL_BUFFER;
   if(name == FXIT_SHORTNAME)
      return FXIT_SIGNAL_BUFFER;
   return -1;
  }

//+------------------------------------------------------------------+
string SignalContractTable()
  {
   return StringFormat("UIS=%d BNS=%d HTFFIB=%d BTP=%d FXIT=%d",
                       UIS_SIGNAL_BUFFER, BNS_SIGNAL_BUFFER,
                       HTFFIB_SIGNAL_BUFFER, BTP_SIGNAL_BUFFER,
                       FXIT_SIGNAL_BUFFER);
  }

#endif

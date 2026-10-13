//+------------------------------------------------------------------+
//|                                                    RiskGuard.mq5 |
//|  Account-level risk guard                                        |
//|                                                                  |
//|  Watches EVERY position on the account, no matter where it was   |
//|  opened (desktop, phone app, other EAs):                         |
//|   1. Max volume per position  -> partial-closes the excess, or   |
//|                                  closes the position when the    |
//|                                  excess is below one volume step |
//|   2. Stop required            -> attaches one if missing, pulls  |
//|                                  it in if wider than the max,    |
//|                                  in points (not one price gap)   |
//|   3. Max open positions       -> closes the newest extra one,    |
//|                                  and deletes pendings that would |
//|                                  fill past the cap                |
//|   4. Daily loss lock          -> flattens and deletes pendings   |
//|                                  until the lock expires. This    |
//|                                  does not block a new phone,     |
//|                                  desktop, or other-EA order.     |
//|                                                                  |
//|  Designed for a hedging account (Vantage MT5).                   |
//|  NOT COMPILED OR TESTED ON A TERMINAL YET. Demo account first.   |
//+------------------------------------------------------------------+
#property copyright   "Trujillofa"
#property version     "0.20"
#property description "Account-level risk guard. Demo first. Lock flattens; it does not block new orders."

#include <Trade\Trade.mqh>
#include <RiskGuardDecisions.mqh>

#define RG_ATTEMPTS 3

//--- inputs. 1000 points is $10 when the symbol point is 0.01 (XAUUSD).
input double InpMaxLots         = 0.02;   // Max volume per position (lots)
input int    InpMaxSLPoints     = 1000;   // Max stop distance from entry, points
input int    InpMaxPositions    = 2;      // Max simultaneous open positions
input double InpDailyLossLimit  = 40.0;   // Daily loss limit, account currency
input int    InpLockMinHours    = 12;     // Minimum lock duration once the daily limit is hit
input bool   InpPush            = true;   // Push notifications to phone (needs MetaQuotes ID)
input int    InpSlippagePoints  = 100;    // Max slippage for protective closes (points)

CTrade trade;
string g_lockVar;
bool   g_warnedNoTrading = false;
bool   g_warnedNoHistory = false;
bool   g_tradeArrived    = false;

//+------------------------------------------------------------------+
int OnInit()
{
   g_lockVar = "RiskGuard_LockUntil_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN));
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetAsyncMode(false);
   EventSetTimer(1);

   Notify(StringFormat("Started. Max %.2f lots, max SL %d points, max %d positions, daily limit %.2f.",
          InpMaxLots, InpMaxSLPoints, InpMaxPositions, InpDailyLossLimit));
   Enforce();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
   Notify("STOPPED. The account is now UNPROTECTED.");
}

// A new deal or order is noted here. Trade requests go out from OnTimer,
// not from this handler.
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD || trans.type == TRADE_TRANSACTION_ORDER_ADD)
      g_tradeArrived = true;
}

void OnTimer()
{
   if(g_tradeArrived)
      g_tradeArrived = false;
   Enforce();
}

//+------------------------------------------------------------------+
//| Main loop                                                        |
//+------------------------------------------------------------------+
void Enforce()
{
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
      return;

   double dayPL = 0.0;
   bool haveDayPL = DailyPL(dayPL);

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      if(!g_warnedNoTrading)
      {
         Notify("Algo Trading is OFF. Guard cannot act. Account is UNPROTECTED.");
         g_warnedNoTrading = true;
      }
      ShowStatus(haveDayPL, dayPL, IsLocked());
      return;
   }
   g_warnedNoTrading = false;

   bool locked = IsLocked();
   if(!haveDayPL)
   {
      if(!g_warnedNoHistory)
      {
         Print("[RiskGuard] HistorySelect failed. Daily lock not evaluated this pass.");
         g_warnedNoHistory = true;
      }
   }
   else
   {
      g_warnedNoHistory = false;
      if(!locked && dayPL <= -InpDailyLossLimit)
      {
         SetLock();
         locked = true;
         Notify(StringFormat("Daily loss limit hit (%.2f). Closing all. Locked until %s (server).",
                dayPL, TimeToString(LockUntil(), TIME_DATE | TIME_MINUTES)));
      }
   }

   if(locked)
   {
      CloseAllPositions("daily lock");
      DeletePending(true, "daily lock");
   }
   else
   {
      DeletePending(false, "position cap");
      EnforceMaxPositions();
      EnforcePerPosition();
   }

   ShowStatus(haveDayPL, dayPL, locked);
}

//+------------------------------------------------------------------+
bool PrepareSymbol(const string sym)
{
   if(SymbolInfoInteger(sym, SYMBOL_SELECT))
      return true;
   if(SymbolSelect(sym, true))
      return true;
   Print("[RiskGuard] SymbolSelect failed for ", sym, ". Skipping this pass.");
   return false;
}

//+------------------------------------------------------------------+
//| Rule 1 + 2: volume cap and stop requirement                      |
//+------------------------------------------------------------------+
void EnforcePerPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      string sym = PositionGetString(POSITION_SYMBOL);
      if(!PrepareSymbol(sym))
         continue;

      double vol  = PositionGetDouble(POSITION_VOLUME);
      double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
      double vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
      double lots = 0.0;
      ENUM_RG_VOLUME action = DecideVolume(vol, InpMaxLots, step, vmin, lots);
      if(action == RG_VOL_PARTIAL)
      {
         if(TryClosePartial(ticket, lots))
            Notify(StringFormat("%s #%s: %.2f lots > max %.2f. Closed %.2f.",
                   sym, IntegerToString((long)ticket), vol, InpMaxLots, lots));
      }
      else if(action == RG_VOL_CLOSE)
      {
         if(TryClose(ticket))
            Notify(StringFormat("%s #%s: %.2f lots is over max %.2f by less than one step. Closed.",
                   sym, IntegerToString((long)ticket), vol, InpMaxLots));
      }

      EnsureStop(ticket);
   }
}

void EnsureStop(const ulong ticket)
{
   if(!PositionSelectByTicket(ticket))
      return;

   string sym    = PositionGetString(POSITION_SYMBOL);
   if(!PrepareSymbol(sym))
      return;

   bool   isBuy  = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
   double open   = PositionGetDouble(POSITION_PRICE_OPEN);
   double curSL  = PositionGetDouble(POSITION_SL);
   double tp     = PositionGetDouble(POSITION_TP);
   int    digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double point  = SymbolInfoDouble(sym, SYMBOL_POINT);
   double minGap = (double)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) * point;
   double bid    = SymbolInfoDouble(sym, SYMBOL_BID);
   double ask    = SymbolInfoDouble(sym, SYMBOL_ASK);

   if(InpMaxSLPoints < 0 || !QuoteUsable(isBuy, bid, ask, point))
   {
      Print("[RiskGuard] Skip stop on ", sym, ": quote or stop distance is unusable.");
      return;
   }

   double required = RequiredStop(isBuy, open, InpMaxSLPoints, point, digits);

   // A stop is fine if it exists and is no farther than the max distance.
   // A trailed stop in profit (above entry for a buy) always passes.
   bool needsFix = StopNeedsFix(isBuy, curSL, required, point);
   if(!needsFix)
      return;

   bool alreadyThrough = StopAlreadyThrough(isBuy, required, bid, ask, minGap);
   if(alreadyThrough)
   {
      if(TryClose(ticket))
         Notify(StringFormat("%s #%s: no valid SL and already past max distance %d points. Closed.",
                sym, IntegerToString((long)ticket), InpMaxSLPoints));
      return;
   }

   if(TryModify(ticket, required, tp))
      Notify(StringFormat("%s #%s: SL %s -> %s.", sym, IntegerToString((long)ticket),
             curSL == 0.0 ? "missing" : DoubleToString(curSL, digits), DoubleToString(required, digits)));
}

//+------------------------------------------------------------------+
//| Rule 3: max open positions (closes the newest)                   |
//+------------------------------------------------------------------+
void EnforceMaxPositions()
{
   int attempts = 10;
   while(PositionsTotal() > InpMaxPositions && attempts-- > 0)
   {
      ulong newest     = 0;
      long  newestTime = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong t = PositionGetTicket(i);
         if(t == 0)
            continue;
         ConsiderPosition(t, PositionGetInteger(POSITION_TIME_MSC), newest, newestTime);
      }
      if(newest == 0)
      {
         Print("[RiskGuard] Max positions: no ticket to close.");
         break;
      }
      if(!TryClose(newest))
         break;
      Notify(StringFormat("More than %d positions. Closed newest #%s.",
             InpMaxPositions, IntegerToString((long)newest)));
   }
}

//+------------------------------------------------------------------+
//| Rule 4: daily loss lock                                          |
//| False means history could not be read. The caller must not treat |
//| that as a day of zero realized P/L.                              |
//+------------------------------------------------------------------+
bool DailyPL(double &pl)
{
   pl = 0.0;
   datetime dayStart = DayStart();
   if(!HistorySelect(dayStart, TimeCurrent() + 60))
      return false;

   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0)
         continue;
      pl += DealContribution(HistoryDealGetInteger(d, DEAL_TYPE),
                             HistoryDealGetDouble(d, DEAL_PROFIT),
                             HistoryDealGetDouble(d, DEAL_SWAP),
                             HistoryDealGetDouble(d, DEAL_COMMISSION));
   }

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetTicket(i) == 0)
         continue;
      if(!PositionCountsToday((datetime)PositionGetInteger(POSITION_TIME), dayStart))
         continue;
      pl += FloatingPL(PositionGetDouble(POSITION_PROFIT), PositionGetDouble(POSITION_SWAP));
   }
   return true;
}

datetime DayStart()
{
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   t.hour = 0;
   t.min  = 0;
   t.sec  = 0;
   return StructToTime(t);
}

datetime LockUntil()
{
   return GlobalVariableCheck(g_lockVar) ? (datetime)GlobalVariableGet(g_lockVar) : 0;
}

bool IsLocked()
{
   return TimeCurrent() < LockUntil();
}

void SetLock()
{
   datetime until = LockDeadline(DayStart(), TimeCurrent(), InpLockMinHours);
   GlobalVariableSet(g_lockVar, (double)until);   // persists across terminal restarts
}

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
bool TryClose(const ulong ticket)
{
   for(int attempt = 1; attempt <= RG_ATTEMPTS; attempt++)
   {
      if(trade.PositionClose(ticket))
         return true;
      Print("[RiskGuard] Close failed #", ticket, " attempt ", attempt, "/", RG_ATTEMPTS,
            ": ", trade.ResultRetcodeDescription());
   }
   return false;
}

bool TryClosePartial(const ulong ticket, const double lots)
{
   for(int attempt = 1; attempt <= RG_ATTEMPTS; attempt++)
   {
      if(trade.PositionClosePartial(ticket, lots))
         return true;
      Print("[RiskGuard] Partial close failed #", ticket, " attempt ", attempt, "/", RG_ATTEMPTS,
            ": ", trade.ResultRetcodeDescription());
   }
   return false;
}

bool TryModify(const ulong ticket, const double sl, const double tp)
{
   for(int attempt = 1; attempt <= RG_ATTEMPTS; attempt++)
   {
      if(trade.PositionModify(ticket, sl, tp))
         return true;
      Print("[RiskGuard] SL modify failed #", ticket, " attempt ", attempt, "/", RG_ATTEMPTS,
            ": ", trade.ResultRetcodeDescription());
   }
   return false;
}

bool TryDelete(const ulong ticket)
{
   for(int attempt = 1; attempt <= RG_ATTEMPTS; attempt++)
   {
      if(trade.OrderDelete(ticket))
         return true;
      Print("[RiskGuard] Pending delete failed #", ticket, " attempt ", attempt, "/", RG_ATTEMPTS,
            ": ", trade.ResultRetcodeDescription());
   }
   return false;
}

void CloseAllPositions(const string why)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      string sym = PositionGetString(POSITION_SYMBOL);
      if(TryClose(ticket))
         Notify(StringFormat("Closed %s #%s (%s).", sym, IntegerToString((long)ticket), why));
   }
}

void DeletePending(const bool flattenAll, const string why)
{
   int n = OrdersTotal();
   ulong tickets[];
   double volumes[];
   long times[];
   ArrayResize(tickets, n);
   ArrayResize(volumes, n);
   ArrayResize(times, n);
   int count = 0;
   for(int i = 0; i < n; i++)
   {
      ulong ticket = OrderGetTicket(i);
      tickets[count] = ticket;
      if(ticket == 0)
      {
         volumes[count] = 0.0;
         times[count] = 0;
      }
      else
      {
         volumes[count] = OrderGetDouble(ORDER_VOLUME_CURRENT);
         times[count] = (long)OrderGetInteger(ORDER_TIME_SETUP_MSC);
      }
      count++;
   }

   bool drop[];
   if(flattenAll)
   {
      ArrayResize(drop, count);
      for(int i = 0; i < count; i++)
         drop[i] = (tickets[i] != 0);
   }
   else
      MarkPendingsToDelete(PositionsTotal(), InpMaxPositions, InpMaxLots,
                           tickets, volumes, times, count, drop);

   for(int i = 0; i < count; i++)
   {
      if(!drop[i])
         continue;
      if(TryDelete(tickets[i]))
         Notify(StringFormat("Deleted pending #%s (%s).", IntegerToString((long)tickets[i]), why));
   }
}

void ShowStatus(const bool havePL, const double dayPL, const bool locked)
{
   string lockLine = locked
      ? "\nLOCKED until " + TimeToString(LockUntil(), TIME_DATE | TIME_MINUTES) + " (server time)"
      : "";
   string plText = havePL ? DoubleToString(dayPL, 2) : "unavailable";
   Comment(StringFormat("RiskGuard v0.20  |  %s\nDay P/L: %s   (limit -%.2f)\nMax lots %.2f  |  Max SL %d points  |  Max positions %d%s",
           locked ? "LOCKED" : "ACTIVE", plText, InpDailyLossLimit,
           InpMaxLots, InpMaxSLPoints, InpMaxPositions, lockLine));
}

void Notify(const string msg)
{
   Print("[RiskGuard] ", msg);
   if(InpPush)
      SendNotification("RiskGuard: " + msg);
}
//+------------------------------------------------------------------+

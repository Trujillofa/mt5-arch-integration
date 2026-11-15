//+------------------------------------------------------------------+
//| RiskGuardDecisions.mqh                                           |
//| Pure decisions for RiskGuard.mq5. No trade requests.             |
//|                                                                  |
//| Host twin: scripts/riskguard_decisions.py (pinned by             |
//| tests/test_riskguard_decisions.py).                              |
//+------------------------------------------------------------------+
#property copyright "Trujillofa"
#property strict

#ifndef RISKGUARD_DECISIONS_MQH
#define RISKGUARD_DECISIONS_MQH

enum ENUM_RG_VOLUME
{
   RG_VOL_OK      = 0,  // inside the cap
   RG_VOL_PARTIAL = 1,  // close lotsOut
   RG_VOL_CLOSE   = 2,  // over the cap by less than one step
   RG_VOL_SKIP    = 3   // volume step is missing; do not invent 0.01
};

double NormalizeVolumeValue(const double volume, const double step, const double volumeMin)
{
   if(step <= 0.0)
      return 0.0;
   double v = MathFloor(volume / step + 1e-9) * step;
   if(v < volumeMin - 1e-9)
      return 0.0;
   int digits = (int)MathMax(0.0, MathCeil(-MathLog10(step)));
   return NormalizeDouble(v, digits);
}

ENUM_RG_VOLUME DecideVolume(const double volume, const double maxLots,
                            const double step, const double volumeMin, double &lotsOut)
{
   lotsOut = 0.0;
   if(step <= 0.0)
      return RG_VOL_SKIP;
   if(!(volume > maxLots + 1e-8))
      return RG_VOL_OK;
   double excess = NormalizeVolumeValue(volume - maxLots, step, volumeMin);
   if(excess > 0.0)
   {
      lotsOut = excess;
      return RG_VOL_PARTIAL;
   }
   return RG_VOL_CLOSE;
}

double RequiredStop(const bool isBuy, const double openPrice, const int distancePoints,
                    const double point, const int digits)
{
   if(point <= 0.0 || distancePoints < 0)
      return 0.0;
   double distance = (double)distancePoints * point;
   return NormalizeDouble(isBuy ? openPrice - distance : openPrice + distance, digits);
}

bool StopNeedsFix(const bool isBuy, const double currentSL, const double required, const double point)
{
   return (currentSL == 0.0) ||
          (isBuy  && currentSL < required - point / 2) ||
          (!isBuy && currentSL > required + point / 2);
}

bool QuoteUsable(const bool isBuy, const double bid, const double ask, const double point)
{
   if(point <= 0.0)
      return false;
   if(isBuy)
      return (bid > 0.0);
   return (ask > 0.0);
}

bool StopAlreadyThrough(const bool isBuy, const double required,
                        const double bid, const double ask, const double minGap)
{
   return isBuy ? (required >= bid - minGap) : (required <= ask + minGap);
}

void ConsiderPosition(const ulong ticket, const long timeMsc, ulong &newest, long &newestTime)
{
   if(ticket == 0)
      return;
   if(timeMsc > newestTime)
   {
      newestTime = timeMsc;
      newest     = ticket;
   }
}

datetime LockDeadline(const datetime dayStart, const datetime now, const int lockMinHours)
{
   datetime nextDay = dayStart + 86400;
   datetime minEnd  = now + lockMinHours * 3600;
   return (nextDay > minEnd) ? nextDay : minEnd;
}

double DealContribution(const long dealType, const double profit, const double swap, const double commission)
{
   if(dealType != DEAL_TYPE_BUY && dealType != DEAL_TYPE_SELL)
      return 0.0;
   return profit + swap + commission;
}

double FloatingPL(const double profit, const double swap)
{
   return profit + swap;
}

bool PositionCountsToday(const datetime openTime, const datetime dayStart)
{
   return (openTime >= dayStart);
}

// Unlocked pendings. Oversized volume always drops. Of the rest, keep the
// oldest up to (maxPositions - positions) slots. A time tie keeps the lower
// index. The caller deletes every pending while the daily lock is on.
void MarkPendingsToDelete(const int positions, const int maxPositions, const double maxLots,
                          const ulong &tickets[], const double &volumes[], const long &times[],
                          const int n, bool &drop[])
{
   ArrayResize(drop, n);
   int slots = maxPositions - positions;
   if(slots < 0)
      slots = 0;
   for(int i = 0; i < n; i++)
   {
      drop[i] = false;
      if(tickets[i] == 0)
         continue;
      if(volumes[i] > maxLots + 1e-8)
      {
         drop[i] = true;
         continue;
      }
      int older = 0;
      for(int j = 0; j < n; j++)
      {
         if(j == i || tickets[j] == 0)
            continue;
         if(volumes[j] > maxLots + 1e-8)
            continue;
         if(times[j] < times[i] || (times[j] == times[i] && j < i))
            older++;
      }
      drop[i] = (older >= slots);
   }
}

#endif

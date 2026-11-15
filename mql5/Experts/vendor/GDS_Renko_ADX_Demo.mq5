//+------------------------------------------------------------------+
//|                    GDS Renko ADX Demo EA                         |
//|          Educational Renko + ADX / DI example for MT5           |
//+------------------------------------------------------------------+
#property copyright "Golden Delta"
#property link      "https://goldendeltaea.com/"
#property version   "1.10"
#property strict
#property description "Educational Renko + ADX Expert Advisor for MetaTrader 5."
#property description "Builds classic fixed-size Renko internally from BID ticks."
#property description "ADX, +DI and -DI are calculated from completed Renko bricks only."
#property description "A completed brick may trigger a trade only when ADX confirms strength."
#property description "TP/SL are virtual: the EA and terminal must remain running."
#property description "Requested volume is normalized to the symbol minimum, maximum and volume step."
#property description "No external indicators, DLLs, custom symbols or offline charts are required."

input double InpBrickSize           = 16.0;  // Renko brick size in price units
input int    InpADXPeriod           = 14;    // Wilder ADX period, completed Renko bricks
input double InpADXThreshold        = 8.5;  // Minimum ADX for a new entry
input double InpMinDISeparation     = 2.5;   // Minimum absolute +DI/-DI separation
input int    InpEntryRunBricks      = 3;     // Minimum same-direction completed brick run
input double InpTakeProfitBricks    = 9.5;   // Virtual take profit in bricks
input double InpStopLossBricks      = 42.0;   // Virtual stop loss in bricks
input int    InpMaxHoldMinutes      = 1060;   // Maximum hold; 0 disables time exit
input int    InpCooldownBricks      = 6;     // Completed bricks to wait after exit
input double InpMaxSpreadFraction   = 0.35;  // Maximum spread / brick size
input double InpLots                = 0.01;  // Requested fixed lot
input ulong  InpMagic               = 26091131; // Unique EA magic; do not optimize

struct SRenkoBrick
  {
   double open;
   double close;
   int    direction; // +1 up, -1 down
   int    run;       // consecutive bricks in current direction
  };

//+------------------------------------------------------------------+
//| Classic fixed-size Renko builder, two-brick reversal             |
//+------------------------------------------------------------------+
const int MAX_BRICKS_PER_TICK=4096;
class CRenkoBuilder
  {
private:
   double m_tick_size;
   long   m_size,m_close;
   int    m_dir,m_run;
   bool   m_anchor;
public:
   void Init(const double tick_size,const long size)
     {
      m_tick_size=tick_size;
      m_size=size;
      m_close=0;
      m_dir=0;
      m_run=0;
      m_anchor=false;
     }

   int PushPrice(const double price,SRenkoBrick &out[])
     {
      ArrayResize(out,0);
      const long p=(long)MathRound(price/m_tick_size);
      if(!m_anchor)
        {
         m_close=p;
         m_anchor=true;
         return 0;
        }

      const long delta=p-m_close;
      int dir=m_dir;
      long count=0;
      bool reversal=false;

      if(m_dir==0)
        {
         if(delta>=m_size) { dir=1; count=delta/m_size; }
         else if(delta<=-m_size) { dir=-1; count=(-delta)/m_size; }
        }
      else if(m_dir>0)
        {
         if(delta>=m_size) count=delta/m_size;
         else if(delta<=-2*m_size)
           {
            dir=-1;
            reversal=true;
            count=(-delta)/m_size-1;
           }
        }
      else
        {
         if(delta<=-m_size) count=(-delta)/m_size;
         else if(delta>=2*m_size)
           {
            dir=1;
            reversal=true;
            count=delta/m_size-1;
           }
        }

      if(count>MAX_BRICKS_PER_TICK) return -1;
      if(count==0) return 0;
      if(ArrayResize(out,(int)count)!=(int)count) return -1;

      for(int i=0;i<(int)count;i++)
        {
         const long open=m_close+((reversal && i==0) ? dir*m_size : 0);
         m_close=open+dir*m_size;
         if(dir==m_dir) m_run++;
         else
           {
            m_dir=dir;
            m_run=1;
           }

         out[i].open=open*m_tick_size;
         out[i].close=m_close*m_tick_size;
         out[i].direction=dir;
         out[i].run=m_run;
        }
      return (int)count;
     }
  };

//+------------------------------------------------------------------+
//| Wilder ADX calculated only from completed synthetic Renko OHLC   |
//+------------------------------------------------------------------+
class CRenkoADX
  {
private:
   int    m_period;
   int    m_tr_count;
   int    m_dx_count;
   bool   m_have_prev;
   bool   m_ready;
   double m_prev_high;
   double m_prev_low;
   double m_prev_close;
   double m_sm_tr;
   double m_sm_plus_dm;
   double m_sm_minus_dm;
   double m_dx_sum;
   double m_adx;
   double m_plus_di;
   double m_minus_di;

   double Max3(const double a,const double b,const double c)
     {
      return MathMax(a,MathMax(b,c));
     }

   double ComputeDX(void)
     {
      if(m_sm_tr<=1.0e-12)
        {
         m_plus_di=0.0;
         m_minus_di=0.0;
         return 0.0;
        }

      m_plus_di=100.0*m_sm_plus_dm/m_sm_tr;
      m_minus_di=100.0*m_sm_minus_dm/m_sm_tr;
      const double total=m_plus_di+m_minus_di;
      if(total<=1.0e-12) return 0.0;
      return 100.0*MathAbs(m_plus_di-m_minus_di)/total;
     }

public:
   void Init(const int period)
     {
      m_period=period;
      m_tr_count=0;
      m_dx_count=0;
      m_have_prev=false;
      m_ready=false;
      m_prev_high=0.0;
      m_prev_low=0.0;
      m_prev_close=0.0;
      m_sm_tr=0.0;
      m_sm_plus_dm=0.0;
      m_sm_minus_dm=0.0;
      m_dx_sum=0.0;
      m_adx=0.0;
      m_plus_di=0.0;
      m_minus_di=0.0;
     }

   void Push(const SRenkoBrick &brick)
     {
      const double high=MathMax(brick.open,brick.close);
      const double low=MathMin(brick.open,brick.close);
      const double close=brick.close;

      if(!m_have_prev)
        {
         m_prev_high=high;
         m_prev_low=low;
         m_prev_close=close;
         m_have_prev=true;
         return;
        }

      const double tr=Max3(high-low,MathAbs(high-m_prev_close),MathAbs(low-m_prev_close));
      const double up_move=high-m_prev_high;
      const double down_move=m_prev_low-low;
      const double plus_dm=(up_move>down_move && up_move>0.0 ? up_move : 0.0);
      const double minus_dm=(down_move>up_move && down_move>0.0 ? down_move : 0.0);

      m_prev_high=high;
      m_prev_low=low;
      m_prev_close=close;

      if(m_tr_count<m_period)
        {
         m_sm_tr+=tr;
         m_sm_plus_dm+=plus_dm;
         m_sm_minus_dm+=minus_dm;
         m_tr_count++;

         if(m_tr_count==m_period)
           {
            const double dx=ComputeDX();
            m_dx_sum=dx;
            m_dx_count=1;
            if(m_period==1)
              {
               m_adx=dx;
               m_ready=true;
              }
           }
         return;
        }

      m_sm_tr=m_sm_tr-m_sm_tr/(double)m_period+tr;
      m_sm_plus_dm=m_sm_plus_dm-m_sm_plus_dm/(double)m_period+plus_dm;
      m_sm_minus_dm=m_sm_minus_dm-m_sm_minus_dm/(double)m_period+minus_dm;
      const double dx=ComputeDX();

      if(!m_ready)
        {
         m_dx_sum+=dx;
         m_dx_count++;
         if(m_dx_count>=m_period)
           {
            m_adx=m_dx_sum/(double)m_period;
            m_ready=true;
           }
         return;
        }

      m_adx=((double)(m_period-1)*m_adx+dx)/(double)m_period;
     }

   bool Ready(void) const { return m_ready; }
   double ADX(void) const { return m_adx; }
   double PlusDI(void) const { return m_plus_di; }
   double MinusDI(void) const { return m_minus_di; }

   int Direction(const double adx_threshold,const double min_di_separation) const
     {
      if(!m_ready || m_adx<adx_threshold) return 0;
      if(MathAbs(m_plus_di-m_minus_di)<min_di_separation) return 0;
      if(m_plus_di>m_minus_di) return 1;
      if(m_minus_di>m_plus_di) return -1;
      return 0;
     }

   int RawDirection(void) const
     {
      if(!m_ready) return 0;
      if(m_plus_di>m_minus_di) return 1;
      if(m_minus_di>m_plus_di) return -1;
      return 0;
     }
  };

CRenkoBuilder g_renko;
CRenkoADX     g_adx;
bool          g_builder_failed=false;
double        g_effective_brick_size=0.0;
int           g_cooldown_left=0;
bool          g_closed_this_tick=false;
bool          g_exit_pending=false;
string        g_exit_reason="";
bool          g_request_this_tick=false;
datetime      g_retry_after=0;
datetime      g_request_session_end=0;
int           g_request_failures=0;
ulong         g_wait_order=0;
bool          g_execution_uncertain=false;
bool          g_uncertain_exit=false;
const int     GDS_MAX_REQUEST_FAILURES=3;

//+------------------------------------------------------------------+
double NormalizeVolume(const double requested)
  {
   double vmin=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);

   if(!MathIsValidNumber(requested) || requested<=0.0) return 0.0;
   if(!MathIsValidNumber(vmin) || !MathIsValidNumber(vmax) ||
      !MathIsValidNumber(step) || vmin<=0.0 || vmax<vmin) return 0.0;
   if(step<=0.0) step=vmin;
   if(step<=0.0) return 0.0;

   double volume=MathRound(requested/step)*step;
   volume=MathMax(vmin,MathMin(vmax,volume));
   volume=NormalizeDouble(volume,8);
   if(volume<vmin-1.0e-10 || volume>vmax+1.0e-10) return 0.0;
   return volume;
  }

//+------------------------------------------------------------------+
bool GetFillingMode(ENUM_ORDER_TYPE_FILLING &filling)
  {
   const long flags=SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE);
   const ENUM_SYMBOL_TRADE_EXECUTION execution=(ENUM_SYMBOL_TRADE_EXECUTION)
      SymbolInfoInteger(_Symbol,SYMBOL_TRADE_EXEMODE);

   filling=ORDER_FILLING_FOK;
   if(execution==SYMBOL_TRADE_EXECUTION_INSTANT ||
      execution==SYMBOL_TRADE_EXECUTION_REQUEST) return true;
   if((flags & SYMBOL_FILLING_FOK)==SYMBOL_FILLING_FOK) return true;
   if((flags & SYMBOL_FILLING_IOC)==SYMBOL_FILLING_IOC)
     {
      filling=ORDER_FILLING_IOC;
      return true;
     }
   if(execution==SYMBOL_TRADE_EXECUTION_MARKET) return false;
   filling=ORDER_FILLING_RETURN;
   return true;
  }

//+------------------------------------------------------------------+
bool FindOurPosition(ulong &ticket,long &type,double &volume,
                     double &open_price,datetime &open_time)
  {
   ticket=0;
   type=-1;
   volume=0.0;
   open_price=0.0;
   open_time=0;

   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      const ulong t=PositionGetTicket(i);
      if(t==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;

      ticket=t;
      type=PositionGetInteger(POSITION_TYPE);
      volume=PositionGetDouble(POSITION_VOLUME);
      open_price=PositionGetDouble(POSITION_PRICE_OPEN);
      open_time=(datetime)PositionGetInteger(POSITION_TIME);
      return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
bool AnyPositionOnSymbol(void)
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      const ulong t=PositionGetTicket(i);
      if(t==0) continue;
      if(PositionGetString(POSITION_SYMBOL)==_Symbol) return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
bool ValidTick(const MqlTick &tick)
  {
   return MathIsValidNumber(tick.bid) && MathIsValidNumber(tick.ask) &&
          tick.bid>0.0 && tick.ask>=tick.bid && tick.time>0;
  }

//+------------------------------------------------------------------+
bool SpreadIsAcceptable(const MqlTick &tick)
  {
   if(!ValidTick(tick)) return false;
   return ((tick.ask-tick.bid)<=g_effective_brick_size*InpMaxSpreadFraction);
  }

//+------------------------------------------------------------------+
int SecondsOfDay(const datetime value)
  {
   MqlDateTime part={};
   if(!TimeToStruct(value,part)) return -1;
   return part.hour*3600+part.min*60+part.sec;
  }

//+------------------------------------------------------------------+
datetime TradingSessionEnd(const datetime now)
  {
   MqlDateTime current={};
   if(now<=0 || !TimeToStruct(now,current)) return 0;
   const int seconds=current.hour*3600+current.min*60+current.sec;
   const datetime midnight=now-seconds;

   for(int offset=0;offset<=1;offset++)
     {
      const ENUM_DAY_OF_WEEK day=(ENUM_DAY_OF_WEEK)
         ((current.day_of_week-offset+7)%7);
      for(uint session=0;session<24;session++)
        {
         datetime from=0,to=0;
         if(!SymbolInfoSessionTrade(_Symbol,day,session,from,to)) break;
         const int start_seconds=SecondsOfDay(from);
         const int end_seconds=SecondsOfDay(to);
         if(start_seconds<0 || end_seconds<0) continue;

         const datetime start=midnight-offset*86400+start_seconds;
         datetime end=midnight-offset*86400+end_seconds;
         if(end<=start) end+=86400;
         if(now>=start && now<end) return end;
        }
     }
   return 0;
  }

//+------------------------------------------------------------------+
bool TradingSessionIsOpen(const datetime when=0)
  {
   return TradingSessionEnd(when>0 ? when : TimeCurrent())>0;
  }

//+------------------------------------------------------------------+
bool HasActiveOrder(const bool only_ours)
  {
   for(int i=OrdersTotal()-1;i>=0;i--)
     {
      if(OrderGetTicket(i)==0) continue;
      if(OrderGetString(ORDER_SYMBOL)!=_Symbol) continue;
      if(!only_ours || (ulong)OrderGetInteger(ORDER_MAGIC)==InpMagic) return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
void MarkExitCompleted(void)
  {
   g_exit_pending=false;
   g_exit_reason="";
   g_cooldown_left=InpCooldownBricks;
   g_closed_this_tick=true;
  }

//+------------------------------------------------------------------+
bool ResolveExecution(void)
  {
   if(g_wait_order!=0)
     {
      if(OrderSelect(g_wait_order)) return false;
      if(!HistoryOrderSelect(g_wait_order)) return false;
      const ENUM_ORDER_STATE state=(ENUM_ORDER_STATE)
         HistoryOrderGetInteger(g_wait_order,ORDER_STATE);
      if(state!=ORDER_STATE_FILLED && state!=ORDER_STATE_CANCELED &&
         state!=ORDER_STATE_REJECTED && state!=ORDER_STATE_EXPIRED) return false;
      g_wait_order=0;
      g_execution_uncertain=false;
     }

   if(g_execution_uncertain)
     {
      ulong ticket=0;
      long type=-1;
      double volume=0.0,price=0.0;
      datetime opened=0;
      const bool exists=FindOurPosition(ticket,type,volume,price,opened);
      if((g_uncertain_exit && !exists) || (!g_uncertain_exit && exists))
         g_execution_uncertain=false;
     }
   return !g_execution_uncertain;
  }

//+------------------------------------------------------------------+
bool RequestWindowIsOpen(void)
  {
   if(g_request_this_tick || !ResolveExecution()) return false;
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) ||
      !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ||
      !MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_EXPERT)) return false;

   const datetime now=TimeCurrent();
   const datetime end=TradingSessionEnd(now);
   if(end<=0) return false;

   if(g_request_session_end!=end)
     {
      g_request_session_end=end;
      g_request_failures=0;
      g_retry_after=0;
     }
   return now>=g_retry_after;
  }

//+------------------------------------------------------------------+
void RegisterFailure(const uint retcode,const string details)
  {
   g_request_failures++;
   const datetime now=TimeCurrent();
   const datetime end=TradingSessionEnd(now);

   if(retcode==TRADE_RETCODE_MARKET_CLOSED ||
      g_request_failures>=GDS_MAX_REQUEST_FAILURES)
      g_retry_after=(end>now ? end : now+300);
   else
      g_retry_after=now+(g_request_failures==1 ? 5 : 30);

   Print("GDS Renko ADX Demo: request deferred. Retcode ",retcode,
         ", ",details,", next attempt no earlier than ",
         TimeToString(g_retry_after,TIME_DATE|TIME_SECONDS));
  }

//+------------------------------------------------------------------+
bool SubmitDeal(MqlTradeRequest &request,const bool is_exit)
  {
   if(!RequestWindowIsOpen()) return false;
   g_request_this_tick=true;

   MqlTradeCheckResult check={};
   ResetLastError();
   if(!OrderCheck(request,check))
     {
      RegisterFailure(check.retcode,check.comment);
      return false;
     }

   if(!TradingSessionIsOpen(TimeCurrent())) return false;

   MqlTradeResult result={};
   ResetLastError();
   const bool sent=OrderSend(request,result);
   const int error=GetLastError();

   if(!sent || (result.retcode!=TRADE_RETCODE_DONE &&
                result.retcode!=TRADE_RETCODE_DONE_PARTIAL &&
                result.retcode!=TRADE_RETCODE_PLACED))
     {
      if(result.retcode==TRADE_RETCODE_TIMEOUT ||
         result.retcode==TRADE_RETCODE_CONNECTION || result.retcode==0)
        {
         g_execution_uncertain=true;
         g_uncertain_exit=is_exit;
         g_wait_order=result.order;
         Print("GDS Renko ADX Demo: execution unconfirmed; requests paused.");
        }
      RegisterFailure(result.retcode,result.comment+" error="+IntegerToString(error));
      return false;
     }

   g_retry_after=0;
   g_wait_order=result.order;
   if(result.order==0)
     {
      g_execution_uncertain=true;
      g_uncertain_exit=is_exit;
      ResolveExecution();
     }
   return true;
  }

//+------------------------------------------------------------------+
bool TradeModeAllowsEntry(const int direction)
  {
   const ENUM_SYMBOL_TRADE_MODE mode=(ENUM_SYMBOL_TRADE_MODE)
      SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE);
   if(mode==SYMBOL_TRADE_MODE_DISABLED || mode==SYMBOL_TRADE_MODE_CLOSEONLY) return false;
   if(mode==SYMBOL_TRADE_MODE_LONGONLY && direction<0) return false;
   if(mode==SYMBOL_TRADE_MODE_SHORTONLY && direction>0) return false;
   return true;
  }

//+------------------------------------------------------------------+
bool TradeModeAllowsClose(void)
  {
   const ENUM_SYMBOL_TRADE_MODE mode=(ENUM_SYMBOL_TRADE_MODE)
      SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE);
   return (mode!=SYMBOL_TRADE_MODE_DISABLED);
  }

//+------------------------------------------------------------------+
void RequestExit(const string reason)
  {
   if(!g_exit_pending) g_exit_reason=reason;
   g_exit_pending=true;
  }

//+------------------------------------------------------------------+
bool SendMarket(const int direction)
  {
   if(direction!=1 && direction!=-1) return false;
   if(g_exit_pending || AnyPositionOnSymbol() || HasActiveOrder(false)) return false;
   if(!TradeModeAllowsEntry(direction)) return false;
   if((SymbolInfoInteger(_Symbol,SYMBOL_ORDER_MODE)&SYMBOL_ORDER_MARKET)==0) return false;

   MqlTick tick={};
   if(!SymbolInfoTick(_Symbol,tick) || !ValidTick(tick)) return false;
   if(!SpreadIsAcceptable(tick)) return false;

   MqlTradeRequest request={};
   if(!GetFillingMode(request.type_filling)) return false;
   request.volume=NormalizeVolume(InpLots);
   if(request.volume<=0.0) return false;

   request.action=TRADE_ACTION_DEAL;
   request.magic=InpMagic;
   request.symbol=_Symbol;
   request.deviation=50;
   request.comment="GDS Renko ADX";
   request.type=(direction>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   request.price=(direction>0 ? tick.ask : tick.bid);
   return SubmitDeal(request,false);
  }

//+------------------------------------------------------------------+
bool CloseOurPosition(const string reason)
  {
   ulong ticket=0;
   long type=-1;
   double volume=0.0,open_price=0.0;
   datetime open_time=0;
   if(!FindOurPosition(ticket,type,volume,open_price,open_time)) return false;
   if(!TradeModeAllowsClose() || HasActiveOrder(true)) return false;

   MqlTick tick={};
   if(!SymbolInfoTick(_Symbol,tick) || !ValidTick(tick)) return false;

   MqlTradeRequest request={};
   if(!GetFillingMode(request.type_filling)) return false;
   request.action=TRADE_ACTION_DEAL;
   request.magic=InpMagic;
   request.position=ticket;
   request.symbol=_Symbol;
   request.volume=volume;
   request.deviation=50;
   request.comment="GDS ADX exit";
   request.type=(type==POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY);
   request.price=(type==POSITION_TYPE_BUY ? tick.bid : tick.ask);

   if(!SubmitDeal(request,true)) return false;
   g_closed_this_tick=true;

   if(!FindOurPosition(ticket,type,volume,open_price,open_time))
     {
      Print("GDS Renko ADX Demo exit: ",reason);
      MarkExitCompleted();
     }
   return true;
  }

//+------------------------------------------------------------------+
void TryPendingExit(void)
  {
   if(!g_exit_pending || !ResolveExecution()) return;

   ulong ticket=0;
   long type=-1;
   double volume=0.0,open_price=0.0;
   datetime open_time=0;
   if(!FindOurPosition(ticket,type,volume,open_price,open_time))
     {
      MarkExitCompleted();
      return;
     }
   CloseOurPosition(g_exit_reason);
  }

//+------------------------------------------------------------------+
void CheckPriceExit(const MqlTick &tick)
  {
   ulong ticket=0;
   long type=-1;
   double volume=0.0,open_price=0.0;
   datetime open_time=0;
   if(!FindOurPosition(ticket,type,volume,open_price,open_time)) return;

   const int direction=(type==POSITION_TYPE_BUY ? 1 : -1);
   const double executable=(direction>0 ? tick.bid : tick.ask);
   if(executable<=0.0) return;

   const double move=direction*(executable-open_price);
   const double tp=InpTakeProfitBricks*g_effective_brick_size;
   const double sl=InpStopLossBricks*g_effective_brick_size;

   if(move>=tp) { RequestExit("TP"); return; }
   if(move<=-sl) { RequestExit("SL"); return; }

   if(InpMaxHoldMinutes>0 && open_time>0)
     {
      const long held_seconds=(long)(TimeCurrent()-open_time);
      if(held_seconds>=(long)InpMaxHoldMinutes*60) RequestExit("TIME");
     }
  }

//+------------------------------------------------------------------+
//| Only a completed Renko brick can update ADX/DI or signal.        |
//+------------------------------------------------------------------+
int ProcessCompletedBrick(const SRenkoBrick &brick,int &raw_direction)
  {
   g_adx.Push(brick);
   raw_direction=g_adx.RawDirection();

   const int direction=g_adx.Direction(InpADXThreshold,InpMinDISeparation);
   if(direction==0) return 0;
   if(brick.direction!=direction) return 0;
   if(brick.run<InpEntryRunBricks) return 0;
   return direction;
  }

//+------------------------------------------------------------------+
void UpdateRenkoAndTrade(const double price)
  {
   if(g_builder_failed) return;

   SRenkoBrick bricks[];
   const int n=g_renko.PushPrice(price,bricks);
   if(n<0)
     {
      g_builder_failed=true;
      Print("GDS ADX: excessive gap/memory failure. New entries paused; existing exits remain active.");
      return;
     }
   if(n==0) return;

   int final_signal=0;
   int final_raw_direction=0;
   for(int i=0;i<n;i++)
     {
      int raw_direction=0;
      final_signal=ProcessCompletedBrick(bricks[i],raw_direction);
      final_raw_direction=raw_direction;
     }

   if(g_cooldown_left>0)
     {
      g_cooldown_left-=n;
      if(g_cooldown_left<0) g_cooldown_left=0;
     }

   ulong ticket=0;
   long type=-1;
   double volume=0.0,open_price=0.0;
   datetime open_time=0;
   const bool have_position=FindOurPosition(ticket,type,volume,open_price,open_time);

   if(have_position)
     {
      const int position_direction=(type==POSITION_TYPE_BUY ? 1 : -1);
      // Directional DI cross is an exit even if ADX has already fallen below
      // the entry threshold. The strength threshold gates entries only.
      if(final_raw_direction!=0 && final_raw_direction==-position_direction)
         RequestExit("DI_FLIP");
      return;
     }

   if(g_closed_this_tick || g_exit_pending) return;
   if(AnyPositionOnSymbol()) return;
   if(g_cooldown_left>0) return;
   if(final_signal==0) return;

   SendMarket(final_signal);
  }

//+------------------------------------------------------------------+
int OnInit(void)
  {
   if(!MathIsValidNumber(InpBrickSize) || InpBrickSize<=0.0 ||
      InpADXPeriod<2 || InpADXPeriod>100 ||
      !MathIsValidNumber(InpADXThreshold) || InpADXThreshold<0.0 || InpADXThreshold>100.0 ||
      !MathIsValidNumber(InpMinDISeparation) || InpMinDISeparation<0.0 || InpMinDISeparation>100.0 ||
      InpEntryRunBricks<1 || InpEntryRunBricks>50 ||
      !MathIsValidNumber(InpTakeProfitBricks) || InpTakeProfitBricks<=0.0 ||
      !MathIsValidNumber(InpStopLossBricks) || InpStopLossBricks<=0.0 ||
      InpMaxHoldMinutes<0 || InpCooldownBricks<0 ||
      !MathIsValidNumber(InpMaxSpreadFraction) || InpMaxSpreadFraction<=0.0 ||
      !MathIsValidNumber(InpLots) || InpLots<=0.0 || InpMagic==0)
     {
      Print("GDS Renko ADX Demo: invalid inputs.");
      return INIT_PARAMETERS_INCORRECT;
     }

   g_request_this_tick=false;
   g_retry_after=0;
   g_request_session_end=0;
   g_request_failures=0;
   g_wait_order=0;
   g_execution_uncertain=false;
   g_uncertain_exit=false;

   const double tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(!MathIsValidNumber(tick_size) || tick_size<=0.0)
     {
      Print("GDS ADX: symbol tick size unavailable.");
      return INIT_FAILED;
     }

   const double units_raw=InpBrickSize/tick_size;
   if(!MathIsValidNumber(units_raw) || units_raw<0.5 || units_raw>1e9)
     {
      Print("GDS ADX: brick size cannot be represented for this symbol.");
      return INIT_FAILED;
     }

   const long units=(long)MathMax(1.0,MathRound(units_raw));
   g_effective_brick_size=(double)units*tick_size;

   const double effective_volume=NormalizeVolume(InpLots);
   if(effective_volume<=0.0)
     {
      Print("GDS ADX: symbol volume settings unavailable or invalid.");
      return INIT_FAILED;
     }

   g_renko.Init(tick_size,units);
   g_adx.Init(InpADXPeriod);

   g_builder_failed=false;
   g_cooldown_left=0;
   g_closed_this_tick=false;
   g_exit_pending=false;
   g_exit_reason="";

   Print("GDS Renko ADX Demo v1.10 started. RequestedBrick=",
         DoubleToString(InpBrickSize,_Digits),
         ", EffectiveBrick=",DoubleToString(g_effective_brick_size,_Digits),
         ", ADXPeriod=",InpADXPeriod,
         ", ADXThreshold=",DoubleToString(InpADXThreshold,2),
         ", MinDISep=",DoubleToString(InpMinDISeparation,2),
         ", EntryRun=",InpEntryRunBricks,
         ", TP=",DoubleToString(InpTakeProfitBricks,2),
         ", SL=",DoubleToString(InpStopLossBricks,2),
         ", RequestedLots=",DoubleToString(InpLots,2),
         ", EffectiveLots=",DoubleToString(effective_volume,2));
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnTick(void)
  {
   g_closed_this_tick=false;
   g_request_this_tick=false;
   ResolveExecution();

   MqlTick tick={};
   if(!SymbolInfoTick(_Symbol,tick) || !ValidTick(tick)) return;

   TryPendingExit();
   CheckPriceExit(tick);
   TryPendingExit();

   // ADX/DI state and entries change only when BID completes Renko bricks.
   UpdateRenkoAndTrade(tick.bid);

   // A DI flip detected on the completed brick may request an exit now.
   TryPendingExit();
  }
//+------------------------------------------------------------------+

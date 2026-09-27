//+------------------------------------------------------------------+
//|             GDS Renko Bollinger 4-Mode Demo EA                  |
//|        Educational multi-engine Renko Bollinger example         |
//+------------------------------------------------------------------+
#property copyright "Golden Delta"
#property link      "https://goldendeltaea.com/"
#property version   "1.30"
#property strict
#property description "Educational four-mode Renko + Bollinger Expert Advisor for MetaTrader 5."
#property description "Four independent internal Renko engines: Breakout, Re-entry, Midline Cross and Squeeze Breakout."
#property description "All four modes are enabled by default; each can be disabled and configured independently."
#property description "Bollinger bands use previous completed Renko closes only; the current brick is excluded."
#property description "Max positions defaults to four on hedging accounts; netting accounts are automatically limited to one symbol position."
#property description "An optional same-tick conflict filter can skip new entries when enabled modes disagree."
#property description "TP/SL are virtual: the EA and terminal must remain running."
#property description "Requested volume is normalized to the symbol minimum, maximum and volume step."
#property description "No external indicators, DLLs, custom symbols or offline charts are required."

enum ENUM_GDS_BB_MODE
  {
   GDS_BB_BREAKOUT=0,
   GDS_BB_REENTRY=1,
   GDS_BB_MIDLINE_CROSS=2,
   GDS_BB_SQUEEZE_BREAKOUT=3
  };

// -------------------------------------------------------------------
// Common execution settings
// -------------------------------------------------------------------
input group "Common execution"
input double InpLots                  = 0.01;       // Requested fixed lot
input ulong  InpMagic                 = 26091150;   // Base magic; four mode magics are Base+1...Base+4
input int    InpMaxPositions          = 4;          // Maximum simultaneous GDS positions (1..4)
input bool   InpSkipOppositeSignals   = true;       // Safety filter: skip new same-tick entries when modes disagree

// -------------------------------------------------------------------
// Mode 1: Breakout - real-tick verified profile
// -------------------------------------------------------------------
input group "1. Breakout"
input bool   InpBreakoutEnabled       = true;       // Enable Breakout mode
input double InpBreakoutBrickSize     = 17.0;       // Renko brick size
input int    InpBreakoutBBPeriod      = 20;         // Bollinger period
input double InpBreakoutDeviation     = 1.0;        // Bollinger deviation
input int    InpBreakoutEntryRun      = 2;          // Minimum same-direction Renko run
input double InpBreakoutTP            = 24.0;       // Virtual TP, bricks
input double InpBreakoutSL            = 42.0;       // Virtual SL, bricks
input int    InpBreakoutMaxHold       = 1230;       // Maximum hold, minutes
input int    InpBreakoutCooldown      = 5;          // Cooldown after exit, completed mode bricks
input double InpBreakoutMaxSpread     = 0.35;       // Max spread / mode brick size

// -------------------------------------------------------------------
// Mode 2: Re-entry / Mean Reversion - real-tick verified profile
// -------------------------------------------------------------------
input group "2. Re-entry / Mean Reversion"
input bool   InpReentryEnabled        = true;       // Enable Re-entry mode
input double InpReentryBrickSize      = 30.0;       // Renko brick size
input int    InpReentryBBPeriod       = 31;         // Bollinger period
input double InpReentryDeviation      = 1.2;        // Bollinger deviation
input int    InpReentryEntryRun       = 1;          // Minimum same-direction Renko run
input double InpReentryTP             = 28.0;       // Virtual TP, bricks
input double InpReentrySL             = 48.5;       // Virtual SL, bricks
input int    InpReentryMaxHold        = 2580;       // Maximum hold, minutes
input int    InpReentryCooldown       = 3;          // Cooldown after exit, completed mode bricks
input double InpReentryMaxSpread      = 0.35;       // Max spread / mode brick size

// -------------------------------------------------------------------
// Mode 3: Midline Cross - real-tick verified profile
// -------------------------------------------------------------------
input group "3. Midline Cross"
input bool   InpMidlineEnabled        = true;       // Enable Midline Cross mode
input double InpMidlineBrickSize      = 30.0;       // Renko brick size
input int    InpMidlineBBPeriod       = 5;          // Bollinger period
input double InpMidlineDeviation      = 3.0;        // Bollinger deviation
input int    InpMidlineEntryRun       = 1;          // Minimum same-direction Renko run
input double InpMidlineTP             = 10.0;       // Virtual TP, bricks
input double InpMidlineSL             = 34.5;       // Virtual SL, bricks
input int    InpMidlineMaxHold        = 2220;       // Maximum hold, minutes
input int    InpMidlineCooldown       = 3;          // Cooldown after exit, completed mode bricks
input double InpMidlineMaxSpread      = 0.35;       // Max spread / mode brick size

// -------------------------------------------------------------------
// Mode 4: Squeeze Breakout - real-tick verified profile
// -------------------------------------------------------------------
input group "4. Squeeze Breakout"
input bool   InpSqueezeEnabled        = true;       // Enable Squeeze Breakout mode
input double InpSqueezeBrickSize      = 14.0;       // Renko brick size
input int    InpSqueezeBBPeriod       = 18;         // Bollinger period
input double InpSqueezeDeviation      = 2.4;        // Bollinger deviation
input double InpSqueezeMaxWidth       = 34.5;       // Maximum full band width, in bricks
input int    InpSqueezeEntryRun       = 1;          // Minimum same-direction Renko run
input double InpSqueezeTP             = 26.0;       // Virtual TP, bricks
input double InpSqueezeSL             = 31.0;       // Virtual SL, bricks
input int    InpSqueezeMaxHold        = 2050;       // Maximum hold, minutes
input int    InpSqueezeCooldown       = 1;          // Cooldown after exit, completed mode bricks
input double InpSqueezeMaxSpread      = 0.35;       // Max spread / mode brick size

struct SRenkoBrick
  {
   double open;
   double close;
   int    direction;
   int    run;
  };

struct SModeTickResult
  {
   int    completed;
   int    signal;
   int    raw_signal;
   double final_close;
   bool   bb_ready;
   double bb_mid;
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
//| Causal Bollinger state from PREVIOUS completed Renko closes      |
//+------------------------------------------------------------------+
class CRenkoBollinger
  {
private:
   int      m_period;
   int      m_count;
   double   m_closes[];
   bool     m_prev_ready;
   int      m_prev_relation;
   int      m_prev_mid_side;
   bool     m_last_ready;
   double   m_last_mid;

   void Append(const double close)
     {
      if(m_count<m_period)
        {
         m_closes[m_count]=close;
         m_count++;
         return;
        }
      for(int i=1;i<m_period;i++) m_closes[i-1]=m_closes[i];
      m_closes[m_period-1]=close;
     }

   bool Bands(const double deviation,double &mid,double &upper,double &lower)
     {
      if(m_count<m_period || m_period<2) return false;
      double sum=0.0;
      for(int i=0;i<m_period;i++) sum+=m_closes[i];
      mid=sum/(double)m_period;

      double variance=0.0;
      for(int i=0;i<m_period;i++)
        {
         const double d=m_closes[i]-mid;
         variance+=d*d;
        }
      variance/=double(m_period);
      const double sd=MathSqrt(MathMax(0.0,variance));
      upper=mid+deviation*sd;
      lower=mid-deviation*sd;
      return true;
     }

public:
   void Init(const int period)
     {
      m_period=period;
      m_count=0;
      ArrayResize(m_closes,m_period);
      ArrayInitialize(m_closes,0.0);
      m_prev_ready=false;
      m_prev_relation=0;
      m_prev_mid_side=0;
      m_last_ready=false;
      m_last_mid=0.0;
     }

   int Push(const SRenkoBrick &brick,const ENUM_GDS_BB_MODE mode,
            const double deviation,const double brick_size,
            const double squeeze_max_width_bricks)
     {
      double mid=0.0,upper=0.0,lower=0.0;
      if(!Bands(deviation,mid,upper,lower))
        {
         Append(brick.close);
         m_last_ready=false;
         return 0;
        }

      int relation=0;
      if(brick.close>upper) relation=1;
      else if(brick.close<lower) relation=-1;

      const int mid_side=(brick.close>=mid ? 1 : -1);
      const double width_bricks=(brick_size>0.0 ? (upper-lower)/brick_size : 0.0);

      int signal=0;
      if(mode==GDS_BB_BREAKOUT)
        {
         if(relation>0 && brick.direction>0) signal=1;
         else if(relation<0 && brick.direction<0) signal=-1;
        }
      else if(mode==GDS_BB_REENTRY)
        {
         if(m_prev_ready && m_prev_relation<0 && relation>=0 && brick.direction>0) signal=1;
         else if(m_prev_ready && m_prev_relation>0 && relation<=0 && brick.direction<0) signal=-1;
        }
      else if(mode==GDS_BB_MIDLINE_CROSS)
        {
         if(m_prev_ready && m_prev_mid_side<0 && mid_side>0 && brick.direction>0) signal=1;
         else if(m_prev_ready && m_prev_mid_side>0 && mid_side<0 && brick.direction<0) signal=-1;
        }
      else if(mode==GDS_BB_SQUEEZE_BREAKOUT)
        {
         if(width_bricks<=squeeze_max_width_bricks)
           {
            if(relation>0 && brick.direction>0) signal=1;
            else if(relation<0 && brick.direction<0) signal=-1;
           }
        }

      m_last_ready=true;
      m_last_mid=mid;
      m_prev_ready=true;
      m_prev_relation=relation;
      m_prev_mid_side=mid_side;
      Append(brick.close);
      return signal;
     }

   bool Ready(void) const { return m_last_ready; }
   double Mid(void) const { return m_last_mid; }
  };

//+------------------------------------------------------------------+
//| One independent Renko+Bollinger engine                           |
//+------------------------------------------------------------------+
class CModeEngine
  {
private:
   bool              m_enabled;
   ENUM_GDS_BB_MODE  m_mode;
   string            m_name;
   double            m_requested_brick;
   double            m_effective_brick;
   int               m_period;
   double            m_deviation;
   double            m_squeeze_width;
   int               m_entry_run;
   double            m_tp;
   double            m_sl;
   int               m_max_hold;
   int               m_cooldown_setting;
   int               m_cooldown_left;
   double            m_max_spread;
   bool              m_failed;
   CRenkoBuilder     m_renko;
   CRenkoBollinger   m_bb;

public:
   bool Configure(const bool enabled,const ENUM_GDS_BB_MODE mode,const string name,
                  const double tick_size,const double requested_brick,
                  const int period,const double deviation,const double squeeze_width,
                  const int entry_run,const double tp,const double sl,
                  const int max_hold,const int cooldown,const double max_spread)
     {
      m_enabled=enabled;
      m_mode=mode;
      m_name=name;
      m_requested_brick=requested_brick;
      m_effective_brick=0.0;
      m_period=period;
      m_deviation=deviation;
      m_squeeze_width=squeeze_width;
      m_entry_run=entry_run;
      m_tp=tp;
      m_sl=sl;
      m_max_hold=max_hold;
      m_cooldown_setting=cooldown;
      m_cooldown_left=0;
      m_max_spread=max_spread;
      m_failed=false;

      if(!m_enabled) return true;
      if(!MathIsValidNumber(requested_brick) || requested_brick<=0.0 ||
         period<2 || period>500 ||
         !MathIsValidNumber(deviation) || deviation<=0.0 || deviation>10.0 ||
         !MathIsValidNumber(squeeze_width) || squeeze_width<=0.0 || squeeze_width>1000.0 ||
         entry_run<1 || entry_run>50 ||
         !MathIsValidNumber(tp) || tp<=0.0 ||
         !MathIsValidNumber(sl) || sl<=0.0 ||
         max_hold<0 || cooldown<0 ||
         !MathIsValidNumber(max_spread) || max_spread<=0.0) return false;

      const double units_raw=requested_brick/tick_size;
      if(!MathIsValidNumber(units_raw) || units_raw<0.5 || units_raw>1.0e9) return false;
      const long units=(long)MathMax(1.0,MathRound(units_raw));
      m_effective_brick=(double)units*tick_size;
      m_renko.Init(tick_size,units);
      m_bb.Init(period);
      return true;
     }

   void PushPrice(const double price,SModeTickResult &out)
     {
      out.completed=0;
      out.signal=0;
      out.raw_signal=0;
      out.final_close=0.0;
      out.bb_ready=false;
      out.bb_mid=0.0;
      if(!m_enabled || m_failed) return;

      SRenkoBrick bricks[];
      const int n=m_renko.PushPrice(price,bricks);
      if(n<0)
        {
         m_failed=true;
         Print("GDS Bollinger ",m_name,": excessive gap/memory failure; new entries paused for this mode.");
         return;
        }
      if(n==0) return;

      out.completed=n;
      for(int i=0;i<n;i++)
        {
         const int raw=m_bb.Push(bricks[i],m_mode,m_deviation,m_effective_brick,m_squeeze_width);
         int signal=0;
         if(raw!=0 && bricks[i].run>=m_entry_run && bricks[i].direction==raw) signal=raw;

         // Only the newest completed brick on this tick may provide the final signal.
         out.signal=signal;
         out.raw_signal=raw;
         out.final_close=bricks[i].close;
         out.bb_ready=m_bb.Ready();
         out.bb_mid=m_bb.Mid();
        }

      if(m_cooldown_left>0)
        {
         m_cooldown_left-=n;
         if(m_cooldown_left<0) m_cooldown_left=0;
        }
     }

   bool Enabled(void) const { return m_enabled; }
   string Name(void) const { return m_name; }
   double EffectiveBrick(void) const { return m_effective_brick; }
   double TakeProfit(void) const { return m_tp; }
   double StopLoss(void) const { return m_sl; }
   int MaxHold(void) const { return m_max_hold; }
   int CooldownLeft(void) const { return m_cooldown_left; }
   double MaxSpread(void) const { return m_max_spread; }
   void StartCooldown(void) { m_cooldown_left=m_cooldown_setting; }
  };

CModeEngine g_breakout;
CModeEngine g_reentry;
CModeEngine g_midline;
CModeEngine g_squeeze;

//+------------------------------------------------------------------+
ulong ModeMagic(const int mode)
  {
   return InpMagic+(ulong)(mode+1);
  }

//+------------------------------------------------------------------+
bool IsOurMagic(const ulong magic,int &mode)
  {
   for(int i=0;i<4;i++)
     {
      if(magic==ModeMagic(i))
        {
         mode=i;
         return true;
        }
     }
   mode=-1;
   return false;
  }

//+------------------------------------------------------------------+
string ModeName(const int mode)
  {
   if(mode==GDS_BB_BREAKOUT) return "Breakout";
   if(mode==GDS_BB_REENTRY) return "Re-entry";
   if(mode==GDS_BB_MIDLINE_CROSS) return "Midline";
   if(mode==GDS_BB_SQUEEZE_BREAKOUT) return "Squeeze";
   return "Unknown";
  }

//+------------------------------------------------------------------+
bool ModeEnabled(const int mode)
  {
   if(mode==GDS_BB_BREAKOUT) return g_breakout.Enabled();
   if(mode==GDS_BB_REENTRY) return g_reentry.Enabled();
   if(mode==GDS_BB_MIDLINE_CROSS) return g_midline.Enabled();
   if(mode==GDS_BB_SQUEEZE_BREAKOUT) return g_squeeze.Enabled();
   return false;
  }

//+------------------------------------------------------------------+
double ModeBrick(const int mode)
  {
   if(mode==GDS_BB_BREAKOUT) return g_breakout.EffectiveBrick();
   if(mode==GDS_BB_REENTRY) return g_reentry.EffectiveBrick();
   if(mode==GDS_BB_MIDLINE_CROSS) return g_midline.EffectiveBrick();
   if(mode==GDS_BB_SQUEEZE_BREAKOUT) return g_squeeze.EffectiveBrick();
   return 0.0;
  }

//+------------------------------------------------------------------+
double ModeTP(const int mode)
  {
   if(mode==GDS_BB_BREAKOUT) return g_breakout.TakeProfit();
   if(mode==GDS_BB_REENTRY) return g_reentry.TakeProfit();
   if(mode==GDS_BB_MIDLINE_CROSS) return g_midline.TakeProfit();
   if(mode==GDS_BB_SQUEEZE_BREAKOUT) return g_squeeze.TakeProfit();
   return 0.0;
  }

//+------------------------------------------------------------------+
double ModeSL(const int mode)
  {
   if(mode==GDS_BB_BREAKOUT) return g_breakout.StopLoss();
   if(mode==GDS_BB_REENTRY) return g_reentry.StopLoss();
   if(mode==GDS_BB_MIDLINE_CROSS) return g_midline.StopLoss();
   if(mode==GDS_BB_SQUEEZE_BREAKOUT) return g_squeeze.StopLoss();
   return 0.0;
  }

//+------------------------------------------------------------------+
int ModeMaxHold(const int mode)
  {
   if(mode==GDS_BB_BREAKOUT) return g_breakout.MaxHold();
   if(mode==GDS_BB_REENTRY) return g_reentry.MaxHold();
   if(mode==GDS_BB_MIDLINE_CROSS) return g_midline.MaxHold();
   if(mode==GDS_BB_SQUEEZE_BREAKOUT) return g_squeeze.MaxHold();
   return 0;
  }

//+------------------------------------------------------------------+
int ModeCooldownLeft(const int mode)
  {
   if(mode==GDS_BB_BREAKOUT) return g_breakout.CooldownLeft();
   if(mode==GDS_BB_REENTRY) return g_reentry.CooldownLeft();
   if(mode==GDS_BB_MIDLINE_CROSS) return g_midline.CooldownLeft();
   if(mode==GDS_BB_SQUEEZE_BREAKOUT) return g_squeeze.CooldownLeft();
   return 0;
  }

//+------------------------------------------------------------------+
void StartModeCooldown(const int mode)
  {
   if(mode==GDS_BB_BREAKOUT) g_breakout.StartCooldown();
   else if(mode==GDS_BB_REENTRY) g_reentry.StartCooldown();
   else if(mode==GDS_BB_MIDLINE_CROSS) g_midline.StartCooldown();
   else if(mode==GDS_BB_SQUEEZE_BREAKOUT) g_squeeze.StartCooldown();
  }

//+------------------------------------------------------------------+
bool ModeSpreadIsAcceptable(const int mode,const MqlTick &tick)
  {
   double max_fraction=0.0;
   if(mode==GDS_BB_BREAKOUT) max_fraction=g_breakout.MaxSpread();
   else if(mode==GDS_BB_REENTRY) max_fraction=g_reentry.MaxSpread();
   else if(mode==GDS_BB_MIDLINE_CROSS) max_fraction=g_midline.MaxSpread();
   else if(mode==GDS_BB_SQUEEZE_BREAKOUT) max_fraction=g_squeeze.MaxSpread();
   else return false;

   const double brick=ModeBrick(mode);
   if(brick<=0.0 || max_fraction<=0.0) return false;
   return ((tick.ask-tick.bid)<=brick*max_fraction);
  }

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
bool IsHedgingAccount(void)
  {
   return ((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
  }

//+------------------------------------------------------------------+
int EffectiveMaxPositions(void)
  {
   if(!IsHedgingAccount()) return 1;
   return MathMax(1,MathMin(4,InpMaxPositions));
  }

//+------------------------------------------------------------------+
bool PositionExists(const ulong ticket)
  {
   if(ticket==0) return false;
   return PositionSelectByTicket(ticket);
  }

//+------------------------------------------------------------------+
bool FindModePosition(const int wanted_mode,ulong &ticket,long &type,double &volume,
                      double &open_price,datetime &open_time,ulong &position_magic)
  {
   ticket=0;
   type=-1;
   volume=0.0;
   open_price=0.0;
   open_time=0;
   position_magic=0;
   if(wanted_mode<0 || wanted_mode>3) return false;

   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      const ulong t=PositionGetTicket(i);
      if(t==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      const ulong magic=(ulong)PositionGetInteger(POSITION_MAGIC);
      int mode=-1;
      if(!IsOurMagic(magic,mode) || mode!=wanted_mode) continue;

      ticket=t;
      type=PositionGetInteger(POSITION_TYPE);
      volume=PositionGetDouble(POSITION_VOLUME);
      open_price=PositionGetDouble(POSITION_PRICE_OPEN);
      open_time=(datetime)PositionGetInteger(POSITION_TIME);
      position_magic=magic;
      return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
bool ModeHasPosition(const int mode)
  {
   ulong ticket=0,magic=0;
   long type=-1;
   double volume=0.0,open_price=0.0;
   datetime open_time=0;
   return FindModePosition(mode,ticket,type,volume,open_price,open_time,magic);
  }

//+------------------------------------------------------------------+
int CountOurPositions(void)
  {
   int count=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      const ulong t=PositionGetTicket(i);
      if(t==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      int mode=-1;
      if(IsOurMagic((ulong)PositionGetInteger(POSITION_MAGIC),mode)) count++;
     }
   return count;
  }

//+------------------------------------------------------------------+
bool ExternalPositionOnSymbol(void)
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      const ulong t=PositionGetTicket(i);
      if(t==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      int mode=-1;
      if(!IsOurMagic((ulong)PositionGetInteger(POSITION_MAGIC),mode)) return true;
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
      if(!only_ours) return true;
      int mode=-1;
      if(IsOurMagic((ulong)OrderGetInteger(ORDER_MAGIC),mode)) return true;
     }
   return false;
  }

bool     g_exit_pending[4];
string   g_exit_reason[4];
ulong    g_exit_ticket[4];
int      g_pending_entry_dir[4];
datetime g_pending_entry_time[4];
bool     g_request_this_tick=false;
datetime g_retry_after=0;
datetime g_request_session_end=0;
int      g_request_failures=0;
ulong    g_wait_order=0;
bool     g_execution_uncertain=false;
bool     g_uncertain_exit=false;
int      g_uncertain_mode=-1;
ulong    g_uncertain_ticket=0;
const int GDS_MAX_REQUEST_FAILURES=3;
const int GDS_ENTRY_QUEUE_TTL=120;

//+------------------------------------------------------------------+
bool AnyPendingExit(void)
  {
   for(int mode=0;mode<4;mode++) if(g_exit_pending[mode]) return true;
   return false;
  }

//+------------------------------------------------------------------+
int PendingEntryCount(void)
  {
   int count=0;
   for(int mode=0;mode<4;mode++) if(g_pending_entry_dir[mode]!=0) count++;
   return count;
  }

//+------------------------------------------------------------------+
void ClearPendingEntry(const int mode)
  {
   if(mode<0 || mode>3) return;
   g_pending_entry_dir[mode]=0;
   g_pending_entry_time[mode]=0;
  }

//+------------------------------------------------------------------+
void MarkExitCompleted(const int mode)
  {
   if(mode<0 || mode>3) return;
   StartModeCooldown(mode);
   g_exit_pending[mode]=false;
   g_exit_reason[mode]="";
   g_exit_ticket[mode]=0;
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
      bool resolved=false;
      if(g_uncertain_exit)
         resolved=!PositionExists(g_uncertain_ticket);
      else if(g_uncertain_mode>=0 && g_uncertain_mode<4)
         resolved=ModeHasPosition(g_uncertain_mode);

      if(resolved)
        {
         g_execution_uncertain=false;
         g_uncertain_mode=-1;
         g_uncertain_ticket=0;
        }
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

   Print("GDS Renko Bollinger 4-Mode: request deferred. Retcode ",retcode,
         ", ",details,", next attempt no earlier than ",
         TimeToString(g_retry_after,TIME_DATE|TIME_SECONDS));
  }

//+------------------------------------------------------------------+
bool SubmitDeal(MqlTradeRequest &request,const bool is_exit,const int owner_mode,const ulong position_ticket=0)
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
         g_uncertain_mode=owner_mode;
         g_uncertain_ticket=position_ticket;
         g_wait_order=result.order;
         Print("GDS Renko Bollinger 4-Mode: execution unconfirmed; requests paused.");
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
      g_uncertain_mode=owner_mode;
      g_uncertain_ticket=position_ticket;
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
void RequestExit(const string reason,const int owner_mode,const ulong ticket)
  {
   if(owner_mode<0 || owner_mode>3 || ticket==0) return;
   if(!g_exit_pending[owner_mode])
     {
      g_exit_reason[owner_mode]=reason;
      g_exit_ticket[owner_mode]=ticket;
     }
   g_exit_pending[owner_mode]=true;
   ClearPendingEntry(owner_mode);
  }

//+------------------------------------------------------------------+
bool SendMarket(const int direction,const int owner_mode)
  {
   if(direction!=1 && direction!=-1) return false;
   if(owner_mode<0 || owner_mode>3 || !ModeEnabled(owner_mode)) return false;
   if(AnyPendingExit() || ModeHasPosition(owner_mode) || HasActiveOrder(false)) return false;
   if(CountOurPositions()>=EffectiveMaxPositions()) return false;
   if(ExternalPositionOnSymbol()) return false;
   if(!TradeModeAllowsEntry(direction)) return false;
   if((SymbolInfoInteger(_Symbol,SYMBOL_ORDER_MODE)&SYMBOL_ORDER_MARKET)==0) return false;

   MqlTick tick={};
   if(!SymbolInfoTick(_Symbol,tick) || !ValidTick(tick)) return false;
   if(!ModeSpreadIsAcceptable(owner_mode,tick)) return false;

   MqlTradeRequest request={};
   if(!GetFillingMode(request.type_filling)) return false;
   request.volume=NormalizeVolume(InpLots);
   if(request.volume<=0.0) return false;

   request.action=TRADE_ACTION_DEAL;
   request.magic=ModeMagic(owner_mode);
   request.symbol=_Symbol;
   request.deviation=50;
   request.comment="GDS BB "+ModeName(owner_mode);
   request.type=(direction>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   request.price=(direction>0 ? tick.ask : tick.bid);
   if(!SubmitDeal(request,false,owner_mode,0)) return false;
   Print("GDS Renko Bollinger entry: ",ModeName(owner_mode)," ",(direction>0 ? "BUY" : "SELL"));
   return true;
  }

//+------------------------------------------------------------------+
bool ClosePositionByTicket(const int owner_mode,const ulong ticket,const string reason)
  {
   if(owner_mode<0 || owner_mode>3 || ticket==0) return false;
   if(!PositionSelectByTicket(ticket))
     {
      MarkExitCompleted(owner_mode);
      return true;
     }

   const ulong magic=(ulong)PositionGetInteger(POSITION_MAGIC);
   int actual_mode=-1;
   if(PositionGetString(POSITION_SYMBOL)!=_Symbol || !IsOurMagic(magic,actual_mode) || actual_mode!=owner_mode)
     {
      g_exit_pending[owner_mode]=false;
      g_exit_reason[owner_mode]="";
      g_exit_ticket[owner_mode]=0;
      return false;
     }

   if(!TradeModeAllowsClose() || HasActiveOrder(true)) return false;

   const long type=PositionGetInteger(POSITION_TYPE);
   const double volume=PositionGetDouble(POSITION_VOLUME);
   MqlTick tick={};
   if(!SymbolInfoTick(_Symbol,tick) || !ValidTick(tick)) return false;

   MqlTradeRequest request={};
   if(!GetFillingMode(request.type_filling)) return false;
   request.action=TRADE_ACTION_DEAL;
   request.magic=magic;
   request.position=ticket;
   request.symbol=_Symbol;
   request.volume=volume;
   request.deviation=50;
   request.comment="GDS BB exit";
   request.type=(type==POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY);
   request.price=(type==POSITION_TYPE_BUY ? tick.bid : tick.ask);

   if(!SubmitDeal(request,true,owner_mode,ticket)) return false;
   Print("GDS Renko Bollinger exit request: ",ModeName(owner_mode)," ",reason);
   return true;
  }

//+------------------------------------------------------------------+
void TryPendingExit(void)
  {
   if(!ResolveExecution()) return;
   for(int mode=0;mode<4;mode++)
     {
      if(!g_exit_pending[mode]) continue;
      const ulong ticket=g_exit_ticket[mode];
      if(ticket==0 || !PositionExists(ticket))
        {
         Print("GDS Renko Bollinger exit completed: ",ModeName(mode)," ",g_exit_reason[mode]);
         MarkExitCompleted(mode);
         continue;
        }
      ClosePositionByTicket(mode,ticket,g_exit_reason[mode]);
      return; // Serialize trade requests: at most one request per tick.
     }
  }

//+------------------------------------------------------------------+
void CheckPriceExits(const MqlTick &tick)
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      const ulong ticket=PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;

      int owner=-1;
      if(!IsOurMagic((ulong)PositionGetInteger(POSITION_MAGIC),owner)) continue;
      if(owner<0 || owner>3 || g_exit_pending[owner]) continue;

      const long type=PositionGetInteger(POSITION_TYPE);
      const double open_price=PositionGetDouble(POSITION_PRICE_OPEN);
      const datetime open_time=(datetime)PositionGetInteger(POSITION_TIME);
      const int direction=(type==POSITION_TYPE_BUY ? 1 : -1);
      const double executable=(direction>0 ? tick.bid : tick.ask);
      if(executable<=0.0) continue;

      const double brick=ModeBrick(owner);
      const double tp=ModeTP(owner)*brick;
      const double sl=ModeSL(owner)*brick;
      const double move=direction*(executable-open_price);

      if(tp>0.0 && move>=tp) { RequestExit("TP",owner,ticket); continue; }
      if(sl>0.0 && move<=-sl) { RequestExit("SL",owner,ticket); continue; }

      const int max_hold=ModeMaxHold(owner);
      if(max_hold>0 && open_time>0)
        {
         const long held_seconds=(long)(TimeCurrent()-open_time);
         if(held_seconds>=(long)max_hold*60) RequestExit("TIME",owner,ticket);
        }
     }
  }

//+------------------------------------------------------------------+
void ProcessOwnerSignalExit(const int owner,const SModeTickResult &result)
  {
   if(result.completed<=0 || owner<0 || owner>3 || g_exit_pending[owner]) return;

   ulong ticket=0,magic=0;
   long type=-1;
   double volume=0.0,open_price=0.0;
   datetime open_time=0;
   if(!FindModePosition(owner,ticket,type,volume,open_price,open_time,magic)) return;

   const int position_direction=(type==POSITION_TYPE_BUY ? 1 : -1);
   if(owner==GDS_BB_REENTRY && result.bb_ready)
     {
      if(position_direction>0 && result.final_close>=result.bb_mid) RequestExit("BB_MID",owner,ticket);
      else if(position_direction<0 && result.final_close<=result.bb_mid) RequestExit("BB_MID",owner,ticket);
     }
   else if(result.raw_signal!=0 && result.raw_signal==-position_direction)
     {
      RequestExit("BB_OPPOSITE",owner,ticket);
     }
  }

//+------------------------------------------------------------------+
void QueueNewSignals(const int &signals[],const MqlTick &tick)
  {
   bool candidate[4]={false,false,false,false};
   bool long_signal=false;
   bool short_signal=false;

   for(int mode=0;mode<4;mode++)
     {
      if(!ModeEnabled(mode) || ModeCooldownLeft(mode)>0 || signals[mode]==0) continue;
      if(ModeHasPosition(mode) || g_pending_entry_dir[mode]!=0 || g_exit_pending[mode]) continue;
      if(!ModeSpreadIsAcceptable(mode,tick)) continue;
      candidate[mode]=true;
      if(signals[mode]>0) long_signal=true;
      if(signals[mode]<0) short_signal=true;
     }

   if(InpSkipOppositeSignals && long_signal && short_signal)
     {
      Print("GDS Renko Bollinger: opposite mode signals on the same tick; new entries skipped by input setting.");
      return;
     }

   int free_slots=EffectiveMaxPositions()-CountOurPositions()-PendingEntryCount();
   if(free_slots<=0) return;

   // Deterministic queue priority: Breakout -> Re-entry -> Midline -> Squeeze.
   for(int mode=0;mode<4 && free_slots>0;mode++)
     {
      if(!candidate[mode]) continue;
      g_pending_entry_dir[mode]=signals[mode];
      g_pending_entry_time[mode]=TimeCurrent();
      free_slots--;
     }
  }

//+------------------------------------------------------------------+
void TryPendingEntry(const MqlTick &tick)
  {
   if(AnyPendingExit() || HasActiveOrder(false) || ExternalPositionOnSymbol()) return;
   if(CountOurPositions()>=EffectiveMaxPositions()) return;

   const datetime now=TimeCurrent();
   for(int mode=0;mode<4;mode++)
     {
      const int direction=g_pending_entry_dir[mode];
      if(direction==0) continue;

      if(g_pending_entry_time[mode]>0 && now-g_pending_entry_time[mode]>GDS_ENTRY_QUEUE_TTL)
        {
         ClearPendingEntry(mode);
         continue;
        }
      if(!ModeEnabled(mode) || ModeCooldownLeft(mode)>0 || ModeHasPosition(mode))
        {
         ClearPendingEntry(mode);
         continue;
        }
      if(!ModeSpreadIsAcceptable(mode,tick)) continue;
      if(!TradeModeAllowsEntry(direction)) continue;

      if(SendMarket(direction,mode)) ClearPendingEntry(mode);
      return; // One trade request per tick; remaining queued modes are handled on following ticks.
     }
  }

//+------------------------------------------------------------------+
void UpdateAllModesAndTrade(const double price,const MqlTick &tick)
  {
   SModeTickResult r0={};
   SModeTickResult r1={};
   SModeTickResult r2={};
   SModeTickResult r3={};

   g_breakout.PushPrice(price,r0);
   g_reentry.PushPrice(price,r1);
   g_midline.PushPrice(price,r2);
   g_squeeze.PushPrice(price,r3);

   ProcessOwnerSignalExit(GDS_BB_BREAKOUT,r0);
   ProcessOwnerSignalExit(GDS_BB_REENTRY,r1);
   ProcessOwnerSignalExit(GDS_BB_MIDLINE_CROSS,r2);
   ProcessOwnerSignalExit(GDS_BB_SQUEEZE_BREAKOUT,r3);

   if(AnyPendingExit()) return;

   int signals[4]={r0.signal,r1.signal,r2.signal,r3.signal};
   QueueNewSignals(signals,tick);
   TryPendingEntry(tick);
  }

//+------------------------------------------------------------------+
int OnInit(void)
  {
   if(!MathIsValidNumber(InpLots) || InpLots<=0.0 || InpMagic==0 ||
      InpMaxPositions<1 || InpMaxPositions>4)
     {
      Print("GDS Renko Bollinger 4-Mode: invalid common inputs.");
      return INIT_PARAMETERS_INCORRECT;
     }

   if(!InpBreakoutEnabled && !InpReentryEnabled && !InpMidlineEnabled && !InpSqueezeEnabled)
     {
      Print("GDS Renko Bollinger 4-Mode: enable at least one strategy mode.");
      return INIT_PARAMETERS_INCORRECT;
     }

   const double tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(!MathIsValidNumber(tick_size) || tick_size<=0.0)
     {
      Print("GDS Bollinger: symbol tick size unavailable.");
      return INIT_FAILED;
     }

   const double effective_volume=NormalizeVolume(InpLots);
   if(effective_volume<=0.0)
     {
      Print("GDS Bollinger: symbol volume settings unavailable or invalid.");
      return INIT_FAILED;
     }

   if(!g_breakout.Configure(InpBreakoutEnabled,GDS_BB_BREAKOUT,"Breakout",tick_size,
                            InpBreakoutBrickSize,InpBreakoutBBPeriod,InpBreakoutDeviation,1.0,
                            InpBreakoutEntryRun,InpBreakoutTP,InpBreakoutSL,
                            InpBreakoutMaxHold,InpBreakoutCooldown,InpBreakoutMaxSpread) ||
      !g_reentry.Configure(InpReentryEnabled,GDS_BB_REENTRY,"Re-entry",tick_size,
                           InpReentryBrickSize,InpReentryBBPeriod,InpReentryDeviation,1.0,
                           InpReentryEntryRun,InpReentryTP,InpReentrySL,
                           InpReentryMaxHold,InpReentryCooldown,InpReentryMaxSpread) ||
      !g_midline.Configure(InpMidlineEnabled,GDS_BB_MIDLINE_CROSS,"Midline",tick_size,
                           InpMidlineBrickSize,InpMidlineBBPeriod,InpMidlineDeviation,1.0,
                           InpMidlineEntryRun,InpMidlineTP,InpMidlineSL,
                           InpMidlineMaxHold,InpMidlineCooldown,InpMidlineMaxSpread) ||
      !g_squeeze.Configure(InpSqueezeEnabled,GDS_BB_SQUEEZE_BREAKOUT,"Squeeze",tick_size,
                           InpSqueezeBrickSize,InpSqueezeBBPeriod,InpSqueezeDeviation,InpSqueezeMaxWidth,
                           InpSqueezeEntryRun,InpSqueezeTP,InpSqueezeSL,
                           InpSqueezeMaxHold,InpSqueezeCooldown,InpSqueezeMaxSpread))
     {
      Print("GDS Renko Bollinger 4-Mode: invalid enabled-mode inputs.");
      return INIT_PARAMETERS_INCORRECT;
     }

   for(int mode=0;mode<4;mode++)
     {
      g_exit_pending[mode]=false;
      g_exit_reason[mode]="";
      g_exit_ticket[mode]=0;
      g_pending_entry_dir[mode]=0;
      g_pending_entry_time[mode]=0;
     }
   g_request_this_tick=false;
   g_retry_after=0;
   g_request_session_end=0;
   g_request_failures=0;
   g_wait_order=0;
   g_execution_uncertain=false;
   g_uncertain_exit=false;
   g_uncertain_mode=-1;
   g_uncertain_ticket=0;

   Print("GDS Renko Bollinger 4-Mode v1.30 started. EffectiveLots=",DoubleToString(effective_volume,2),
         ", MaxPositions=",EffectiveMaxPositions(),
         ", SkipOppositeSameTick=",(InpSkipOppositeSignals ? "ON" : "OFF"),
         ", Account=",(IsHedgingAccount() ? "HEDGING" : "NETTING"),
         ", Breakout=",(InpBreakoutEnabled ? "ON" : "OFF"),
         ", Re-entry=",(InpReentryEnabled ? "ON" : "OFF"),
         ", Midline=",(InpMidlineEnabled ? "ON" : "OFF"),
         ", Squeeze=",(InpSqueezeEnabled ? "ON" : "OFF"));
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnTick(void)
  {
   g_request_this_tick=false;
   ResolveExecution();

   MqlTick tick={};
   if(!SymbolInfoTick(_Symbol,tick) || !ValidTick(tick)) return;

   // Exits always have priority over new entries.
   TryPendingExit();
   CheckPriceExits(tick);
   TryPendingExit();

   // Every enabled mode receives the same BID tick, but builds its own Renko stream.
   UpdateAllModesAndTrade(tick.bid,tick);

   // Completed-brick mode logic may request an exit now.
   TryPendingExit();
   if(!AnyPendingExit()) TryPendingEntry(tick);
  }
//+------------------------------------------------------------------+

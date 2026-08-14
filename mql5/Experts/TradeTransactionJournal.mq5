//+------------------------------------------------------------------+
//| TradeTransactionJournal.mq5                                      |
//| Read-only OnTradeTransaction journal (identifiers only).         |
//|                                                                  |
//| Official AlgoBook: the handler is asynchronous. A slow handler   |
//| stalls the transaction queue. This EA copies ids into a ring     |
//| and returns; OnTimer writes JSONL/CSV. No OrderSend. No network. |
//|                                                                  |
//| Output: MQL5/Files/mt5_arch/journal/                             |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.00"
#property description "Journals trade-transaction ids only — never places orders"
#property strict

#include <FxSymbolRegistry.mqh>

input string InpBroker   = "";                 // required: vantage|fpmarkets|exness|wsf
input string InpSymbol   = "";                 // optional canonical; empty = chart symbol
input int    InpTimerSec = 1;                  // flush interval (seconds)
input string InpOutDir   = "mt5_arch\\journal";

#define JOURNAL_Q_CAP 256

struct JournalIds
  {
   long     seq;
   ulong    request_id;
   ulong    order;
   ulong    deal;
   ulong    position;
   ulong    position_by;
   int      trans_type;
   int      order_type;
   int      deal_type;
   int      order_state;
   datetime time;
   string   symbol;
  };

JournalIds g_q[];
int        g_q_head = 0;
int        g_q_tail = 0;
int        g_q_n    = 0;
int        g_dropped = 0;
long       g_seq    = 0;
string     g_jsonl;
string     g_csv;
bool       g_csv_header = false;

//+------------------------------------------------------------------+
string JsonEsc(const string s)
  {
   string o = s;
   StringReplace(o, "\\", "\\\\");
   StringReplace(o, "\"", "\\\"");
   return o;
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   string broker = InpBroker;
   StringTrimLeft(broker);
   StringTrimRight(broker);
   StringToLower(broker);
   if(StringLen(broker) == 0)
     {
      Print("TradeTransactionJournal: InpBroker is required (vantage|fpmarkets|exness|wsf)");
      return INIT_PARAMETERS_INCORRECT;
     }

   FolderCreate("mt5_arch");
   if(!FolderCreate(InpOutDir))
      Print("TradeTransactionJournal: FolderCreate ", InpOutDir,
            " err=", GetLastError(), " (ok if exists)");

   ArrayResize(g_q, JOURNAL_Q_CAP);
   g_jsonl = InpOutDir + "\\events.jsonl";
   g_csv   = InpOutDir + "\\events.csv";
   g_csv_header = FileIsExist(g_csv, 0);

   string requested = InpSymbol;
   StringTrimLeft(requested);
   StringTrimRight(requested);
   if(StringLen(requested) == 0)
      requested = _Symbol;

   string canonical = "";
   string broker_sym = "";
   if(!FxRegistryLookup(broker, requested, canonical, broker_sym))
     {
      canonical = FxCanonicalFromBrokerSymbolAny(requested);
      broker_sym = requested;
     }

   WriteManifest(broker, requested, canonical, broker_sym);
   EventSetTimer((int)MathMax(1, InpTimerSec));
   Print("TradeTransactionJournal ON broker=", broker,
         " requested=", requested,
         " -> Files/", InpOutDir,
         " | ids only, NO ORDERS");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   FlushQueue();
  }

//+------------------------------------------------------------------+
void OnTick()
  {
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   FlushQueue();
  }

//+------------------------------------------------------------------+
//| Copy identifiers and return. No files, no loops, no network.     |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(g_q_n >= JOURNAL_Q_CAP)
     {
      g_dropped++;
      return;
     }
   JournalIds ev;
   ev.seq         = ++g_seq;
   ev.request_id  = result.request_id;
   ev.order       = (trans.order != 0) ? trans.order : request.order;
   ev.deal        = (trans.deal != 0) ? trans.deal : result.deal;
   ev.position    = (trans.position != 0) ? trans.position : request.position;
   ev.position_by = trans.position_by;
   ev.trans_type  = (int)trans.type;
   ev.order_type  = (int)trans.order_type;
   ev.deal_type   = (int)trans.deal_type;
   ev.order_state = (int)trans.order_state;
   ev.time        = TimeCurrent();
   ev.symbol      = trans.symbol;
   g_q[g_q_head]  = ev;
   g_q_head       = (g_q_head + 1) % JOURNAL_Q_CAP;
   g_q_n++;
  }

//+------------------------------------------------------------------+
void WriteManifest(const string broker, const string requested,
                   const string canonical, const string broker_sym)
  {
   string path = InpOutDir + "\\manifest.json";
   int h = FileOpen(path, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      Print("TradeTransactionJournal: manifest open fail err=", GetLastError());
      return;
     }
   FileWriteString(h, "{\n");
   FileWriteString(h, "  \"schema\": \"mt5-trade-journal/v1\",\n");
   FileWriteString(h, "  \"source\": \"mql5_export\",\n");
   FileWriteString(h, "  \"recorded_at\": \"" +
                  TimeToString(TimeGMT(), TIME_DATE|TIME_SECONDS) + "Z\",\n");
   FileWriteString(h, "  \"broker\": \"" + JsonEsc(broker) + "\",\n");
   FileWriteString(h, "  \"symbol\": {\n");
   FileWriteString(h, "    \"requested\": \"" + JsonEsc(requested) + "\",\n");
   FileWriteString(h, "    \"canonical\": \"" + JsonEsc(canonical) + "\",\n");
   FileWriteString(h, "    \"broker_symbol\": \"" + JsonEsc(broker_sym) + "\"\n");
   FileWriteString(h, "  },\n");
   FileWriteString(h, "  \"account\": {\n");
   FileWriteString(h, "    \"login\": " +
                  IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ",\n");
   FileWriteString(h, "    \"server\": \"" +
                  JsonEsc(AccountInfoString(ACCOUNT_SERVER)) + "\"\n");
   FileWriteString(h, "  },\n");
   FileWriteString(h, "  \"expert\": \"TradeTransactionJournal\",\n");
   FileWriteString(h, "  \"note\": \"OnTradeTransaction is asynchronous; this record is identifiers only. Slow handlers stall the queue.\"\n");
   FileWriteString(h, "}\n");
   FileClose(h);
  }

//+------------------------------------------------------------------+
void FlushQueue()
  {
   if(g_q_n <= 0)
      return;

   int hj = FileOpen(g_jsonl, FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(hj == INVALID_HANDLE)
     {
      Print("TradeTransactionJournal: jsonl open fail err=", GetLastError());
      return;
     }
   FileSeek(hj, 0, SEEK_END);

   int hc = FileOpen(g_csv, FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(hc == INVALID_HANDLE)
     {
      FileClose(hj);
      Print("TradeTransactionJournal: csv open fail err=", GetLastError());
      return;
     }
   FileSeek(hc, 0, SEEK_END);
   if(!g_csv_header || FileSize(hc) == 0)
     {
      FileWriteString(hc, "seq,time,trans_type,request_id,order,deal,position,position_by,symbol,order_type,deal_type,order_state\n");
      g_csv_header = true;
     }

   while(g_q_n > 0)
     {
      JournalIds ev = g_q[g_q_tail];
      g_q_tail = (g_q_tail + 1) % JOURNAL_Q_CAP;
      g_q_n--;
      FileWriteString(hj, FormatJsonl(ev) + "\n");
      FileWriteString(hc, FormatCsv(ev) + "\n");
     }
   FileClose(hj);
   FileClose(hc);
   if(g_dropped > 0)
      Print("TradeTransactionJournal: dropped=", g_dropped, " (queue full)");
  }

//+------------------------------------------------------------------+
string FormatJsonl(const JournalIds &ev)
  {
   string t = TimeToString(ev.time, TIME_DATE|TIME_SECONDS);
   string j = "{";
   j += "\"seq\":" + IntegerToString(ev.seq) + ",";
   j += "\"time\":\"" + t + "\",";
   j += "\"trans_type\":" + IntegerToString(ev.trans_type) + ",";
   j += "\"request_id\":" + IntegerToString((long)ev.request_id) + ",";
   j += "\"order\":" + IntegerToString((long)ev.order) + ",";
   j += "\"deal\":" + IntegerToString((long)ev.deal) + ",";
   j += "\"position\":" + IntegerToString((long)ev.position) + ",";
   j += "\"position_by\":" + IntegerToString((long)ev.position_by) + ",";
   j += "\"symbol\":\"" + JsonEsc(ev.symbol) + "\",";
   j += "\"order_type\":" + IntegerToString(ev.order_type) + ",";
   j += "\"deal_type\":" + IntegerToString(ev.deal_type) + ",";
   j += "\"order_state\":" + IntegerToString(ev.order_state);
   j += "}";
   return j;
  }

//+------------------------------------------------------------------+
string FormatCsv(const JournalIds &ev)
  {
   string line = IntegerToString(ev.seq);
   line += "," + TimeToString(ev.time, TIME_DATE|TIME_SECONDS);
   line += "," + IntegerToString(ev.trans_type);
   line += "," + IntegerToString((long)ev.request_id);
   line += "," + IntegerToString((long)ev.order);
   line += "," + IntegerToString((long)ev.deal);
   line += "," + IntegerToString((long)ev.position);
   line += "," + IntegerToString((long)ev.position_by);
   line += "," + ev.symbol;
   line += "," + IntegerToString(ev.order_type);
   line += "," + IntegerToString(ev.deal_type);
   line += "," + IntegerToString(ev.order_state);
   return line;
  }

//+------------------------------------------------------------------+
//| SAFETY: this EA never calls OrderSend / trade classes.           |
//+------------------------------------------------------------------+

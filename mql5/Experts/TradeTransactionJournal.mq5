//+------------------------------------------------------------------+
//| TradeTransactionJournal.mq5                                      |
//| Read-only OnTradeTransaction journal (identifiers only).         |
//|                                                                  |
//| Official AlgoBook: the handler is asynchronous. A slow handler   |
//| stalls the transaction queue. This EA copies ids into a ring     |
//| and returns; OnTimer writes JSONL/CSV. No OrderSend. No network. |
//|                                                                  |
//| Each OnInit opens a fresh session directory. Manifest create     |
//| failure aborts. Overflow consumes a sequence and is persisted.   |
//| Output: MQL5/Files/mt5_arch/journal/<session_id>/                |
//+------------------------------------------------------------------+
#property copyright   "mt5-arch-integration / trading"
#property link        "https://github.com/Trujillofa/mt5-arch-integration"
#property version     "1.10"
#property description "Journals trade-transaction ids only — never places orders"
#property strict

#include <FxSymbolRegistry.mqh>

input string InpBroker   = "";                 // required: vantage|fpmarkets|exness|wsf
input string InpSymbol   = "";                 // optional canonical; empty = chart symbol
input int    InpTimerSec = 1;                  // flush interval (seconds)
input string InpOutDir   = "mt5_arch\\journal";

#define JOURNAL_Q_CAP 256
#define OVERFLOW_CAP  64

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
   string   session_id;
   bool     overflow;
  };

JournalIds g_q[];
JournalIds g_overflow[];
long       g_overflow_seqs[];
int        g_q_head = 0;
int        g_q_tail = 0;
int        g_q_n    = 0;
int        g_dropped = 0;
int        g_overflow_n = 0;
int        g_overflow_seq_n = 0;
long       g_seq    = 0;
string     g_session = "";
string     g_session_dir = "";
string     g_jsonl;
string     g_csv;
string     g_overflow_path;
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
string MakeSessionId()
  {
   datetime now = TimeGMT();
   string id = "run-";
   id += IntegerToString((long)now);
   id += "-";
   id += IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));
   id += "-";
   id += IntegerToString((long)GetTickCount());
   return id;
  }

//+------------------------------------------------------------------+
bool InitSessionDir()
  {
   g_session = MakeSessionId();
   FolderCreate("mt5_arch");
   FolderCreate(InpOutDir);
   g_session_dir = InpOutDir + "\\" + g_session;
   if(FileIsExist(g_session_dir + "\\manifest.json", 0))
     {
      Print("TradeTransactionJournal: refuse overwrite of session ", g_session);
      return false;
     }
   if(!FolderCreate(g_session_dir) && !FileIsExist(g_session_dir, 0))
     {
      Print("TradeTransactionJournal: FolderCreate ", g_session_dir,
            " err=", GetLastError());
      return false;
     }
   g_jsonl = g_session_dir + "\\events.jsonl";
   g_csv   = g_session_dir + "\\events.csv";
   g_overflow_path = g_session_dir + "\\overflow.json";
   g_csv_header = false;
   return true;
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

   ArrayResize(g_q, JOURNAL_Q_CAP);
   ArrayResize(g_overflow, OVERFLOW_CAP);
   ArrayResize(g_overflow_seqs, OVERFLOW_CAP);

   string requested = InpSymbol;
   StringTrimLeft(requested);
   StringTrimRight(requested);
   if(StringLen(requested) == 0)
      requested = _Symbol;

   string canonical = "";
   string broker_sym = "";
   if(!FxRegistryLookup(broker, requested, canonical, broker_sym))
     {
      Print("TradeTransactionJournal: no exact registry mapping for ",
            broker, "/", requested, " (no any-broker fallback)");
      return INIT_PARAMETERS_INCORRECT;
     }

   if(!InitSessionDir())
      return INIT_FAILED;
   if(!WriteManifest(broker, requested, canonical, broker_sym))
      return INIT_FAILED;
   if(!WriteOverflow())
      return INIT_FAILED;

   EventSetTimer((int)MathMax(1, InpTimerSec));
   Print("TradeTransactionJournal ON broker=", broker,
         " requested=", requested,
         " session=", g_session,
         " -> Files/", g_session_dir,
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
void RecordOverflow()
  {
   g_dropped++;
   JournalIds ev;
   ev.seq         = ++g_seq;
   ev.request_id  = 0;
   ev.order       = 0;
   ev.deal        = 0;
   ev.position    = 0;
   ev.position_by = 0;
   ev.trans_type  = -1;
   ev.order_type  = 0;
   ev.deal_type   = 0;
   ev.order_state = 0;
   ev.time        = TimeCurrent();
   ev.symbol      = "";
   ev.session_id  = g_session;
   ev.overflow    = true;
   if(g_overflow_seq_n < OVERFLOW_CAP)
     {
      g_overflow_seqs[g_overflow_seq_n] = ev.seq;
      g_overflow_seq_n++;
     }
   if(g_overflow_n < OVERFLOW_CAP)
     {
      g_overflow[g_overflow_n] = ev;
      g_overflow_n++;
     }
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
      RecordOverflow();
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
   ev.session_id  = g_session;
   ev.overflow    = false;
   g_q[g_q_head]  = ev;
   g_q_head       = (g_q_head + 1) % JOURNAL_Q_CAP;
   g_q_n++;
  }

//+------------------------------------------------------------------+
bool WriteManifest(const string broker, const string requested,
                   const string canonical, const string broker_sym)
  {
   string path = g_session_dir + "\\manifest.json";
   if(FileIsExist(path, 0))
     {
      Print("TradeTransactionJournal: manifest already exists; refuse overwrite");
      return false;
     }
   int h = FileOpen(path, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      Print("TradeTransactionJournal: manifest open fail err=", GetLastError());
      return false;
     }
   FileWriteString(h, "{\n");
   FileWriteString(h, "  \"schema\": \"mt5-trade-journal/v1\",\n");
   FileWriteString(h, "  \"source\": \"mql5_export\",\n");
   FileWriteString(h, "  \"session_id\": \"" + JsonEsc(g_session) + "\",\n");
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
   FileWriteString(h, "  \"overflow\": {\n");
   FileWriteString(h, "    \"path\": \"overflow.json\"\n");
   FileWriteString(h, "  },\n");
   FileWriteString(h, "  \"note\": \"OnTradeTransaction is asynchronous; this record is identifiers only. Slow handlers stall the queue.\"\n");
   FileWriteString(h, "}\n");
   FileClose(h);
   return true;
  }

//+------------------------------------------------------------------+
bool WriteOverflow()
  {
   int h = FileOpen(g_overflow_path, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      Print("TradeTransactionJournal: overflow open fail err=", GetLastError());
      return false;
     }
   FileWriteString(h, "{\n");
   FileWriteString(h, "  \"dropped\": " + IntegerToString(g_dropped) + ",\n");
   FileWriteString(h, "  \"seqs\": [");
   for(int i = 0; i < g_overflow_seq_n; i++)
     {
      if(i > 0)
         FileWriteString(h, ",");
      FileWriteString(h, IntegerToString(g_overflow_seqs[i]));
     }
   FileWriteString(h, "],\n");
   FileWriteString(h, "  \"truncated\": ");
   FileWriteString(h, (g_dropped > g_overflow_seq_n) ? "true" : "false");
   FileWriteString(h, "\n}\n");
   FileClose(h);
   return true;
  }

//+------------------------------------------------------------------+
void FlushQueue()
  {
   if(g_q_n <= 0 && g_overflow_n <= 0)
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
      FileWriteString(hc, "seq,session_id,time,trans_type,request_id,order,deal,position,position_by,symbol,order_type,deal_type,order_state,overflow\n");
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
   for(int i = 0; i < g_overflow_n; i++)
     {
      FileWriteString(hj, FormatJsonl(g_overflow[i]) + "\n");
      FileWriteString(hc, FormatCsv(g_overflow[i]) + "\n");
     }
   g_overflow_n = 0;
   FileClose(hj);
   FileClose(hc);
   WriteOverflow();
  }

//+------------------------------------------------------------------+
string FormatJsonl(const JournalIds &ev)
  {
   string t = TimeToString(ev.time, TIME_DATE|TIME_SECONDS);
   string j = "{";
   j += "\"seq\":" + IntegerToString(ev.seq) + ",";
   j += "\"session_id\":\"" + JsonEsc(ev.session_id) + "\",";
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
   j += "\"order_state\":" + IntegerToString(ev.order_state) + ",";
   j += "\"overflow\":" + (ev.overflow ? "true" : "false");
   j += "}";
   return j;
  }

//+------------------------------------------------------------------+
string FormatCsv(const JournalIds &ev)
  {
   string line = IntegerToString(ev.seq);
   line += "," + ev.session_id;
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
   line += ",";
   line += ev.overflow ? "true" : "false";
   return line;
  }

//+------------------------------------------------------------------+
//| SAFETY: this EA never calls OrderSend / trade classes.           |
//+------------------------------------------------------------------+

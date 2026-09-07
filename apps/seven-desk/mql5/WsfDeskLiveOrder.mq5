//+------------------------------------------------------------------+
//| WsfDeskLiveOrder.mq5 — Seven Desk WSF-only one-shot OrderSend.   |
//| Hard-stops unless login==149736, server contains WSF, and the    |
//| request confirm token is WSF-149736. Market min-lot is default.  |
//| Pending US30 limits may use an explicit volume. No retry on a    |
//| rejected open. Not a copy engine. Not an EA.                     |
//+------------------------------------------------------------------+
#property copyright "seven-desk"
#property version   "1.00"
#property strict

#define EXPECT_LOGIN     149736
#define EXPECT_CONFIRM   "WSF-149736"
#define REQUEST_PATH     "mt5_arch\\wsf_desk_order_request.txt"
#define RESULT_PATH      "mt5_arch\\wsf_desk_order_result.json"
#define CLAIM_PATH       "mt5_arch\\wsf_desk_order_claimed.txt"
#define REQUEST_TTL_SEC  90

string g_request_id = "";
string g_action     = "scratch";
string g_symbol     = "EURUSDc";
string g_side       = "BUY";
string g_confirm    = "";
double g_volume     = 0.0;
int    g_use_vmin   = 1;
int    g_magic      = 20263847;
long   g_issued_at  = 0;
string g_order_type = "market";
double g_price      = 0.0;
double g_sl         = 0.0;
double g_tp         = 0.0;
ulong  g_ticket     = 0;

void WriteResult(const string body)
  {
   int h = FileOpen(RESULT_PATH, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("FileOpen failed ", RESULT_PATH, " err=", GetLastError());
      return;
     }
   FileWriteString(h, body);
   FileClose(h);
   Print("Wrote ", RESULT_PATH);
  }

string JEsc(const string s)
  {
   string o = s;
   StringReplace(o, "\\", "\\\\");
   StringReplace(o, "\"", "\\\"");
   StringReplace(o, "\n", "\\n");
   StringReplace(o, "\r", "");
   return o;
  }

string ReadLineValue(const string line, const string key)
  {
   string prefix = key + "=";
   if(StringFind(line, prefix) != 0)
      return "";
   return StringSubstr(line, StringLen(prefix));
  }

bool ReadRequest()
  {
   int h = FileOpen(REQUEST_PATH, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return false;
   while(!FileIsEnding(h))
     {
      string line = FileReadString(h);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(line == "" || StringFind(line, "#") == 0)
         continue;
      string v;
      v = ReadLineValue(line, "request_id"); if(v != "") g_request_id = v;
      v = ReadLineValue(line, "action");     if(v != "") g_action = v;
      v = ReadLineValue(line, "symbol");     if(v != "") g_symbol = v;
      v = ReadLineValue(line, "side");       if(v != "") g_side = v;
      v = ReadLineValue(line, "confirm");    if(v != "") g_confirm = v;
      v = ReadLineValue(line, "volume");     if(v != "") g_volume = StringToDouble(v);
      v = ReadLineValue(line, "use_volume_min"); if(v != "") g_use_vmin = (int)StringToInteger(v);
      v = ReadLineValue(line, "magic");      if(v != "") g_magic = (int)StringToInteger(v);
      v = ReadLineValue(line, "issued_at");  if(v != "") g_issued_at = StringToInteger(v);
      v = ReadLineValue(line, "order_type"); if(v != "") g_order_type = v;
      v = ReadLineValue(line, "price");      if(v != "") g_price = StringToDouble(v);
      v = ReadLineValue(line, "sl");         if(v != "") g_sl = StringToDouble(v);
      v = ReadLineValue(line, "tp");         if(v != "") g_tp = StringToDouble(v);
      v = ReadLineValue(line, "ticket");     if(v != "") g_ticket = (ulong)StringToInteger(v);
     }
   FileClose(h);
   return true;
  }

void DeleteRequest()
  {
   FileDelete(REQUEST_PATH);
  }

bool ResultAlreadyFor(const string request_id)
  {
   if(request_id == "")
      return false;
   int h = FileOpen(RESULT_PATH, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return false;
   string body = "";
   while(!FileIsEnding(h))
      body += FileReadString(h);
   FileClose(h);
   return (StringFind(body, "\"request_id\": \"" + request_id + "\"") >= 0);
  }

bool AlreadyClaimed(const string request_id)
  {
   if(request_id == "")
      return false;
   int h = FileOpen(CLAIM_PATH, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return false;
   string line = FileReadString(h);
   FileClose(h);
   StringTrimLeft(line);
   StringTrimRight(line);
   return (line == request_id);
  }

void WriteClaim(const string request_id)
  {
   int h = FileOpen(CLAIM_PATH, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, request_id);
   FileClose(h);
  }

ENUM_ORDER_TYPE_FILLING PickFilling(const string symbol)
  {
   long flags = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if((flags & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   if((flags & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
  }

bool WaitConnected(const int max_ms)
  {
   int waited = 0;
   while(waited < max_ms)
     {
      long login = AccountInfoInteger(ACCOUNT_LOGIN);
      bool conn = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
      if(login == EXPECT_LOGIN && conn)
         return true;
      Sleep(500);
      waited += 500;
     }
   // Login-only is not connected — do not proceed to OrderSend.
   return false;
  }

bool WaitSymbolReady(const string symbol, const int max_ms)
  {
   int waited = 0;
   SymbolSelect(symbol, true);
   while(waited < max_ms)
     {
      ResetLastError();
      if(SymbolIsSynchronized(symbol) && SymbolInfoDouble(symbol, SYMBOL_BID) > 0.0)
         return true;
      Sleep(250);
      waited += 250;
     }
   return (SymbolIsSynchronized(symbol) && SymbolInfoDouble(symbol, SYMBOL_BID) > 0.0);
  }

string FailJson(const string stage, const string reason,
                const long login, const string server,
                const int retcode, const string retmsg)
  {
   return
      "{\n"
      "  \"ok\": false,\n"
      "  \"source\": \"seven-desk\",\n"
      "  \"request_id\": \"" + JEsc(g_request_id) + "\",\n"
      "  \"stage\": \"" + JEsc(stage) + "\",\n"
      "  \"reason\": \"" + JEsc(reason) + "\",\n"
      "  \"login\": " + IntegerToString(login) + ",\n"
      "  \"server\": \"" + JEsc(server) + "\",\n"
      "  \"retcode\": " + IntegerToString(retcode) + ",\n"
      "  \"retmsg\": \"" + JEsc(retmsg) + "\"\n"
      "}\n";
  }

bool IsUs30Family(const string symbol)
  {
   string u = symbol;
   StringToUpper(u);
   StringReplace(u, ".", "");
   StringReplace(u, "_", "");
   StringReplace(u, "-", "");
   return (u == "US30" || u == "US30CASH" || u == "US30C" || u == "US30M" ||
           u == "US30R" || u == "US30PRO" || u == "DJ30" || u == "DJ30CASH" ||
           u == "DJI30" || u == "WS30");
  }

bool SelectUs30Variant(string &symbol)
  {
   string variants[] = {"US30","US30.cash","US30.Cash","US30c","US30.m",
                        "US30m","US30.r","DJ30","DJ30.cash","DJI30","WS30"};
   if(symbol != "" && SymbolSelect(symbol, true))
      return true;
   for(int i = 0; i < ArraySize(variants); i++)
     {
      if(variants[i] == symbol)
         continue;
      if(SymbolSelect(variants[i], true))
        {
         symbol = variants[i];
         return true;
        }
     }
   return false;
  }

bool ResolveSymbol(string &symbol, const long login, const string server)
  {
   if(IsUs30Family(symbol))
     {
      if(SelectUs30Variant(symbol))
         return true;
      WriteResult(FailJson("symbol",
                           "US30 family not in catalog — SymbolSelect failed (tried US30, US30.cash, DJ30, …)",
                           login, server, GetLastError(), symbol));
      return false;
     }
   if(symbol != "EURUSDc" && symbol != "EURUSD")
     {
      WriteResult(FailJson("symbol", "symbol not allowed — EURUSDc/EURUSD or US30 family",
                           login, server, 0, symbol));
      return false;
     }
   if(SymbolSelect(symbol, true))
      return true;
   if(symbol == "EURUSDc" && SymbolSelect("EURUSD", true))
     {
      symbol = "EURUSD";
      return true;
     }
   WriteResult(FailJson("symbol", "SymbolSelect failed", login, server, GetLastError(), ""));
   return false;
  }

ulong FindPositionTicket(const string symbol)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == symbol &&
         (int)PositionGetInteger(POSITION_MAGIC) == g_magic)
         return t;
     }
   return 0;
  }

void FillDealsFromHistory(const ulong position_ticket, const ulong order_ticket,
                          const ulong close_order, const bool need_close,
                          ulong &deal_open, ulong &deal_close,
                          double &open_price, double &close_price,
                          double &profit, double &swap, double &commission)
  {
   const int max_attempts = need_close ? 8 : 1;
   for(int attempt = 0; attempt < max_attempts; attempt++)
     {
      bool selected = false;
      if(position_ticket > 0)
         selected = HistorySelectByPosition(position_ticket);
      if(!selected)
         selected = HistorySelect(TimeCurrent() - 86400, TimeCurrent() + 3600);
      if(selected)
        {
         profit = 0.0;
         swap = 0.0;
         commission = 0.0;
         for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
           {
            ulong d = HistoryDealGetTicket(i);
            if(d == 0)
               continue;
            ulong pos = (ulong)HistoryDealGetInteger(d, DEAL_POSITION_ID);
            ulong ord = (ulong)HistoryDealGetInteger(d, DEAL_ORDER);
            const bool match_pos = (position_ticket > 0 &&
                                    (pos == position_ticket || pos == order_ticket));
            const bool match_ord = (order_ticket > 0 && ord == order_ticket) ||
                                   (close_order > 0 && ord == close_order);
            if(!match_pos && !match_ord)
               continue;
            ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(d, DEAL_ENTRY);
            double px = HistoryDealGetDouble(d, DEAL_PRICE);
            if(entry == DEAL_ENTRY_IN)
              {
               deal_open = d;
               if(open_price <= 0.0)
                  open_price = px;
              }
            else if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_INOUT ||
                    entry == DEAL_ENTRY_OUT_BY)
              {
               deal_close = d;
               if(close_price <= 0.0)
                  close_price = px;
               profit += HistoryDealGetDouble(d, DEAL_PROFIT);
               swap += HistoryDealGetDouble(d, DEAL_SWAP);
               commission += HistoryDealGetDouble(d, DEAL_COMMISSION);
              }
           }
        }
      if(!need_close || deal_close > 0)
         break;
      Sleep(250);
     }
  }

bool SendDeal(const string symbol, const ENUM_ORDER_TYPE type, const double volume,
              const ulong position, const ENUM_ORDER_TYPE_FILLING filling,
              const int digits, const string comment,
              MqlTradeResult &res)
  {
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick) || tick.ask <= 0.0 || tick.bid <= 0.0)
      return false;
   MqlTradeRequest req;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = symbol;
   req.volume = volume;
   req.type = type;
   req.price = NormalizeDouble(type == ORDER_TYPE_BUY ? tick.ask : tick.bid, digits);
   req.deviation = 30;
   req.magic = g_magic;
   req.comment = comment;
   req.type_filling = filling;
   req.type_time = ORDER_TIME_GTC;
   if(position > 0)
      req.position = position;
   ResetLastError();
   return OrderSend(req, res);
  }

bool TradeRetOk(const uint ret)
  {
   return (ret == TRADE_RETCODE_DONE ||
           ret == TRADE_RETCODE_DONE_PARTIAL ||
           ret == TRADE_RETCODE_PLACED);
  }

bool ResolveVolume(const string symbol, const long login, const string server,
                   double &volume)
  {
   const double vmin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   const double vmax = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   const double vstep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(vmin <= 0.0)
     {
      WriteResult(FailJson("volume", "SYMBOL_VOLUME_MIN is 0", login, server, 0, ""));
      return false;
     }
   if(g_use_vmin == 1)
     {
      volume = vmin;
      return true;
     }
   if(g_volume <= 0.0)
     {
      WriteResult(FailJson("volume", "volume must be greater than 0", login, server, 0, ""));
      return false;
     }
   if(g_volume + 1e-8 < vmin)
     {
      WriteResult(FailJson("volume", "requested volume is below SYMBOL_VOLUME_MIN",
                           login, server, 0,
                           "requested=" + DoubleToString(g_volume, 2) +
                           " min=" + DoubleToString(vmin, 2)));
      return false;
     }
   if(vmax > 0.0 && g_volume > vmax + 1e-8)
     {
      WriteResult(FailJson("volume", "requested volume exceeds SYMBOL_VOLUME_MAX",
                           login, server, 0,
                           "requested=" + DoubleToString(g_volume, 2) +
                           " max=" + DoubleToString(vmax, 2)));
      return false;
     }
   volume = g_volume;
   if(vstep > 0.0)
      volume = vmin + vstep * MathRound((g_volume - vmin) / vstep);
   if(volume + 1e-8 < vmin)
      volume = vmin;
   return true;
  }

bool SendPending(const string symbol, const ENUM_ORDER_TYPE type, const double volume,
                 const double price, const double sl, const double tp,
                 const ENUM_ORDER_TYPE_FILLING filling, const int digits,
                 const string comment, MqlTradeResult &res)
  {
   MqlTradeRequest req;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action = TRADE_ACTION_PENDING;
   req.symbol = symbol;
   req.volume = volume;
   req.type = type;
   req.price = NormalizeDouble(price, digits);
   if(sl > 0.0)
      req.sl = NormalizeDouble(sl, digits);
   if(tp > 0.0)
      req.tp = NormalizeDouble(tp, digits);
   req.magic = g_magic;
   req.comment = comment;
   req.type_filling = filling;
   req.type_time = ORDER_TIME_GTC;
   ResetLastError();
   return OrderSend(req, res);
  }

ulong FindPendingTicket(const string symbol)
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0)
         continue;
      if(OrderGetString(ORDER_SYMBOL) == symbol &&
         (int)OrderGetInteger(ORDER_MAGIC) == g_magic)
         return t;
     }
   return 0;
  }

bool RemovePending(const ulong ticket, MqlTradeResult &res)
  {
   MqlTradeRequest req;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action = TRADE_ACTION_REMOVE;
   req.order = ticket;
   ResetLastError();
   return OrderSend(req, res);
  }

void OnStart()
  {
   if(!ReadRequest())
     {
      WriteResult(FailJson("request", "missing wsf_desk_order_request.txt",
                           AccountInfoInteger(ACCOUNT_LOGIN),
                           AccountInfoString(ACCOUNT_SERVER), GetLastError(), ""));
      return;
     }
   if(g_confirm != EXPECT_CONFIRM)
     {
      WriteResult(FailJson("confirm", "confirm token is not WSF-149736 — refusing OrderSend",
                           AccountInfoInteger(ACCOUNT_LOGIN),
                           AccountInfoString(ACCOUNT_SERVER), 0, ""));
      DeleteRequest();
      return;
     }
   Print("WsfDeskLiveOrder request_id=", g_request_id, " issued_at=", g_issued_at);
   if(ResultAlreadyFor(g_request_id))
     {
      Print("WsfDeskLiveOrder already has a result for ", g_request_id, " — not sending OrderSend");
      DeleteRequest();
      return;
     }
   if(g_issued_at > 0 && ((long)TimeGMT() - g_issued_at) > REQUEST_TTL_SEC)
     {
      WriteResult(FailJson("orphan", "stale wsf_desk_order_request — refusing OrderSend",
                           AccountInfoInteger(ACCOUNT_LOGIN),
                           AccountInfoString(ACCOUNT_SERVER), 0, ""));
      DeleteRequest();
      return;
     }
   if(AlreadyClaimed(g_request_id))
     {
      WriteResult(FailJson("orphan", "request_id already claimed — not sending OrderSend",
                           AccountInfoInteger(ACCOUNT_LOGIN),
                           AccountInfoString(ACCOUNT_SERVER), 0, ""));
      DeleteRequest();
      return;
     }
   WriteClaim(g_request_id);
   DeleteRequest();

   if(!WaitConnected(20000))
     {
      WriteResult(FailJson("connect", "timeout waiting for login 149736 + connected",
                           AccountInfoInteger(ACCOUNT_LOGIN),
                           AccountInfoString(ACCOUNT_SERVER), 0, ""));
      return;
     }

   const long login = AccountInfoInteger(ACCOUNT_LOGIN);
   const string server = AccountInfoString(ACCOUNT_SERVER);
   if(login != EXPECT_LOGIN)
     {
      WriteResult(FailJson("account", "login is not 149736 — refusing OrderSend",
                           login, server, 0, ""));
      return;
     }
   if(StringFind(server, "WSF") < 0)
     {
      WriteResult(FailJson("account", "server does not contain WSF — refusing OrderSend",
                           login, server, 0, ""));
      return;
     }

   string symbol = g_symbol;
   if(!ResolveSymbol(symbol, login, server))
      return;

   ResetLastError();
   if(!SymbolInfoInteger(symbol, SYMBOL_SELECT))
      SymbolSelect(symbol, true);
   StringToLower(g_order_type);
   const bool pending_type = (g_order_type == "buy_limit" || g_order_type == "sell_limit");
   if(!WaitSymbolReady(symbol, 20000))
     {
      if(!(pending_type && SymbolInfoInteger(symbol, SYMBOL_SELECT)))
        {
         WriteResult(FailJson("symbol", "symbol not synchronized — no bid yet",
                              login, server, GetLastError(), symbol));
         return;
        }
      Print("WsfDeskLiveOrder pending without bid — SymbolSelect ok for ", symbol);
     }
   Sleep(300);

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
     {
      WriteResult(FailJson("perm", "TERMINAL_TRADE_ALLOWED is false (Algo Trading off)",
                           login, server, 0, ""));
      return;
     }
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
     {
      WriteResult(FailJson("perm", "MQL_TRADE_ALLOWED is false",
                           login, server, 0, ""));
      return;
     }

   StringToUpper(g_side);
   StringToLower(g_action);
   const bool want_cancel = (g_action == "cancel");
   const bool want_open = (g_action == "scratch" || g_action == "open");
   const bool want_close = (g_action == "scratch" || g_action == "close");
   if(!want_open && !want_close && !want_cancel)
     {
      WriteResult(FailJson("action", "action must be scratch, open, close, or cancel",
                           login, server, 0, g_action));
      return;
     }
   if(pending_type && g_action == "scratch")
     {
      WriteResult(FailJson("action", "scratch is market open+close only",
                           login, server, 0, g_order_type));
      return;
     }

   double volume = 0.0;
   if(!want_cancel)
     {
      if(!ResolveVolume(symbol, login, server, volume))
         return;
     }

   ENUM_ORDER_TYPE_FILLING filling = PickFilling(symbol);
   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   const string comment_open = "7desk-" + g_request_id;
   const string comment_close = "7desk-c-" + g_request_id;

   if(want_cancel)
     {
      ulong ticket = g_ticket;
      if(ticket == 0)
         ticket = FindPendingTicket(symbol);
      if(ticket == 0)
        {
         WriteResult(FailJson("cancel", "no pending desk order to cancel",
                              login, server, 0, symbol));
         return;
        }
      MqlTradeResult cres;
      bool sent = RemovePending(ticket, cres);
      if(!sent || !TradeRetOk(cres.retcode))
        {
         WriteResult(FailJson("cancel", "TRADE_ACTION_REMOVE rejected — not retrying",
                              login, server, (int)cres.retcode,
                              cres.comment + " last=" + IntegerToString(GetLastError())));
         return;
        }
      WriteResult(
         "{\n"
         "  \"ok\": true,\n"
         "  \"source\": \"seven-desk\",\n"
         "  \"request_id\": \"" + JEsc(g_request_id) + "\",\n"
         "  \"stage\": \"cancelled\",\n"
         "  \"reason\": \"seven-desk pending cancelled\",\n"
         "  \"login\": " + IntegerToString(login) + ",\n"
         "  \"server\": \"" + JEsc(server) + "\",\n"
         "  \"company\": \"" + JEsc(AccountInfoString(ACCOUNT_COMPANY)) + "\",\n"
         "  \"symbol\": \"" + JEsc(symbol) + "\",\n"
         "  \"order_type\": \"" + JEsc(g_order_type) + "\",\n"
         "  \"order\": " + IntegerToString((long)ticket) + ",\n"
         "  \"ticket\": " + IntegerToString((long)ticket) + ",\n"
         "  \"balance_after\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n"
         "}\n");
      return;
     }

   if(pending_type && want_open)
     {
      if(g_price <= 0.0)
        {
         WriteResult(FailJson("price", "pending order requires price > 0",
                              login, server, 0, ""));
         return;
        }
      ENUM_ORDER_TYPE ptype = (g_order_type == "sell_limit")
                              ? ORDER_TYPE_SELL_LIMIT : ORDER_TYPE_BUY_LIMIT;
      MqlTradeResult pres;
      bool sent = SendPending(symbol, ptype, volume, g_price, g_sl, g_tp,
                              filling, digits, comment_open, pres);
      if(!sent || !TradeRetOk(pres.retcode))
        {
         WriteResult(FailJson("pending", "OrderSend pending rejected — not retrying",
                              login, server, (int)pres.retcode,
                              pres.comment + " last=" + IntegerToString(GetLastError())));
         return;
        }
      WriteResult(
         "{\n"
         "  \"ok\": true,\n"
         "  \"source\": \"seven-desk\",\n"
         "  \"request_id\": \"" + JEsc(g_request_id) + "\",\n"
         "  \"stage\": \"pending\",\n"
         "  \"reason\": \"seven-desk pending placed\",\n"
         "  \"login\": " + IntegerToString(login) + ",\n"
         "  \"server\": \"" + JEsc(server) + "\",\n"
         "  \"company\": \"" + JEsc(AccountInfoString(ACCOUNT_COMPANY)) + "\",\n"
         "  \"symbol\": \"" + JEsc(symbol) + "\",\n"
         "  \"volume\": " + DoubleToString(volume, 2) + ",\n"
         "  \"side\": \"" + JEsc(g_side) + "\",\n"
         "  \"order_type\": \"" + JEsc(g_order_type) + "\",\n"
         "  \"price\": " + DoubleToString(g_price, digits) + ",\n"
         "  \"sl\": " + DoubleToString(g_sl, digits) + ",\n"
         "  \"tp\": " + DoubleToString(g_tp, digits) + ",\n"
         "  \"order\": " + IntegerToString((long)pres.order) + ",\n"
         "  \"ticket\": " + IntegerToString((long)pres.order) + ",\n"
         "  \"retcode\": " + IntegerToString((int)pres.retcode) + ",\n"
         "  \"balance_after\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n"
         "}\n");
      return;
     }

   ulong order_ticket = 0;
   ulong close_order = 0;
   ulong position_ticket = 0;
   ulong deal_open = 0;
   ulong deal_close = 0;
   double open_price = 0.0;
   double close_price = 0.0;
   uint open_ms = 0;
   uint close_ms = 0;
   int open_ret = 0;
   int close_ret = 0;
   string close_msg = "";

   if(want_open)
     {
      ENUM_ORDER_TYPE otype = (g_side == "SELL") ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      MqlTradeResult res;
      bool sent = SendDeal(symbol, otype, volume, 0, filling, digits, comment_open, res);
      open_ret = (int)res.retcode;
      open_ms = GetTickCount();
      if(!sent || (res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_DONE_PARTIAL))
        {
         WriteResult(FailJson("open", "OrderSend rejected — not retrying",
                              login, server, open_ret,
                              res.comment + " last=" + IntegerToString(GetLastError())));
         return;
        }
      order_ticket = res.order;
      deal_open = res.deal;
      open_price = res.price;
      position_ticket = res.order;
      Sleep(400);
      if(!PositionSelectByTicket(position_ticket))
         position_ticket = FindPositionTicket(symbol);
      if(position_ticket > 0 && PositionSelectByTicket(position_ticket))
        {
         double px = PositionGetDouble(POSITION_PRICE_OPEN);
         if(px > 0.0)
            open_price = px;
        }
      else if(want_close)
        {
         WriteResult(
            "{\n"
            "  \"ok\": false,\n"
            "  \"source\": \"seven-desk\",\n"
            "  \"request_id\": \"" + JEsc(g_request_id) + "\",\n"
            "  \"stage\": \"select_position\",\n"
            "  \"reason\": \"open filled but position not found\",\n"
            "  \"login\": " + IntegerToString(login) + ",\n"
            "  \"server\": \"" + JEsc(server) + "\",\n"
            "  \"symbol\": \"" + JEsc(symbol) + "\",\n"
            "  \"volume\": " + DoubleToString(volume, 2) + ",\n"
            "  \"side\": \"" + JEsc(g_side) + "\",\n"
            "  \"order\": " + IntegerToString((long)order_ticket) + ",\n"
            "  \"deal_open\": " + IntegerToString((long)deal_open) + ",\n"
            "  \"open_price\": " + DoubleToString(open_price, digits) + ",\n"
            "  \"retcode\": " + IntegerToString(open_ret) + "\n"
            "}\n");
         return;
        }
     }
   else
     {
      position_ticket = FindPositionTicket(symbol);
      if(position_ticket == 0 || !PositionSelectByTicket(position_ticket))
        {
         ulong pending_ticket = g_ticket;
         if(pending_ticket == 0)
            pending_ticket = FindPendingTicket(symbol);
         if(pending_ticket > 0)
           {
            MqlTradeResult cres;
            bool sent = RemovePending(pending_ticket, cres);
            if(!sent || !TradeRetOk(cres.retcode))
              {
               WriteResult(FailJson("cancel", "TRADE_ACTION_REMOVE rejected — not retrying",
                                    login, server, (int)cres.retcode,
                                    cres.comment + " last=" + IntegerToString(GetLastError())));
               return;
              }
            WriteResult(
               "{\n"
               "  \"ok\": true,\n"
               "  \"source\": \"seven-desk\",\n"
               "  \"request_id\": \"" + JEsc(g_request_id) + "\",\n"
               "  \"stage\": \"cancelled\",\n"
               "  \"reason\": \"seven-desk pending cancelled\",\n"
               "  \"login\": " + IntegerToString(login) + ",\n"
               "  \"server\": \"" + JEsc(server) + "\",\n"
               "  \"symbol\": \"" + JEsc(symbol) + "\",\n"
               "  \"order\": " + IntegerToString((long)pending_ticket) + ",\n"
               "  \"ticket\": " + IntegerToString((long)pending_ticket) + ",\n"
               "  \"balance_after\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n"
               "}\n");
            return;
           }
         WriteResult(FailJson("close", "no open desk position to close",
                              login, server, 0, symbol));
         return;
        }
      volume = PositionGetDouble(POSITION_VOLUME);
      open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      g_side = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? "BUY" : "SELL";
     }

   bool closed = !want_close;
   if(want_close)
     {
      if(!PositionSelectByTicket(position_ticket))
        {
         WriteResult(FailJson("close", "position vanished before close",
                              login, server, 0, ""));
         return;
        }
      ENUM_ORDER_TYPE ctype = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
                              ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      double close_vol = PositionGetDouble(POSITION_VOLUME);
      for(int attempt = 0; attempt < 12; attempt++)
        {
         MqlTradeResult res;
         bool sent = SendDeal(symbol, ctype, close_vol, position_ticket,
                              filling, digits, comment_close, res);
         close_ret = (int)res.retcode;
         close_msg = res.comment;
         if(sent && (res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_DONE_PARTIAL))
           {
            closed = true;
            close_price = res.price;
            deal_close = res.deal;
            close_order = res.order;
            close_ms = GetTickCount();
            break;
           }
         Print("close attempt ", attempt, " ret=", res.retcode, " ", res.comment);
         Sleep(750);
        }
     }

   double profit = 0.0;
   double swap = 0.0;
   double commission = 0.0;
   FillDealsFromHistory(position_ticket, order_ticket, close_order, want_close,
                        deal_open, deal_close,
                        open_price, close_price, profit, swap, commission);

   const int hold = (open_ms > 0 && close_ms >= open_ms) ? (int)(close_ms - open_ms) : 0;
   WriteResult(
      "{\n"
      "  \"ok\": " + ((want_close ? closed : true) ? "true" : "false") + ",\n"
      "  \"source\": \"seven-desk\",\n"
      "  \"request_id\": \"" + JEsc(g_request_id) + "\",\n"
      "  \"stage\": \"" + (want_close ? (closed ? "closed" : "close") : "open") + "\",\n"
      "  \"reason\": \"" + JEsc(want_close ? (closed ? "seven-desk open+close" : close_msg) : "seven-desk open") + "\",\n"
      "  \"login\": " + IntegerToString(login) + ",\n"
      "  \"server\": \"" + JEsc(server) + "\",\n"
      "  \"company\": \"" + JEsc(AccountInfoString(ACCOUNT_COMPANY)) + "\",\n"
      "  \"symbol\": \"" + JEsc(symbol) + "\",\n"
      "  \"volume\": " + DoubleToString(volume, 2) + ",\n"
      "  \"side\": \"" + JEsc(g_side) + "\",\n"
      "  \"filling\": " + IntegerToString((int)filling) + ",\n"
      "  \"order\": " + IntegerToString((long)order_ticket) + ",\n"
      "  \"position\": " + IntegerToString((long)position_ticket) + ",\n"
      "  \"deal_open\": " + IntegerToString((long)deal_open) + ",\n"
      "  \"deal_close\": " + IntegerToString((long)deal_close) + ",\n"
      "  \"open_price\": " + DoubleToString(open_price, digits) + ",\n"
      "  \"close_price\": " + DoubleToString(close_price, digits) + ",\n"
      "  \"profit\": " + DoubleToString(profit, 2) + ",\n"
      "  \"swap\": " + DoubleToString(swap, 2) + ",\n"
      "  \"commission\": " + DoubleToString(commission, 2) + ",\n"
      "  \"close_retcode\": " + IntegerToString(close_ret) + ",\n"
      "  \"hold_ms\": " + IntegerToString(hold) + ",\n"
      "  \"balance_after\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n"
      "}\n");
  }

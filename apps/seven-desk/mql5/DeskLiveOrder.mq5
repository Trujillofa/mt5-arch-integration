//+------------------------------------------------------------------+
//| DeskLiveOrder.mq5 — Seven Desk prefix-local min-lot OrderSend.   |
//| Identity comes from the request file (expect_login / confirm /   |
//| needle). Min lot only. No retry on a rejected open.              |
//+------------------------------------------------------------------+
#property copyright "seven-desk"
#property version   "1.00"
#property strict

#define REQUEST_PATH     "mt5_arch\\desk_live_order_request.txt"
#define RESULT_PATH      "mt5_arch\\desk_live_order_result.json"

string g_request_id = "";
string g_action     = "scratch";
string g_symbol     = "EURUSD";
string g_side       = "BUY";
string g_confirm    = "";
string g_expect_confirm = "";
long   g_expect_login = 0;
string g_expect_needle = "";
double g_volume     = 0.0;
int    g_use_vmin   = 1;
int    g_magic      = 20263850;

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
      v = ReadLineValue(line, "expect_login"); if(v != "") g_expect_login = StringToInteger(v);
      v = ReadLineValue(line, "expect_confirm"); if(v != "") g_expect_confirm = v;
      v = ReadLineValue(line, "expect_needle"); if(v != "") g_expect_needle = v;
     }
   FileClose(h);
   return true;
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
      if(g_expect_login > 0 && login == g_expect_login && conn)
         return true;
      Sleep(500);
      waited += 500;
     }
   return (g_expect_login > 0 && AccountInfoInteger(ACCOUNT_LOGIN) == g_expect_login);
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

bool ResolveSymbol(string &symbol, const long login, const string server)
  {
   if(symbol != "EURUSDc" && symbol != "EURUSD")
     {
      WriteResult(FailJson("symbol", "symbol not allowed — EURUSDc/EURUSD only",
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
   if(symbol == "EURUSD" && SymbolSelect("EURUSDc", true))
     {
      symbol = "EURUSDc";
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
                          ulong &deal_open, ulong &deal_close,
                          double &open_price, double &close_price,
                          double &profit, double &swap, double &commission)
  {
   HistorySelect(TimeCurrent() - 300, TimeCurrent() + 5);
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
     {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0)
         continue;
      ulong pos = (ulong)HistoryDealGetInteger(d, DEAL_POSITION_ID);
      ulong ord = (ulong)HistoryDealGetInteger(d, DEAL_ORDER);
      if(pos != position_ticket && ord != order_ticket && pos != order_ticket)
         continue;
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(d, DEAL_ENTRY);
      double px = HistoryDealGetDouble(d, DEAL_PRICE);
      if(entry == DEAL_ENTRY_IN)
        {
         deal_open = d;
         if(open_price <= 0.0)
            open_price = px;
        }
      else if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_INOUT)
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

void OnStart()
  {
   if(!ReadRequest())
     {
      WriteResult(FailJson("request", "missing desk_live_order_request.txt",
                           AccountInfoInteger(ACCOUNT_LOGIN),
                           AccountInfoString(ACCOUNT_SERVER), GetLastError(), ""));
      return;
     }
   if(g_expect_login <= 0 || g_expect_confirm == "" || g_expect_needle == "")
     {
      WriteResult(FailJson("request", "expect_login/confirm/needle required",
                           AccountInfoInteger(ACCOUNT_LOGIN),
                           AccountInfoString(ACCOUNT_SERVER), 0, ""));
      return;
     }
   if(g_confirm != g_expect_confirm)
     {
      WriteResult(FailJson("confirm", "confirm token mismatch — refusing OrderSend",
                           AccountInfoInteger(ACCOUNT_LOGIN),
                           AccountInfoString(ACCOUNT_SERVER), 0, ""));
      return;
     }

   if(!WaitConnected(45000))
     {
      WriteResult(FailJson("connect", "timeout waiting for expected login + connected",
                           AccountInfoInteger(ACCOUNT_LOGIN),
                           AccountInfoString(ACCOUNT_SERVER), 0, ""));
      return;
     }

   const long login = AccountInfoInteger(ACCOUNT_LOGIN);
   const string server = AccountInfoString(ACCOUNT_SERVER);
   if(login != g_expect_login)
     {
      WriteResult(FailJson("account", "login does not match expect_login — refusing OrderSend",
                           login, server, 0, ""));
      return;
     }
   if(StringFind(server, g_expect_needle) < 0)
     {
      WriteResult(FailJson("account", "server does not contain expect_needle — refusing OrderSend",
                           login, server, 0, ""));
      return;
     }

   string symbol = g_symbol;
   if(!ResolveSymbol(symbol, login, server))
      return;

   ResetLastError();
   if(!SymbolInfoInteger(symbol, SYMBOL_SELECT))
      SymbolSelect(symbol, true);
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

   const double vmin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   const double vstep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(vmin <= 0.0)
     {
      WriteResult(FailJson("volume", "SYMBOL_VOLUME_MIN is 0", login, server, 0, ""));
      return;
     }
   double volume = vmin;
   if(g_use_vmin != 1)
     {
      if(g_volume <= 0.0 || MathAbs(g_volume - vmin) > 1e-8)
        {
         WriteResult(FailJson("volume", "requested volume is not the symbol minimum",
                              login, server, 0,
                              "requested=" + DoubleToString(g_volume, 2) +
                              " min=" + DoubleToString(vmin, 2)));
         return;
        }
      volume = vmin;
     }
   if(vstep > 0.0)
      volume = MathMax(vmin, vstep);
   if(MathAbs(volume - vmin) > 1e-8 && volume > vmin + 1e-8)
     {
      WriteResult(FailJson("volume", "resolved volume exceeds symbol minimum — refusing",
                           login, server, 0, DoubleToString(volume, 2)));
      return;
     }

   StringToUpper(g_side);
   StringToLower(g_action);
   const bool want_open = (g_action == "scratch" || g_action == "open");
   const bool want_close = (g_action == "scratch" || g_action == "close");
   if(!want_open && !want_close)
     {
      WriteResult(FailJson("action", "action must be scratch, open, or close",
                           login, server, 0, g_action));
      return;
     }

   ENUM_ORDER_TYPE_FILLING filling = PickFilling(symbol);
   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   const string comment_open = "7desk-" + g_request_id;
   const string comment_close = "7desk-c-" + g_request_id;

   ulong order_ticket = 0;
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
   FillDealsFromHistory(position_ticket, order_ticket, deal_open, deal_close,
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

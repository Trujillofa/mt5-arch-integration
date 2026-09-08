//+------------------------------------------------------------------+
//| DeskOrderBridge.mqh — in-process Seven Desk OrderSend.           |
//| Polled by Mt5ArchBridge. Market, limit, and stop all use this    |
//| path. price=0 on a pending means a 50-point offset from bid/ask. |
//+------------------------------------------------------------------+
#ifndef DESK_ORDER_BRIDGE_MQH
#define DESK_ORDER_BRIDGE_MQH

#define DESK_REQ_PATH      "mt5_arch\\desk_live_order_request.txt"
#define DESK_RES_PATH      "mt5_arch\\desk_live_order_result.json"
#define DESK_CLAIM_PATH    "mt5_arch\\desk_live_order_claimed.txt"
#define DESK_REQ_TTL_SEC   90
#define DESK_LIMIT_OFFSET_POINTS 50

string g_desk_request_id = "";
string g_desk_action     = "open";
string g_desk_symbol     = "EURUSD";
string g_desk_side       = "BUY";
string g_desk_confirm    = "";
string g_desk_expect_confirm = "";
long   g_desk_expect_login = 0;
string g_desk_expect_needle = "";
double g_desk_volume     = 0.0;
int    g_desk_use_vmin   = 0;
int    g_desk_magic      = 20263848;
long   g_desk_issued_at  = 0;
string g_desk_order_type = "market";
double g_desk_price      = 0.0;
double g_desk_sl         = 0.0;
double g_desk_tp         = 0.0;
ulong  g_desk_ticket     = 0;
bool   g_desk_busy       = false;
uint   g_desk_last_poll  = 0;

void DeskOrdEnsureDir()
  {
   FolderCreate("mt5_arch");
   FolderCreate("mt5_arch", FILE_COMMON);
  }

int DeskOrdOpen(const string rel, const int flags)
  {
   int h = FileOpen(rel, flags);
   if(h == INVALID_HANDLE)
      h = FileOpen(rel, flags | FILE_COMMON);
   return h;
  }

bool DeskOrdRequestPresent()
  {
   return (FileIsExist(DESK_REQ_PATH, 0) || FileIsExist(DESK_REQ_PATH, FILE_COMMON));
  }

void DeskOrdWriteResult(const string body)
  {
   DeskOrdEnsureDir();
   int h = DeskOrdOpen(DESK_RES_PATH, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("DeskOrder FileOpen failed ", DESK_RES_PATH, " err=", GetLastError());
      return;
     }
   FileWriteString(h, body);
   FileClose(h);
   Print("DeskOrder wrote ", DESK_RES_PATH);
  }

string DeskOrdEsc(const string s)
  {
   string o = s;
   StringReplace(o, "\\", "\\\\");
   StringReplace(o, "\"", "\\\"");
   StringReplace(o, "\n", "\\n");
   StringReplace(o, "\r", "");
   return o;
  }

string DeskOrdLineValue(const string line, const string key)
  {
   string prefix = key + "=";
   if(StringFind(line, prefix) != 0)
      return "";
   return StringSubstr(line, StringLen(prefix));
  }

void DeskOrdResetFields()
  {
   g_desk_request_id = "";
   g_desk_action     = "open";
   g_desk_symbol     = "EURUSD";
   g_desk_side       = "BUY";
   g_desk_confirm    = "";
   g_desk_expect_confirm = "";
   g_desk_expect_login = 0;
   g_desk_expect_needle = "";
   g_desk_volume     = 0.0;
   g_desk_use_vmin   = 0;
   g_desk_magic      = 20263848;
   g_desk_issued_at  = 0;
   g_desk_order_type = "market";
   g_desk_price      = 0.0;
   g_desk_sl         = 0.0;
   g_desk_tp         = 0.0;
   g_desk_ticket     = 0;
  }

bool DeskOrdReadRequest()
  {
   DeskOrdResetFields();
   DeskOrdEnsureDir();
   int h = DeskOrdOpen(DESK_REQ_PATH, FILE_READ | FILE_TXT | FILE_ANSI);
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
      v = DeskOrdLineValue(line, "request_id"); if(v != "") g_desk_request_id = v;
      v = DeskOrdLineValue(line, "action");     if(v != "") g_desk_action = v;
      v = DeskOrdLineValue(line, "symbol");     if(v != "") g_desk_symbol = v;
      v = DeskOrdLineValue(line, "side");       if(v != "") g_desk_side = v;
      v = DeskOrdLineValue(line, "confirm");    if(v != "") g_desk_confirm = v;
      v = DeskOrdLineValue(line, "volume");     if(v != "") g_desk_volume = StringToDouble(v);
      v = DeskOrdLineValue(line, "use_volume_min"); if(v != "") g_desk_use_vmin = (int)StringToInteger(v);
      v = DeskOrdLineValue(line, "magic");      if(v != "") g_desk_magic = (int)StringToInteger(v);
      v = DeskOrdLineValue(line, "expect_login"); if(v != "") g_desk_expect_login = StringToInteger(v);
      v = DeskOrdLineValue(line, "expect_confirm"); if(v != "") g_desk_expect_confirm = v;
      v = DeskOrdLineValue(line, "expect_needle"); if(v != "") g_desk_expect_needle = v;
      v = DeskOrdLineValue(line, "issued_at"); if(v != "") g_desk_issued_at = StringToInteger(v);
      v = DeskOrdLineValue(line, "order_type"); if(v != "") g_desk_order_type = v;
      v = DeskOrdLineValue(line, "price");     if(v != "") g_desk_price = StringToDouble(v);
      v = DeskOrdLineValue(line, "sl");        if(v != "") g_desk_sl = StringToDouble(v);
      v = DeskOrdLineValue(line, "tp");        if(v != "") g_desk_tp = StringToDouble(v);
      v = DeskOrdLineValue(line, "ticket");    if(v != "") g_desk_ticket = (ulong)StringToInteger(v);
     }
   FileClose(h);
   return true;
  }

void DeskOrdDeleteRequest()
  {
   FileDelete(DESK_REQ_PATH);
   FileDelete(DESK_REQ_PATH, FILE_COMMON);
  }

bool DeskOrdResultAlreadyFor(const string request_id)
  {
   if(request_id == "")
      return false;
   int h = DeskOrdOpen(DESK_RES_PATH, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return false;
   string body = "";
   while(!FileIsEnding(h))
      body += FileReadString(h);
   FileClose(h);
   return (StringFind(body, "\"request_id\": \"" + request_id + "\"") >= 0);
  }

bool DeskOrdAlreadyClaimed(const string request_id)
  {
   if(request_id == "")
      return false;
   int h = DeskOrdOpen(DESK_CLAIM_PATH, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return false;
   string line = FileReadString(h);
   FileClose(h);
   StringTrimLeft(line);
   StringTrimRight(line);
   return (line == request_id);
  }

void DeskOrdWriteClaim(const string request_id)
  {
   DeskOrdEnsureDir();
   int h = DeskOrdOpen(DESK_CLAIM_PATH, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, request_id);
   FileClose(h);
  }

string DeskOrdFail(const string stage, const string reason,
                   const long login, const string server,
                   const int retcode, const string retmsg)
  {
   return
      "{\n"
      "  \"ok\": false,\n"
      "  \"source\": \"seven-desk\",\n"
      "  \"path\": \"ea\",\n"
      "  \"request_id\": \"" + DeskOrdEsc(g_desk_request_id) + "\",\n"
      "  \"stage\": \"" + DeskOrdEsc(stage) + "\",\n"
      "  \"reason\": \"" + DeskOrdEsc(reason) + "\",\n"
      "  \"login\": " + IntegerToString(login) + ",\n"
      "  \"server\": \"" + DeskOrdEsc(server) + "\",\n"
      "  \"retcode\": " + IntegerToString(retcode) + ",\n"
      "  \"retmsg\": \"" + DeskOrdEsc(retmsg) + "\"\n"
      "}\n";
  }

ENUM_ORDER_TYPE_FILLING DeskOrdPickFilling(const string symbol)
  {
   long flags = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if((flags & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   if((flags & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
  }

bool DeskOrdIsUs30(const string symbol)
  {
   string u = symbol;
   StringToUpper(u);
   StringReplace(u, ".", "");
   StringReplace(u, "_", "");
   StringReplace(u, "-", "");
   return (u == "US30" || u == "US30CASH" || u == "US30C" || u == "US30M" ||
           u == "US30R" || u == "US30PRO" || u == "DJ30" || u == "DJ30C" ||
           u == "DJ30CASH" || u == "DJI30" || u == "WS30");
  }

bool DeskOrdSelectUs30(string &symbol)
  {
   string variants[] = {"US30","US30.cash","US30.Cash","US30c","US30.c","US30.m",
                        "US30m","US30.r","DJ30","DJ30.c","DJ30c","DJ30.cash",
                        "DJI30","WS30"};
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

bool DeskOrdSymbolAllowed(const string symbol)
  {
   if(symbol == "EURUSD" || symbol == "EURUSDc" || symbol == "EURUSD.pro")
      return true;
   if(StringFind(symbol, "BTCUSD") == 0)
      return true;
   if(DeskOrdIsUs30(symbol))
      return true;
   return false;
  }

bool DeskOrdResolveSymbol(string &symbol, const long login, const string server)
  {
   if(!DeskOrdSymbolAllowed(symbol))
     {
      DeskOrdWriteResult(DeskOrdFail("symbol", "symbol not allowed — EURUSD/EURUSDc/EURUSD.pro, BTCUSD*, or US30 family",
                           login, server, 0, symbol));
      return false;
     }
   if(DeskOrdIsUs30(symbol))
     {
      if(DeskOrdSelectUs30(symbol))
         return true;
      DeskOrdWriteResult(DeskOrdFail("symbol",
                           "US30 family not in catalog — SymbolSelect failed",
                           login, server, GetLastError(), symbol));
      return false;
     }
   if((symbol == "EURUSD" || symbol == "EURUSDc") &&
      StringFind(server, "ACG") >= 0 &&
      SymbolSelect("EURUSD.pro", true))
     {
      symbol = "EURUSD.pro";
      return true;
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
   DeskOrdWriteResult(DeskOrdFail("symbol", "SymbolSelect failed", login, server, GetLastError(), ""));
   return false;
  }

bool DeskOrdTradeRetOk(const uint ret)
  {
   return (ret == TRADE_RETCODE_DONE ||
           ret == TRADE_RETCODE_DONE_PARTIAL ||
           ret == TRADE_RETCODE_PLACED);
  }

bool DeskOrdResolveVolume(const string symbol, const long login, const string server,
                          double &volume)
  {
   const double vmin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   const double vmax = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   const double vstep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(vmin <= 0.0)
     {
      DeskOrdWriteResult(DeskOrdFail("volume", "SYMBOL_VOLUME_MIN is 0", login, server, 0, ""));
      return false;
     }
   if(g_desk_use_vmin == 1)
     {
      volume = vmin;
      return true;
     }
   if(g_desk_volume <= 0.0)
     {
      DeskOrdWriteResult(DeskOrdFail("volume", "volume must be greater than 0", login, server, 0, ""));
      return false;
     }
   if(g_desk_volume + 1e-8 < vmin)
     {
      DeskOrdWriteResult(DeskOrdFail("volume", "requested volume is below SYMBOL_VOLUME_MIN",
                           login, server, 0,
                           "requested=" + DoubleToString(g_desk_volume, 2) +
                           " min=" + DoubleToString(vmin, 2)));
      return false;
     }
   if(vmax > 0.0 && g_desk_volume > vmax + 1e-8)
     {
      DeskOrdWriteResult(DeskOrdFail("volume", "requested volume exceeds SYMBOL_VOLUME_MAX",
                           login, server, 0,
                           "requested=" + DoubleToString(g_desk_volume, 2) +
                           " max=" + DoubleToString(vmax, 2)));
      return false;
     }
   volume = g_desk_volume;
   if(vstep > 0.0)
      volume = vmin + vstep * MathRound((g_desk_volume - vmin) / vstep);
   if(volume + 1e-8 < vmin)
      volume = vmin;
   return true;
  }

bool DeskOrdOffsetPrice(const string symbol, const string order_type,
                        const int digits, double &price,
                        const long login, const string server)
  {
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick) || tick.bid <= 0.0 || tick.ask <= 0.0)
     {
      DeskOrdWriteResult(DeskOrdFail("price", "no bid/ask for limit offset — refusing OrderSend",
                           login, server, GetLastError(), symbol));
      return false;
     }
   const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(point <= 0.0)
     {
      DeskOrdWriteResult(DeskOrdFail("price", "SYMBOL_POINT is 0 — refusing OrderSend",
                           login, server, 0, symbol));
      return false;
     }
   const double offset = DESK_LIMIT_OFFSET_POINTS * point;
   if(order_type == "sell_limit" || order_type == "buy_stop")
      price = NormalizeDouble(tick.ask + offset, digits);
   else
      price = NormalizeDouble(tick.bid - offset, digits);
   if(order_type == "buy_limit" && price >= tick.ask)
     {
      DeskOrdWriteResult(DeskOrdFail("price", "auto buy_limit would market (price >= ask) — refusing",
                           login, server, 0, DoubleToString(price, digits)));
      return false;
     }
   if(order_type == "sell_limit" && price <= tick.bid)
     {
      DeskOrdWriteResult(DeskOrdFail("price", "auto sell_limit would market (price <= bid) — refusing",
                           login, server, 0, DoubleToString(price, digits)));
      return false;
     }
   if(order_type == "buy_stop" && price <= tick.ask)
     {
      DeskOrdWriteResult(DeskOrdFail("price", "auto buy_stop would trigger immediately (price <= ask) — refusing",
                           login, server, 0, DoubleToString(price, digits)));
      return false;
     }
   if(order_type == "sell_stop" && price >= tick.bid)
     {
      DeskOrdWriteResult(DeskOrdFail("price", "auto sell_stop would trigger immediately (price >= bid) — refusing",
                           login, server, 0, DoubleToString(price, digits)));
      return false;
     }
   return true;
  }

bool DeskOrdSendPending(const string symbol, const ENUM_ORDER_TYPE type, const double volume,
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
   req.magic = g_desk_magic;
   req.comment = comment;
   req.type_filling = filling;
   req.type_time = ORDER_TIME_GTC;
   ResetLastError();
   return OrderSend(req, res);
  }

bool DeskOrdSendDeal(const string symbol, const ENUM_ORDER_TYPE type, const double volume,
                     const ulong position, const ENUM_ORDER_TYPE_FILLING filling,
                     const int digits, const string comment, MqlTradeResult &res)
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
   req.magic = g_desk_magic;
   req.comment = comment;
   req.type_filling = filling;
   req.type_time = ORDER_TIME_GTC;
   if(position > 0)
      req.position = position;
   ResetLastError();
   return OrderSend(req, res);
  }

ulong DeskOrdFindPending(const string symbol)
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0)
         continue;
      if(OrderGetString(ORDER_SYMBOL) == symbol &&
         (int)OrderGetInteger(ORDER_MAGIC) == g_desk_magic)
         return t;
     }
   return 0;
  }

ulong DeskOrdFindPosition(const string symbol)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == symbol &&
         (int)PositionGetInteger(POSITION_MAGIC) == g_desk_magic)
         return t;
     }
   return 0;
  }

bool DeskOrdRemovePending(const ulong ticket, MqlTradeResult &res)
  {
   MqlTradeRequest req;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action = TRADE_ACTION_REMOVE;
   req.order = ticket;
   ResetLastError();
   return OrderSend(req, res);
  }

bool DeskOrdSendSltp(const ulong ticket, const double sl, const double tp,
                     const int digits, MqlTradeResult &res)
  {
   if(!PositionSelectByTicket(ticket))
      return false;
   MqlTradeRequest req;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action = TRADE_ACTION_SLTP;
   req.position = ticket;
   req.symbol = PositionGetString(POSITION_SYMBOL);
   req.sl = sl > 0.0 ? NormalizeDouble(sl, digits) : 0.0;
   req.tp = tp > 0.0 ? NormalizeDouble(tp, digits) : 0.0;
   ResetLastError();
   return OrderSend(req, res);
  }

ulong DeskOrdResolvePositionTicket(const string symbol)
  {
   if(g_desk_ticket > 0)
     {
      if(PositionSelectByTicket(g_desk_ticket))
         return g_desk_ticket;
      return 0;
     }
   return DeskOrdFindPosition(symbol);
  }

bool DeskOrdIsNetting()
  {
   return (AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_NETTING);
  }

void DeskOrdProcessRequest()
  {
   const long login0 = AccountInfoInteger(ACCOUNT_LOGIN);
   const string server0 = AccountInfoString(ACCOUNT_SERVER);
   if(!DeskOrdReadRequest())
     {
      DeskOrdWriteResult(DeskOrdFail("request", "missing desk_live_order_request.txt",
                           login0, server0, GetLastError(), ""));
      return;
     }
   if(g_desk_expect_login <= 0 || g_desk_expect_confirm == "" || g_desk_expect_needle == "")
     {
      DeskOrdWriteResult(DeskOrdFail("request", "expect_login/confirm/needle required",
                           login0, server0, 0, ""));
      return;
     }
   if(g_desk_confirm != g_desk_expect_confirm)
     {
      DeskOrdWriteResult(DeskOrdFail("confirm", "confirm token mismatch — refusing OrderSend",
                           login0, server0, 0, ""));
      DeskOrdDeleteRequest();
      return;
     }
   Print("DeskOrder request_id=", g_desk_request_id, " issued_at=", g_desk_issued_at);
   if(DeskOrdResultAlreadyFor(g_desk_request_id))
     {
      Print("DeskOrder already has a result for ", g_desk_request_id);
      DeskOrdDeleteRequest();
      return;
     }
   if(g_desk_issued_at > 0 && ((long)TimeGMT() - g_desk_issued_at) > DESK_REQ_TTL_SEC)
     {
      DeskOrdWriteResult(DeskOrdFail("orphan", "stale desk_live_order_request — refusing OrderSend",
                           login0, server0, 0, ""));
      DeskOrdDeleteRequest();
      return;
     }
   if(DeskOrdAlreadyClaimed(g_desk_request_id))
     {
      DeskOrdWriteResult(DeskOrdFail("orphan", "request_id already claimed — not sending OrderSend",
                           login0, server0, 0, ""));
      DeskOrdDeleteRequest();
      return;
     }
   DeskOrdWriteClaim(g_desk_request_id);
   DeskOrdDeleteRequest();

   const long login = AccountInfoInteger(ACCOUNT_LOGIN);
   const string server = AccountInfoString(ACCOUNT_SERVER);
   if(login != g_desk_expect_login)
     {
      DeskOrdWriteResult(DeskOrdFail("account", "login does not match expect_login — refusing OrderSend",
                           login, server, 0, ""));
      return;
     }
   if(StringFind(server, g_desk_expect_needle) < 0)
     {
      DeskOrdWriteResult(DeskOrdFail("account", "server does not contain expect_needle — refusing OrderSend",
                           login, server, 0, ""));
      return;
     }
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) && login <= 0)
     {
      DeskOrdWriteResult(DeskOrdFail("connect", "terminal not connected — refusing OrderSend",
                           login, server, 0, ""));
      return;
     }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
     {
      DeskOrdWriteResult(DeskOrdFail("perm", "TERMINAL_TRADE_ALLOWED is false (Algo Trading off)",
                           login, server, 0, ""));
      return;
     }
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
     {
      DeskOrdWriteResult(DeskOrdFail("perm", "MQL_TRADE_ALLOWED is false — EA cannot OrderSend",
                           login, server, 0, ""));
      return;
     }

   string symbol = g_desk_symbol;
   if(!DeskOrdResolveSymbol(symbol, login, server))
      return;

   StringToLower(g_desk_order_type);
   StringToUpper(g_desk_side);
   StringToLower(g_desk_action);
   const bool pending_type = (g_desk_order_type == "buy_limit" || g_desk_order_type == "sell_limit" ||
                              g_desk_order_type == "buy_stop" || g_desk_order_type == "sell_stop");
   const bool want_cancel = (g_desk_action == "cancel");
   const bool want_modify = (g_desk_action == "modify");
   const bool want_open = (g_desk_action == "scratch" || g_desk_action == "open");
   const bool want_close = (g_desk_action == "scratch" || g_desk_action == "close");
   if(!want_open && !want_close && !want_cancel && !want_modify)
     {
      DeskOrdWriteResult(DeskOrdFail("action", "action must be scratch, open, close, cancel, or modify",
                           login, server, 0, g_desk_action));
      return;
     }
   if(pending_type && g_desk_action == "scratch")
     {
      DeskOrdWriteResult(DeskOrdFail("action", "scratch is market open+close only",
                           login, server, 0, g_desk_order_type));
      return;
     }

   double volume = 0.0;
   if(!want_cancel && !want_modify)
     {
      if(!DeskOrdResolveVolume(symbol, login, server, volume))
         return;
     }

   ENUM_ORDER_TYPE_FILLING filling = DeskOrdPickFilling(symbol);
   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   const string comment_open = "7desk-" + g_desk_request_id;
   const string comment_close = "7desk-c-" + g_desk_request_id;

   if(want_modify)
     {
      ulong ticket = DeskOrdResolvePositionTicket(symbol);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
        {
         DeskOrdWriteResult(DeskOrdFail("modify", "no open position to modify",
                              login, server, 0, symbol));
         return;
        }
      string pos_symbol = PositionGetString(POSITION_SYMBOL);
      double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      MqlTradeResult mres;
      bool sent = DeskOrdSendSltp(ticket, g_desk_sl, g_desk_tp, digits, mres);
      if(!sent || !DeskOrdTradeRetOk(mres.retcode))
        {
         DeskOrdWriteResult(DeskOrdFail("modify", "TRADE_ACTION_SLTP rejected — not retrying",
                              login, server, (int)mres.retcode,
                              mres.comment + " last=" + IntegerToString(GetLastError())));
         return;
        }
      DeskOrdWriteResult(
         "{\n"
         "  \"ok\": true,\n"
         "  \"source\": \"seven-desk\",\n"
         "  \"path\": \"ea\",\n"
         "  \"request_id\": \"" + DeskOrdEsc(g_desk_request_id) + "\",\n"
         "  \"stage\": \"modified\",\n"
         "  \"reason\": \"seven-desk position sl/tp modified\",\n"
         "  \"login\": " + IntegerToString(login) + ",\n"
         "  \"server\": \"" + DeskOrdEsc(server) + "\",\n"
         "  \"symbol\": \"" + DeskOrdEsc(pos_symbol) + "\",\n"
         "  \"sl\": " + DoubleToString(g_desk_sl, digits) + ",\n"
         "  \"tp\": " + DoubleToString(g_desk_tp, digits) + ",\n"
         "  \"order\": " + IntegerToString((long)ticket) + ",\n"
         "  \"ticket\": " + IntegerToString((long)ticket) + ",\n"
         "  \"position\": " + IntegerToString((long)ticket) + ",\n"
         "  \"open_price\": " + DoubleToString(open_price, digits) + ",\n"
         "  \"retcode\": " + IntegerToString((int)mres.retcode) + ",\n"
         "  \"balance_after\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n"
         "}\n");
      return;
     }

   if(want_cancel)
     {
      ulong ticket = g_desk_ticket;
      if(ticket == 0)
         ticket = DeskOrdFindPending(symbol);
      if(ticket == 0)
        {
         DeskOrdWriteResult(DeskOrdFail("cancel", "no pending desk order to cancel",
                              login, server, 0, symbol));
         return;
        }
      MqlTradeResult cres;
      bool sent = DeskOrdRemovePending(ticket, cres);
      if(!sent || !DeskOrdTradeRetOk(cres.retcode))
        {
         DeskOrdWriteResult(DeskOrdFail("cancel", "TRADE_ACTION_REMOVE rejected — not retrying",
                              login, server, (int)cres.retcode,
                              cres.comment + " last=" + IntegerToString(GetLastError())));
         return;
        }
      DeskOrdWriteResult(
         "{\n"
         "  \"ok\": true,\n"
         "  \"source\": \"seven-desk\",\n"
         "  \"path\": \"ea\",\n"
         "  \"request_id\": \"" + DeskOrdEsc(g_desk_request_id) + "\",\n"
         "  \"stage\": \"cancelled\",\n"
         "  \"reason\": \"seven-desk pending cancelled\",\n"
         "  \"login\": " + IntegerToString(login) + ",\n"
         "  \"server\": \"" + DeskOrdEsc(server) + "\",\n"
         "  \"company\": \"" + DeskOrdEsc(AccountInfoString(ACCOUNT_COMPANY)) + "\",\n"
         "  \"symbol\": \"" + DeskOrdEsc(symbol) + "\",\n"
         "  \"order_type\": \"" + DeskOrdEsc(g_desk_order_type) + "\",\n"
         "  \"order\": " + IntegerToString((long)ticket) + ",\n"
         "  \"ticket\": " + IntegerToString((long)ticket) + ",\n"
         "  \"balance_after\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n"
         "}\n");
      return;
     }

   if(pending_type && want_open)
     {
      double price = g_desk_price;
      if(price <= 0.0)
        {
         if(!DeskOrdOffsetPrice(symbol, g_desk_order_type, digits, price, login, server))
            return;
        }
      ENUM_ORDER_TYPE ptype = ORDER_TYPE_BUY_LIMIT;
      if(g_desk_order_type == "sell_limit")
         ptype = ORDER_TYPE_SELL_LIMIT;
      else if(g_desk_order_type == "buy_stop")
         ptype = ORDER_TYPE_BUY_STOP;
      else if(g_desk_order_type == "sell_stop")
         ptype = ORDER_TYPE_SELL_STOP;
      MqlTradeResult pres;
      bool sent = DeskOrdSendPending(symbol, ptype, volume, price, g_desk_sl, g_desk_tp,
                                     filling, digits, comment_open, pres);
      if(!sent || !DeskOrdTradeRetOk(pres.retcode))
        {
         DeskOrdWriteResult(DeskOrdFail("pending", "OrderSend pending rejected — not retrying",
                              login, server, (int)pres.retcode,
                              pres.comment + " last=" + IntegerToString(GetLastError())));
         return;
        }
      DeskOrdWriteResult(
         "{\n"
         "  \"ok\": true,\n"
         "  \"source\": \"seven-desk\",\n"
         "  \"path\": \"ea\",\n"
         "  \"request_id\": \"" + DeskOrdEsc(g_desk_request_id) + "\",\n"
         "  \"stage\": \"pending\",\n"
         "  \"reason\": \"seven-desk pending placed\",\n"
         "  \"login\": " + IntegerToString(login) + ",\n"
         "  \"server\": \"" + DeskOrdEsc(server) + "\",\n"
         "  \"company\": \"" + DeskOrdEsc(AccountInfoString(ACCOUNT_COMPANY)) + "\",\n"
         "  \"symbol\": \"" + DeskOrdEsc(symbol) + "\",\n"
         "  \"volume\": " + DoubleToString(volume, 2) + ",\n"
         "  \"side\": \"" + DeskOrdEsc(g_desk_side) + "\",\n"
         "  \"order_type\": \"" + DeskOrdEsc(g_desk_order_type) + "\",\n"
         "  \"price\": " + DoubleToString(price, digits) + ",\n"
         "  \"sl\": " + DoubleToString(g_desk_sl, digits) + ",\n"
         "  \"tp\": " + DoubleToString(g_desk_tp, digits) + ",\n"
         "  \"order\": " + IntegerToString((long)pres.order) + ",\n"
         "  \"ticket\": " + IntegerToString((long)pres.order) + ",\n"
         "  \"retcode\": " + IntegerToString((int)pres.retcode) + ",\n"
         "  \"balance_after\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n"
         "}\n");
      return;
     }

   if(want_close && !want_open)
     {
      ulong position_ticket = DeskOrdResolvePositionTicket(symbol);
      if(position_ticket == 0 || !PositionSelectByTicket(position_ticket))
        {
         ulong pending_ticket = g_desk_ticket;
         if(pending_ticket == 0)
            pending_ticket = DeskOrdFindPending(symbol);
         if(pending_ticket > 0)
           {
            MqlTradeResult cres;
            bool sent = DeskOrdRemovePending(pending_ticket, cres);
            if(!sent || !DeskOrdTradeRetOk(cres.retcode))
              {
               DeskOrdWriteResult(DeskOrdFail("cancel", "TRADE_ACTION_REMOVE rejected — not retrying",
                                    login, server, (int)cres.retcode,
                                    cres.comment + " last=" + IntegerToString(GetLastError())));
               return;
              }
            DeskOrdWriteResult(
               "{\n"
               "  \"ok\": true,\n"
               "  \"source\": \"seven-desk\",\n"
               "  \"path\": \"ea\",\n"
               "  \"request_id\": \"" + DeskOrdEsc(g_desk_request_id) + "\",\n"
               "  \"stage\": \"cancelled\",\n"
               "  \"reason\": \"seven-desk pending cancelled\",\n"
               "  \"login\": " + IntegerToString(login) + ",\n"
               "  \"server\": \"" + DeskOrdEsc(server) + "\",\n"
               "  \"symbol\": \"" + DeskOrdEsc(symbol) + "\",\n"
               "  \"order\": " + IntegerToString((long)pending_ticket) + ",\n"
               "  \"ticket\": " + IntegerToString((long)pending_ticket) + ",\n"
               "  \"balance_after\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n"
               "}\n");
            return;
           }
         DeskOrdWriteResult(DeskOrdFail("close", "no open desk position to close",
                              login, server, 0, symbol));
         return;
        }
      ENUM_ORDER_TYPE ctype = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
                              ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      double close_vol = PositionGetDouble(POSITION_VOLUME);
      double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      MqlTradeResult res;
      bool sent = DeskOrdSendDeal(symbol, ctype, close_vol, position_ticket,
                                  filling, digits, comment_close, res);
      if(!sent && DeskOrdIsNetting())
         sent = DeskOrdSendDeal(symbol, ctype, close_vol, 0,
                                filling, digits, comment_close, res);
      if(!sent || (res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_DONE_PARTIAL))
        {
         DeskOrdWriteResult(DeskOrdFail("close", "OrderSend close rejected — not retrying",
                              login, server, (int)res.retcode,
                              res.comment + " last=" + IntegerToString(GetLastError())));
         return;
        }
      DeskOrdWriteResult(
         "{\n"
         "  \"ok\": true,\n"
         "  \"source\": \"seven-desk\",\n"
         "  \"path\": \"ea\",\n"
         "  \"request_id\": \"" + DeskOrdEsc(g_desk_request_id) + "\",\n"
         "  \"stage\": \"closed\",\n"
         "  \"reason\": \"seven-desk position closed\",\n"
         "  \"login\": " + IntegerToString(login) + ",\n"
         "  \"server\": \"" + DeskOrdEsc(server) + "\",\n"
         "  \"symbol\": \"" + DeskOrdEsc(symbol) + "\",\n"
         "  \"volume\": " + DoubleToString(close_vol, 2) + ",\n"
         "  \"order\": " + IntegerToString((long)res.order) + ",\n"
         "  \"position\": " + IntegerToString((long)position_ticket) + ",\n"
         "  \"deal_close\": " + IntegerToString((long)res.deal) + ",\n"
         "  \"open_price\": " + DoubleToString(open_price, digits) + ",\n"
         "  \"close_price\": " + DoubleToString(res.price, digits) + ",\n"
         "  \"close_retcode\": " + IntegerToString((int)res.retcode) + ",\n"
         "  \"balance_after\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n"
         "}\n");
      return;
     }

   ENUM_ORDER_TYPE otype = (g_desk_side == "SELL") ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   MqlTradeResult ores;
   bool osent = DeskOrdSendDeal(symbol, otype, volume, 0, filling, digits, comment_open, ores);
   if(!osent || (ores.retcode != TRADE_RETCODE_DONE && ores.retcode != TRADE_RETCODE_DONE_PARTIAL))
     {
      DeskOrdWriteResult(DeskOrdFail("open", "OrderSend rejected — not retrying",
                           login, server, (int)ores.retcode,
                           ores.comment + " last=" + IntegerToString(GetLastError())));
      return;
     }
   DeskOrdWriteResult(
      "{\n"
      "  \"ok\": true,\n"
      "  \"source\": \"seven-desk\",\n"
      "  \"path\": \"ea\",\n"
      "  \"request_id\": \"" + DeskOrdEsc(g_desk_request_id) + "\",\n"
      "  \"stage\": \"open\",\n"
      "  \"reason\": \"seven-desk open\",\n"
      "  \"login\": " + IntegerToString(login) + ",\n"
      "  \"server\": \"" + DeskOrdEsc(server) + "\",\n"
      "  \"symbol\": \"" + DeskOrdEsc(symbol) + "\",\n"
      "  \"volume\": " + DoubleToString(volume, 2) + ",\n"
      "  \"side\": \"" + DeskOrdEsc(g_desk_side) + "\",\n"
      "  \"order\": " + IntegerToString((long)ores.order) + ",\n"
      "  \"deal_open\": " + IntegerToString((long)ores.deal) + ",\n"
      "  \"open_price\": " + DoubleToString(ores.price, digits) + ",\n"
      "  \"balance_after\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "\n"
      "}\n");
  }

bool DeskOrderProcessIfRequested()
  {
   if(g_desk_busy)
      return false;
   if(!DeskOrdRequestPresent())
      return false;
   g_desk_busy = true;
   DeskOrdProcessRequest();
   g_desk_busy = false;
   return true;
  }

void DeskOrderPollOnTick()
  {
   uint now = GetTickCount();
   if(now - g_desk_last_poll < 200)
      return;
   g_desk_last_poll = now;
   DeskOrderProcessIfRequested();
  }

#endif

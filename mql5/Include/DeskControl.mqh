//+------------------------------------------------------------------+
//| DeskControl.mqh — read-only entry inhibit switch (Stage 0).       |
//| The coordinator owns mt5_arch\control.json; this EA never writes  |
//| it. Missing file = entries allowed. Unreadable or malformed file  |
//| = entries FAIL CLOSED. Only entries consult this gate; close,     |
//| cancel, and modify never do (exits are never gated).              |
//+------------------------------------------------------------------+
#ifndef DESK_CONTROL_MQH
#define DESK_CONTROL_MQH

#define DESK_CONTROL_PATH "mt5_arch\\control.json"

bool   g_desk_ctl_present   = false;
bool   g_desk_ctl_inhibited = false;
string g_desk_ctl_reason    = "";
string g_desk_ctl_operator  = "";
string g_desk_ctl_updated   = "";

int DeskCtlOpen()
  {
   int h = FileOpen(DESK_CONTROL_PATH, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      h = FileOpen(DESK_CONTROL_PATH, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   return h;
  }

bool DeskCtlPresent()
  {
   return (FileIsExist(DESK_CONTROL_PATH, 0) ||
           FileIsExist(DESK_CONTROL_PATH, FILE_COMMON));
  }

string DeskCtlReadAll()
  {
   int h = DeskCtlOpen();
   if(h == INVALID_HANDLE)
      return "";
   string body = "";
   while(!FileIsEnding(h))
      body += FileReadString(h);
   FileClose(h);
   return body;
  }

// Minimal JSON value reader for the flat control.json object. Returns the
// unquoted string/token, or "" when the key is absent. No nested objects.
string DeskCtlValue(const string json, const string key)
  {
   string needle = "\"" + key + "\"";
   int k = StringFind(json, needle);
   if(k < 0)
      return "";
   int colon = StringFind(json, ":", k + StringLen(needle));
   if(colon < 0)
      return "";
   int n = StringLen(json);
   int i = colon + 1;
   while(i < n)
     {
      ushort c = StringGetCharacter(json, i);
      if(c == ' ' || c == '\t' || c == '\r' || c == '\n')
        {
         i++;
         continue;
        }
      break;
     }
   if(i >= n)
      return "";
   if(StringGetCharacter(json, i) == '"')
     {
      string out = "";
      i++;
      while(i < n)
        {
         ushort c = StringGetCharacter(json, i);
         if(c == '\\' && i + 1 < n)
           {
            out += ShortToString(StringGetCharacter(json, i + 1));
            i += 2;
            continue;
           }
         if(c == '"')
            break;
         out += ShortToString(c);
         i++;
        }
      return out;
     }
   string token = "";
   while(i < n)
     {
      ushort c = StringGetCharacter(json, i);
      if(c == ',' || c == '}' || c == ']' || c == ' ' || c == '\t' ||
         c == '\r' || c == '\n')
         break;
      token += ShortToString(c);
      i++;
     }
   return token;
  }

void DeskControlLoad()
  {
   g_desk_ctl_present   = DeskCtlPresent();
   g_desk_ctl_inhibited = false;
   g_desk_ctl_reason    = "";
   g_desk_ctl_operator  = "";
   g_desk_ctl_updated   = "";
   if(!g_desk_ctl_present)
      return;

   string body = DeskCtlReadAll();
   if(StringLen(body) == 0)
     {
      // The coordinator writes atomically; an empty read means the file was
      // removed mid-read or is locked. Block entries rather than guess.
      g_desk_ctl_inhibited = true;
      g_desk_ctl_reason    = "control.json unreadable";
      return;
     }

   string flag = DeskCtlValue(body, "inhibited");
   StringToLower(flag);
   if(flag == "true")
      g_desk_ctl_inhibited = true;
   else if(flag == "false")
      g_desk_ctl_inhibited = false;
   else
     {
      g_desk_ctl_inhibited = true;
      g_desk_ctl_reason    = "control.json malformed (missing boolean inhibited)";
      return;
     }

   g_desk_ctl_reason   = DeskCtlValue(body, "reason");
   g_desk_ctl_operator = DeskCtlValue(body, "operator");
   g_desk_ctl_updated  = DeskCtlValue(body, "updated_at");
  }

// Re-read control.json; return true when a new entry must be refused.
bool DeskControlEntriesBlocked(string &reason)
  {
   DeskControlLoad();
   if(!g_desk_ctl_inhibited)
      return false;
   reason = g_desk_ctl_reason;
   if(g_desk_ctl_operator != "")
      reason += " (operator=" + g_desk_ctl_operator + ")";
   if(g_desk_ctl_updated != "")
      reason += " updated_at=" + g_desk_ctl_updated;
   if(reason == "")
      reason = "entries inhibited";
   return true;
  }

void DeskControlLogOnInit()
  {
   DeskControlLoad();
   if(!g_desk_ctl_present)
     {
      Print("DeskControl: no control.json — entries allowed");
      return;
     }
   string state = "false";
   if(g_desk_ctl_inhibited)
      state = "true";
   Print("DeskControl: inhibited=", state,
         " reason=", g_desk_ctl_reason,
         " operator=", g_desk_ctl_operator,
         " updated_at=", g_desk_ctl_updated);
  }

#endif

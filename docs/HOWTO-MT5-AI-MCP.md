# How to use MetaTrader 5 AI Assistant / MCP from this repo

**Status:** platform HOWTO · read-only on the Linux side · no live orders
**Does not** implement MetaQuotes' in-terminal assistant, and does not authorize trading.

[MetaQuotes' 11 Aug 2026 note](https://www.metatrader.com/en/news/metaquotes/3733038-traders-have-already-used-1-trillion-tokens-in-ai)
is about the **official** AI Assistant that shipped with MT5 build **6060**
([release notes](https://www.metatrader5.com/en/releasenotes/terminal/2447); methods expanded in
[build 6090](https://www.metatrader5.com/en/releasenotes/terminal/2450)).
That assistant is a Windows desktop feature. This repo's working path is
Linux Python → file-bridge snapshots. Those are different products that can
share a workflow (an AI agent calling MT5 tools) but not the same binary.

## What the article actually added

Two official layers, both inside `terminal64.exe` / MetaEditor:

| Layer | What it is | Credentials |
|-------|------------|-------------|
| **AI Assistant** | Chat UI in the terminal and MetaEditor. Default model is free **MQL5 Lite** after an MQL5.community login. Optional keys: OpenAI, Anthropic, Gemini, DeepSeek, Ollama. | MQL5.community, or a provider API key |
| **Internal MCP server** | Local tool server so **Claude Code**, **OpenAI Codex**, or Cursor can call MT5 tools. Typical URL `http://127.0.0.1:22346/mcp` (MetaEditor has used `22345`). | Bearer token shown in Tools → Options → MCP |

The assistant can analyze charts, review positions/history, add indicators
(build 6090+), and generate MQL5. Trading, web, and shell access are separate
permission toggles. Keep trading on **manual confirmation** (or off).

Windows 7 is unsupported for the assistant as of 6090. Web/iOS/Android terminals
do not ship this MCP server.

## Three routes (pick one)

```
A  Official assistant UI     → sign in to MQL5.community inside MT5
B  Official MCP HTTP         → Cursor / Claude Code → 127.0.0.1:22346
C  mt5-arch MCP (this repo)  → Cursor / Claude Code → `mt5-arch mcp` stdio
                               → FileBridgeClient / RPyC (same as the CLI)
```

**A/B** need MT5 **build ≥ 6060** (6090+ preferred) and a Windows-enough Wine
prefix. They can fail under Wine the same way RPyC already does (`IPC timeout`,
missing Win10 APIs). **C** uses the stack this repo already trusts.

Do **not** follow Windows-only FastMCP + official `MetaTrader5` Python package
articles as the Arch path. That package is the RPyC/IPC backend this repo
defaults away from.

## Route A — official assistant (try, then fall back)

1. `uv run mt5-arch ping --json` and read `build`. Need **≥ 6060**.
2. In the terminal: **Help → About** (same number).
3. **Tools → Options → Community** — log in with an MQL5.community account
   (not the broker login).
4. **Tools → Options → AI Assistant** — provider should be MQL5.community;
   MQL5 Lite is configured automatically. Optional: paste your own provider key.
5. Launch the assistant from **File**, the toolbar, or Navigator. Ask
   read-only questions first (trend / open risk / history). Do not grant
   unattended trading.

If the assistant menu is missing, greyed out, or crashes under Wine, skip to C.

## Route B — official MCP HTTP (external agents)

Only when the terminal actually exposes the listener:

1. **Tools → Options → MCP** → Enable internal server.
2. Copy the displayed **Address** (on Windows that is usually `127.0.0.1:22346`;
   under Wine read `ss` — do not assume localhost).
3. **Generate** a token. The dialog API Key is short (**~42 characters**).
   Store it as `MT5_MCP_TOKEN` (environment or gitignored `.env`). Never commit it.
   The **168-character** `assistant.ini` `ApiKey=` is a different value and
   **401s** on a Linux `Authorization: Bearer` handshake.
4. Trading permission: leave **off** or **manual confirmation**. Official MCP
   **can trade**. This repo never calls `OrderSend` through MCP.
5. Confirm a listener before configuring a client:

```bash
ss -ltn | grep -E '22345|22346' || true
WINEPREFIX=~/.mt5-vantage ./scripts/21-official-mcp-status.sh
```

Claude Code (replace the URL with the listener `ss` actually shows):

```bash
claude mcp add --transport http mt5 http://127.0.0.1:22346/mcp \
  --header "Authorization: Bearer ${MT5_MCP_TOKEN}"
```

Do **not** commit a project `.mcp.json` with a live URL. Cursor's project
`.mcp.json` is often tracked; use a **gitignored** local file instead
(`.cursor/mcp.local.json` or `~/.cursor/mcp.json`). Windows/localhost snippet
(only if `ss` shows `127.0.0.1:22346`):

```json
{
  "mcpServers": {
    "mt5-official": {
      "type": "http",
      "url": "http://127.0.0.1:22346/mcp",
      "headers": {
        "Authorization": "Bearer ${MT5_MCP_TOKEN}"
      }
    }
  }
}
```

Official MCP **can trade** if you allow it. Leave trading permission off or on
manual confirmation. Multiple `terminal64.exe` instances can fight for 22346
(`WSAEADDRINUSE` / 10048).

Wine note (verified on Vantage / Wine 11.15 / build 6140):

- The portable ini is `Config/assistant.ini` (UTF-16-LE). `[MCP.MetaTrader] Enable=1` is what Tools → Options → MCP → **Enable internal server** writes. MetaEditor uses `[MCP.MetaEditor]` on 22345.
- Always take the client URL from `ss` / `./scripts/21-official-mcp-status.sh`, not from the journal alone. The journal line `MCP started on 127.0.0.1:22346` is the *Windows* bind; older Wine remaps sometimes exposed a LAN address (`192.168.0.144:22346`) while localhost refused. On the current host (build 6140) the listener is `127.0.0.1:22346` — prefer that. A non-localhost bind exposes a server that **can trade**; disable MCP on every prefix that does not need it (FP/Exness/WSF).
- Dialog API Key ≈ **42 chars** → `MT5_MCP_TOKEN`. `assistant.ini ApiKey=` ≈ **168 chars** is not that token (HTTP 401, `WWW-Authenticate: Bearer realm="MetaTrader5-MCP"`). Copy a freshly **Generate**d dialog token. Never commit it. Rotate if it was ever printed.
- Gitignored Cursor / Grok HTTP config for this host (match whatever `ss` shows; localhost is current):

```json
{
  "mcpServers": {
    "mt5-official": {
      "type": "http",
      "url": "http://127.0.0.1:22346/mcp",
      "headers": {
        "Authorization": "Bearer ${MT5_MCP_TOKEN}"
      }
    }
  }
}
```

  Write that to `.cursor/mcp.local.json` (gitignored) or `~/.cursor/mcp.json`.
  Export `MT5_MCP_TOKEN` in the environment Cursor inherits. This repo does not
  `OrderSend` via official MCP.
- Check without printing secrets: `WINEPREFIX=~/.mt5-vantage ./scripts/21-official-mcp-status.sh`.
- Route A still needs an **MQL5.community** login (Tools → Options → Community), not the broker login. If the assistant menu is missing after that, skip to C.
- If `ss` shows nothing after Enable=1 + restart, or the handshake stays 401 after a UI-generated token, use route C.

## Route C — `mt5-arch mcp` (implemented here)

Read-only stdio MCP over the same client as `mt5-arch ping|account|symbols|candles`.
No new Python dependency. No `OrderSend`. `config` uses `Settings.redacted_summary()`.

```bash
# same prerequisites as the CLI
export MT5_BACKEND=file
uv run mt5-arch mcp
```

Tools: `ping`, `account`, `symbols`, `candles`, `config`, `brokers`, `resolve`.
There is no positions/order tool — the EA may write `positions.json`, but this
server does not expose it.

Cursor / Claude Code stdio config (repo-local):

```json
{
  "mcpServers": {
    "mt5-arch": {
      "command": "uv",
      "args": ["run", "--directory", "/ABS/PATH/mt5-arch-integration", "mt5-arch", "mcp"]
    }
  }
}
```

The client must inherit the same env the CLI needs (`WINEPREFIX`, `MT5_BACKEND`,
`MT5_BRIDGE_DIR`, `MT5_BROKER`, …). `scripts/16-use-broker.sh` still applies.
Logs go to stderr; stdout is JSON-RPC only.

First probe (read-only): ask the agent to call `ping`, then `account`, and to
report terminal `build` / `connected` and account currency — not a trade.

`config` / `brokers` / `resolve` work without a live bridge. `ping` / `account` /
`symbols` / `candles` fail closed on a stale `heartbeat.txt` the same way the CLI
does (Algo Trading off or EA detached).

## Safety

- This HOWTO is not investment advice. Assistant output can be wrong or stale.
- Never log `MT5_PASSWORD`, provider API keys, or the official MCP token.
- Do not expose 22346 off localhost.
- Research layer stays offline. `src/mt5_arch` does not import `backtest.py` /
  `live_trader.py`. Do not pass `--live`.
- Catalog / blog profit-factor claims are still not evidence
  ([ARTICLE-INTAKE.md](ARTICLE-INTAKE.md)).

## Related

- CLI inventory: [MT5-INTEGRATION-CAPABILITIES.md](MT5-INTEGRATION-CAPABILITIES.md)
- File bridge vs RPyC: [ARCHITECTURE.md](ARCHITECTURE.md)
- Wine / Algo Trading: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Zacks fundamentals / ETF holdings (separate user MCP, not MT5): [research/ZACKS-MCP-OVERLAY-LANE.md](research/ZACKS-MCP-OVERLAY-LANE.md)

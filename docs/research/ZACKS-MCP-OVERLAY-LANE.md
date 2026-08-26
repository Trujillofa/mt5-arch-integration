# Zacks MCP overlay lane — 2026-08-22

**Status:** `SCHEMA_PASS` / overlay **BLOCKED** for KEEP  
**Not:** US-index 1%/20% scalp (archived) · not an XAU OHLC family · not a charter freeze  
**Source:** Zacks Investment Research via Cursor MCP `zacks` → `https://mcp.zacksdata.com`

## Premise

Gold-complex **listed** names and gold ETFs (GDX, GLD, NEM and peers) have
point-in-time statements and **current** holdings that this platform repo has
never used as exogenous context. That is a new data family. It does not
reopen the archived US-index session-scalp goal and does not mutate XAU
charters.

## Why this repo

`~/.cursor/mcp.json` already documents official MT5 MCP (`mt5-official`) for
this host. Zacks is the other new HTTP MCP in that file. Use it here only as
an **observe-only overlay** for XAU-adjacent listed equity / ETF context.

## 2026-08-22 probe (schema only)

| Fact | Result |
|---|---|
| Tools | `get_company_snapshot`, `get_income_statement`, `get_balance_sheet`, `get_cash_flow`, `get_etf_holdings` |
| GDX holdings | Current as-of `2026-08-22`; tool params are `symbol` + `top_n` only |
| NEM annual statements | 5 period-ends (2021–2025) even when more periods were requested |
| PEAD timestamps | Absent — do not treat this as an earnings-surprise feed |

No statement values or holdings weights are stored in this repo.

## Contract (data-proof only)

**May**

- Document MCP wiring next to official MT5 MCP
- Re-run a schema probe if Zacks adds historical as-of or longer statement depth
- Use live MCP in a desk session for **today's** GDX/GLD/miner context

**Must not**

- Edit `results/xau_charters/*` or `results/xau_loop_status.md` from this lane
- Revive US-index 1%/20% or treat overlay observations as a scalp KEEP
- Backtest holdings-change or 10y quality factors on this MCP until history exists
- Commit `MT5_MCP_TOKEN`, LAN MCP URLs, or live Zacks numeric extracts
- Send orders through official MT5 MCP

## User MCP snippet (Zacks only)

Write to gitignored `.cursor/mcp.local.json` or `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "zacks": {
      "type": "http",
      "url": "https://mcp.zacksdata.com"
    }
  }
}
```

Official MT5 MCP stays on the existing HOWTO
([HOWTO-MT5-AI-MCP.md](../HOWTO-MT5-AI-MCP.md)). Do not commit that URL or token.

## Stop / reopen

A later KEEP path needs dated holdings **or** >=10y statements, plus a
separate price/cost source, plus a new charter if anyone proposes an XAU
family. Until then the overlay is observation-only.

# AGENTS.md — mt5-arch-integration

## Purpose

Platform layer only: **Wine MT5 + RPyC/mt5linux + thin Python CLI**.

Do **not** add strategy engines, risk managers, Telegram bots, or TimescaleDB here. Those belong in `mt5-trading-agent` or other app repos.

## Conventions

- Secrets only via `.env` / environment variables; never log `MT5_PASSWORD`.
- Scripts are bash, `set -euo pipefail`, shared helpers in `scripts/lib.sh`.
- Default Wine prefix: `~/.mt5` (outside the git tree).
- RPyC default port: `18812`, bind localhost.
- Typed models in `mt5_arch/models.py` stay compatible with the agent bridge shapes where practical (`AccountInfo`, `SymbolInfo`, `Candle`).

## Verification

```bash
./scripts/00-check-deps.sh
uv run pytest
uv run ruff check src tests
# Live (optional):
./scripts/healthcheck.sh --ping
```

## Safe operations

- Prefer reusing an existing Wine prefix; only wipe with `01-create-prefix.sh --force` when the user asks.
- Do not push remotes or force-push without explicit user approval.
- Do not place live orders in smoke tests without an explicit live flag and user consent.

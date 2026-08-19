# Timescale sketch (`timescale_true_cvd_v1`)

**Status: unused / unstarted.**

- Do not `docker compose up` unless a later increment asks.
- Do not point clients at crypto-agent `127.0.0.1:15432`.
- If ever started: `127.0.0.1:15433` only, local password via `CVD_PG_PASSWORD`.
- `./data/` is gitignored. It must stay off git.

Schema: `schema.sql`. Design: [`../TIMESCALE-TRUE-CVD-DESIGN.md`](../TIMESCALE-TRUE-CVD-DESIGN.md).

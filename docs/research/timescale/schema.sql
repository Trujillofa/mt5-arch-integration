-- timescale_true_cvd_v1 — UNUSED sketch.
-- Do not apply unless a later increment explicitly starts local Timescale.
-- Not a production schema. Not the crypto-agent database.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- One MqlTick after a documented CSV dump. Not MqlRates. Not .tkc.
CREATE TABLE IF NOT EXISTS ticks (
    broker                  TEXT NOT NULL,
    symbol                  TEXT NOT NULL,
    source                  TEXT NOT NULL,
    time_utc                TIMESTAMPTZ NOT NULL,
    time_msc                BIGINT NOT NULL,
    seq                     INTEGER NOT NULL,
    bid                     DOUBLE PRECISION,
    ask                     DOUBLE PRECISION,
    last                    DOUBLE PRECISION,
    volume                  BIGINT,
    volume_real             DOUBLE PRECISION,
    flags                   INTEGER NOT NULL,
    server_utc_offset_sec   INTEGER,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (broker, symbol, time_utc, time_msc, seq),
    CONSTRAINT ticks_source_not_tkc CHECK (source <> 'tkc'),
    CONSTRAINT ticks_source_known CHECK (
        source IN ('copyticks_csv', 'synthetic')
    )
);

SELECT create_hypertable(
    'ticks',
    'time_utc',
    if_not_exists => TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS ticks_source_msc_seq_uidx
    ON ticks (broker, symbol, source, time_msc, seq);

CREATE INDEX IF NOT EXISTS ticks_symbol_time_idx
    ON ticks (broker, symbol, time_utc DESC);

COMMENT ON TABLE ticks IS
    'Broker MqlTick tape for research CVD. Quote-only rows are stored; they do not add to cvd_true.';
COMMENT ON COLUMN ticks.last IS '0 / NULL means no last trade on this tick.';
COMMENT ON COLUMN ticks.flags IS
    'MT5: BID=2 ASK=4 LAST=8 VOLUME=16 BUY=32 SELL=64.';
COMMENT ON COLUMN ticks.server_utc_offset_sec IS
    'Subtract from broker wall time_msc to obtain time_utc. Do not assume UTC.';

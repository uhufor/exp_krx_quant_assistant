SCHEMA_SQL = """
-- 종목 마스터
CREATE TABLE IF NOT EXISTS symbols (
    symbol       VARCHAR PRIMARY KEY,
    name         VARCHAR,
    market       VARCHAR,
    source       VARCHAR,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 일별 OHLCV
CREATE TABLE IF NOT EXISTS ohlcv_daily (
    symbol       VARCHAR NOT NULL,
    date         DATE NOT NULL,
    open         DOUBLE,
    high         DOUBLE,
    low          DOUBLE,
    close        DOUBLE NOT NULL,
    volume       BIGINT,
    source       VARCHAR,
    fetched_at   TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- 데이터 수집 실행 기록
CREATE TABLE IF NOT EXISTS data_fetch_runs (
    run_id       VARCHAR PRIMARY KEY,
    started_at   TIMESTAMP NOT NULL,
    finished_at  TIMESTAMP,
    status       VARCHAR NOT NULL DEFAULT 'running',  -- running | ok | error
    provider     VARCHAR,
    symbol_count INTEGER DEFAULT 0,
    error_msg    VARCHAR,
    notes        VARCHAR
);

-- 전략 실행 기록
CREATE TABLE IF NOT EXISTS strategy_runs (
    run_id       VARCHAR PRIMARY KEY,
    strategy     VARCHAR NOT NULL,
    params       JSON,
    started_at   TIMESTAMP NOT NULL,
    finished_at  TIMESTAMP,
    status       VARCHAR NOT NULL DEFAULT 'running',
    symbol_count INTEGER DEFAULT 0
);

-- 신호
CREATE TABLE IF NOT EXISTS signals (
    id           VARCHAR PRIMARY KEY,
    run_id       VARCHAR NOT NULL,
    symbol       VARCHAR NOT NULL,
    signal_date  DATE NOT NULL,
    signal_type  VARCHAR NOT NULL,  -- buy | sell | hold | watch | no_signal
    strategy     VARCHAR NOT NULL,
    score        DOUBLE,
    metrics      JSON,
    risk_flags   JSON,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 리포트
CREATE TABLE IF NOT EXISTS reports (
    id           VARCHAR PRIMARY KEY,
    run_id       VARCHAR NOT NULL,
    signal_id    VARCHAR NOT NULL,
    report_type  VARCHAR NOT NULL,  -- A | B
    content      TEXT NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 알림 발송 outbox (exactly-once 보장)
CREATE TABLE IF NOT EXISTS notification_outbox (
    id           VARCHAR PRIMARY KEY,
    run_id       VARCHAR NOT NULL,
    channel      VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    payload      TEXT NOT NULL,
    status       VARCHAR NOT NULL DEFAULT 'pending',  -- pending | sent | failed
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at      TIMESTAMP,
    error_msg    VARCHAR,
    retry_count  INTEGER DEFAULT 0,
    UNIQUE (channel, content_hash)
);

-- 실행 이벤트 로그
CREATE TABLE IF NOT EXISTS run_events (
    id           BIGINT PRIMARY KEY,
    run_id       VARCHAR NOT NULL,
    event_type   VARCHAR NOT NULL,
    message      TEXT,
    level        VARCHAR DEFAULT 'INFO',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE SEQUENCE IF NOT EXISTS run_events_id_seq START 1;
"""

BACKTEST_SCHEMA_SQL = """
-- 백테스트 실행 이력 (P3) — 정의·데이터 지문으로 재실행 캐시 판정
--
-- cache_key = definition_hash + params_hash + coverage_fingerprint 의 합성 해시.
-- 셋 중 하나라도 달라지면 다른 실행으로 취급하므로, DART/KRX로 데이터가 새로 채워지면
-- coverage_fingerprint가 바뀌어 캐시가 자동 무효화된다(낡은 결과 노출 불가).
--
-- 거래내역(trades)은 저장하지 않는다 — 재실행으로 재생성 가능하며 용량이 크다.
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id               VARCHAR   NOT NULL,
    cache_key            VARCHAR   NOT NULL,
    strategy_id          VARCHAR   NOT NULL,
    definition_hash      VARCHAR   NOT NULL,
    coverage_fingerprint VARCHAR   NOT NULL,
    params               JSON      NOT NULL,
    metrics              JSON      NOT NULL,
    per_symbol           JSON      NOT NULL,
    equity_curves        JSON      NOT NULL,
    benchmark            VARCHAR,
    benchmark_note       VARCHAR,
    errors               JSON      NOT NULL,
    executed_at          TIMESTAMP NOT NULL,
    PRIMARY KEY (run_id)
);
"""

# 이미 backtest_runs가 만들어진 DB에도 신규 컬럼을 적용하기 위한 멱등 마이그레이션(P1).
# CREATE TABLE IF NOT EXISTS는 기존 테이블의 컬럼을 늘려주지 않으므로 별도 경로가 필요하다.
BACKTEST_MIGRATION_SQL = (
    "ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS is_portfolio BOOLEAN",
    "ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS weights JSON",
)

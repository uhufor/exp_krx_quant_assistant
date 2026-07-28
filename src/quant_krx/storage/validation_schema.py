VALIDATION_SCHEMA_SQL = """
-- OOS/워크포워드 검증 실행 이력 (P4)
--
-- backtest_runs와 별개 테이블인 이유: 검증 1회는 내부적으로 (그리드 조합 × 폴드) 만큼
-- 백테스트를 돌린다. 그 중간 실행을 backtest_runs에 쌓으면 "사용자가 의도적으로 돌린
-- 백테스트" 이력이 검증 부산물에 파묻힌다. 따라서 내부 실행은 기록하지 않고, 검증 1회를
-- 여기 1행으로 요약한다(폴드 상세는 folds JSON).
--
-- 캐시 키가 없는 것도 의도적이다 — 검증은 비싸고 명시적으로 돌리는 작업이라 조용한
-- 캐시 히트가 오히려 혼란스럽다(백테스트 캐시와 다른 판단).
CREATE TABLE IF NOT EXISTS validation_runs (
    validation_id VARCHAR   NOT NULL,
    strategy_id   VARCHAR   NOT NULL,
    spec          JSON      NOT NULL,
    params        JSON      NOT NULL,
    summary       JSON      NOT NULL,
    folds         JSON      NOT NULL,
    oos_equity    JSON      NOT NULL,
    executed_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (validation_id)
);
"""

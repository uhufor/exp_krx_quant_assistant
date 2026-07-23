SCREENING_SCHEMA_SQL = """
-- 노코드 스크리닝 조건 (EPIC-03) — body(JSON)가 진실 원천
CREATE TABLE IF NOT EXISTS screening_conditions (
    id         VARCHAR   NOT NULL,
    name       VARCHAR,
    body       JSON      NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    PRIMARY KEY (id)
);
"""

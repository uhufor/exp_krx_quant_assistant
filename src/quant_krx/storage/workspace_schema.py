WORKSPACE_SCHEMA_SQL = """
-- 전략 활성 상태 (PRD-R03 FR-03)
CREATE TABLE IF NOT EXISTS strategy_activation (
    strategy_id  VARCHAR   NOT NULL,
    active       BOOLEAN   NOT NULL,
    updated_at   TIMESTAMP,
    PRIMARY KEY (strategy_id)
);

-- 사용자 Template (PRD-R03 FR-21). Built-in 5종은 코드 상수(BUILTIN_TEMPLATES)로 DB 미저장.
CREATE TABLE IF NOT EXISTS strategy_templates (
    template_id  VARCHAR   NOT NULL,
    name         VARCHAR,
    bundle       JSON      NOT NULL,
    created_at   TIMESTAMP,
    updated_at   TIMESTAMP,
    PRIMARY KEY (template_id)
);
"""

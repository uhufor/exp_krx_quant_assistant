DEFINITION_SCHEMA_SQL = """
-- Formula 정의 (PRD-R02 REQ-P1) — definition(JSON)이 진실 원천, 나머지는 조회용 비정규 컬럼
CREATE TABLE IF NOT EXISTS formulas (
    id             VARCHAR   NOT NULL,
    name           VARCHAR,
    version        VARCHAR,
    schema_version INTEGER,
    definition     JSON      NOT NULL,
    created_at     TIMESTAMP,
    updated_at     TIMESTAMP,
    PRIMARY KEY (id)
);

-- Rule 정의 (동형)
CREATE TABLE IF NOT EXISTS rules (
    id             VARCHAR   NOT NULL,
    name           VARCHAR,
    version        VARCHAR,
    schema_version INTEGER,
    definition     JSON      NOT NULL,
    created_at     TIMESTAMP,
    updated_at     TIMESTAMP,
    PRIMARY KEY (id)
);

-- Strategy 정의 (동형)
CREATE TABLE IF NOT EXISTS strategies (
    id             VARCHAR   NOT NULL,
    name           VARCHAR,
    version        VARCHAR,
    schema_version INTEGER,
    definition     JSON      NOT NULL,
    created_at     TIMESTAMP,
    updated_at     TIMESTAMP,
    PRIMARY KEY (id)
);
"""

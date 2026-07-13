FUNDAMENTAL_SCHEMA_SQL = """
-- 밸류에이션 일별 (PRD-R01 FR-14)
CREATE TABLE IF NOT EXISTS fundamental_daily (
    symbol      VARCHAR   NOT NULL,
    date        DATE      NOT NULL,
    close       DOUBLE,
    per         DOUBLE,
    pbr         DOUBLE,
    eps         DOUBLE,
    bps         DOUBLE,
    div         DOUBLE,
    dps         DOUBLE,
    market_cap  DOUBLE,
    shares      DOUBLE,
    source      VARCHAR,
    fetched_at  TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- 재무제표 분기 (PRD-R01 FR-15)
CREATE TABLE IF NOT EXISTS financial_statements (
    symbol                    VARCHAR  NOT NULL,
    fiscal_year               INTEGER  NOT NULL,
    fiscal_quarter            INTEGER  NOT NULL CHECK (fiscal_quarter IN (1,2,3,4)),
    statement_scope           VARCHAR  NOT NULL
        CHECK (statement_scope IN ('consolidated','separate')),
    revenue                   DOUBLE,
    gross_profit              DOUBLE,
    operating_income          DOUBLE,
    net_income                DOUBLE,
    pretax_income             DOUBLE,
    income_tax                DOUBLE,
    total_assets              DOUBLE,
    total_debt                DOUBLE,
    total_equity              DOUBLE,
    current_assets            DOUBLE,
    current_liabilities       DOUBLE,
    operating_cash_flow       DOUBLE,
    interest_expense          DOUBLE,
    depreciation_amortization DOUBLE,
    cash_and_equivalents      DOUBLE,
    invested_capital          DOUBLE,
    period_end                DATE,
    disclosure_date           DATE,
    source                    VARCHAR,
    fetched_at                TIMESTAMP,
    PRIMARY KEY (symbol, fiscal_year, fiscal_quarter, statement_scope)
);
"""

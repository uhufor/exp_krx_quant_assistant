SCREENING_CACHE_SCHEMA_SQL = """
-- 스크리닝 실행 결과 캐시 (P2)
--
-- EPIC-03 D5는 "실행 결과는 휘발성"으로 정했지만, 동적 유니버스 백테스트는 리밸런싱
-- 시점마다 같은 조건을 반복 실행하므로(월간 5년이면 60회) 캐시 없이는 실데이터 사용이
-- 현실적이지 않다. 조회 이력을 쌓는 테이블이 아니라 **재계산을 피하기 위한 캐시**이며,
-- condition_hash가 조건 본문에서 파생되므로 조건을 고치면 자동으로 무효화된다.
--
-- symbols는 통과 종목 코드 배열(JSON). 이름/시장은 표시용이라 캐시하지 않는다 —
-- 백테스트가 필요로 하는 것은 종목 코드뿐이다.
CREATE TABLE IF NOT EXISTS screening_result_cache (
    condition_id   VARCHAR   NOT NULL,
    condition_hash VARCHAR   NOT NULL,
    as_of          DATE      NOT NULL,
    symbols        JSON      NOT NULL,
    computed_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (condition_id, condition_hash, as_of)
);
"""

# PRD-R03 : No-Code Stock Screening

**Milestone**: Milestone 3 — No-Code Stock Screening
**Status**: Approved for implementation
**의존**: 없음(신규 독립 패키지) — `factors/`(계산 위임), `data/`(DI), `workspace/numeric`(leaf 공유)를 소비만 함 / **소비자**: 없음(최상위, CLI/GUI 사용자)
**근거**: `.omc/specs/deep-interview-epic03-nocode-screening.md`, `.omc/plans/epic-03-nocode-screening.md`(Architect/Critic 3라운드 APPROVE)

---

## 1. Background & Goal

기존 노코드 전략 워크스페이스는 종목 1개씩 조건을 평가하는 구조라 "전종목 대상 조건을 만족하는 종목을 찾는" 스크리닝 유스케이스를 표현할 수 없다. 사용자는 다음과 같은 복합 조건으로 KOSPI/KOSDAQ 전체에서 종목을 스크리닝하고 싶어한다:

> (MACD 0~5봉 전 중 하나에서 골든크로스 발생) AND (52주 최고가 대비 0%~-10%) AND (거래대금 순위 Top100) AND (거래량 순위 Top100)

목표:
1. AND/OR/NOT으로 임의 중첩 가능한 복합 조건을 사용자가 코드 없이 정의한다.
2. 조건에는 기존 비교 조건뿐 아니라 "최근 N봉 이내 이벤트 발생 여부"(시계열 윈도우)와 "전종목 대상 상대 순위"(크로스섹셔널) 조건을 포함할 수 있다.
3. CLI와 GUI가 완전히 동일한 서비스 계층을 통해 동일한 결과를 낸다.
4. 기존 노코드 워크스페이스(Formula/Rule/Strategy) 코드는 한 줄도 변경하지 않는다.

## 2. Scope

**In**: 스크리닝 조건 스키마(`screening/definition.py`) / 조건 평가 엔진(`screening/evaluation.py`) / 크로스섹셔널 순위 엔진(`screening/ranking.py`) / 스캔 유니버스 해석(`screening/universe.py`) / 신규 팩터 3종(거래대금·거래량·52주 최고가) / `DataProvider` 프로토콜 확장(`fetch_market_snapshot`) / 조건 정의 영속화(`screening_conditions` 테이블) / CLI(`screen-*`) / GUI(스크리닝 빌더 화면 + API 라우터).

**Out (확정)**: 실행 결과/이력 영속화 / Telegram 알림 연동 / 기존 3계층(`rule/formula/strategy`) 및 `workspace/evaluation.py`·`workspace/service.py`의 리팩터링(비침습 원칙) / 사용자 지정 부분집합 유니버스 / 6종 제외 필터(관리종목 등)의 실제 데이터 연동(하드 비활성화만, §8).

## 3. 핵심 계약 (Functional Requirements)

### 3.1 스크리닝 조건 스키마
- **FR-01** `screening/definition.py`는 자체 `Predicate{left, operator, right}`, `Composition{op: AND|OR|NOT, operands}`, `Operand`(`FactorOperand`/`ConstantOperand`/`FormulaOperand`), 신규 리프 `WindowPredicate{inner: Node, n_bars: int, include_current_bar: bool}`, `RankPredicate{factor_id, column, params, rank_metric: asc|desc, top_n: int}`, `ScreeningCondition{id, name, version, universe, root: Node, schema_version}`을 정의한다. **`quant_krx.rule.definition`을 import하지 않는다**(코드 완전 독립, INV-2 관례 준수).
- **FR-02** 직렬화(`to_dict`/`from_dict`)는 왕복 무손실이며 `schema_version` 다운그레이드를 차단한다(`rule/definition.py` 패턴 참고, 독립 구현).
- **FR-03** `screening/dispatch.py`가 `predicate`/`composition`/`window_predicate`/`rank_predicate` 4개 태그를 인식하는 screening 전용 `node_from_dict`를 제공한다(rule의 디스패치와 완전 독립).

### 3.2 평가 계약
- **FR-04** Predicate 평가는 `quant_krx.workspace.numeric`의 `compare`/`crosses` 함수를 그대로 import해서 호출한다(재구현 금지 — leaf 드리프트 구조적 차단). AND/OR/NOT 폴딩은 독립 구현하며 `workspace/evaluation.py::_eval_rule_node`와의 크로스-패리티 테스트로 의미론적 동일성을 보증한다.
- **FR-05** `WindowPredicate`는 내부 조건의 boolean Series에 대해 "최근 N봉(현재봉 포함/제외 파라미터화) 중 하나라도 True"를 rolling 연산으로 판정한다. `n_bars`, `include_current_bar`는 사용자가 UI/CLI에서 직접 설정한다.
- **FR-06** `RankPredicate`는 `DataProvider.fetch_market_snapshot(as_of_date, market)`(FR-09)로 얻은 시장 전체 단면에 대해 `.rank(method="min")`으로 순위를 매기고 `top_n` 임계를 적용한다. 종목별 순차 fetch를 사용하지 않는다.
- **FR-07** Predicate/WindowPredicate가 참조하는 팩터의 최대 필요 이력(예: MACD~35봉, rolling_high=252봉)을 조건 트리에서 동적으로 산정해, 종목별 시계열 조회 시 필요한 만큼만 요청한다(항상 252봉을 강제하지 않음).

### 3.3 데이터 계약
- **FR-08** `factors/catalog/`에 순수 계산 팩터 3종을 추가한다: `trading_value`(`close*volume`, **근사치** — RankPredicate에는 사용하지 않고 시계열 Formula/Predicate 비교 전용), `volume`(패스스루), `rolling_high`(`high.rolling(window).max()`, `window:int=252` 파라미터화). 기존 `PriceFactor` 패턴을 따르며 `register()`에 등록한다. INV-1(순수성) 위반 없음.
- **FR-09** `DataProvider` 프로토콜(`data/base.py`)에 `fetch_market_snapshot(date: date, market: str = "KRX") -> pd.DataFrame`(컬럼: `symbol, close, volume, trading_value` — 네이티브 거래대금 포함)을 신규 추가하고 `PyKrxAdapter`(`get_market_ohlcv_by_ticker` 기반, KOSPI+KOSDAQ 합산)와 `FixtureAdapter`(합성 스냅샷) 양쪽에 구현한다. `FDRAdapter`는 screening이 실제로 주입하지 않으므로 본 EPIC 범위에서 제외한다(후속 조사 대상).
- **FR-10** `screening/universe.py::resolve_scan_universe(provider: DataProvider, exclusion_filters: frozenset[str]) -> list[str]`가 `provider.list_symbols(market="KRX")`(이미 KOSPI+KOSDAQ 합산을 반환함, 확인됨)로 유니버스를 가져오고 4종 필터(`etf`/`etn`/`preferred`/`spac`)를 적용한다. 결과가 빈 리스트면 `EmptyUniverseError`를 던진다(조용한 빈 결과 금지).
- **FR-11** `screening/universe_data.py`가 `ohlcv_daily` 테이블을 캐시로 사용해 반복 스크리닝 실행 시 이미 확보된 구간은 재조회하지 않고 경계 바깥 구간만 증분 조회한다(신규 구현 — 기존 ad-hoc 백테스트 경로에는 이런 캐시가 없었음).

### 3.4 제외 필터 계약 (안전)
- **FR-12** `ScanUniverse.exclusion_filters` 스키마는 10종 필드를 예약하되, 6종(관리종목/투자경고·위험/거래정지/정리매매/환기종목/불성실공시기업)은 `ScreeningCondition` 생성/수정 시 포함되면 `UnsupportedFilterError`(명확한 사유)로 거부한다. CLI/GUI 모두 이 6종 토글은 비활성화 상태로 렌더링하고 "v1 미지원(데이터 소스 없음)" 안내를 노출한다. 선택 가능해 보이지만 효과 없는 UI를 만들지 않는다(안전 이슈, 확정 결정).

### 3.5 서비스·영속화 계약
- **FR-13** `screening/service.py::ScreeningService`가 `WorkspaceService`와 동일한 CRUD 파사드 패턴(create/show/edit/delete/list/validate/run)을 제공하며 CLI/GUI가 동일하게 호출한다. `run()`은 (동적 lookback 산정 → 유니버스 해석 → 시계열/순위 조건 평가 → 결과 조합) 후 통과 종목 리스트를 반환한다(DB 저장 없음).
- **FR-14** 신규 DuckDB 테이블 `screening_conditions`(PK `id`)를 additive DDL로 추가한다. 실행 결과/이력 테이블은 추가하지 않는다.

### 3.6 CLI/GUI 계약
- **FR-15** `__main__.py`에 `screen-create/show/edit/delete/list/validate/run` typer 커맨드를 `rule-*` 패턴으로 추가한다. `screen-run`은 저장된 조건을 실시간 실행해 통과 종목(코드+이름)을 출력한다.
- **FR-16** `api/routers/screenings.py` + `web/src/pages/ScreeningBuilderPage.tsx` + `web/src/tree/ScreeningTreeEditor.tsx`(6종 하드 비활성화 토글 포함)가 `rules.py`/`RuleBuilderPage.tsx`/`RuleTreeEditor.tsx` 패턴을 참고해 독립 구현된다(import 아님).

## 4. Acceptance Criteria (pytest 기계 검증, 기대값 하드코딩 금지)

- **AC-01** 스키마: 직렬화 왕복 무손실, `n_bars`/`top_n` 검증, `schema_version` 다운그레이드 차단, 6종 필터 포함 시 `UnsupportedFilterError`.
- **AC-02** 폴딩 크로스-패리티: `workspace/evaluation.py::_eval_rule_node`와 screening 평가기가 동일 boolean 입력에 대해 AND/OR/NOT 동일 결과. leaf(compare/crosses)는 공유 코드이므로 정적 import 확인만으로 충분.
- **AC-03** 신규 팩터: 산식 재도출 parity(하드코딩 기대값 금지), warm-up NaN, 결정론.
- **AC-04** WindowPredicate 경계값: 골든크로스가 정확히 3봉 전 발생한 합성 데이터로 `n_bars=5` True / `n_bars=2` False / `include_current_bar` on-off 경계.
- **AC-05** RankPredicate 경계값: 합성 다종목 거래대금으로 정확히 100위/101위 경계.
- **AC-06** 유니버스: 4종 필터 차집합 정확성, 빈 유니버스 시 `EmptyUniverseError`, `fetch_market_snapshot` 프로토콜 계약(양 adapter 동일 컬럼 반환).
- **AC-07** 서비스 통합: `tmp_path` DuckDB + `FixtureAdapter`로 조건 저장 → 실행 → 통과 종목 검증, watchlist 미사용 확인.
- **AC-08** CLI/GUI 동등성: 예시 조건(§1 인용)을 CLI/GUI 양쪽에서 생성·저장·실행 시 통과 종목 목록을 종목코드 오름차순 정렬 후 바이트 단위 동일.
- **AC-09** 회귀 없음: `uv run pytest tests/ -q` 전체 통과, 특히 `tests/unit/factors/test_purity_ast.py`(INV-1), 기존 `rule-*`/`strategy-*`/`fetch-fundamental` 테스트 무변경·무회귀.

## 5. CLI

- **FR-15 상세**: `screen-create <file>`(JSON 정의 파일) / `screen-show <id>` / `screen-edit <id> <file>` / `screen-delete <id>` / `screen-list` / `screen-validate <id>` / `screen-run <id>`(대상일 옵션 기본 최근 거래일). 미존재 id는 힌트 + non-zero 종료(기존 CLI 관례 준수).

## 6. 데이터 가용성 한계 (명시적 기록)

- pykrx는 관리종목/투자경고·위험/거래정지/정리매매/환기종목/불성실공시기업 상태 플래그를 노출하는 API가 없음(확인: `get_stock_major_changes`는 상호/대표이사 변경 이력일 뿐 상태 플래그 아님). 이 6종은 v1 하드 비활성화 대상이며, 데이터 소스 확보는 별도 EPIC 후보(ADR Follow-up #1, 사용자 재확인 필요).

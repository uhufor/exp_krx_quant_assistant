# TRD-R03 : No-Code Stock Screening

**대응 PRD**: `PRD-R03-SCREENING.md`
**계층**: 신규 독립 패키지(`screening/`) — `factors/`(계산 위임)·`data/`(DI)·`workspace/numeric`(leaf 공유)를 소비만 함 / **의존**: 없음(신규) / **소비자**: 없음(최상위, CLI/GUI)
**Status**: Approved (Architect/Critic 3라운드 컨센서스, `.omc/plans/epic-03-nocode-screening.md` 참고)
**전제**: 본 문서는 main 브랜치 시점에서 No-Code Stock Screening을 **처음 구현한다**고 가정한다. 모든 서술은 PRD-R03 + README.md(§4 D1~D5·§5 공통 불변 원칙) + 컨센서스 플랜(`.omc/plans/epic-03-nocode-screening.md`, Architect 3라운드/Critic 3라운드 검토 기록) 역추적으로만 정당화한다.

---

## 0. RALPLAN-DR 요약 (SHORT)

### Principles (5)

1. 기존 3계층(Formula/Rule/Strategy)·`workspace/evaluation.py`·`workspace/service.py`는 코드 한 줄도 건드리지 않는다.
2. `factors/` 순수성(INV-1)은 절대 위반하지 않는다.
3. 저장소의 기존 관례(INV-2: 중복 > 결합)를 따른다 — `screening/`은 `rule.definition`을 import하지 않고 자체 스키마를 독립 정의하되, leaf(비교/교차) 로직만 `workspace.numeric`을 그대로 import해 공유한다.
4. CLI/GUI 동등성은 협상 불가.
5. 미구현 기능은 침묵하지 않는다(6종 필터 하드 비활성화, 빈 유니버스 명시적 에러).

### Decision Drivers (top 3)

1. **`rule/definition.py`의 dispatch/eval이 자기 노드 집합에 하드바인딩** — `Composition.from_dict`(모듈 레벨 `node_from_dict`, `predicate`/`composition` 태그만 인식)와 `_eval_rule_node`(자기 재귀)가 신규 노드 타입(`WindowPredicate`/`RankPredicate`)을 지원하지 못함. "트리 전체 import 재사용"이 기술적으로 불가능함을 1차 Architect 검토에서 확증.
2. **AND/OR/NOT 폴딩(자명)과 compare/crosses leaf(실질 드리프트 위험)의 위험 수준이 다름** — 2차 Architect 검토에서 발견. 완전 격리(독립 재구현)는 폴딩엔 안전하지만 leaf엔 위험을 방치한다.
3. **pykrx 데이터 가용성 한계 + `DataProvider` 프로토콜에 스냅샷 메서드 부재** — 10종 제외 필터 중 4종만 즉시 구현 가능. 순위 조건의 데이터 경로(시장 전체 스냅샷)가 기존 프로토콜(종목별 fetch만)과 맞지 않아 DI 원칙과 충돌할 뻔함(2차 Critic 검토에서 발견, 프로토콜 확장으로 해소).

### Viable Options

**결정 축 A — 조건 트리 구현 방식**

| Option | 설명 | 채택 |
|---|---|---|
| A1: `rule.definition` 트리 전체 import 재사용 | Composition/Predicate 그대로 import | ❌ 기술적으로 불가능(dispatch/eval 하드바인딩) |
| A2: 완전 독립 재구현(폴딩+leaf 모두) | rule 미참조, 전부 독립 코드 | ❌ leaf(compare/crosses) 드리프트 위험 방치 |
| **A2': 폴딩 독립 + leaf 공유** ✅채택 | AND/OR/NOT은 독립 구현(크로스-패리티 테스트로 보증), compare/crosses는 `workspace.numeric` import | 격리(Non-Goal 준수)와 드리프트 방지(구조적 공유)를 동시 달성 |
| A3: 공유 트리워커 추출 + `rule` 리팩터링 | rule도 공유 모듈로 전환 | ❌ Non-Goal(기존 rule 코드 리팩터링 금지) 위반, Follow-up으로만 보류 |

**무효화 근거**: A1은 코드 사실(`rule/definition.py:163-185`)로 반증됨. A2(완전 독립)는 leaf가 실질 드리프트 위험을 안고 있음에도 아무 안전장치가 없어 기각. A3는 사용자가 확정한 Non-Goal에 정면 저촉되어 기각. A2'는 `workspace.numeric`이 rule/formula/strategy/evaluation.py가 아닌 순수 유틸(rule 자신도 이미 소비 중)이므로 참조가 "리팩터링"에 해당하지 않아 Non-Goal을 지키면서 드리프트 방지 이익을 확보.

**결정 축 B — 스캔 유니버스 제외조건 범위**

| Option | 설명 | 채택 |
|---|---|---|
| B1: 10종 전부 노출, 미구현 6종 no-op | | ❌ 안전 이슈(선택했는데 효과 없음을 사용자가 인지 못함) |
| **B2: 4종만 v1 포함, 6종 하드 비활성화** ✅채택 | ETF/ETN/우선주/SPAC만 실제 동작, 나머지는 선택 자체 차단 | 구현된 모든 기능이 실제 동작, 정직한 스코프 |
| B3: 6종 위한 신규 데이터 소스 조사·통합 | | ❌ EPIC 범위 초과, 크롤링 리스크 — 별도 EPIC 후보 |

**결정 축 C — 크로스섹셔널 순위 데이터 경로**

| Option | 설명 | 채택 |
|---|---|---|
| C1: 종목별 순차 fetch로 순위 산출 | | ❌ ~2,500콜 병목 |
| C2: `PyKrxAdapter` 하드코딩 스냅샷 호출 | | ❌ DI 원칙(AC-08) 위반 |
| **C3: `DataProvider` 프로토콜에 `fetch_market_snapshot` 추가, DI로 호출** ✅채택 | 1~2콜, 프로토콜 확장은 `data/`만 건드림 | 성능·DI 원칙 동시 충족 |

### ADR 요약

- **Decision**: A2'(폴딩 독립+leaf 공유) + B2(4종만 v1) + C3(프로토콜 확장 DI).
- **Drivers**: 트리 하드바인딩으로 인한 재사용 불가 / leaf 드리프트 위험과 폴딩 자명성의 비대칭 / pykrx 데이터 한계 / DI-성능 모순.
- **Consequences**: `screening/`과 `rule/`이 폴딩 로직만 형태적 중복(크로스-패리티 테스트로 보증), leaf(compare/crosses)는 코드 공유로 드리프트 불가능. `DataProvider` 프로토콜이 확장되어 모든 어댑터가 `fetch_market_snapshot`을 구현 대상이 되나(screening이 실제 주입하는 PyKrx/Fixture만 필수, FDR은 후속 조사). 6종 필터는 사용자 재확인이 필요한 스코프 축소.
- **Follow-ups**: (1) 6종 필터 사용자 재확인, (2) A3(공유 트리워커로 rule까지 통합)는 향후 명시 승인 시 재검토, (3) 성능 벤치마크 실측 후 병렬화 검토, (4) `FDRAdapter`의 `fetch_market_snapshot` 지원 여부 조사.

---

## 1. 목적

`screening/` 패키지의 기술 요구사항을 확정한다: 조건 스키마의 완전 독립 배선(leaf 공유 예외), 평가 엔진의 폴딩/leaf 분리 구현, 순위 엔진의 스냅샷 데이터 경로, 유니버스 해석·제외 필터 하드 비활성화, 영속화·서비스·CLI/GUI 배선.

## 2. 범위 (In / Out)

### In
- `screening/definition.py`·`screening/dispatch.py`(완전 독립 스키마 + 디스패치)
- `screening/evaluation.py`(폴딩 독립 + leaf `workspace.numeric` 공유)
- `screening/ranking.py`(크로스섹셔널 순위, `fetch_market_snapshot` DI 소비)
- `screening/universe.py` + `screening/universe_data.py`(유니버스 해석 + OHLCV 캐시)
- `data/base.py::DataProvider` 프로토콜 확장(`fetch_market_snapshot`) + `PyKrxAdapter`/`FixtureAdapter` 구현
- `factors/catalog/`(`trading_value`/`volume`/`rolling_high` 3종 추가)
- `screening/service.py`(`ScreeningService` CRUD 파사드)
- `data/screening_schema.py`(`screening_conditions` additive DDL)
- CLI(`screen-*`)·GUI(`api/routers/screenings.py`, `ScreeningBuilderPage.tsx`, `ScreeningTreeEditor.tsx`)

### Out (확정)
- `rule/`, `formula/`, `strategy/`, `workspace/evaluation.py`, `workspace/service.py` 변경 (비침습 원칙).
- 스크리닝 실행 결과/이력 영속화.
- Telegram 알림 연동.

## 3. PRD 추적성 매트릭스

| FR | 요지 | TR | 근거 |
|---|---|---|---|
| FR-01~03 | 독립 스키마 + 디스패치 | TR-R03S-001, TR-R03S-002 | PRD §3.1 |
| FR-04 | leaf 공유 + 폴딩 독립 | TR-R03S-003 | PRD §3.2, A2' |
| FR-05 | WindowPredicate rolling 판정 | TR-R03S-004 | PRD §3.2 |
| FR-06 | RankPredicate 스냅샷 기반 | TR-R03S-005 | PRD §3.2, C3 |
| FR-07 | 동적 lookback 산정 | TR-R03S-006 | PRD §3.2 |
| FR-08 | 신규 팩터 3종 | TR-R03S-007 | PRD §3.3 |
| FR-09 | `fetch_market_snapshot` 프로토콜 확장 | TR-R03S-008 | PRD §3.3, C3 |
| FR-10 | 유니버스 해석 + `EmptyUniverseError` | TR-R03S-009 | PRD §3.3 |
| FR-11 | OHLCV 캐시(신규) | TR-R03S-010 | PRD §3.3 |
| FR-12 | 6종 필터 하드 비활성화 | TR-R03S-011 | PRD §3.4, B2 |
| FR-13 | `ScreeningService` CRUD | TR-R03S-012 | PRD §3.5 |
| FR-14 | `screening_conditions` DDL | TR-R03S-013 | PRD §3.5 |
| FR-15 | CLI `screen-*` | TR-R03S-014 | PRD §3.6 |
| FR-16 | GUI 라우터/페이지 | TR-R03S-015 | PRD §3.6 |

**커버리지**: FR-01~16 전건 매핑 완료. 공백 0.

## 4. 기술 요구사항 (TR-R03S-xxx)

### 4.1 스키마·디스패치

**TR-R03S-001 — 완전 독립 스키마 배선**
- `screening/definition.py`는 `Predicate`, `Composition`, `Operand`(`FactorOperand`/`ConstantOperand`/`FormulaOperand`), `WindowPredicate`, `RankPredicate`, `ScreeningCondition`을 `rule.definition` import 없이 독립 정의한다(A2'). `frozen=True`, `to_dict`/`from_dict` 왕복 무손실, `schema_version` 다운그레이드 차단(`rule/definition.py:188-225` 패턴 참고, 코드 독립).
- 근거: `← FR-01/02, A2', PRD §3.1`

**TR-R03S-002 — screening 전용 디스패치**
- `screening/dispatch.py::node_from_dict`가 `predicate`/`composition`/`window_predicate`/`rank_predicate` 4개 태그를 인식한다. `rule.definition._NODE_DISPATCH`와 독립(참조 없음).
- 근거: `← FR-03, PRD §3.1`

### 4.2 평가 엔진

**TR-R03S-003 — 폴딩 독립 + leaf 공유 배선(A2', 핵심 결정)**
- `screening/evaluation.py::_eval_screening_node`의 Predicate 평가는 `quant_krx.workspace.numeric.compare`/`.crosses`를 **그대로 import해서 호출**한다(재구현 금지). Composition(AND/OR/NOT) 폴딩은 독립 구현하되 `tests/unit/screening/test_logic_parity.py`가 `workspace/evaluation.py::_eval_rule_node`와 동일 boolean 입력에 대해 동일 결과임을 검증한다.
- 근거: 이 배선은 `workspace/numeric.py`가 rule/formula/strategy/evaluation.py에 속하지 않는 독립 순수 유틸이며 rule 자신도 이미 이를 소비(`workspace/evaluation.py:118-120`)한다는 사실로 정당화된다 — Non-Goal("기존 rule/formula/strategy 코드 리팩터링 금지")은 `numeric.py` 참조에 저촉되지 않는다(참조 ≠ 리팩터링).
- `← FR-04, A2', PRD §3.2`

**TR-R03S-004 — WindowPredicate rolling 판정**
- 내부 조건 boolean Series에 대해 `n_bars`(정수)와 `include_current_bar`(bool) 파라미터로 "최근 N봉 중 하나라도 True"를 rolling `.any()` 계열 연산으로 판정한다. 경계값(`n_bars=0`, `include_current_bar` on/off)은 테스트로 고정(PRD AC-04).
- `← FR-05, PRD §3.2`

**TR-R03S-005 — RankPredicate 스냅샷 기반 배선(C3)**
- `screening/ranking.py::compute_cross_sectional_rank()`가 `provider.fetch_market_snapshot(as_of_date, market)`(TR-R03S-008, DI)로 얻은 단면에서 지정 컬럼(`trading_value`/`volume`)에 `.rank(method="min")`을 적용하고 `top_n` 임계 필터를 적용한다. 종목별 순차 fetch 금지. `factors/`는 import하되 위치는 `factors/` 밖(INV-1 유지, `test_purity_ast.py` 스캔 대상 아님).
- `← FR-06, C3, PRD §3.2`

**TR-R03S-006 — 동적 lookback 산정**
- 조건 트리를 순회해 참조된 팩터/윈도우의 최대 필요 이력(예: `rolling_high.window`, MACD 기본 warm-up, `WindowPredicate.n_bars`)을 산정하고, 종목별 시계열 조회 시 이 값만큼만 요청한다(항상 252봉 강제 금지).
- `← FR-07, PRD §3.2`

### 4.3 데이터 계약

**TR-R03S-007 — 신규 팩터 3종(factors/ 순수 계층)**
- `factors/catalog/technical.py`에 `TradingValueFactor`(id=`trading_value`, `close*volume`, description에 "근사치 — RankPredicate 미사용" 명시), `VolumeFactor`(id=`volume`, 패스스루), `RollingHighFactor`(id=`rolling_high`, `window:int=252`, `high.rolling(window).max()`, `_mark_warmup_nan` 적용)를 `PriceFactor` 패턴(`:18-35`)으로 추가, `register()`(`:211-218`)에 등록.
- `← FR-08, PRD §3.3`

**TR-R03S-008 — `DataProvider` 프로토콜 확장(C3)**
- `data/base.py::DataProvider`에 `fetch_market_snapshot(date: date, market: str = "KRX") -> pd.DataFrame`(컬럼: `symbol, close, volume, trading_value`)를 추가한다(구조적 `runtime_checkable Protocol`이므로 기존 구현체를 깨뜨리지 않음 — 새 메서드를 호출하는 코드만 신규 메서드를 요구). `PyKrxAdapter`는 `stock.get_market_ohlcv_by_ticker(date, market)`(KOSPI+KOSDAQ 각 1콜 합산)로 구현하고, `FixtureAdapter`는 합성 스냅샷으로 구현한다. `FDRAdapter`는 screening이 주입하지 않으므로 본 EPIC 범위에서 구현 보류(Follow-up #4).
- `← FR-09, C3, PRD §3.3`

**TR-R03S-009 — 유니버스 해석 + 명시적 실패**
- `screening/universe.py::resolve_scan_universe(provider: DataProvider, exclusion_filters: frozenset[str]) -> list[str]`가 `provider.list_symbols(market="KRX")`(KOSPI+KOSDAQ 합산 확인됨, `pykrx_adapter.py:27-29`)를 호출하고 4종 필터를 적용한다: `etf`(`stock.get_etf_ticker_list()` 차집합), `etn`(`stock.get_etn_ticker_list()` 차집합), `preferred`(종목명 패턴), `spac`(종목명 "기업인수목적" 패턴). 결과가 빈 리스트면 `EmptyUniverseError`(조용한 빈 결과 금지 — `pykrx_adapter.py:33-34`의 예외 삼킴과 무관하게 screening 계층에서 별도 방어).
- `← FR-10, PRD §3.3`

**TR-R03S-010 — OHLCV 캐시(신규, 성능)**
- `screening/universe_data.py`가 `ohlcv_daily`(PK `symbol, date`) 커버리지를 조회해 경계 바깥 구간만 provider로 채우고 upsert한다. 이는 `data_loading.py`의 fundamental gap-fill 패턴을 **참고한 신규 구현**이다(OHLCV에는 기존에 이런 캐시가 없었음). `--no-cache` 옵션으로 우회 가능.
- `← FR-11, PRD §3.3`

### 4.4 제외 필터 안전 배선

**TR-R03S-011 — 6종 필터 하드 비활성화(B2)**
- `ScanUniverse.exclusion_filters` 스키마는 10종 필드를 예약한다. `ScreeningCondition` 생성/수정 시 6종(관리종목/투자경고·위험/거래정지/정리매매/환기종목/불성실공시기업) 중 하나라도 포함되면 `UnsupportedFilterError`(명확한 사유)로 거부한다. CLI/GUI는 이 6종 토글을 비활성화 렌더링 + "v1 미지원" 안내.
- `← FR-12, B2, PRD §3.4`

### 4.5 서비스·영속화·CLI/GUI

**TR-R03S-012 — `ScreeningService` CRUD 배선**
- `WorkspaceService` CRUD 패턴(create/show/edit/delete/list/validate/run)을 따른다. `run()`은 동적 lookback 산정(TR-R03S-006) → 유니버스 해석(TR-R03S-009) → 시계열 조건 평가(TR-R03S-003/004) + 순위 조건 평가(TR-R03S-005) 조합 → 통과 종목 리스트 반환(DB 저장 없음).
- `← FR-13, PRD §3.5`

**TR-R03S-013 — `screening_conditions` additive DDL**
- PK `id`, JSON 직렬화된 조건 본문. 기존 8+2+3테이블 DDL 무변경. `CREATE TABLE IF NOT EXISTS` 멱등.
- `← FR-14, PRD §3.5`

**TR-R03S-014 — CLI 배선**
- `__main__.py`에 `screen-create/show/edit/delete/list/validate/run` typer 커맨드를 `rule-*`(`__main__.py:587-624`) 패턴으로 추가.
- `← FR-15, PRD §3.6`

**TR-R03S-015 — GUI 배선**
- `api/routers/screenings.py`(`api/routers/rules.py` 패턴), `web/src/pages/ScreeningBuilderPage.tsx`(`RuleBuilderPage.tsx` 패턴, import 아닌 참고), `web/src/tree/ScreeningTreeEditor.tsx`(6종 하드 비활성화 토글 포함).
- `← FR-16, PRD §3.6`

## 5. 비기능 요구사항 (NFR)

| NFR | 요구 | 검증 |
|---|---|---|
| NFR-01 완전 격리(폴딩) | screening 폴딩 로직은 rule import 없음 | 정적 import 스캔 + 크로스-패리티 테스트 |
| NFR-02 leaf 무드리프트 | compare/crosses는 rule과 동일 코드 | `workspace.numeric` import 정적 확인 |
| NFR-03 오프라인 검증 | 전 AC가 네트워크 없이 Fixture+격리 DuckDB로 검증 | CI green |
| NFR-04 성능(비-CI) | 전체 유니버스 스크리닝 1회 실행 시간 기록(캐시 미스/히트) | 수동 벤치마크, `docs/NO_CODE_SCREENING.md` 기록 |
| NFR-05 안전 | 6종 필터는 선택 자체 불가(no-op 아님), 빈 유니버스는 에러 | `UnsupportedFilterError`/`EmptyUniverseError` 단위 테스트 |

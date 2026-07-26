# Refined Epics — No-Code Stock Screening PRD

**작성일**: 2026-07-23
**Status**: Approved for implementation (deep-interview → omc-plan consensus 3라운드, Architect/Critic APPROVE)
**지위**: 본 디렉터리의 PRD-R03이 요구사항의 유일한 진실 원천이며, 외부 문서 없이 자체 완결적으로 TRD → DESIGN → 구현 진행이 가능해야 한다.
**근거**: `.omc/specs/deep-interview-epic03-nocode-screening.md`(명확도 11%), `.omc/plans/epic-03-nocode-screening.md`(컨센서스 승인 완료)

---

## 1. 제품 정의 (한 문장)

**No-Code Stock Screening** = 사용자가 코드 없이, AND/OR/NOT으로 조합된 복합 조건(비교·시계열 윈도우·전종목 순위)을 정의해 KOSPI/KOSDAQ 전체 유니버스에서 조건을 만족하는 종목을 CLI와 GUI 양쪽에서 동일하게 스크리닝하는 EPIC-03 기능.

## 2. 기반 전제 (Baseline)

본 PRD는 EPIC_R01(Factor Platform, Declarative Definition Core, Workspace & Execution)과 EPIC_R02(GUI)가 완료된 현재 브랜치 위에 구현한다. 전제하는 기존 자산:

- **노코드 전략 워크스페이스**: Formula → Rule → Strategy 3계층(`formula/`, `rule/`, `strategy/`), `Predicate`/`Composition`(AND/OR/NOT) 조건 트리, `WorkspaceService` 파사드, CLI(`rule-*`/`strategy-*`)와 GUI(`web/`, `api/routers/`)가 동일한 서비스 계층을 공유(`docs/NO_CODE_STRATEGY_WORKSPACE.md`).
- **팩터 플랫폼**: `factors/` 32종(가격·기술 7 + 밸류에이션 11 + 재무제표 14), INV-1(순수 계산, 실행/저장 계층 역참조 금지, AST 강제) 불변식.
- **데이터 계층**: `DataProvider` 프로토콜(`FDRAdapter`/`PyKrxAdapter`/`FixtureAdapter`), `list_symbols()`가 KOSPI+KOSDAQ 종목 코드를 반환하지만 현재 어디서도 호출되지 않는 미사용 코드.

이 상태의 공백 — 전종목 스캔·순위 조건·시계열 윈도우 조건이 없다 — 을 본 EPIC-03이 메운다. 기존 노코드 워크스페이스(Formula/Rule/Strategy)와 다운스트림(신호→리포트→알림)은 재사용하지 않으며(무관한 별개 기능), 재구축하지도 않는다(코드 한 줄도 건드리지 않음).

## 3. 계층 구조 (단일 PRD, 신규 독립 패키지)

| 구성요소 | 책임 | 코드 경계 | 비고 |
|---|---|---|---|
| **신규 팩터** | 거래대금/거래량/52주 최고가 순수 계산 | `factors/catalog/` (기존 확장) | INV-1 순수성 유지 |
| **스크리닝 스키마·평가·순위 엔진** | 조건 정의·평가·전종목 순위 | `screening/`(전체 신규 독립 패키지) | `rule/definition.py` import 금지(완전 독립) — leaf(compare/crosses)만 `workspace/numeric` 공유 |
| **데이터 프로토콜 확장** | 시장 전체 스냅샷 조회 | `data/base.py`(`DataProvider`에 `fetch_market_snapshot` 추가) | 기존 3개 어댑터 확장, `rule/formula/strategy` 미변경 |
| **CLI/GUI** | 조건 CRUD·실행 | `__main__.py`(`screen-*`), `api/routers/screenings.py`, `web/src/pages/ScreeningBuilderPage.tsx` | 기존 `rule-*`/`RuleBuilderPage` 패턴 재사용(참고, import 아님) |

의존 방향: `screening/` → `factors/`(계산 위임) + `data/`(DI) + `workspace/numeric`(leaf 공유), 역방향 금지. `rule/`, `formula/`, `strategy/`, `workspace/evaluation.py`, `workspace/service.py`는 **코드 한 줄도 변경하지 않는다**(Non-Goal, 확정).

## 4. 핵심 제품 결정 (D1~D5)

### D1. 스크리닝은 기존 전략 워크스페이스의 확장이 아니라 완전히 별개의 신규 기능이다
사용자가 deep-interview Round 0에서 명시적으로 확인: 스크리닝은 factor/formula/rule/strategy/backtest의 확장이 아니라 개별적인 신규 기능이며, 검색 조건 구성 방식을 새로 만들어야 한다. → PRD §5, TRD §0 결정 축 A

### D2. 조건 트리(AND/OR/NOT)는 개념적으로 재사용하되 코드는 독립이다
`rule/definition.py`의 `Composition.from_dict`/`_eval_rule_node`가 자기 노드 집합에 하드바인딩되어 있어(`predicate`/`composition` 태그만 인식) 트리 전체 재사용은 기술적으로 불가능함이 확인됨(Architect 1라운드). `screening/`은 자체 `Predicate`/`Composition`/`WindowPredicate`/`RankPredicate`를 독립 정의하되(저장소의 기존 INV-2 관례 "중복 > 결합"과 일치), 비교/교차 leaf 로직(`numeric.compare`/`numeric.crosses`)만 `workspace.numeric`을 그대로 import해 재사용한다(드리프트 구조적 차단). → PRD §6, TRD 결정 축 A2, DESIGN §3

### D3. 순위 조건과 시계열 조건은 데이터 경로가 근본적으로 다르다
`RankPredicate`(거래대금/거래량 순위)는 as-of 단일 거래일 시장 전체 스냅샷(`DataProvider.fetch_market_snapshot`, 1~2콜)만 필요하고, `WindowPredicate`/`Predicate`(MACD 골든크로스 등)는 종목별 동적 lookback 시계열이 필요하다. 이 둘을 같은 데이터 경로로 처리하지 않는다. → PRD §7, TRD 결정 축(성능)

### D4. 미구현 기능은 침묵하지 않는다
10종 제외 필터(관리종목/투자경고·위험/우선주/거래정지/정리매매/환기종목/불성실공시기업/ETF/SPAC/ETN) 중 4종(ETF/ETN/우선주/SPAC)만 pykrx 데이터로 즉시 구현 가능하다. 나머지 6종은 v1에서 **하드 비활성화**(선택 불가, 선택 가능한 no-op 금지 — 안전 이슈)한다. 빈 유니버스도 조용히 통과시키지 않고 `EmptyUniverseError`로 승격한다. → PRD §8, TRD 결정 축 B

### D5. 조건 정의는 영속화하되 실행 결과는 휘발성이다
스크리닝 조건 정의(`ScreeningCondition`)는 DuckDB에 저장해 재사용 가능하지만, 실행 결과(통과 종목 목록)는 매번 실시간 계산하며 이력/추이를 저장하는 테이블은 두지 않는다(사용자 확정). → PRD §9

## 5. 전 계층 공통 불변 원칙

1. **완전 독립**: `screening/`은 `rule/formula/strategy/workspace/evaluation.py/workspace/service.py`를 import하지 않는다(leaf 유틸 `workspace.numeric`만 예외 — 순수 유틸이며 Non-Goal 대상 아님).
2. **`factors/` 순수성(INV-1) 불변**: 신규 팩터는 순수 단일 종목 계산만 하고, 전종목 순위 계산은 `factors/` 밖(`screening/ranking.py`)에 둔다.
3. **CLI/GUI 동등성**: 동일 조건을 CLI/GUI 양쪽에서 생성·실행 시 통과 종목 목록이 (정렬 후) 바이트 단위로 동일하다.
4. **명시적 실패**: 빈 유니버스, 미지원 필터 선택 시도는 조용히 통과하지 않고 명확한 에러로 거부한다.
5. **오프라인 검증 가능**: 모든 요구사항은 네트워크·실데이터 없이 합성 Fixture + 격리 DuckDB + pytest로 결정론 검증 가능해야 한다.
6. **additive 진화**: 신규 테이블(`screening_conditions`)만 추가, 기존 DDL 변경 금지. `DataProvider` 프로토콜은 메서드 추가만(기존 메서드 시그니처 무변경).

## 6. 명시적 전역 Out of Scope (Non-Goal)

- 스크리닝 실행 결과(통과 종목 목록)의 DB 저장/이력 추적/추이 분석.
- Telegram 등 알림 파이프라인 연동.
- 기존 `factor/formula/rule/strategy/backtest`/`workspace/evaluation.py`/`workspace/service.py` 코드의 리팩터링 또는 구조 변경(단, `data/base.py::DataProvider` 프로토콜에 신규 메서드 추가는 예외 — 기존 메서드 무변경).
- 사용자 지정 부분집합(코스피200, 특정 산업군) 유니버스 — v1은 KOSPI+KOSDAQ 전체 + 토글식 제외조건만.
- 6종 제외 필터(관리종목/투자경고·위험/거래정지/정리매매/환기종목/불성실공시기업)의 실제 데이터 연동 — v1은 하드 비활성화, 별도 데이터 소스 확보는 후속 EPIC(사용자 재확인 필요, ADR Follow-up #1).

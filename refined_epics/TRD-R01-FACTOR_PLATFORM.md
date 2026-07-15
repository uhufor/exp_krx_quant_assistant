# TRD-R01 : Factor Platform

**대응 PRD**: `PRD-R01-FACTOR_PLATFORM.md`
**계층**: R01 (최하위, 순수 — 실행·저장 무의존) / **소비자**: R02(참조 검증), R03(평가·실행)
**Status**: Draft for review
**전제**: 본 문서는 main 브랜치 시점에서 팩터 플랫폼을 **처음 구현한다**고 가정한다. 모든 서술은 PRD-R01 + `README.md` 역추적으로만 정당화한다.

> **문서 규약(§D no-restate)**: PRD-R01이 이미 TR급으로 확정한 항목(32종 산식표 §4, DDL §6, `FactorMetadata`/`ParamSpec`/`FactorInput` 시그니처 §3, as-of 규약 FR-17)은 본 문서 §4 TR에서 반복 서술하지 않고 §3 추적성 매트릭스 1행으로 축약한다(`FR-xx ← TR-R01-yy (PRD 확정 인용)`). §4 TR은 **PRD에 없는 기술 결정**(계층 간 배선, NFR, AC→pytest 매핑 구체화, Open Tension 해소, 모듈 배치 원칙, 오류 모델 구체화)만 담는다. 시그니처의 확정 원천은 후속 `DESIGN-R01 §3`이며, 본 TRD는 이를 재정의하지 않는다(§D-2).

---

## 0. RALPLAN-DR 요약 (SHORT)

본 절은 **이 TRD 수준에서 새로 내리는 기술 결정**(PRD가 확정하지 않은 배선·구현 선택)에 한정한다. D1~D5·32종 산식·DDL·시그니처는 확정 전제이므로 재논쟁하지 않는다(README §4/§5 정본 인용).

### Principles (원칙 3)

1. **PRD 역추적 유일 정당화**: 모든 TR은 PRD-R01의 FR/AC/INV 또는 README §4(D1~D5)/§5(공통 원칙 7)로 역추적된다. TR은 요구사항을 창작하지 않고 기술 번역·배선만 한다.
2. **결정론·오프라인 검증이 완료 판정 축**: 모든 AC는 합성 Fixture + 격리 DuckDB + pytest로 네트워크·실데이터·시각 의존 없이 2회 동일 검증 가능해야 한다. 기대값 하드코딩 금지(산식 재도출).
3. **계층 순수성 우선**: `factors/`·`data/`는 실행·저장·백테스트 계층을 import하지 않는다(INV-1). 문서 경계 = 코드 경계이며 이는 최상위 제약이다.

### Decision Drivers (상위 3)

1. **결정성 보존**: 결측 사유·as-of 정렬·수집 게이트의 경계 케이스(공시 tie-break, div0, 미래 일자)가 비결정성의 원천이 되지 않도록 배선한다.
2. **상위 계층 인용 안정성**: R02 직렬화가 참조할 팩터 `id`·`FactorInput` 형상은 안정 앵커여야 하며, 배선 선택이 이 앵커를 흔들면 안 된다.
3. **degrade 우선(미연동이 카탈로그를 막지 않음)**: DART 미연동 상태에서도 32종 전건이 등록·조회되고, 재무 팩터는 예외 없이 NaN으로 강등된다.

### Viable Options (TRD 수준의 자유 결정, ≥2 + 무효화 근거)

**결정 축 A1 — 수집 품질 게이트(FR-17b) 배치**

| 옵션 | 방식 | 장점 | 단점 |
|---|---|---|---|
| **A1-i. 저장 경로 단일 게이트** ✅채택 | `data/` upsert 진입점 직전에 4종 검사(PK 중복·오름차순·미래 일자·음수) 단일 함수 배치, 위반 행 제외+사유 기록 | 어댑터 3종이 게이트를 우회 불가(단일 강제점) / `fetch-fundamental`·Daily 자동수집이 동일 경로 공유(FR-17a) | 게이트가 provider별 특수 규칙을 알기 어려움(공통 규칙만 강제) |
| A1-ii. 어댑터 내부 검증 | 각 어댑터가 자체 검증 후 저장 | provider 특화 규칙 가능 | 어댑터 3종 규칙 drift / 신규 어댑터가 게이트 누락 위험 / 공유 경로 보장 불가 |

**무효화 근거**: A1-ii는 driver#1(결정성 보존)과 FR-17a(동일 upsert 경로 공유)를 구조적으로 위협 — 어댑터별 게이트는 3중 drift와 우회 가능성을 남긴다. A1-i는 단일 강제점으로 "위반 행 제외+기록, 수집 중단 없음"을 한 곳에서 보증한다.

**결정 축 A2 — as-of 정렬(FR-17) 구현 수단**

| 옵션 | 방식 | 장점 | 단점 |
|---|---|---|---|
| **A2-i. `pandas.merge_asof`(backward)** ✅채택 | 일별 인덱스를 left, `disclosure_date` 정렬 재무행을 right로 backward 병합, tie는 `period_end` 최신 선정렬로 해소 | PRD FR-17 "merge_asof 계열" 직접 충족 / 벡터 연산 결정론 / 경계(최초 공시 이전) 자연스러운 NaN | tie-break을 병합 전 정렬로 보장해야 함(명세 필요) |
| A2-ii. 수동 groupby + forward-fill | reindex 후 ffill 루프 | 세밀 제어 | 루프 기반 비결정성·성능 열위 / 경계 처리 수기 / PRD "merge_asof 계열" 이탈 |

**무효화 근거**: A2-ii는 driver#1을 위협(수기 경계 처리로 결정론 공백 위험)하고 FR-17의 "벡터 연산(merge_asof 계열)" 문구를 이탈한다. A2-i를 채택하되, tie-break은 병합 전 `(disclosure_date asc, period_end desc)` 정렬 후 중복 `disclosure_date` 최상단 선택으로 명세한다(TR-R01-011).

---

## 1. 목적

플랫폼이 관리하는 1급 자원으로서 Factor(투자 지표)를 제공하는 계층의 **기술 요구사항**을 확정한다. 구체적으로:

- 팩터 메타데이터·계산·레지스트리·결측 계약을 구현 착수 가능한 수준의 배선·오류 모델·테스트 매핑으로 번역한다.
- 펀더멘털 데이터 계층(저장 2테이블·수집 Provider·as-of 정렬·품질 게이트)의 기술 배선을 확정한다.
- 상위 계층(R02 참조 검증, R03 평가·실행)이 인용할 인터페이스 앵커(팩터 `id`, `FactorInput` 형상, `compute_factor` 디스패치)의 안정성 규약을 명시한다.
- 모든 요구사항을 합성 Fixture + 격리 DuckDB + pytest 결정론 검증으로 매핑한다.

본 문서는 시그니처·DDL·산식을 **재정의하지 않는다**(PRD 확정 원천). 그것들의 **배선·강제·검증 방식**만 확정한다.

## 2. 범위 (In / Out)

### In

- 팩터 메타데이터·계산 Protocol·단일 디스패치·레지스트리의 배선 및 강제 규칙.
- 팩터 카탈로그 32종(PRD §4)의 산식 원천 준수 규칙(산식 자체는 PRD 확정, 본 문서는 parity 검증 배선).
- 펀더멘털 데이터 계층: 저장 2테이블 DDL 준수·`FundamentalProvider` Protocol 분리·어댑터 3종 배치·as-of 정렬·수집 품질 게이트.
- 결측 규약(FactorNote 4종·`attrs["notes"]`·`get_factor_notes` advisory·degrade)의 채널 배선.
- 조회·수집 CLI 3계약(`list-factors`/`show-factor`/`fetch-fundamental`)의 오류 모델과 환경 힌트.
- 계층 순수성 INV-1 AST 스캔 규칙.

### Out (확정)

- Formula/Rule/Strategy 정의·평가·백테스트 (→ R02/R03).
- 팩터 계산값의 영속화·캐싱 (입력 데이터만 DB 저장 — PRD §2 Out).
- 복합 점수형 팩터(F-Score·Z-Score 등, 확장 후보).
- 실시간·해외 데이터.
- **Phase F2-b DART 실데이터 연동은 명시적 Out** — 본 문서 완료 정의는 합성 Fixture 결정론 검증까지다. PRD §8의 후속 명세 4항목은 §4.7 "Deferred TR"로 승계한다.

## 3. PRD 추적성 매트릭스 (공백 0)

> **판독 규약**: "TR" 열은 §4의 기술 결정을 가리킨다. **(PRD 확정 인용)** 표시 행은 PRD가 이미 TR급으로 확정한 항목으로, §4에서 반복하지 않고 본 매트릭스로 축약한다(시그니처 원천 = DESIGN-R01 §3). 나머지 행은 §4가 PRD에 없는 기술 결정을 추가한다.

### 3.1 Functional Requirements (FR-01~FR-18)

| FR | 요지 | TR | 근거 |
|---|---|---|---|
| FR-01 | `FactorMetadata` 불변 형상(id/display_name/category/description/params/output/required_data) | TR-R01-002, TR-R01-013 (PRD 확정 인용) | PRD §3.1 |
| FR-02 | `ParamSpec` 형상 + default==생성자 기본값 단일 원천 | TR-R01-004 (PRD 확정 인용) | PRD §3.1 |
| FR-02a | `validate_params` 교차 제약 훅 — 인스턴스화 + 정의 검증 양쪽 호출 | TR-R01-005 | PRD §3.1 |
| FR-03 | `category` 11종 열거, 확장=열거 추가 | TR-R01-016 (additive) | PRD §3.1 |
| FR-04 | 팩터 `id` = R02 직렬화 참조 안정 앵커, 개명=신규 id | TR-R01-013 | PRD §3.1 |
| FR-05 | `FactorInput(ohlcv, valuation, financials)` 입력 번들 | TR-R01-003 (PRD 확정 인용) | PRD §3.2 |
| FR-05a | `FactorInput` 3프레임 형상(단일 종목·오름차순 DatetimeIndex·컬럼 계약) | TR-R01-003 (PRD 확정 인용) | PRD §3.2 |
| FR-06 | `compute_factor` 유일 인가 디스패치(required_data==("ohlcv",) 분기) | TR-R01-002 | PRD §3.2 |
| FR-07 | 반환 항상 DataFrame·컬럼==output·인덱스 보존 | TR-R01-002 (PRD 확정 인용) | PRD §3.2 |
| FR-08 | 결정론·입력 비변조·상이 파라미터 독립 계산 | TR-R01-002, TR-R01-015 | PRD §3.2, D1 |
| FR-09 | `factors/` 순수성(INV-1, AST 스캔) | TR-R01-001 | PRD §3.2 |
| FR-10 | 레지스트리(중복 예외·`list_factors`·`get_factor(id, **params)` 오버라이드 인스턴스) | TR-R01-002, TR-R01-014 (PRD 확정 인용) | PRD §3.3 |
| FR-11 | 데이터 무관 카탈로그 결정성 + `show-factor` 환경 힌트 | TR-R01-014 | PRD §3.3 |
| FR-12 | 결측=NaN, FactorNote 4종, `attrs["notes"]`, `get_factor_notes` 유일 접근자 | TR-R01-006 | PRD §3.4 |
| FR-13 | 사유 advisory(진실=NaN 셀), `financials=None` degrade 무예외 | TR-R01-006, TR-R01-007 | PRD §3.4 |
| FR-14 | `fundamental_daily` DDL + 주가 정합 불변식(close==OHLCV close) | TR-R01-008, TR-R01-010 (PRD 확정 인용) | PRD §6.1 |
| FR-15 | `financial_statements` DDL(PK·계정 전건·statement_scope 도메인) | TR-R01-008 (PRD 확정 인용) | PRD §6.1 |
| FR-16 | `FundamentalProvider` Protocol 분리 + 어댑터 3종(PyKrx lazy import) | TR-R01-008 | PRD §6.2 |
| FR-17 | as-of 정렬(disclosure_date forward-fill·이전 NaN+INSUFFICIENT_HISTORY·tie-break period_end 최신·merge_asof) | TR-R01-011 (PRD 확정 인용) | PRD §6.2 |
| FR-17a | `fetch-fundamental` CLI + Daily 자동수집 동일 upsert 경로 공유 | TR-R01-009, TR-R01-012 | PRD §6.3 |
| FR-17b | 수집 품질 게이트(PK 중복·오름차순·미래 일자·음수) 위반 행 제외+기록 | TR-R01-009 | PRD §6.3 |
| FR-18 | CLI `list-factors`/`show-factor`/`fetch-fundamental` + 미존재 non-zero | TR-R01-012 | PRD §7 |

### 3.2 팩터 카탈로그 (PRD §4, 32종)

| PRD 항목 | 요지 | TR | 근거 |
|---|---|---|---|
| §4.1 | 가격·기술 7종(`price` 포함, `required_data=("ohlcv",)`) | TR-R01-002 (PRD 확정 인용) | PRD §4.1, D2 |
| §4.2 | 밸류에이션 11종(`required_data=("valuation",)`) | TR-R01-011 (PRD 확정 인용) | PRD §4.2 |
| §4.3 | 재무제표 14종(as-of·연결 우선 폴백) | TR-R01-011 (PRD 확정 인용) | PRD §4.3 |
| §5 | 파생 팩터 순수 헬퍼 단일 원천(get_factor 미참조) | TR-R01-017 | PRD §5 |

### 3.3 Acceptance Criteria (AC-01~AC-08)

| AC | 요지 | §6 승계 | TR |
|---|---|---|---|
| AC-01 | 레지스트리 32종 등록·중복 0·카테고리 분포 | AC-R01-01 | TR-R01-014, TR-R01-016 |
| AC-02 | 산식 재도출 parity·결정론·비변조·컬럼==output·warm-up NaN | AC-R01-02 | TR-R01-002, TR-R01-015 |
| AC-03 | ParamSpec default 대조·범위 위반 거부·교차 제약 거부·상이 파라미터 독립 | AC-R01-03 | TR-R01-004, TR-R01-005 |
| AC-04 | 디스패치 라우팅·required_data≠("ohlcv",) 전수 FactorInput 호환 | AC-R01-04 | TR-R01-002 |
| AC-05 | 결측 NaN+사유·financials=None degrade·get_factor_notes 경계 통과 | AC-R01-05 | TR-R01-006, TR-R01-007 |
| AC-06 | as-of 경계·tie-break·주가 정합 불변식 | AC-R01-06 | TR-R01-010, TR-R01-011 |
| AC-07 | INV-1 AST green·2테이블 멱등 재연결·CLI 3계약 | AC-R01-07 | TR-R01-001, TR-R01-008, TR-R01-012 |
| AC-08 | fetch-fundamental 멱등·품질 게이트 제외+기록·Fixture 오프라인 | AC-R01-08 | TR-R01-009 |

### 3.4 INV / 확정 결정(D1~D5)

| 항목 | 요지 | TR | 근거 |
|---|---|---|---|
| INV-1 | `factors/`가 백테스트·실행·수집·저장 미import(AST 강제) | TR-R01-001 | PRD FR-09 |
| D1 | 팩터 파라미터 오버라이드 1급(정의 검증 + 평가 완전 해석) | TR-R01-004, TR-R01-005 | README §4 |
| D2 | 가격은 참조 가능한 팩터(`price` output `close`) | TR-R01-002 (§4.1 인용) | README §4 |
| 공통 원칙 6 | additive 진화(기존 DDL 무변경) | TR-R01-016 | README §5 |
| 공통 원칙 7 | 오류 메시지 한국어+행동 힌트, CLI non-zero | TR-R01-015 | README §5 |

**커버리지**: FR-01~18(18건) + AC-01~08(8건) + INV-1 + D1/D2 전건 매핑 완료. 공백 0.

## 4. 기술 요구사항 (TR-R01-xxx)

> 각 TR은 PRD가 확정하지 않은 기술 결정만 담는다. 시그니처·산식·DDL의 확정 원천은 DESIGN-R01 §3이며 여기서 재정의하지 않는다. 완전한 함수 본문은 두지 않고 시그니처·의사코드·표·서술까지만 확정한다.

### 4.1 모듈 배치 및 계층 순수성

**TR-R01-001 — 2패키지 분할과 INV-1 AST 스캔 강제**
- `factors/`(팩터 메타·계산·레지스트리·결측·파생 헬퍼)와 `data/`(펀더멘털 저장·수집 Provider·어댑터·as-of·품질 게이트)를 별도 패키지로 배치한다. `factors/`는 데이터를 계산하는 순수 계층, `data/`는 입력을 조달·저장하는 계층이다.
- INV-1 강제: `factors/` 하위 모든 모듈은 백테스트 엔진·실행 계층(R03)·데이터 수집·저장(DuckDB) 계층을 import하지 않는다. 데이터는 호출자가 `FactorInput`으로 주입한다. `data/`는 저장(DuckDB)·수집을 담당하되 `factors/`를 역참조하지 않는다(단방향).
- 검증 배선: AST 스캔 테스트가 `factors/` import 그래프를 순회하여 금지 모듈(vectorbt·jobs·storage·data 수집기) 참조를 0건으로 강제한다. `TYPE_CHECKING` 블록의 타입 전용 import는 예외 허용(런타임 미로딩).
- 근거: `← FR-09 / INV-1 / PRD-R01 §3.2`

### 4.2 계산 계약 배선

**TR-R01-002 — `compute_factor` 단일 인가 디스패치 배선**
- `compute_factor(factor, data: FactorInput) -> pd.DataFrame`를 **유일 인가 실행 API**로 배선한다. 호출자는 `factor.compute()`를 직접 호출하지 않는다(R02/R03 포함).
- 디스패치 규칙(PRD FR-06 확정): `required_data == ("ohlcv",)`이면 `factor.compute(data.ohlcv)`, 그 외 `factor.compute(data)`. 이 분기 외 경로는 없다.
- 강제 배선: 레지스트리 전수 스캔 테스트가 `required_data ≠ ("ohlcv",)`인 모든 등록 팩터의 `compute`가 `FactorInput` 시그니처를 구현하는지 확인한다(정적 검사 + 인스턴스화 호출 검사).
- 반환 형상 보존(PRD FR-07 확정): 항상 DataFrame(단일 출력도 1컬럼), 컬럼 집합 == `metadata.output`, 인덱스 == 입력 DatetimeIndex. 디스패치는 이 형상을 변조하지 않는다.
- 결측 사유 보존(TR-R01-006 연계): 디스패치는 `factor.compute` 반환 프레임의 `attrs["notes"]`를 **그대로 통과**시킨다(재구성·소실 금지) — 이것이 AC-05 "디스패치 경계 통과 후 판독" 요구의 배선이다.
- `price` 팩터(D2)는 `required_data=("ohlcv",)` 분기로 수정주가 종가를 패스스루하며 다른 팩터와 동형으로 디스패치된다.
- 근거: `← FR-06 / FR-07 / FR-08 / FR-10 / D2 / AC-04 / PRD-R01 §3.2·§4.1`

**TR-R01-003 — `FactorInput` 3프레임 형상 = 계층 공유 앵커 (PRD 확정 인용)**
- `FactorInput(ohlcv, valuation, financials)`의 3프레임 형상(단일 종목·오름차순 `DatetimeIndex`·컬럼 계약)은 PRD FR-05/05a에서 확정된다. 본 TR은 이를 재정의하지 않고 **계층 공유 계약**으로 고정한다: 팩터 구현·픽스처·R03 평가 엔진이 참조하는 유일한 입력 계약이며, R02/R03 문서는 이 형상을 DESIGN-R01 §3 링크로만 인용한다(재기술 금지, §D-2).
- 기술 결정: `financials` 프레임은 `disclosure_date` 오름차순 정렬을 입력 계약의 일부로 요구한다(as-of 정렬 TR-R01-011의 전제). 이 정렬 책임은 데이터 조달 계층(`data/` 어댑터)에 둔다.
- 근거: `← FR-05 / FR-05a / PRD-R01 §3.2`

**TR-R01-004 — `ParamSpec` 단일 원천 강제 배선 (PRD 확정 인용 + 대조 테스트)**
- `ParamSpec`(name/type/default/description/min·max)의 형상은 PRD FR-02 확정. 본 TR은 **default == 생성자 기본값 단일 원천**의 기계적 강제를 배선한다: 전수 대조 테스트가 각 등록 팩터의 `ParamSpec.default`와 팩터 생성자 시그니처의 기본값을 대조하여 불일치를 0건으로 강제한다(이중 원천 금지).
- 범위 검증 배선: `get_factor(id, **params)`가 min/max 위반 시 ParamSpec 기반 예외(허용 범위 힌트 포함)를 발생한다.
- 근거: `← FR-02 / D1 / AC-03 / PRD-R01 §3.1`

**TR-R01-005 — `validate_params` 교차 제약 훅 이중 호출 배선**
- 선택적 훅 `validate_params(params) -> tuple[str, ...]`(오류 목록, 빈 튜플=통과)을 교차 파라미터 제약(예: `macd`의 `fast < slow`)이 있는 팩터가 노출한다.
- **이중 호출 강제(PRD에 없는 배선 결정)**: 이 훅은 (a) `get_factor(id, **params)` 인스턴스화 경로와 (b) 정의 검증 경로(R02 §5.4가 소비) **양쪽에서 호출**된다. R02는 본 훅을 DESIGN-R01 §3 링크로 인용해 정의 시점 검증에 재사용한다(신규 검증 로직 0). 파라미터 위반은 실행 시점이 아니라 정의/인스턴스화 시점에 거부된다.
- 검증 배선: `macd` fast≥slow 인스턴스화가 거부됨을 AC-03 테스트로 확인. 훅 미노출 팩터는 빈 제약으로 간주(호출 안전).
- 근거: `← FR-02a / D1 / AC-03 / PRD-R01 §3.1`

### 4.3 결측 채널 배선

**TR-R01-006 — 결측 사유 advisory 채널 배선**
- 계산 불가 셀 = NaN을 진실 원천으로 하고, 사유(`FactorNote` str-Enum 4종: `MISSING_INPUT`/`NON_POSITIVE_DENOMINATOR`/`ZERO_DENOMINATOR`/`INSUFFICIENT_HISTORY`)를 반환 프레임의 `attrs["notes"]`(컬럼→사유 매핑)에 싣는다. `get_factor_notes(result) -> dict[str, FactorNote]`가 유일 접근자다.
- advisory 규약(PRD FR-13): 사유는 **자문**이며, 반환 직후·변환 이전에 판독한다. 후속 pandas 연산이 `attrs`를 소실시킬 수 있으므로 소비자(R03 평가 엔진)는 `compute_factor` 반환 직후 `get_factor_notes`를 호출하도록 인용 계약에 명시한다.
- 배선 결정: `attrs["notes"]`는 컬럼 단위 매핑이며, 한 컬럼에 복수 사유가 발생하면 §4 표의 지정 사유(가장 구체적 원인)를 단일 값으로 기록한다(다중 사유 목록화는 out — additive 후보).
- 근거: `← FR-12 / FR-13 / AC-05 / PRD-R01 §3.4`

**TR-R01-007 — `financials=None` degrade 배선**
- `financials=None`(또는 `valuation=None`)이면 해당 데이터를 요구하는 팩터는 **예외 없이** 전 구간 NaN + `MISSING_INPUT`으로 강등한다. 데이터 미연동이 카탈로그 등록·타 팩터 계산을 차단하지 않는다(FR-11 결정성과 정합).
- 배선: `compute` 진입 시 필요 프레임 부재를 감지하면 입력 인덱스(가용 시 ohlcv 인덱스) 형상의 전-NaN DataFrame을 반환하고 `attrs["notes"]`에 `MISSING_INPUT`을 채운다. 인덱스 참조조차 불가하면(전 프레임 None) 빈 DataFrame + 사유를 반환한다.
- 근거: `← FR-13 / AC-05 / PRD-R01 §3.4`

### 4.4 펀더멘털 데이터 계층 배선

**TR-R01-008 — 저장 2테이블 + `FundamentalProvider` Protocol 분리 + 어댑터 3종**
- 저장 DDL 2테이블(`fundamental_daily`·`financial_statements`)의 컬럼·PK·도메인은 PRD §6.1(FR-14/15) 확정. 본 TR은 배치·멱등 배선만 확정: `CREATE TABLE IF NOT EXISTS` 멱등, `financial_statements`는 `INSERT OR REPLACE` 멱등 upsert. `invested_capital` 등 원장 부재 파생 계정은 **어댑터가 산출·저장**하고 팩터는 저장값을 소비한다(계산 계층은 파생 계정 재계산 안 함).
- `FundamentalProvider` Protocol은 OHLCV `DataProvider`와 **분리 정의**한다(FR-16) — 밸류에이션·재무제표 조회 메서드를 별도 계약으로 둔다(baseline `DataProvider`는 OHLCV 전용으로 무변경, §8 앵커 표).
- 어댑터 3종 배치: `PyKrxFundamentalAdapter`(밸류에이션 — PyKrx 일별 fundamental + 시가총액 + 종가 병합, **PyKrx는 함수 내부 lazy import** — setuptools 충돌 회피), `DartFundamentalAdapter`(재무제표, §4.7 Deferred), `FixtureFundamentalAdapter`(합성 CSV — OHLCV 픽스처와 동일 종목 정합).
- 근거: `← FR-14 / FR-15 / FR-16 / AC-07 / PRD-R01 §6.1·§6.2`

**TR-R01-009 — 수집 실행 경로 통합 + 품질 게이트(A1-i 채택)**
- `fetch-fundamental` CLI 수집과 Daily 자동수집(R03 §7)은 **동일 Provider·upsert 경로를 공유**한다(FR-17a). 공유 경로 진입점을 `data/` 계층에 단일 함수로 배치하여 두 호출자가 우회 없이 재사용한다.
- 품질 게이트(FR-17b, A1-i): upsert 직전 단일 게이트에서 4종 검사 — (1) PK 중복 없음, (2) 일자 오름차순, (3) 미래 일자 없음(주입된 as-of 기준 시각 초과 배제 — 시각은 주입, 네트워크·현재시각 의존 금지), (4) 음수 불가 필드(`market_cap`, `shares`) 위반 없음. **위반 행은 저장에서 제외하고 사유와 함께 수집 결과에 기록**하되 수집 전체를 중단하지 않는다.
- 멱등: 재실행 시 `INSERT OR REPLACE`로 중복 0 보장(AC-08).
- 근거: `← FR-17a / FR-17b / AC-08 / PRD-R01 §6.3`

**TR-R01-010 — 주가 정합 불변식 배선**
- `fundamental_daily.close`는 OHLCV `ohlcv_daily`와 **동일한 조정 종가 원천**을 사용한다(FR-14 불변식). 배선: 밸류에이션 어댑터가 종가를 병합할 때 OHLCV 파이프라인과 동일 수정주가 계열을 참조하도록 계약하고, 정합 테스트가 동일 (symbol, date)에서 두 테이블 `close` 동등을 강제한다(AC-06).
- 근거: `← FR-14 / AC-06 / PRD-R01 §6.1`

**TR-R01-011 — as-of 정렬 배선(A2-i `merge_asof` 채택)**
- 규약은 PRD FR-17 확정(disclosure_date forward-fill·최초 공시 이전 NaN+INSUFFICIENT_HISTORY·동일 disclosure_date tie-break=period_end 최신). 본 TR은 구현 수단만 확정: `pandas.merge_asof`(direction=`backward`)로 일별 인덱스에 최근 공시값을 병합한다.
- tie-break 배선: 병합 전 재무 프레임을 `(disclosure_date asc, period_end desc)`로 정렬하고 동일 `disclosure_date` 그룹에서 최상단(=period_end 최신)만 남긴 뒤 병합한다.
- 연결/별도 폴백 단일 계열(PRD §4.3): `statement_scope` 연결(consolidated) 우선, 부재 시 별도(separate) 폴백으로 단일 계열을 먼저 구성한 후 as-of 정렬·계산한다.
- 경계: 최초 공시 이전 구간은 NaN + `INSUFFICIENT_HISTORY`(merge_asof 좌측 미매치가 자연스러운 NaN 산출, 사유는 별도 기록).
- 근거: `← FR-17 / AC-06 / PRD-R01 §4.3·§6.2`

### 4.5 카탈로그 결정성·id 안정성·CLI·오류 모델

**TR-R01-013 — 팩터 `id` 안정 앵커 불변식**
- 팩터 `id`(snake_case, 전역 유일)는 R02 직렬화 정의가 참조하는 **안정 앵커**다. 한번 공개된 id는 변경하지 않으며, 개명이 필요하면 신규 id를 additive로 추가한다(FR-04). 이는 R02 왕복 무손실·참조 무결성의 전제이므로 R02/R03이 인용하는 계약이다.
- 배선: id 중복 등록은 레지스트리에서 예외(FR-10). 공개 id 목록 변경은 additive만 허용(제거·개명 금지) — 회귀 테스트로 기존 id 존재를 강제.
- 근거: `← FR-04 / PRD-R01 §3.1`

**TR-R01-014 — 데이터 무관 카탈로그 결정성 + 환경 힌트**
- 데이터 가용성과 무관하게 32종 전건이 항상 등록·조회된다(재무 팩터 포함). 레지스트리 등록은 데이터·환경에 의존하지 않는다(FR-11).
- `show-factor <id>`는 데이터 가용성 힌트를 표시한다: DART 미설정 시 재무 팩터에 대해 "값은 NaN"(TR-R01-007 degrade와 정합) 힌트를 노출한다. 이 힌트는 조회 표시용이며 등록 여부에 영향을 주지 않는다.
- 근거: `← FR-11 / AC-01 / PRD-R01 §3.3`

**TR-R01-012 — CLI 3계약 표면 + 오류 모델**
- `list-factors [--category <c>]`: id·표시명·카테고리·설명 표. 미존재 카테고리는 힌트 + non-zero.
- `show-factor <id>`: 설명·파라미터 명세(기본값·제약)·산출 컬럼·`required_data`·데이터 가용성 힌트(TR-R01-014). 미존재 id는 사용 가능 id 힌트 + non-zero 종료.
- `fetch-fundamental`: 심볼 목록(기본 watchlist)·기간·데이터 종류(valuation/financials)·provider 옵션. 멱등 수집(TR-R01-009). 수집 결과에 제외 행·사유 요약 출력.
- 오류 모델(TR-R01-015 준수): 모든 실패는 한국어 메시지 + 행동 가능 힌트 + non-zero.
- 근거: `← FR-18 / FR-17a / AC-07 / AC-08 / PRD-R01 §7`

**TR-R01-015 — 오류 모델 구체화(전역)**
- 오류 메시지는 **한국어 + 행동 가능한 힌트**를 담는다: 누락 id → 사용 가능 id 목록, 파라미터 범위 위반 → 허용 범위, 교차 제약 위반 → 위반 조건(예: `fast < slow`). CLI 실패는 non-zero 종료.
- 결정론 관련: 계산·수집 어디서도 네트워크·현재시각에 의존하지 않는다(시각은 주입). 이는 오류 재현성의 전제이며 FR-08과 정합.
- 근거: `← 공통 원칙 7 / FR-08 / README §5`

### 4.6 파생 팩터·additive·테스트 배선

**TR-R01-017 — 파생 팩터 순수 헬퍼 단일 원천**
- 파생 팩터(`peg`, `roe_approx`, `eps_growth` 등)는 다른 Factor 인스턴스를 `get_factor`로 참조하지 않는다(레지스트리 결합·순서 의존 금지). 산식은 순수 헬퍼 모듈에 단일 원천으로 두고 공유한다(예: `peg`가 `per`·`eps_growth` 산식 헬퍼를 함수 호출로 재사용).
- 근거: `← PRD-R01 §5`

**TR-R01-016 — additive 진화 원칙**
- 신규 카테고리 = `category` 열거 추가(FR-03), 신규 팩터 = Protocol 구현 + 레지스트리 1회 등록(OCP), 신규 저장 = 테이블 추가. **기존 DDL·공개 id·ParamSpec default는 변경하지 않는다**. 결측 사유 확장은 `FactorNote` 열거 추가로만.
- 근거: `← FR-03 / 공통 원칙 6 / README §5`

**TR-R01-018 — 테스트 전략 배선**
- 모든 AC는 합성 Fixture + 격리 DuckDB(tmp) + pytest로 네트워크·실데이터·LLM·시각 의존 없이 검증한다. 결정론은 **2회 실행 동일**으로 판정한다.
- **기대값 하드코딩 금지**: 산식 parity는 §4 표의 산식을 테스트가 pandas로 **독립 재도출**하여 대조한다(골든 상수 금지). Fixture는 OHLCV 픽스처와 종목 정합하는 밸류에이션·재무 합성 CSV를 포함한다.
- 근거: `← 원칙 3 / AC-02 / AC-08 / PRD-R01 §9`

### 4.7 Deferred TR — Phase F2-b DART 실데이터 연동 (본 PRD 완료 정의 밖)

> 본 문서 완료 정의는 합성 Fixture 결정론 검증까지다. DART 실연동은 별도 후속 단계이며, 착수 시 아래 4개 명세 확정이 **선행**되어야 한다(미확정 시 어댑터 구현 공전). 본 절은 PRD §8을 승계해 Deferred TR로 남긴다.

**TR-R01-D01 (Deferred)** — 종목코드 → DART `corp_code`(8자리) 해결: `corpCode.xml` 다운로드·캐싱·조회 규약. `← PRD-R01 §8.1`
**TR-R01-D02 (Deferred)** — FR-15 전 계정에 대한 DART `account_nm` 완전 매핑 열거(누락 계정 → 해당 팩터 영구 NaN). `← PRD-R01 §8.2`
**TR-R01-D03 (Deferred)** — `disclosure_date`/`period_end` 추출 규약(`rcept_dt` 등) — as-of 조인 키. `← PRD-R01 §8.3`
**TR-R01-D04 (Deferred)** — 연결(`CFS`) 우선 → 별도(`OFS`) 폴백 정책(별도재무만 공시 종목 누락 방지). `← PRD-R01 §8.4`

**Deferred 완료 정의**: 실 종목에서 F2 14종이 NaN 아닌 값 산출 + 실데이터 통합 테스트. (본 TRD의 완료 판정에는 미포함.)

## 5. 비기능 요구사항 (NFR)

| NFR | 요구 | 검증 |
|---|---|---|
| **NFR-01 결정론** | 동일 입력(데이터+파라미터) → 동일 출력. 계산·수집·as-of·직렬화 전부 네트워크·현재시각 미의존(시각 주입). | 2회 실행 프레임 동등(`assert_frame_equal`) |
| **NFR-02 오프라인 검증** | 전 AC가 네트워크·실데이터·LLM 없이 합성 Fixture + 격리 DuckDB로 검증. | CI 오프라인 실행 green |
| **NFR-03 계층 순수성** | `factors/`가 실행·저장·수집 계층 미import(INV-1). | AST 스캔 테스트 green |
| **NFR-04 입력 비변조** | `compute_factor`가 입력 `FactorInput` 프레임을 변조하지 않음. | 계산 전후 입력 해시 동등 |
| **NFR-05 성능 상한** | 단일 종목·수년치 일별(수천 행) 팩터 계산은 벡터 연산(pandas rolling/ewm/merge_asof)으로 수행하며 파이썬 행-루프를 두지 않는다. | 구현 리뷰 + 루프 부재 정적 확인 |
| **NFR-06 degrade 무중단** | 데이터 미연동(financials/valuation=None)이 카탈로그 등록·타 팩터·CLI 조회를 중단시키지 않음. | AC-05 degrade 테스트 |
| **NFR-07 멱등** | `fetch-fundamental`·테이블 생성 재실행이 중복·오류 0. | AC-07/08 재실행 테스트 |

## 6. 수용 기준 (PRD AC 승계 + pytest 매핑)

> PRD AC-01~08을 `AC-R01-xx`로 승계·구체화하고 pytest 검증 방법을 명시한다. 기대값 하드코딩 금지(산식 재도출).

- **AC-R01-01 (← AC-01)** 레지스트리 32종 등록·중복 0·카테고리 분포 일치. 중복 id 등록 시 예외.
  - *pytest*: 등록 목록 크기==32, 카테고리별 count가 §4 분포와 일치, 중복 id 등록이 예외 발생.
- **AC-R01-02 (← AC-02)** 전 팩터 산식 재도출 parity(§4 표) · 결정론(2회 동일) · 입력 비변조 · 컬럼==output · warm-up NaN+INSUFFICIENT_HISTORY.
  - *pytest*: 각 팩터마다 테스트가 §4 산식을 pandas로 독립 재계산→`assert_frame_equal`; 2회 호출 동등; 입력 해시 불변; `set(result.columns)==set(metadata.output)`.
- **AC-R01-03 (← AC-03)** ParamSpec default==생성자 기본값(전수) · 범위 위반 오버라이드 거부 · 교차 제약 위반(`macd` fast≥slow) 인스턴스화 거부(FR-02a) · 상이 파라미터 2인스턴스 독립 계산(sma(5)≠sma(20)).
  - *pytest*: introspection으로 default 대조; `get_factor("bollinger", window=1)` 등 범위 위반 예외; `get_factor("macd", fast=26, slow=12)` 예외; sma(5)·sma(20) 결과 상이.
- **AC-R01-04 (← AC-04)** `compute_factor` 양 시그니처 라우팅 정확 · `required_data≠("ohlcv",)` 전 팩터 FactorInput 호환(전수 스캔).
  - *pytest*: ohlcv 팩터가 `data.ohlcv`로, 펀더멘털 팩터가 `data`로 호출됨을 확인; 레지스트리 순회로 시그니처 호환 전수 검사.
- **AC-R01-05 (← AC-05)** §4 표 각 NaN 조건 → NaN + 지정 사유 · `financials=None` → F2 전 구간 NaN+MISSING_INPUT 무예외 · `get_factor_notes`가 디스패치 경계 통과 후 판독 가능.
  - *pytest*: 경계 Fixture(eps≤0, bps≤0, div0 등)에서 NaN 위치·`get_factor_notes` 사유 일치; `financials=None` 무예외 전-NaN; `compute_factor` 반환 직후 `attrs["notes"]` 접근 가능.
- **AC-R01-06 (← AC-06)** as-of 공시일 이전 셀 미반영(경계 픽스처) · 동일 공시일 tie-break(period_end 최신) · `fundamental_daily.close`==OHLCV close 정합.
  - *pytest*: 공시 이전 일자 NaN; 동일 disclosure_date 2레코드에서 period_end 최신 값 선택; 두 테이블 close 동등.
- **AC-R01-07 (← AC-07)** INV-1 AST 스캔 green · 2테이블 존재 + 멱등 재연결 · CLI 3계약(목록/상세/미존재 non-zero).
  - *pytest*: AST 스캔 0 위반; `CREATE TABLE IF NOT EXISTS` 2회 무오류; CLI runner로 `list-factors`/`show-factor`/미존재 id non-zero.
- **AC-R01-08 (← AC-08)** `fetch-fundamental` 멱등 재실행(중복 0) · 품질 게이트 위반 행 제외+기록(FR-17b) · Fixture provider 오프라인 검증.
  - *pytest*: `FixtureFundamentalAdapter`로 2회 수집 후 행 수 동일; 위반 행(PK 중복·미래 일자·음수) 제외되고 결과에 사유 기록.

## 7. 리스크·완화 (Open Tensions)

| # | Tension | 영향 | 완화 |
|---|---|---|---|
| OT-1 | **결측 사유 소실** — pandas 연산이 `attrs`를 드롭해 `get_factor_notes`가 빈 값 반환 | R03 평가 시 사유 판독 불가 | 인용 계약에 "반환 직후 판독" 명시(TR-R01-006), 디스패치가 attrs 통과 보장(TR-R01-002), 경계 테스트로 강제(AC-05) |
| OT-2 | **as-of tie-break 비결정성** — 동일 disclosure_date 복수 레코드 순서 불안정 | 값 선택 비결정 | 병합 전 `(disclosure_date asc, period_end desc)` 정렬 + 그룹 최상단 선택(TR-R01-011) |
| OT-3 | **파생 계정 이중 산출** — `invested_capital` 등을 어댑터·팩터 양쪽 계산 | 값 불일치 | 어댑터 산출·저장, 팩터는 저장값 소비 단일화(TR-R01-008) |
| OT-4 | **ParamSpec 이중 원천 drift** — default가 생성자 기본값과 어긋남 | 검증-실행 괴리 | 전수 대조 테스트 강제(TR-R01-004/AC-03) |
| OT-5 | **미래 일자·현재시각 의존** — 품질 게이트가 시스템 시각 참조 시 비결정 | 테스트 비재현 | 기준 시각 주입, 네트워크·현재시각 금지(TR-R01-009/015, NFR-01) |
| OT-6 | **degrade 누락** — 재무 팩터가 데이터 부재 시 예외 발생 | 카탈로그 차단 | financials=None 무예외 전-NaN 배선(TR-R01-007/AC-05), NFR-06 |
| OT-7 | **DART 명세 공백** — Deferred 4항목 미확정으로 F2-b 어댑터 공전 | 실연동 지연 | §4.7 Deferred TR로 선행 명세 명시, 본 완료 정의는 Fixture까지로 격리 |

## 8. 부록

### 8.1 마일스톤 (논리 단위)

| M | 범위 | 완료 신호 |
|---|---|---|
| M0 | 모듈 골격(`factors/`·`data/`) + INV-1 AST 스캔 | AST green |
| M1 | 메타·ParamSpec·레지스트리·`compute_factor` 디스패치 + 가격·기술 7종 | AC-01~04 부분 |
| M2 | 결측 채널(FactorNote·attrs·get_factor_notes) + 밸류에이션 11종 | AC-05 부분 |
| M3 | 저장 2테이블 + Provider Protocol + Fixture 어댑터 + as-of + 재무 14종 | AC-05/06 |
| M4 | 수집 경로·품질 게이트·CLI 3계약 | AC-07/08 |
| (Deferred) | Phase F2-b DART 실연동 | §4.7, 본 완료 정의 밖 |

> 마일스톤은 문서상 논리 단위다(스프린트 분할은 구현 계획 시점 확정).

### 8.2 baseline 앵커 표 (main 시점 재사용 자산)

> R02/R03 문서가 "기존 자산"으로 인용할 정본. main 시점에 이미 존재하는 자산의 명칭·역할을 고정한다(출처: README §2 Baseline). 본 R01은 이들을 **재구축하지 않고** OHLCV `DataProvider`·DuckDB 저장 관례·CLI·Settings 형식을 계승한다.

| 앵커 명칭 | 역할 | R01에서의 관계 |
|---|---|---|
| `Portfolio.from_signals` (vectorbt) | 백테스트 엔진 | R01 미사용(R03 소비). INV-1로 `factors/` 미참조 |
| `BacktestMetrics` | 지표 산식 원천 | R01 미사용(R03 소비) |
| 신호 분류기(SignalClassifier) | 백테스트 결과→신호 분류 | R01 미사용(R03 소비) |
| content-hash 기반 `notification_outbox` | 중복 발송 방지 | R01 미사용(R03 다운스트림) |
| DuckDB 기존 8테이블 (`symbols`, `ohlcv_daily`, `data_fetch_runs`, `strategy_runs`, `signals`, `reports`, `notification_outbox`, `run_events`) | 기존 영속 스키마 | R01은 `fundamental_daily`·`financial_statements` **2테이블 additive 추가**(기존 8테이블 무변경) |
| OHLCV `DataProvider` 프로토콜 | OHLCV 조달 계약 | R01 `FundamentalProvider`는 이와 **분리 정의**(FR-16), `ohlcv_daily.close`는 주가 정합 불변식의 원천(FR-14) |
| Typer CLI | 명령 표면 | R01 CLI 3계약(`list-factors`/`show-factor`/`fetch-fundamental`)을 동일 Typer 관례로 추가 |
| Pydantic Settings | 설정 로딩 | R01 provider·환경 힌트(DART 미설정)를 동일 Settings 관례로 소비 |

### 8.3 계층 인터페이스 참조표 (상위가 인용할 앵커)

> 시그니처 확정 원천은 DESIGN-R01 §3. 상위(R02/R03)는 아래를 링크 인용하며 재정의하지 않는다(§D-2).

| 인터페이스 | 형태(요약) | 소비자 | 확정 원천 |
|---|---|---|---|
| 팩터 `id` | snake_case 전역 유일, 안정 앵커 | R02 직렬화 참조, R03 평가 | TR-R01-013 / DESIGN-R01 §3 |
| `FactorMetadata` | id/display_name/category/description/params/output/required_data | R02 참조 검증, R03 | PRD §3.1 / DESIGN-R01 §3 |
| `ParamSpec` + `validate_params` | name/type/default/min·max + 교차 제약 훅 | R02 params 검증(D1) | TR-R01-004/005 / DESIGN-R01 §3 |
| `FactorInput` | (ohlcv, valuation, financials) 3프레임, 단일 종목 | R03 평가 엔진 입력 계약 | TR-R01-003 / DESIGN-R01 §3 |
| `compute_factor(factor, data)` | 유일 인가 디스패치 → DataFrame | R03 평가 엔진 | TR-R01-002 / DESIGN-R01 §3 |
| `get_factor(id, **params)` | 오버라이드 인스턴스 생성 | R03 평가(파라미터 해석) | TR-R01-002/004 / DESIGN-R01 §3 |
| `get_factor_notes(result)` | 결측 사유 유일 접근자 | R03 평가(사유 판독) | TR-R01-006 / DESIGN-R01 §3 |
| `FundamentalProvider` | 밸류에이션·재무제표 조달, OHLCV Provider와 분리 | R03 Daily 자동수집 | TR-R01-008 / DESIGN-R01 §3 |

---

**추적성 요약**: FR-01~18 · AC-01~08 · INV-1 · D1/D2 전건이 §3 매트릭스에서 ≥1 TR로 매핑(공백 0). §4는 TR-R01-001~018 + Deferred TR-R01-D01~D04로 구성되며, PRD 확정 항목(산식·DDL·시그니처·as-of 규약)은 §3 매트릭스로 축약해 §4 중복 서술을 두지 않는다(§D-9 준수).

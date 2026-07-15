# TRD-R02 : Declarative Definition Core

**대응 PRD**: `PRD-R02-DECLARATIVE_DEFINITION_CORE.md`
**계층**: R02 (중간, 순수 — 평가·실행·백테스트·storage 무의존) / **의존**: R01(팩터 레지스트리·ParamSpec) / **소비자**: R03(평가·실행·CLI)
**Status**: Draft for review
**전제**: 본 문서는 main 브랜치 시점에서 선언형 정의 코어를 **처음 구현한다**고 가정한다. 모든 서술은 PRD-R02 + `README.md`(§4 D1~D5 · §5 공통 불변 원칙 7) + 하위 계층 확정 인터페이스(`DESIGN-R01 §3`) 역추적으로만 정당화한다.

> **문서 규약(§D-9 no-restate)**: PRD-R02가 이미 TR급으로 확정한 항목(REQ-C1~C7 표현 계약 상세 §3, §5 도메인 형상·연산자 집합, 3테이블 동형 DDL 골격 §4, REQ-V1~V5 검증기 요구 §6)은 본 문서 §4 TR에서 반복 서술하지 않고 §3 추적성 매트릭스 1행으로 축약한다(`REQ-xx ← TR-R02-yy (PRD 확정 인용)`). §4 TR은 **PRD에 없는 기술 결정**(R01 인터페이스 소비 배선, `_jsonnorm` 공유 leaf 배치, 저장 게이트 리졸버 주입, 오류 모델 구체화, AC→pytest 매핑, NFR)만 담는다.
>
> **인터페이스 인용 규약(§D-2)**: R02가 소비하는 R01 시그니처(`ParamSpec`·`validate_params`·`FactorCategory`·`get_factor`·`list_factors`·`FactorMetadata`)는 **재정의하지 않고** `DESIGN-R01 §3.x`를 링크 인용한다(요약 1줄까지만 허용). R02 자체 도메인 타입의 시그니처 확정 원천은 후속 `DESIGN-R02 §3`이며, 본 TRD는 이를 재정의하지 않는다.
>
> **하위 문서 규율(§D-1)**: 본 문서는 상위(R03)를 인용하지 않는다. 상위 소비 지점은 "소비자: PRD-R03 §y" 포인터만 둔다(예: 활성 전략이 참조하는 엔티티의 수정·삭제 차단은 R03 책임).

---

## 0. RALPLAN-DR 요약 (SHORT)

본 절은 **이 TRD 수준에서 새로 내리는 기술 결정**(PRD가 확정하지 않은 배선·구현 선택)에 한정한다. D1~D5·REQ-C/P/V·§5 도메인 형상·3테이블 DDL은 확정 전제이므로 재논쟁하지 않는다(README §4/§5 정본 인용).

### Principles (원칙 3)

1. **PRD 역추적 유일 정당화**: 모든 TR은 PRD-R02의 REQ-C/P/V·§5·INV·AC 또는 README §4(D1~D5)/§5(공통 원칙 7)로 역추적된다. TR은 요구사항을 창작하지 않고 기술 번역·배선만 한다.
2. **계층 순수성 우선**: `strategy/`·`rule/`·`formula/`는 백테스트·평가·storage를 import하지 않으며 서로도 import하지 않는다(INV-1~3). 허용 참조는 R01 팩터 레지스트리 + 공유 JSON 정규화 leaf뿐이다. 문서 경계 = 코드 경계이며 최상위 제약이다.
3. **결정론·오프라인 검증이 완료 판정 축**: 모든 AC는 합성 Fixture + 격리 DuckDB + pytest로 네트워크·LLM·실데이터 없이 2회 동일 검증 가능해야 한다. 기대값 하드코딩 금지.

### Decision Drivers (상위 3)

1. **왕복 무손실 구조적 폐색**: 자유형 매핑(`metadata`, operand `params`)의 왕복 불일치가 세 엔티티에 걸쳐 drift를 만들지 않도록, 정규화 규약을 단일 원천으로 배선한다(REQ-C2).
2. **참조 무결성의 저장 시점 강제**: dangling factor/formula/rule 참조·순환은 실행이 아니라 저장 게이트에서 차단해야 하며(공통 원칙 4·REQ-P3), 이 강제가 계층 순수성(INV)과 충돌하지 않도록 리졸버 주입으로 배선한다.
3. **상위 계층 인용 안정성**: R03가 소비할 검증기 3종·`is_runnable`은 안정 앵커여야 하며, 배선 선택이 이 앵커를 흔들면 안 된다.

### Viable Options (TRD 수준의 자유 결정, ≥2 + 무효화 근거)

**결정 축 B1 — 공유 JSON 정규화 leaf(`_jsonnorm`) 배치 (REQ-C2)**

| 옵션 | 방식 | 장점 | 단점 |
|---|---|---|---|
| **B1-i. 단일 공유 leaf 모듈** ✅채택 | `quant_krx/_jsonnorm.py` 단일 leaf에 정규화 함수(중첩 tuple→list·str 키·JSON 스칼라·bool 거부)를 두고 세 패키지가 각자 import | 정규화 규약 단일 원천 → 왕복 규약 drift 원천 차단 / INV-2(패키지 상호 미import) 유지(leaf는 도메인 패키지가 아님) | leaf 모듈 하나가 세 패키지의 공통 의존이 됨(허용 — R01 레지스트리와 동급 leaf) |
| B1-ii. 각 패키지 중복 구현 | `strategy/`·`rule/`·`formula/` 각자 정규화 헬퍼 보유 | 패키지 자기완결 | 3중 drift(같은 규약이 셋으로 갈라짐) → REQ-C2 왕복 무손실이 엔티티별로 어긋날 위험 / 규약 변경 시 3곳 수정 |

**무효화 근거**: B1-ii는 driver#1(왕복 무손실 구조적 폐색)을 정면 위협 — 정규화가 세 벌로 갈라지면 `from_dict(to_dict(x))==x`가 엔티티마다 다른 경계에서 깨질 수 있다. B1-i는 정규화를 leaf 단일 원천으로 두어 세 엔티티가 동일 규약을 공유하며, leaf는 도메인 패키지가 아니므로 INV-2(상호 leaf 독립)를 위반하지 않는다.

**결정 축 B2 — 저장 게이트 참조 리졸버 주입 방식 (REQ-P3)**

| 옵션 | 방식 | 장점 | 단점 |
|---|---|---|---|
| **B2-i. self-store default-on 리졸버 + `check_*` 완화 플래그** ✅채택 | `upsert_*`가 자기 자신의 store를 리졸버로 기본 주입(존재·순환 검증 default-on)하되, 플래그로 완화 가능 | 정상 저장은 참조 무결성 자동 강제(REQ-P3) / 부분 조립·테스트는 플래그로 완화 / storage→도메인 단방향 유지(도메인은 storage 미인지) | 플래그 오사용 시 무검증 저장 가능(테스트·부분 조립으로 한정) |
| B2-ii. 항상 전역 강제(플래그 없음) | 모든 upsert가 무조건 전체 참조 검증 | 우회 불가 | 참조 대상이 아직 없는 **부분 조립**(Formula 먼저·Rule 나중) 시나리오·단위 테스트를 구조적으로 차단 |
| B2-iii. 저장 시점 무검증(실행 시점만) | upsert는 저장만, 검증은 R03 평가 진입 | storage 단순 | 공통 원칙 4·REQ-P3(부분 저장 없음·저장 시점 무결성) 정면 위반 — dangling이 DB에 진입 |

**무효화 근거**: B2-iii는 REQ-P3와 공통 원칙 4(참조 무결성은 저장 시점)를 위반하므로 배제. B2-ii는 REQ-P3의 "플래그로 완화 가능(테스트·부분 조립용)" 명문 요구를 충족 못 한다. B2-i만이 default-on 강제와 완화 가능성을 동시에 만족한다.

**결정 축 B3 — params 오버라이드 검증 로직 소유권 (D1, §5.4)**

| 옵션 | 방식 | 장점 | 단점 |
|---|---|---|---|
| **B3-i. R01 `ParamSpec`·`validate_params` 훅 재사용(링크 인용)** ✅채택 | R02 참조 검증기가 `DESIGN-R01 §3.2 ParamSpec`·`§3.3 validate_params`를 소비, 신규 검증 로직 0 | 이중 원천 없음(D1 완전 해석 단일 원천) / INV-1(허용 참조=R01 레지스트리) 준수 | R01 인터페이스 안정성에 의존(TR-R01-004/005 앵커) |
| B3-ii. R02 자체 params 검증 독자 구현 | R02가 min/max·교차 제약을 독자 구현 | R01 결합 축소 | ParamSpec 이중 원천 → D1 검증-실행 괴리 위험 / INV-1 허용 참조 초과(레지스트리 외 로직 복제) |

**무효화 근거**: B3-ii는 D1(파라미터 완전 해석의 단일 원천)을 위협 — 검증 규칙이 R01과 R02로 갈라지면 정의 검증과 평가가 어긋날 수 있다. B3-i는 R01 훅을 링크 인용으로 재사용해 단일 원천을 유지한다(R02는 "언제 호출하는가"만 배선).

---

## 1. 목적

전략을 코드가 아니라 **선언적·직렬화 가능·코드 실행 없는 데이터**로 정의하는 세 개의 1급 엔티티(Formula·Rule·Strategy)의 **정의 + 영속 + 검증** 계층의 기술 요구사항을 확정한다. 구체적으로:

- 세 도메인 패키지(`strategy/`·`rule/`·`formula/`)와 공유 정규화 leaf(`_jsonnorm`)의 모듈 배치·의존 방향·INV-1~3 AST 스캔 규칙을 확정한다.
- 공통 표현 계약(왕복·결정론·canonical eq/hash·schema_version)의 **배선·강제 방식**을 확정한다(계약 상세는 PRD-R02 §3 확정 원천).
- 3테이블 동형 저장·CRUD·저장 게이트(검증 강제·리졸버 주입·`check_*` 플래그)의 배선을 확정한다.
- D1 파라미터 오버라이드 검증이 R01 `ParamSpec`·`validate_params` 훅을 **어떻게 소비하는가**(신규 검증 로직 0)를 배선한다.
- 검증기 3종·`is_runnable`을 R03가 인용할 안정 앵커로 확정한다(**소비자: PRD-R03 §4**).
- 모든 요구사항을 합성 Fixture + 격리 DuckDB + pytest 결정론 검증으로 매핑한다.

본 문서는 R01 시그니처·§5 도메인 형상·연산자 집합·DDL 골격을 **재정의하지 않는다**(확정 원천). 그것들의 **배선·강제·검증 방식**만 확정한다.

## 2. 범위 (In / Out)

### In

- 세 엔티티 불변 도메인 타입의 모듈 배치와 재귀 JSON 직렬화 왕복 배선(계약 상세는 PRD §3·§5 확정, 본 문서는 강제 배선).
- 공유 JSON 정규화 leaf(`_jsonnorm`) 배치와 세 패키지의 소비 규약.
- DuckDB `strategies`·`rules`·`formulas` 3테이블 동형 DDL 준수·CRUD·저장 게이트 배선.
- 검증기 3종(Formula/Rule/Strategy) 비발생+엄격 변형·`is_runnable`의 배선 및 오류 모델.
- D1 파라미터 오버라이드 검증(ParamSpec 대조 + `validate_params` 훅 소비 + `column ∈ output`)의 R01 인터페이스 소비 배선.
- 참조 검증(factor/formula/rule 존재·컬럼 일치·DAG 순환)의 리졸버 주입 배선.
- 계층 순수성 INV-1~3 AST 스캔 규칙.

### Out (확정)

- **Formula compute·Rule 평가·Strategy 백테스트·Daily 실행**(데이터에 정의를 적용한 시계열 산출) — R03 소관. 본 계층은 정의·영속·검증까지만.
- 정규화·순위 함수(rank/zscore/min/max/clip) — 연산자 열거 additive 확장으로 후속(PRD §2 Out).
- 리밸런싱 정책 필드(D5 — Portfolio Epic에서 `schema_version` 증가와 함께 additive 재도입).
- Builder UI·AI 생성 정의.
- 팩터 계산·산식·레지스트리 자체(→ R01).

## 3. PRD 추적성 매트릭스 (공백 0)

> **판독 규약**: "TR" 열은 §4의 기술 결정을 가리킨다. **(PRD 확정 인용)** 표시 행은 PRD-R02가 이미 TR급으로 확정한 항목으로, §4에서 반복하지 않고 본 매트릭스로 축약한다(§D-9). 시그니처 확정 원천은 R02 자체 타입=후속 `DESIGN-R02 §3`, R01 소비 인터페이스=`DESIGN-R01 §3`. 나머지 행은 §4가 PRD에 없는 기술 결정을 추가한다.

### 3.1 공통 표현 계약 (REQ-C1~C7)

| REQ | 요지 | TR | 근거 |
|---|---|---|---|
| REQ-C1 | 선언성 — 순수 JSON, 코드·람다·산술식 문자열 금지, 태그 판별 트리 노드만 | TR-R02-001, TR-R02-002 | PRD §3 |
| REQ-C2 | 왕복 무손실 `from_dict(to_dict(x))==x` + 생성 시점 정규화(공유 leaf) | TR-R02-002 | PRD §3 |
| REQ-C3 | 결정론 — `to_json` 키 정렬 고정, 오류 순서 결정론 | TR-R02-003 | PRD §3 |
| REQ-C4 | schema_version — 미래 버전 거부, 누락 필드 관대 복원, 초기값 1 | TR-R02-004 | PRD §3 |
| REQ-C5 | canonical-JSON eq/hash — `30`≠`30.0` 구분 | TR-R02-003 | PRD §3 |
| REQ-C6 | 상수 피연산자 `int`/`float`만, `bool` 생성 거부 | TR-R02-002 (PRD 확정 인용) | PRD §3 |
| REQ-C7 | 불변성 — 전 도메인 타입 frozen | TR-R02-002 (PRD 확정 인용) | PRD §3 |

### 3.2 영속화 계약 (REQ-P1~P4)

| REQ | 요지 | TR | 근거 |
|---|---|---|---|
| REQ-P1 | 3테이블 동형 DDL(JSON `definition` + 비정규 식별 컬럼), additive 멱등 | TR-R02-005 (PRD 확정 인용) | PRD §4 |
| REQ-P2 | CRUD(멱등 upsert·`created_at` 보존·`now` 주입·`list_*` id 정렬), storage→도메인 단방향 | TR-R02-005 | PRD §4 |
| REQ-P3 | 저장 게이트 — 검증 강제·부분 저장 없음·self-store 리졸버 default-on·완화 플래그 | TR-R02-006 | PRD §4 |
| REQ-P4 | dangling 정책 — 저장 시점 차단, 사후 삭제 비계단식, 활성 참조 보호는 R03 위임 | TR-R02-007 | PRD §4 |

### 3.3 도메인별 확정 형상 (§5.1~§5.4)

| 형상 | 요지 | TR | 근거 |
|---|---|---|---|
| §5.1 Formula | 표현 트리(BinaryOp/UnaryOp/피연산자 3종)·`output_column`·태그 규약·arity 거부 | TR-R02-014 (PRD 확정 인용) | PRD §5.1 |
| §5.1 required_data 파생 | 저장 필드 아님 — expression+레지스트리 전이 합집합 파생 함수 | TR-R02-014 | PRD §5.1 |
| §5.1 DAG | Formula 간 참조 비순환 — 자기참조·2-사이클·장주기 거부 | TR-R02-010 | PRD §5.1 |
| §5.1 관대 복원 | `FormulaOperand.column` 누락 시 `"value"` 복원 | TR-R02-014 | PRD §5.1 |
| §5.2 Rule | Predicate/Composition·비교/교차/논리 연산자·피연산자 3종(별개 클래스) | TR-R02-012 (PRD 확정 인용) | PRD §5.2 |
| §5.2 교차 가드 | `crosses_*`는 좌/우 최소 1개가 factor 또는 formula | TR-R02-012 | PRD §5.2 |
| §5.2 float 비교 | `==`/`!=` 원소별 엄밀 비교(의미론 문서·CLI 명시) | TR-R02-012 | PRD §5.2 |
| §5.3 Strategy | 컨테이너(factor_refs·universe·rule·metadata·schema_version) | TR-R02-013 (PRD 확정 인용) | PRD §5.3 |
| §5.3 factor_refs 일관성 | rule 슬롯 전이 참조 factor 집합과 정확 일치(초안 rule=None은 보류) | TR-R02-011 | PRD §5.3 |
| §5.3 universe | KRX 6자리 숫자 형식, 빈 튜플=watchlist 전체(D5) | TR-R02-013 | PRD §5.3 |
| §5.3 rule 슬롯 (D4) | `None` 또는 `{"roles":{...}}` whitelist fail-closed, entry≥1=runnable | TR-R02-013 | PRD §5.3 |
| §5.3 리밸런싱 부재 (D5) | 정의에 리밸런싱 필드 없음 | TR-R02-013 | PRD §5.3 |
| §5.4 params 검증 (D1) | ParamSpec 대조 + `validate_params` 훅 + `column ∈ output` | TR-R02-008 | PRD §5.4 |

### 3.4 검증 요구사항 (REQ-V1~V5)

| REQ | 요지 | TR | 근거 |
|---|---|---|---|
| REQ-V1 | 검증기 3종 비발생(non-raising) + 엄격 변형, 결과 `ok+errors(순서 결정론)` | TR-R02-015 | PRD §6 |
| REQ-V2 | 공통 검증(구조 well-formedness·id/name/output_column 형식·왕복 동일성·코드 없음 재확인) | TR-R02-015 | PRD §6 |
| REQ-V3 | 참조 검증(factor 존재·column∈output·params 검증 / formula 존재·컬럼 일치·순환 / rule 존재·factor_refs 일관성) | TR-R02-008, TR-R02-009, TR-R02-010, TR-R02-011 | PRD §6 |
| REQ-V4 | 오류 메시지 — 한국어 + 행동 가능 힌트(누락 id·유효 컬럼·허용 범위) | TR-R02-016 | PRD §6 |
| REQ-V5 | `is_runnable(defn)` — roles 형상·entry≥1 → True (R03 활성화·백테스트 전제) | TR-R02-015 | PRD §6 |

### 3.5 Acceptance Criteria (AC-01~AC-07)

| AC | 요지 | TR (검증) | §6 |
|---|---|---|---|
| AC-01 | 왕복·결정론·canonical eq/hash(`30`vs`30.0`)·frozen·미래 schema_version 거부 | TR-R02-002/003/004 | AC-R02-01 |
| AC-02 | 구조 거부(미지 연산자/kind/태그·arity·bool 상수·비-str 키·비-snake_case id) | TR-R02-002/012/014 | AC-R02-02 |
| AC-03 | 참조 검증(미존재 id·column∉output·formula 컬럼 불일치·상수 crosses 상수·params 위반·factor_refs 불일치) | TR-R02-008/009/011/012 | AC-R02-03 |
| AC-04 | DAG(자기참조·2-사이클·장주기 거부·다이아몬드 통과·저장 게이트 순환 upsert 예외+무변경) | TR-R02-010/006 | AC-R02-04 |
| AC-05 | rule 슬롯(roles entry1+ 통과·None 통과 is_runnable=False·빈 entry/미지 키/rule_ids/인라인 거부·중복 rule id 거부·순서 보존) | TR-R02-013/015 | AC-R02-05 |
| AC-06 | CRUD(저장→조회 동일·멱등·created_at 보존·id 정렬·삭제 후 None·무효 upsert 예외·다중 참조 가능) | TR-R02-005/006 | AC-R02-06 |
| AC-07 | 순수성(INV-1~3 AST 스캔 green·3테이블 존재·멱등 재연결) | TR-R02-001/005 | AC-R02-07 |

### 3.6 INV / 확정 결정 (D1~D5)

| 식별자 | 요지 | TR | 근거 |
|---|---|---|---|
| INV-1 | 세 도메인 패키지는 백테스트·실행·storage 미import. 허용: R01 레지스트리 + `_jsonnorm` leaf | TR-R02-001 | PRD §7 |
| INV-2 | `rule`↔`formula`↔`strategy` 상호 미import(타 엔티티는 주입 리졸버 duck typing) | TR-R02-001 | PRD §7 |
| INV-3 | 타입 주석 목적 import는 `TYPE_CHECKING` 하에서만(스캔 제외) | TR-R02-001 | PRD §7 |
| **D1** | 파라미터 오버라이드 완전 해석 — 정의 검증에서 ParamSpec 대조 + `validate_params` 훅 | TR-R02-008 | README §4 |
| **D4** | rule 슬롯 roles 단일 형상(whitelist fail-closed, entry≥1=runnable) | TR-R02-013 | README §4 |
| **D5** | 선언한 것은 해석되거나 없음 — universe 실제 소비(R03), 리밸런싱 필드 부재 | TR-R02-013 | README §4 |

> D2(가격=팩터), D3(선언형 단일 실행 경로)는 R01(price 팩터 등록)·R03(Daily 실행 경로) 소관이며 R02 정의 계층에 직접 관여하지 않는다. R02는 `price`를 여느 factor id와 동형으로 참조·검증할 뿐이다(별도 배선 불요).

## 4. 기술 요구사항 (TR-R02-xxx)

> 각 TR은 PRD가 확정하지 않은 기술 결정만 담는다. R02 자체 타입 시그니처의 확정 원천은 후속 `DESIGN-R02 §3`, R01 소비 인터페이스는 `DESIGN-R01 §3`이며 여기서 재정의하지 않는다. 완전한 함수 본문은 두지 않고 시그니처 요약·의사코드·표·서술까지만 확정한다(R5).

### 4.1 모듈 배치 및 계층 순수성

**TR-R02-001 — 3패키지 분할 + `_jsonnorm` 공유 leaf + INV-1~3 AST 스캔 강제**
- `strategy/`·`rule/`·`formula/`를 별도 패키지로 배치한다. 각 패키지는 `definition`(도메인 타입 + `from_dict`/`to_dict`) + `validation`(검증기) 모듈을 갖는다. 세 패키지는 정의·검증만 담당하며 평가·실행·백테스트를 포함하지 않는다.
- **공유 정규화 leaf(B1-i)**: 자유형 매핑 정규화 함수는 `quant_krx/_jsonnorm.py` 단일 leaf 모듈에 두고 세 패키지가 각자 import한다. 이 leaf는 도메인 패키지가 아니므로 세 패키지가 공유해도 INV-2(패키지 상호 미import)를 위반하지 않는다 — R01 팩터 레지스트리와 동급의 허용 leaf 참조다.
- **INV-1 강제**: 세 도메인 패키지 하위 모든 모듈은 백테스트 엔진(`vectorbt`)·평가/실행 계층(`quant_krx.workspace`·`quant_krx.jobs`·`quant_krx.quant`)·storage(`quant_krx.storage`, DuckDB)를 런타임 import하지 않는다. 허용 참조는 R01 팩터 레지스트리(`quant_krx.factors`)와 `_jsonnorm` leaf뿐이다.
- **INV-2 강제**: `rule`·`formula`·`strategy` 패키지는 서로를 import하지 않는다. 타 엔티티 객체는 주입 리졸버가 반환한 것을 **duck typing으로만** 소비한다(예: Rule의 `FormulaOperand`는 Formula 패키지를 참조하지 않고 `formula_id` 문자열만 보유).
- **INV-3 강제**: 타입 주석 목적의 import는 `if TYPE_CHECKING:` 블록 하에서만 허용(런타임 미로딩 → 스캔 제외).
- 검증 배선: AST 스캔 테스트가 세 패키지 import 그래프를 순회하여 금지 모듈(vectorbt·workspace·jobs·quant·storage) 및 패키지 상호 참조를 0건으로 강제한다. `TYPE_CHECKING` guard 내부는 별도 판정으로 예외 처리.
- 근거: `← INV-1 / INV-2 / INV-3 / REQ-C2 / AC-07 / PRD-R02 §7`

### 4.2 공통 표현 계약 배선

**TR-R02-002 — 왕복 무손실 + `_jsonnorm` 공유 leaf 정규화 배선 (REQ-C1/C2/C6/C7)**
- 자유형 매핑(`metadata`, operand `params`)은 **생성 시점**에 `_jsonnorm` leaf 함수로 JSON-native 정규화한다: 중첩 tuple→list 변환, str 키만 허용, JSON 스칼라(`int`/`float`/`str`/`bool`/`None`)만 허용 — 위반은 생성 거부. 이로써 `from_dict(to_dict(x))==x`(REQ-C2)를 구조적으로 폐색한다.
- **상수 규약 배선(REQ-C6)**: `ConstantOperand.value`는 `int`/`float`만 허용하고 `bool`은 생성 시 거부한다(Python에서 `bool`은 `int` 하위형이므로 `isinstance(value, bool)` 선차단 배선을 명시). 자유형 매핑 내부의 `bool` 값은 JSON 스칼라로 허용되나 상수 피연산자 값으로서의 `bool`은 거부 — 두 경로의 판정 지점을 분리한다.
- **선언성 배선(REQ-C1)**: 산술·논리는 태그 판별 트리 노드로만 표현하며, 산술식 문자열(`"PER*ROE"`)·람다·실행 코드의 저장·파싱·평가 경로를 두지 않는다. `from_dict`는 오직 태그(`node`/`kind`) 분기로만 노드를 복원한다.
- **불변성 배선(REQ-C7)**: 전 도메인 타입은 frozen dataclass로 배치하며, 수정은 새 인스턴스 생성으로 표현한다(in-place 변경 API 부재).
- 근거: `← REQ-C1 / REQ-C2 / REQ-C6 / REQ-C7 / AC-01 / AC-02 / PRD-R02 §3`

**TR-R02-003 — canonical-JSON eq/hash + 결정론 직렬화 배선 (REQ-C3/C5)**
- **결정론 직렬화(REQ-C3)**: `to_json`은 키 정렬 고정(예: `sort_keys=True` 상당)으로 동일 정의 → 바이트 동일을 보장한다. 검증 오류 목록의 순서도 결정론적이어야 한다(트리 순회 순서 고정 — 예: 좌→우, 깊이 우선).
- **canonical eq/hash(REQ-C5)**: 세 엔티티의 `__eq__`/`__hash__`는 **canonical JSON 표현 기반**으로 배선한다(필드 기반 eq 금지). 근거는 자유 수치 상수 리프에서 필드 기반 eq는 `30`==`30.0`이지만 직렬 표현(`30` vs `30.0`)이 달라 해시 계약이 깨지기 때문이며, `30`과 `30.0`은 서로 다른 정의로 취급한다(`{Formula(...30...), Formula(...30.0...)}`의 set 크기 = 2). 구현 수단(canonical 문자열 산출 알고리즘)의 확정은 후속 DESIGN-R02 §3 소관이며, 본 TR은 "eq/hash의 근거는 canonical JSON"이라는 배선 결정만 고정한다.
- 근거: `← REQ-C3 / REQ-C5 / AC-01 / PRD-R02 §3`

**TR-R02-004 — schema_version 관대/엄격 복원 배선 (REQ-C4)**
- 모든 정의는 `schema_version` 필드를 가지며 초기값은 1이다. `from_dict`는 본문 `schema_version`이 코드 버전보다 **크면 거부**(다운그레이드 차단 — 미래 버전을 현 코드가 안전 해석 불가), **같거나 작으면 누락 필드를 기본값으로 관대 복원**한다.
- 관대 복원의 구체 예: `FormulaOperand.column` 누락 → `"value"`(TR-R02-014), rule 슬롯 누락 → `None`(초안). 관대 복원은 additive 필드 추가(공통 원칙 6) 시 하위 호환을 보장하는 배선이다.
- 근거: `← REQ-C4 / AC-01 / 공통 원칙 6 / PRD-R02 §3`

### 4.3 영속화·저장 게이트 배선

**TR-R02-005 — 3테이블 동형 DDL + CRUD 배선 (REQ-P1/P2)**
- 저장 3테이블(`strategies`·`rules`·`formulas`)은 동형이다: 단일 JSON `definition` 본문 + 비정규화 식별 컬럼(`id` PK·`name`·`version`·`schema_version`·`created_at`·`updated_at`). DDL 형상은 PRD §4 확정. 본 TR은 배치·멱등 배선만 확정: `CREATE TABLE IF NOT EXISTS` 멱등(재연결 무오류, AC-07).
- **CRUD 배선(REQ-P2)**: `upsert_*`/`get_*`/`list_*`/`delete_*`를 storage 계층 메서드로 제공한다. **방향은 storage → 도메인**(도메인 패키지는 storage를 모른다, INV-1). `INSERT OR REPLACE` 멱등, 신규 시 `created_at=now`·갱신 시 `created_at` 보존·`updated_at` 갱신, `now`는 **주입**으로 결정론 확보. `list_*`는 `id` 오름차순 정렬.
- `definition`(JSON)이 진실 원천이고 `name`/`version`/`schema_version`은 조회용 비정규화 컬럼이다(질의 편의, 진실 원천 아님).
- 근거: `← REQ-P1 / REQ-P2 / AC-06 / AC-07 / PRD-R02 §4`

**TR-R02-006 — 저장 게이트: 검증 강제 + 리졸버 주입 + `check_*` 플래그 (REQ-P3, B2-i)**
- 모든 `upsert_*`는 저장 **전** 해당 엔티티 검증기를 강제한다. 무효 정의(구조 위반·미존재 참조·순환·형상 위반)는 **부분 저장 없이** 검증 예외로 차단된다(트랜잭션 경계에서 저장 미수행 → store 무변경, AC-04/AC-06).
- **리졸버 주입(B2-i)**: 참조 존재·순환 검증은 자기 자신의 store를 리졸버로 **기본 주입(default-on)** 한다. 예: `upsert_formula`는 `formulas` store 기반 리졸버를 formula 참조 존재·순환 검증에 주입, `upsert_rule`은 `formulas` store 리졸버(`FormulaOperand` 참조)·factor 레지스트리를 주입, `upsert_strategy`는 `rules` store 리졸버·factor 레지스트리를 주입.
- **완화 플래그**: `check_*` 플래그(예: `check_formula_store`·`check_rule_store`, 기본 True)로 리졸버 주입을 끌 수 있다(부분 조립·단위 테스트용). 플래그 off는 참조 존재 검증만 완화하며 구조 검증은 항상 수행한다.
- storage가 도메인 검증기를 호출하되(storage→도메인 단방향), 도메인 검증기는 storage를 모르고 주입된 리졸버(콜러블)만 소비한다 — INV-1 유지.
- 근거: `← REQ-P3 / AC-04 / AC-06 / PRD-R02 §4`

**TR-R02-007 — dangling 정책 배선 (REQ-P4)**
- 참조 무결성 보장 시점은 **저장 시점**이다(TR-R02-006 게이트). 참조된 엔티티의 **사후 삭제는 계단식으로 정리하지 않는다**(`delete_*`는 비계단식) — 남은 dangling 참조는 실행 시점에 R03 평가 진입의 명확 실패(`EvaluationError`)로 격리된다.
- **활성 참조 보호는 본 계층의 책임이 아니다**: 활성 전략이 참조 중인 Formula/Rule의 수정·삭제 차단은 활성 상태(activation)를 아는 상위 계층 책임이다. 본 TR은 정책 경계만 고정하고 상세는 위임한다 — **소비자: PRD-R03 §4(FR-04a)**.
- 근거: `← REQ-P4 / 공통 원칙 4 / PRD-R02 §4` (활성 참조 보호 상세는 PRD-R03 §4 위임)

### 4.4 참조 검증·params 검증 배선 (R01 인터페이스 소비)

**TR-R02-008 — D1 params 오버라이드 검증 배선 (§5.4, R01 소비)**
- `FactorRef.params`·`FactorOperand.params`(Rule/Formula 공통)는 해당 factor의 **ParamSpec 대조**로 검증한다: 미지 파라미터 이름 거부, 타입 불일치 거부(int 자리 float 등), min/max 범위 위반 거부. 대조 원천은 `DESIGN-R01 §3.2 ParamSpec`(재정의 없이 링크 인용) — R02는 이 명세를 소비만 하며 검증 규칙을 복제하지 않는다(B3-i, D1 단일 원천).
- **교차 제약 훅 소비**: 팩터가 `validate_params` 훅(`DESIGN-R01 §3.3`, 인스턴스화 + 정의 검증 양쪽 호출점 중 후자)을 노출하면 교차 제약(예: `macd` fast<slow)도 정의 시점에 함께 검증한다. R02는 훅을 링크 인용으로 재사용하며 신규 검증 로직을 두지 않는다(TR-R01-005의 "소비자: PRD-R02 §5.4" 지점의 실현). 훅 미노출 팩터는 빈 제약으로 간주.
- **`column ∈ metadata.output` 검증**: params와 무관하게 항상 수행한다(파라미터는 출력 컬럼 집합을 바꾸지 않는다 — R01 계약). 유효 컬럼 목록은 `DESIGN-R01 §3` `FactorMetadata.output`에서 조회.
- 빈 매핑 = 전부 기본값. 동일 `factor_id`·상이 `params`의 두 피연산자는 서로 다른 지표 참조이며, 정의 검증은 각각 독립으로 params 대조한다(평가 시 독립 인스턴스화는 R03 보장 — 소비자 포인터).
- 팩터 존재·레지스트리 조회는 `DESIGN-R01 §3.8 list_factors`·`§3.7 get_factor` 앵커를 소비하되, **정의 검증은 인스턴스화 없이 ParamSpec 정적 대조로 수행**함을 원칙으로 한다(실행 없음 — REQ-C1). 레지스트리 기반 검증은 플래그로 완화 가능(REQ-V3).
- 근거: `← REQ-V3 / §5.4 / D1 / AC-03 / PRD-R02 §5.4` (R01 앵커: DESIGN-R01 §3.2/§3.3/§3.7/§3.8)

**TR-R02-009 — factor/formula/rule 참조 존재 검증 + 리졸버 주입 (REQ-V3)**
- **factor 참조**: `FactorOperand.factor_id`·`FactorRef.factor_id`는 R01 팩터 레지스트리 존재를 검증한다(`DESIGN-R01 §3.8` 조회 링크). 미존재 시 REQ-V4 힌트(사용 가능 id 목록). 레지스트리 기반 검증은 플래그로 완화 가능.
- **formula 참조**: `FormulaOperand.formula_id`는 주입 리졸버로 존재를 검증하고, `FormulaOperand.column == 참조 Formula.output_column` 일치를 검증한다(불일치 거부 + 유효 컬럼 힌트). 리졸버는 저장 게이트가 `formulas` store 기반으로 default-on 주입(TR-R02-006).
- **rule 참조**: Strategy rule 슬롯의 `rule_id`는 주입 리졸버로 `rules` store 존재를 검증한다.
- Rule 패키지의 `FormulaOperand`는 Formula 패키지와 **별개 클래스**이며 리졸버 반환 객체를 duck typing으로만 소비한다(INV-2).
- 근거: `← REQ-V3 / §5.1 / §5.2 / §5.3 / AC-03 / PRD-R02 §6`

**TR-R02-010 — Formula DAG 순환 검출 배선 (§5.1 DAG)**
- Formula 간 참조는 비순환이어야 한다. 자기참조·2-사이클·3-노드 이상 장주기를 전부 거부한다. 검출 배선: 주입 리졸버로 참조 Formula를 확장하며 **DFS(gray/black 표시)** 로 순환을 탐지한다(구현 수단 확정은 후속 DESIGN-R02 §6). 순환 발견 시 순환 경로 힌트(REQ-V4)와 함께 거부.
- 저장 게이트에서 기본 강제: 순환 Formula의 `upsert_formula`는 예외 + store 무변경(AC-04). 다이아몬드 DAG(공유 참조·비순환)는 통과.
- 근거: `← §5.1 / REQ-V3 / AC-04 / PRD-R02 §5.1`

**TR-R02-011 — Strategy factor_refs↔rule 전이 참조 집합 일치 검증 배선 (§5.3)**
- rule 슬롯이 존재하면(roles 형상), `factor_refs`의 `factor_id` 집합은 rule 슬롯이 **전이적으로 참조하는 factor 집합**과 **정확히 일치**해야 한다. 전이 집합 산출 배선: 참조 Rule들의 `FactorOperand.factor_id` ∪ 참조 Rule이 참조하는 `FormulaOperand`가 전이적으로 참조하는 factor(§5.1 required_data 전이 파생과 동일 순회) 합집합.
- 불일치(선언-실제 drift)는 검증 실패다(초과·부족 양방향). 힌트: 누락/잉여 factor id 목록(REQ-V4).
- **초안(rule=None)에서는 집합 일치 검증을 보류**한다(빌더 중간 상태 허용, D5의 "선언만 하고 미해석" 금지와 구별 — 초안은 미완성이지 미해석 필드가 아님).
- 근거: `← §5.3 / REQ-V3 / AC-03 / D5 / PRD-R02 §5.3`

### 4.5 도메인 형상 검증 배선

**TR-R02-012 — Rule 구조 가드 배선 (§5.2)**
- **교차 연산자 구조 가드**: `crosses_above`/`crosses_below`는 좌/우 피연산자 중 **최소 1개가 factor 또는 formula**여야 한다(`상수 crosses 상수`는 축퇴 — 구조 거부). 검증 배선: Predicate 생성/`from_dict`·검증 시 피연산자 `kind` 조합을 판정.
- **float 비교 의미론 명시**: `==`/`!=`는 원소별 엄밀 비교다. 부동소수점 시계열 간 동등 비교는 일반적으로 항상 False가 되므로 주 용도는 상수·정수형 지표이며, 이 의미론을 CLI 도움말·문서에 명시하는 배선을 요구한다(정의 계층은 의미론 문서화까지, 평가 동작은 R03).
- **논리 연산자 arity**: `AND`/`OR`는 피연산자 ≥2, `NOT`은 정확히 1. arity 위반은 생성/`from_dict` 거부(AC-02).
- 근거: `← §5.2 / AC-02 / AC-03 / PRD-R02 §5.2`

**TR-R02-013 — Strategy roles 형상(D4) + universe(D5) 배선 (§5.3)**
- **rule 슬롯 whitelist fail-closed(D4)**: `None`(초안) 또는 `{"roles": {"entry": [rule_id,...], "exit": [rule_id,...]}}`만 유효. 그 외 모든 형상(인라인 Rule 본문·`{"rule_ids": [...]}` 형상 포함)은 거부한다. 역할 키는 `entry`/`exit`만(미지 키 거부), `entry`는 비어있지 않아야 하고(무거래 전략 구조적 차단), `exit`는 생략/빈 리스트 허용. 역할 내 rule id 중복 거부, 순서 보존(왕복).
- **universe 형식(D5)**: `Universe.symbols`는 KRX 6자리 숫자 형식이어야 한다(형식 위반 거부). 빈 튜플 = 파이프라인 watchlist 전체(실행 의미 소비는 **소비자: PRD-R03 §7**). 시장 전체·조건식 universe는 후속 additive.
- **리밸런싱 필드 부재(D5)**: 정의 스키마에 리밸런싱 정책 필드를 두지 않는다("정의는 되지만 해석되지 않는" 필드 금지). 후속 Portfolio Epic에서 `schema_version` 증가와 함께 additive 도입.
- 근거: `← §5.3 / D4 / D5 / AC-05 / PRD-R02 §5.3`

**TR-R02-014 — Formula 표현 트리·출력·required_data 파생 배선 (§5.1)**
- **표현 트리 태그 규약**: `node`("binary"|"unary") + 리프 `kind`("factor"|"constant"|"formula"). 이항 `+`/`-`/`*`/`/`, 단항 `neg`. 미지 태그·arity 위반(Binary left 누락 등)·태그 부재/중복은 `from_dict` 거부(AC-02).
- **output_column**: 단일(snake_case). `FormulaOperand.column` 직렬 본문 누락 시 `"value"`로 관대 복원(TR-R02-004 관대 복원의 구체 예).
- **required_data 전이 파생 함수**: `required_data`는 저장 필드가 **아니라** expression + R01 레지스트리에서 참조 factor들의 `required_data`(및 formula 참조를 통한 전이)를 합집합으로 **파생하는 함수**로 제공한다(진실 원천 = expression + 레지스트리, drift 원천 제거). R01 `FactorMetadata.required_data`(`DESIGN-R01 §3` 링크)를 소비.
- Formula는 factor 레지스트리에 등록되지 않는 **별도 네임스페이스**(`formulas` 테이블)이며 Rule/다른 Formula가 `id`+`output_column`으로만 참조한다.
- 근거: `← §5.1 / REQ-C1 / REQ-C4 / PRD-R02 §5.1`

### 4.6 검증기·오류 모델·additive·테스트 배선

**TR-R02-015 — 검증기 3종 + `is_runnable` 배선 — R03 인용 원천 (REQ-V1/V2/V5)**
- 각 엔티티(Formula/Rule/Strategy)에 **비발생(non-raising) 검증기 + 엄격 변형(첫 오류 예외)** 을 배선한다. 비발생 검증기 결과는 `ok + errors(순서 결정론)`. 엄격 변형은 저장 게이트(TR-R02-006)가 소비한다.
- **공통 검증(REQ-V2)**: 구조 well-formedness(연산자·arity·kind·태그) / id·name·output_column 형식(snake_case·비공백) / 직렬화 왕복 동일성 / 코드 없음 재확인(태그 트리만·문자열식 부재).
- **`is_runnable(defn)`(REQ-V5)**: rule 슬롯이 roles 형상이고 entry ≥ 1이면 True. "정의 검증은 통과하나 실행 시점에 거부되는" 상태를 구조적으로 금지한다(D4). **본 판정은 R03의 활성화·백테스트 전제 조건으로 소비되는 안정 앵커다** — 시그니처 확정 원천은 후속 DESIGN-R02 §3, **소비자: PRD-R03 §4**. 배선 선택이 이 앵커를 흔들지 않도록 고정.
- 근거: `← REQ-V1 / REQ-V2 / REQ-V5 / AC-05 / D4 / PRD-R02 §6` (소비자: PRD-R03 §4)

**TR-R02-016 — 오류 모델 구체화 (REQ-V4)**
- 검증 오류 메시지는 **한국어 + 행동 가능 힌트**를 담는다: 누락 factor/formula/rule id → "사용 가능: …" 목록, `column ∉ output` → 유효 컬럼 목록, params 범위 위반 → 허용 범위, 순환 → 순환 경로, factor_refs 불일치 → 누락/잉여 id 목록.
- 오류 순서는 결정론적(REQ-C3·REQ-V1 — 트리 순회 순서 고정). CLI 실패는 non-zero 종료(R03 CLI 계층이 소비 — 소비자 포인터).
- 근거: `← REQ-V4 / 공통 원칙 7 / README §5`

**TR-R02-017 — additive 진화 원칙 배선**
- 신규 연산자 = 연산자 열거 추가, 신규 피연산자 = `kind` 추가, 신규 필드 = JSON 본문 + `schema_version` 증가(관대 복원 TR-R02-004), 신규 저장 = 테이블 추가. **기존 3테이블 DDL·공개 정의 형상은 변경하지 않는다**. 정규화·순위 함수(rank/zscore 등)는 이 원칙에 따른 연산자 additive 확장 후보(PRD §2 Out).
- 근거: `← REQ-C4 / 공통 원칙 6 / README §5`

**TR-R02-018 — 테스트 전략 배선**
- 모든 AC는 합성 Fixture + 격리 DuckDB(tmp) + pytest로 네트워크·실데이터·LLM·시각 의존 없이 검증한다. 결정론은 **2회 실행 동일**(직렬화 바이트 동일·검증 오류 순서 동일)으로 판정한다.
- **기대값 하드코딩 금지**: canonical eq/hash·왕복·구조 거부는 대표 정의(중첩 트리 포함)를 산출·재구성하여 대조한다. factor/formula 참조 검증은 R01 레지스트리 + 격리 store 리졸버 주입으로 검증(실데이터 불요). `now`·`as_of`는 주입.
- 근거: `← 원칙 3 / AC-01~07 / PRD-R02 §8`

## 5. 비기능 요구사항 (NFR)

| NFR | 요구 | 검증 |
|---|---|---|
| **NFR-01 결정론** | 직렬화(바이트 동일)·검증(오류 순서 동일)·canonical eq/hash가 네트워크·현재시각 미의존(`now`/`as_of` 주입). | 2회 실행 동일(직렬 바이트·오류 목록) |
| **NFR-02 오프라인 검증** | 전 AC가 네트워크·실데이터·LLM 없이 합성 Fixture + 격리 DuckDB로 검증. | CI 오프라인 green |
| **NFR-03 계층 순수성** | 세 도메인 패키지가 백테스트·평가·storage·상호 패키지 미import(INV-1~3). 허용: R01 레지스트리 + `_jsonnorm` leaf. | AST 스캔 green |
| **NFR-04 왕복 무손실** | `from_dict(to_dict(x))==x` 전 엔티티·중첩 트리·자유형 매핑. | 왕복 동등 테스트 |
| **NFR-05 저장 시점 무결성** | dangling 참조·순환이 부분 저장 없이 저장 게이트에서 차단(store 무변경). | 무효 upsert 예외 + store 카운트 불변 |
| **NFR-06 canonical 계약** | `30`≠`30.0` 등 자유 수치 상수의 eq/hash가 canonical JSON 기반으로 일관. | set 크기 2 테스트 |
| **NFR-07 멱등** | 3테이블 생성·upsert 재실행이 중복·오류 0(`created_at` 보존). | 재실행 count 1·created_at 불변 |

## 6. 수용 기준 (PRD AC 승계 + pytest 매핑)

> PRD-R02 AC-01~07을 `AC-R02-xx`로 승계·구체화하고 pytest 검증 방법을 명시한다. 기대값 하드코딩 금지.

- **AC-R02-01 (← AC-01)** 세 엔티티 대표 정의(중첩 트리 포함)의 `from_dict(to_dict)==원본` · 2회 직렬화 바이트 동일 · canonical eq/hash(`30` vs `30.0` 구분 — set 크기 2) · frozen 위반 예외 · 미래 `schema_version` 거부.
  - *pytest*: 각 엔티티 왕복 동등; `to_json` 2회 바이트 동일; `{defn_30, defn_30_0}` set 크기 2; frozen 필드 대입 시 예외; `schema_version=코드버전+1` `from_dict` 거부.
- **AC-R02-02 (← AC-02)** 미지 연산자/kind/태그 · arity 위반(AND 1항·NOT 2항·Binary left 누락) · bool 상수 · 비-str 매핑 키 · 비-snake_case id — 전부 생성 또는 `from_dict`/검증 거부.
  - *pytest*: 각 위반 케이스가 `from_dict`/생성 시 예외; `ConstantOperand(True)` 거부; 비-str 키 매핑 거부; 대문자·공백 id 거부.
- **AC-R02-03 (← AC-03)** 미존재 factor/formula/rule id 거부(+힌트) · `column ∉ output` 거부(+유효 컬럼) · formula 컬럼 불일치 거부 · `상수 crosses 상수` 거부 · params(미지 이름·타입·범위·교차 제약 `validate_params`) 위반 거부/유효 통과 · factor_refs–rule 전이 집합 불일치 거부/일치 통과.
  - *pytest*: 격리 store + R01 레지스트리로 각 참조 위반 예외 + 힌트 문자열 포함; `get_factor("macd")` 계열 fast≥slow params 거부; factor_refs 초과/부족 케이스 거부, 정확 일치 통과.
- **AC-R02-04 (← AC-04)** 자기참조·2-사이클·3-노드 장주기 거부(순환 경로 힌트) · 다이아몬드 DAG 통과 · 저장 게이트에서 순환 formula upsert 시 예외 + store 무변경.
  - *pytest*: DFS 검출로 각 순환 케이스 예외; 다이아몬드 통과; `upsert_formula(순환)` 예외 후 `list_formulas` count 불변.
- **AC-R02-05 (← AC-05)** roles(entry 1+) 통과 · `None` 통과(단 `is_runnable=False`) · 빈 entry·미지 역할 키·`rule_ids` 형상·인라인 본문 전부 거부 · 역할 내 중복 rule id 거부 · 순서 왕복 보존.
  - *pytest*: `is_runnable` roles/None 분기; 빈 entry·`{"rule_ids":...}`·인라인 dict 거부; 중복 rule id 거부; roles 리스트 순서 왕복 동일.
- **AC-R02-06 (← AC-06)** 저장→조회 동일 · 멱등 upsert(count 1·`created_at` 보존·`updated_at` 갱신) · 목록 id 정렬 · 삭제 후 None · 무효 정의 upsert 예외(부분 저장 없음) · 하나의 Rule/Formula를 복수 Strategy/Rule/Formula가 참조 가능.
  - *pytest*: `get_*`==원본; 2회 upsert count 1·created_at 불변·updated_at 갱신; `list_*` id 오름차순; `delete_*` 후 `get_*` None; 무효 upsert 예외 후 store 불변; 공유 참조 2 엔티티 저장.
- **AC-R02-07 (← AC-07)** INV-1~3 AST 스캔 green · 테이블 3종 존재 + 멱등 재연결.
  - *pytest*: AST 스캔 0 위반(금지 모듈 + 패키지 상호 참조); `CREATE TABLE IF NOT EXISTS` 2회 무오류; 3테이블 존재.

### 6.1 AC → 테스트 모듈 매핑 (예시 경로)

| AC | 테스트(예시 경로) | 검증 핵심 |
|---|---|---|
| AC-R02-01 | `tests/unit/definition/test_roundtrip.py` | 왕복·2회 바이트 동일·canonical eq/hash·frozen·미래 버전 거부 |
| AC-R02-02 | `tests/unit/definition/test_structural_reject.py` | 미지 연산자/kind/태그·arity·bool 상수·비-str 키·id 형식 |
| AC-R02-03 | `tests/unit/definition/test_reference_validation.py` | factor/formula/rule 참조·column∈output·params·factor_refs 일관성 |
| AC-R02-04 | `tests/unit/definition/test_formula_dag.py` | 자기참조·사이클·다이아몬드·저장 게이트 순환 무변경 |
| AC-R02-05 | `tests/unit/definition/test_strategy_roles.py` | roles whitelist·is_runnable·중복·순서 보존 |
| AC-R02-06 | `tests/unit/storage/test_definition_crud.py` | CRUD 멱등·created_at 보존·정렬·저장 게이트·공유 참조 |
| AC-R02-07 | `tests/unit/definition/test_purity_ast.py`, `tests/unit/storage/test_definition_schema.py` | AST 스캔·3테이블 멱등 |

- 통합·CRUD 테스트는 `tmp_path` 격리 DuckDB + 격리 store 리졸버로 네트워크·실데이터 없이 실행(NFR-02). 결정론은 2회 실행 동일로 판정(NFR-01).

## 7. 리스크·완화 (Open Tensions)

| # | Tension | 영향 | 완화 |
|---|---|---|---|
| OT-1 | **정규화 규약 drift** — `_jsonnorm`이 세 패키지에 갈라져 왕복이 엔티티별로 어긋남 | REQ-C2 왕복 붕괴 | 단일 공유 leaf 배치(B1-i·TR-R02-001/002), 왕복 동등 테스트 3엔티티 강제(NFR-04) |
| OT-2 | **canonical eq/hash 공백** — 필드 기반 eq로 `30`==`30.0`이 되어 해시 계약 붕괴 | set 의미·중복 판정 오류 | canonical JSON 기반 eq/hash 배선(TR-R02-003), set 크기 2 테스트(NFR-06/AC-01) |
| OT-3 | **저장 게이트 우회** — 무검증 저장으로 dangling·순환이 DB 진입 | 실행 시점 비결정 실패 | default-on 리졸버 강제(B2-i·TR-R02-006), 완화는 플래그로 한정(테스트·부분 조립), 무효 upsert 무변경 테스트(NFR-05/AC-04/06) |
| OT-4 | **params 검증 이중 원천** — R02가 min/max·교차 제약을 독자 구현해 R01과 drift | D1 검증-실행 괴리 | R01 `ParamSpec`·`validate_params` 훅 링크 재사용(B3-i·TR-R02-008), 신규 검증 로직 0 |
| OT-5 | **factor_refs–rule drift** — 선언 목록과 실제 전이 참조 불일치 | 선언-실제 괴리 | 전이 참조 집합 정확 일치 검증(TR-R02-011), 초안(rule=None)은 보류 |
| OT-6 | **패키지 상호 import 유혹** — Rule이 Formula 클래스를 직접 참조 | INV-2 위반·순환 | 별개 클래스 + 주입 리졸버 duck typing(TR-R02-001/009), AST 스캔 강제(AC-07) |
| OT-7 | **활성 참조 보호 경계 침범** — R02가 활성 상태 기반 삭제 차단을 구현 | 계층 책임 혼선 | dangling 정책은 저장 시점까지만(TR-R02-007), 활성 참조 보호는 R03 위임(소비자 포인터) |

## 8. 부록

### 8.1 마일스톤 (논리 단위)

| M | 범위 | 완료 신호 |
|---|---|---|
| M0 | 3패키지 골격 + `_jsonnorm` leaf + INV-1~3 AST 스캔 | AST green(AC-07 부분) |
| M1 | 공통 표현 계약(왕복·정규화·canonical eq/hash·schema_version) + Formula 도메인 타입·표현 트리 | AC-01/02 부분 |
| M2 | Formula 검증기(구조·참조·DAG) + required_data 전이 파생 | AC-03/04 부분 |
| M3 | Rule 도메인 타입·검증기(피연산자 3종·교차 가드·params 검증 R01 소비) | AC-02/03 |
| M4 | Strategy 도메인 타입·검증기(roles D4·universe·factor_refs 일관성·is_runnable) | AC-05 |
| M5 | 3테이블 DDL + CRUD + 저장 게이트(리졸버 주입·check_* 플래그) | AC-06/07 |

> 마일스톤은 문서상 논리 단위다(스프린트 분할은 구현 계획 시점 확정).

### 8.2 하위(R01) 인터페이스 참조표 (R02가 링크 인용)

> 시그니처 확정 원천은 `DESIGN-R01 §3`. R02는 아래를 링크 인용하며 재정의하지 않는다(§D-2). R02 자체 도메인 타입의 확정 원천은 후속 `DESIGN-R02 §3`.

| 인터페이스 | 형태(요약) | R02 소비 지점 | 확정 원천 |
|---|---|---|---|
| 팩터 `id` | snake_case 전역 유일, 안정 앵커 | Formula/Rule/Strategy 직렬화 참조·존재 검증 | DESIGN-R01 §3.8 / TR-R01-013 |
| `FactorMetadata.output` | 산출 컬럼 집합 | `column ∈ output` 검증(TR-R02-008) | DESIGN-R01 §3 |
| `FactorMetadata.required_data` | 요구 데이터 종류 튜플 | Formula required_data 전이 파생(TR-R02-014) | DESIGN-R01 §3 |
| `ParamSpec` | name/type/default/min·max/choices | params 대조 검증(D1·TR-R02-008) | DESIGN-R01 §3.2 |
| `validate_params` | 교차 제약 훅 → 위반 사유 튜플 | 정의 시점 교차 제약 검증(TR-R02-008) | DESIGN-R01 §3.3 |
| `get_factor(id, **params)` | 오버라이드 인스턴스 생성 | (정의 검증은 인스턴스화 없이 ParamSpec 대조; 실 인스턴스화는 R03) | DESIGN-R01 §3.7 |
| `list_factors(category=None)` | 등록 팩터 메타 목록 | factor 존재 검증·힌트 목록(TR-R02-009/016) | DESIGN-R01 §3.8 |
| `FactorCategory` | 카테고리 str-Enum | (참조 표시용, R02 직접 검증 대상 아님) | DESIGN-R01 §3.1 |

### 8.3 상위(R03) 소비 포인터 (본 문서 비인용 — 위임)

> §D-1: 본 문서는 상위를 인용하지 않는다. 아래는 R02 산출물을 R03가 어디서 소비하는지의 역방향 포인터만 둔다(상세는 R03 소관).

| R02 산출물 | R03 소비 지점(포인터) |
|---|---|
| 검증기 3종(비발생+엄격) | 전이 검증 재사용, 신규 검증 로직 0 — PRD-R03 §4(FR-02) |
| `is_runnable(defn)` | 활성화·백테스트 전제 조건 — PRD-R03 §4 |
| `universe.symbols`(빈 튜플=watchlist 전체) | 실행 대상 필터 해석(D5) — PRD-R03 §7 |
| 활성 전략 참조 엔티티 수정·삭제 차단 | 활성 상태 기반 보호(REQ-P4 위임) — PRD-R03 §4(FR-04a) |
| dangling 참조 실행 시점 실패 | `EvaluationError` 격리 — PRD-R03 §5 |
| params 오버라이드 독립 인스턴스화 | 평가 시 상이 params 독립 계산 — PRD-R03 §5.3 |

---

**추적성 요약**: REQ-C1~C7 · REQ-P1~P4 · REQ-V1~V5 · §5.1~§5.4 도메인 형상 · INV-1~3 · D1/D4/D5 · AC-01~07 전건이 §3 매트릭스에서 ≥1 TR로 매핑(공백 0). §4는 TR-R02-001~018로 구성되며, PRD 확정 항목(REQ-C 표현 계약 상세·§5 연산자 집합·3테이블 DDL 골격·REQ-V 검증기 요구)은 §3 매트릭스로 축약해 §4 중복 서술을 두지 않는다(§D-9 준수). R01 소비 인터페이스는 `DESIGN-R01 §3.x` 링크 인용(재정의 없음, §D-2), R02 자체 타입 시그니처 확정 원천은 후속 `DESIGN-R02 §3`. 검증기 3종·`is_runnable`은 R03가 인용하는 안정 앵커(§8.3 소비자 포인터).

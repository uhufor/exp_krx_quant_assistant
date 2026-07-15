# PRD-R02 : Declarative Definition Core

**Milestone**: Milestone 2 — No-Code Quant Strategy Platform
**Status**: Approved for implementation
**의존**: PRD-R01 (팩터 레지스트리·ParamSpec) / **소비자**: PRD-R03 (평가·실행·CLI)

---

## 1. Background & Goal

전략은 코드가 아니라 **선언적·직렬화 가능·코드 실행 없는 데이터**로 정의된다. 본 계층은 세 개의 독립 1급 엔티티의 **정의 + 영속 + 검증**을 제공하며, 평가·실행은 하지 않는다(PRD-R03 소관).

| 엔티티 | 책임 | 하지 않는 것 |
|---|---|---|
| **Formula** | Factor·상수·다른 Formula의 **산술 조합**으로 파생 지표(Custom Factor) 정의 | 조건 판단, 계산 실행 |
| **Rule** | Factor/Formula/상수의 **비교·논리 결합**으로 투자 조건 정의 | 산술 합성, 평가 실행 |
| **Strategy** | 지표 참조 + Universe + Rule의 **역할(entry/exit) 참조**를 묶은 전략 정의 | 백테스트/Daily 실행 |

**경계 규칙(확정)**: 새 값을 만드는 산술은 Formula(`PER × ROE`), 참/거짓 판단은 Rule(`PER > 10 AND RSI < 30`). Rule은 Formula를 피연산자로 참조할 수 있으나 산술식을 내장하지 않는다.

## 2. Scope

**In**: 세 엔티티의 불변 도메인 타입 + 재귀 JSON 직렬화 / DuckDB `strategies`·`rules`·`formulas` 테이블 + CRUD / 검증기 3종 + 저장 게이트 / **파라미터 오버라이드 검증(D1)** / 공유 JSON 정규화 leaf 모듈.

**Out (확정)**: Formula compute·Rule 평가·백테스트·Daily(→ R03) / 정규화·순위 함수(rank/zscore/min/max/clip — 연산자 열거 additive 확장으로 후속) / 리밸런싱 정책 필드(D5 — Portfolio Epic에서 `schema_version` 증가와 함께 additive 재도입) / Builder UI·AI 생성.

## 3. 공통 표현 계약 (세 엔티티 공통)

- **REQ-C1 (선언성)**: 정의는 순수 JSON 데이터만 담는다. 실행 코드·람다·eval 대상·산술식 **문자열**(`"PER*ROE"`)의 저장·파싱·평가 금지. 산술·논리는 태그 판별 트리 노드로만 표현한다.
- **REQ-C2 (왕복 무손실)**: `from_dict(to_dict(x)) == x`. 자유형 매핑(`metadata`, operand `params`)은 **생성 시점**에 JSON-native로 정규화(중첩 tuple→list, str 키만, JSON 스칼라만 — 위반은 생성 거부)하여 왕복을 구조적으로 폐색한다. 정규화 함수는 세 패키지가 공유하는 leaf 모듈에 둔다(패키지 상호 import 금지, INV §7).
- **REQ-C3 (결정론)**: `to_json`은 키 정렬 고정으로 동일 정의 → 바이트 동일. 검증 오류의 순서도 결정론적.
- **REQ-C4 (스키마 버전)**: 모든 정의는 `schema_version`을 가진다. 본문 버전이 코드 버전보다 크면 `from_dict` 거부(다운그레이드 차단), 같거나 낮으면 누락 필드를 기본값으로 관대 복원. 초기값은 1이다.
- **REQ-C5 (동등성·해시 통일)**: 세 엔티티 모두 **canonical JSON 기반** `__eq__`/`__hash__`. (근거: 자유 수치 상수 리프에서 필드 기반 eq는 `30`==`30.0`인데 직렬 표현은 달라 해시 계약이 깨진다. `30`과 `30.0`은 서로 다른 정의다.)
- **REQ-C6 (상수)**: 상수 피연산자 값은 `int`/`float`만. `bool`은 생성 시 거부.
- **REQ-C7 (불변성)**: 모든 도메인 타입은 frozen. 수정은 새 인스턴스 생성으로 표현.

## 4. 영속화 계약

- **REQ-P1** 테이블 3종(`strategies`/`rules`/`formulas`)은 동형이다: 단일 JSON `definition` 본문 + 비정규화 식별 컬럼(`id` PK, `name`, `version`, `schema_version`, `created_at`, `updated_at`). additive DDL(`CREATE TABLE IF NOT EXISTS` 멱등), 마이그레이션 프레임워크 없음.
- **REQ-P2** CRUD는 storage 계층 메서드(`upsert_*`/`get_*`/`list_*`/`delete_*`)로 제공한다(도메인 패키지는 storage를 모름 — 방향: storage → 도메인). `INSERT OR REPLACE` 멱등, 신규 시 `created_at=now`·갱신 시 보존, `now` 주입으로 결정론. `list_*`는 id 정렬.
- **REQ-P3 (저장 게이트)**: 모든 `upsert_*`는 저장 전 해당 검증기를 강제한다. 무효 정의(구조 위반·미존재 참조·순환·형상 위반)는 **부분 저장 없이** 검증 예외로 차단된다. 참조 존재·순환 검증은 자기 자신의 store를 리졸버로 기본 주입(default-on)하되, 플래그로 완화 가능(테스트·부분 조립용).
- **REQ-P4 (dangling 정책)**: 참조 무결성 보장 시점은 **저장 시점**이다. 참조된 엔티티의 사후 삭제를 계단식으로 정리하지 않으며, 실행 시점 재확인은 R03 평가 진입의 명확 실패로 처리한다. 단, **활성 전략이 참조 중인 엔티티의 수정·삭제 차단**은 활성 상태를 아는 Workspace 계층의 책임이다(PRD-R03 FR-04a).

## 5. 도메인별 확정 형상

### 5.1 Formula
- 표현 트리: `Expr = BinaryOp(op, left, right) | UnaryOp(op, operand) | FactorOperand | ConstantOperand | FormulaOperand`. 이항 연산자 `+`,`-`,`*`,`/`, 단항 `neg`. 가중합은 별도 연산자 없이 상수곱+덧셈. 직렬화 태그: `node`("binary"|"unary"), 리프 `kind`("factor"|"constant"|"formula"). 미지 태그·arity 위반·태그 부재/중복은 `from_dict` 거부.
- 컨테이너: `Formula(id, name, version, expression, output_column="value", metadata, schema_version)`. `output_column`은 단일(snake_case). 직렬 본문에서 `FormulaOperand.column` 누락 시 `"value"`로 관대 복원한다.
- **출력 계약**: Formula는 factor와 동형으로 "id + 출력 컬럼"으로 참조된다. 단 factor 레지스트리에 등록되지 않는 **별도 네임스페이스**(`formulas` 테이블)다. `required_data`는 저장 필드가 아니라 참조 factor들의 `required_data`를 formula 참조를 통해 **전이적으로 합집합 파생**하는 함수로 제공한다(진실 원천 = expression + 레지스트리, drift 원천 제거).
- **DAG**: Formula 간 참조는 비순환이어야 한다. 자기참조·2-사이클·장주기 전부 검증(리졸버 주입 + DFS)에서 거부, 저장 게이트에서 기본 강제.

### 5.2 Rule
- 표현 트리: `Node = Predicate(left, operator, right) | Composition(op, operands)`. 비교 `>`,`>=`,`<`,`<=`,`==`,`!=` + 교차 `crosses_above`,`crosses_below`. 논리 `AND`/`OR`(피연산자 ≥2), `NOT`(정확히 1). `==`/`!=`는 원소별 엄밀 비교다 — 부동소수점 시계열 간 동등 비교는 일반적으로 항상 False가 되므로 주 용도는 상수·정수형 지표이며, 이 의미론을 CLI 도움말·문서에 명시한다.
- 피연산자 3종: `FactorOperand(factor_id, column, params)` | `ConstantOperand(value)` | `FormulaOperand(formula_id, column)`. Rule 패키지의 operand는 Formula 패키지와 **별개 클래스**(상호 leaf 독립 — 리졸버 반환 객체는 duck typing으로만 소비).
- **교차 구조 가드**: `crosses_*`는 좌/우 중 최소 1개가 factor 또는 formula 피연산자여야 한다(`상수 crosses 상수`는 축퇴 — 구조 거부).

### 5.3 Strategy
- 컨테이너: `StrategyDefinition(id, name, version, factor_refs, universe, rule, metadata, schema_version)`.
  - `factor_refs: tuple[FactorRef(factor_id, params), ...]` 최소 1개 — 이 전략이 사용하는 지표의 선언 목록(빌더 UX·가용성 판정용). **일관성 검증 강제**: rule 슬롯이 존재하면 factor_refs의 `factor_id` 집합은 rule 슬롯이 **전이적으로 참조하는 factor 집합**(참조 Rule의 FactorOperand + 참조 Formula가 전이 참조하는 factor 포함)과 정확히 일치해야 하며, 불일치는 검증 실패다(선언-실제 drift 차단). 초안(rule=None)에서는 집합 일치 검증을 보류한다.
  - `universe: Universe(symbols: tuple[str, ...])` — 실행 대상 종목의 정적 목록. **빈 튜플 = 파이프라인 watchlist 전체**(기본). 실행 의미는 R03 §7이 소비한다(D5 — "선언만 하고 미해석" 상태 금지). 심볼은 KRX 6자리 숫자 형식이어야 한다(형식 위반은 검증 거부). 시장 전체·조건식 universe는 후속 additive.
  - **리밸런싱 필드는 없다**(D5).
- **rule 슬롯 (D4, roles 단일 형상)**: 다음 둘만 유효하다 — whitelist fail-closed, 그 외 모든 형상(인라인 Rule 본문 포함)은 거부.
  1. `None` — **초안(draft)**. 저장은 가능하나 실행 가능(runnable) 상태가 아니다.
  2. `{"roles": {"entry": [rule_id, ...], "exit": [rule_id, ...]}}` — 역할 키는 `entry`/`exit`만(미지 키 거부), `entry`는 **비어있지 않아야** 하고(무거래 전략의 구조적 차단), `exit`는 생략/빈 리스트 허용(청산 규칙 없음 = 보유 지속). 역할 내 rule id 중복은 거부, 순서는 보존.

### 5.4 파라미터 오버라이드 (D1 — 정의 계층의 책임 범위)
- `FactorRef.params`·`FactorOperand.params`(Rule/Formula 공통)는 해당 factor의 **ParamSpec(PRD-R01 FR-02)에 대해 검증**된다: 미지 파라미터 이름 거부, 타입 불일치 거부(int 자리의 float 등), min/max 범위 위반 거부. 팩터가 `validate_params` 훅(PRD-R01 FR-02a)을 노출하면 교차 제약(예: `macd` fast<slow)도 정의 시점에 함께 검증한다. 빈 매핑 = 전부 기본값.
- `column ∈ metadata.output` 검증은 params와 무관하게 항상 수행(파라미터는 출력 컬럼 집합을 바꾸지 않는다 — R01 계약).
- 동일 `factor_id`·상이 `params`의 두 피연산자는 **서로 다른 지표 참조**다(SMA(5) vs SMA(20)). 평가 시 각각 독립 인스턴스로 계산됨은 R03이 보장한다.

## 6. 검증 요구사항 (검증기 3종)

- **REQ-V1** 각 엔티티에 비발생(non-raising) 검증기 + 엄격 변형(첫 오류 예외)을 제공한다. 결과는 `ok + errors(순서 결정론)`.
- **REQ-V2 공통 검증**: 구조 well-formedness(연산자·arity·kind·태그) / id·name·output_column 형식(snake_case·비공백) / 직렬화 왕복 동일성 / 코드 없음 재확인.
- **REQ-V3 참조 검증**: factor id 존재 + column ∈ output + **params 검증(D1: ParamSpec 대조 + `validate_params` 훅 호출, PRD-R01 FR-02a)** — 레지스트리 기반, 플래그로 완화 가능. formula 참조 존재 + `FormulaOperand.column == 참조 Formula.output_column` + 순환 거부 — 주입 리졸버 기반. Strategy의 rule id 존재 + **factor_refs 일관성(§5.3)** — 주입 리졸버 기반.
- **REQ-V4 오류 메시지**: 한국어 + 행동 가능한 힌트(누락 id와 "사용 가능: …" 목록, 잘못된 컬럼과 유효 컬럼 목록, 범위 위반 파라미터와 허용 범위).
- **REQ-V5 runnable 판정**: `is_runnable(defn)` — rule 슬롯이 roles 형상이고 entry ≥ 1이면 True. R03의 활성화·백테스트 전제 조건으로 소비된다.

## 7. 아키텍처 불변식 (AST import 스캔으로 기계 강제)

| INV | 내용 |
|---|---|
| **INV-1** | 세 도메인 패키지는 백테스트 엔진·실행 계층·storage를 런타임 import하지 않는다. 허용 참조: 팩터 레지스트리(R01) + 공유 JSON 정규화 leaf. |
| **INV-2** | `rule` ↔ `formula` ↔ `strategy` 패키지는 **서로를 import하지 않는다**(상호 leaf 독립·순환 방지). 타 엔티티 객체는 주입 리졸버가 반환한 것을 duck typing으로만 사용. |
| **INV-3** | 타입 주석 목적의 import는 `TYPE_CHECKING` 하에서만 허용(스캔 제외 대상). |

## 8. Acceptance Criteria (pytest 기계 검증)

- **AC-01 왕복·결정론**: 세 엔티티 대표 정의(중첩 트리 포함)의 `from_dict(to_dict)==원본`, 2회 직렬화 바이트 동일, canonical eq/hash(`30` vs `30.0` 구분 — set 크기 2), frozen 위반 예외, 미래 `schema_version` 거부.
- **AC-02 구조 거부**: 미지 연산자/kind/태그, arity 위반(AND 1항·NOT 2항·Binary left 누락), bool 상수, 비-str 매핑 키, 비-snake_case id — 전부 생성 또는 `from_dict`/검증 거부.
- **AC-03 참조 검증**: 미존재 factor/formula/rule id 거부(+힌트), `column ∉ output` 거부(+유효 컬럼 힌트), formula 컬럼 불일치 거부, `상수 crosses 상수` 거부, **params: 미지 이름·타입 불일치·범위 위반·교차 제약(validate_params) 위반 거부 / 유효 오버라이드 통과**, factor_refs–rule 전이 참조 집합 불일치 거부/일치 통과.
- **AC-04 DAG**: 자기참조·2-사이클·3-노드 장주기 거부(순환 경로 힌트), 다이아몬드 DAG 통과, 저장 게이트에서 순환 formula upsert 시 예외 + store 무변경.
- **AC-05 rule 슬롯**: roles(entry 1+) 통과, `None` 통과(단 `is_runnable=False`), 빈 entry·미지 역할 키·`rule_ids` 형상·인라인 본문 전부 거부, 역할 내 중복 rule id 거부, 순서 왕복 보존.
- **AC-06 CRUD**: 저장→조회 동일, 멱등 upsert(count 1·`created_at` 보존·`updated_at` 갱신), 목록 id 정렬, 삭제 후 None, 무효 정의 upsert 예외(부분 저장 없음), 하나의 Rule/Formula를 복수 Strategy/Rule/Formula가 참조 가능.
- **AC-07 순수성**: INV-1~3 AST 스캔 green. 테이블 3종 존재 + 멱등 재연결.

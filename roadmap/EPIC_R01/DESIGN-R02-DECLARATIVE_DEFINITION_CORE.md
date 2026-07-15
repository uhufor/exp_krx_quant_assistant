# DESIGN-R02 : Declarative Definition Core

**대응 PRD**: `PRD-R02-DECLARATIVE_DEFINITION_CORE.md` / **짝 TRD**: `TRD-R02-DECLARATIVE_DEFINITION_CORE.md`
**계층**: R02 (중간, 순수 — 평가·실행·백테스트·storage 무의존) / **의존**: R01(팩터 레지스트리·ParamSpec) / **소비자**: R03(평가·실행·CLI)
**Status**: Draft for review
**전제**: 본 문서는 main 브랜치 시점에서 선언형 정의 코어를 **처음 구현한다**고 가정한다. 모든 설계 서술은 PRD-R02 + `README.md`(§4 D1~D5 · §5 공통 불변 원칙 7) + 짝 TRD-R02(B1/B2/B3 · TR-R02-001~018) + 하위 계층 확정 인터페이스(`DESIGN-R01 §3`) 역추적으로만 정당화한다.

> **인터페이스 인용 규약(§D-2)**: R02가 소비하는 R01 시그니처(`ParamSpec`·`validate_params`·`FactorMetadata`·`get_factor`·`list_factors`·`FactorCategory`)의 **확정 원천은 `DESIGN-R01 §3`**이며 본 문서는 이를 **재정의하지 않고 링크 인용**한다(요약 1줄까지). R02 자체 도메인 타입의 시그니처 확정 원천은 **본 문서 §3**이다(**소비자: PRD-R03 §4/§5** — 상위 계층이 인용하는 안정 앵커).
>
> **하위 문서 규율(§D-1)**: 본 문서는 상위(R03)를 인용하지 않는다. 상위 소비 지점은 "소비자: PRD-R03 §y" 포인터만 둔다.

---

## 1. 개요

### 1.1 목적

전략을 코드가 아니라 **선언적·직렬화 가능·코드 실행 없는 데이터**로 정의하는 세 개의 1급 엔티티(Formula·Rule·Strategy)의 **정의 + 영속 + 검증** 계층의 구현 형상(모듈 구조·타입 시그니처·직렬화 규약·DDL·검증 알고리즘·ADR)을 확정한다. 본 계층은 정의를 데이터에 적용해 시계열을 산출하는 **평가·실행을 하지 않는다**(R03 소관).

### 1.2 PRD/TRD와의 관계

- **PRD-R02**: 요구사항 원천(REQ-C1~C7·REQ-P1~P4·REQ-V1~V5·§5 도메인 형상·INV-1~3·AC-01~07). 재논쟁 대상 아님.
- **TRD-R02**: 배선·강제 방식 확정(TR-R02-001~018, 결정 축 B1 `_jsonnorm` 단일 공유 leaf / B2 저장 게이트 self-store 리졸버 default-on + `check_*` 완화 / B3 params 검증 = R01 훅 재사용).
- **본 DESIGN-R02**: TR의 배선 결정을 **실제 타입 시그니처·DDL·알고리즘 의사코드·ADR**로 구체화한다. PRD가 이미 확정한 연산자 집합·3테이블 DDL 골격·검증기 요구는 **재정의 없이 구현 형상으로 번역**한다.

### 1.3 자기완결성·오염 가드 선언

본 문서의 모든 설계 서술은 PRD-R02 + TRD-R02 + README §4/§5 + `DESIGN-R01 §3` 역추적으로만 정당화된다. main 시점 최초 구현("앞으로 만들 것")의 관점으로만 서술하며, 이 네 원천 밖의 문서·산출물을 설계 근거로 두지 않는다.

### 1.4 R03가 인용하는 확정 앵커(선결 고지)

다음 §3 시그니처는 상위 계층(R03)이 **재정의 없이 인용**하는 안정 앵커다: 검증기 3종 `validate_formula`/`validate_rule`/`validate_definition`(+엄격 변형), `is_runnable`, `derive_required_data`, 도메인 타입 `Formula`/`Rule`/`StrategyDefinition`의 `from_dict`/`to_dict`, 리졸버 타입 계약(`FormulaResolver`/`RuleResolver`). 배선 선택이 이 앵커를 흔들지 않도록 §3에서 고정한다.

---

## 2. 모듈 구조 및 의존 방향

### 2.1 패키지 트리

```
quant_krx/
├── _jsonnorm.py                 # 공유 정규화 leaf (B1-i, TR-R02-001/002)
│                                #   JSONScalar · normalize_mapping · normalize_value
│                                #   · canonical_json · CanonicalEq 믹스인
│                                #   도메인 패키지가 아님 — R01 레지스트리와 동급 허용 leaf
├── formula/                     # Formula 정의·검증 (INV-1: 실행·저장·백테스트 미import)
│   ├── __init__.py              #   공개 API 재노출(Formula, BinaryOp, …, validate_formula,
│   │                            #   validate_formula_strict, derive_required_data)
│   ├── definition.py            #   BinaryOp·UnaryOp·FactorOperand·ConstantOperand
│   │                            #   ·FormulaOperand·Formula + from_dict/to_dict (§3.3)
│   ├── validation.py            #   validate_formula(+strict)·derive_required_data (§3.4)
│   └── errors.py                #   DefinitionError 계층 재노출(§3.1)
├── rule/                        # Rule 정의·검증
│   ├── __init__.py              #   공개 API 재노출(Rule, Predicate, Composition, 피연산자 3종,
│   │                            #   validate_rule, validate_rule_strict)
│   ├── definition.py            #   Predicate·Composition·FactorOperand·ConstantOperand
│   │                            #   ·FormulaOperand·Rule + from_dict/to_dict (§3.5)
│   │                            #   ※ FormulaOperand는 formula 패키지와 별개 클래스(formula_id만 보유)
│   └── validation.py            #   validate_rule(+strict) (§3.6)
├── strategy/                    # Strategy 정의·검증
│   ├── __init__.py              #   공개 API 재노출(StrategyDefinition, FactorRef, Universe,
│   │                            #   RuleBinding, validate_definition, validate_definition_strict,
│   │                            #   is_runnable)
│   ├── definition.py            #   FactorRef·Universe·RuleBinding·StrategyDefinition
│   │                            #   + from_dict/to_dict (§3.7)
│   └── validation.py            #   validate_definition(+strict)·is_runnable (§3.8)
└── (storage/db.py)              # CRUD·저장 게이트 (storage 계층 — 도메인 밖, §7)
                                 #   upsert_*/get_*/list_*/delete_* × 3 + check_* 플래그
```

- 세 도메인 패키지는 각각 `definition`(도메인 타입 + `from_dict`/`to_dict`) + `validation`(검증기) 모듈로 동형 배치한다(TR-R02-001).
- 공통 오류 계층(`DefinitionError`, §3.1)은 세 패키지가 공유해야 하므로 `_jsonnorm`과 동급의 leaf(또는 `formula/errors.py`에 정의 후 재노출)에 둔다. 본 설계는 오류 계층을 `_jsonnorm`와 함께 **공유 leaf**로 배치한다(패키지 상호 import 없이 세 패키지가 참조 가능).

### 2.2 의존 방향과 INV-1~3

```
        (호출자: R03 WorkspaceService / 평가 엔진 / storage 게이트)
                        │  정의 객체 · 리졸버(콜러블) 주입
                        ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ formula/ │   │  rule/   │   │ strategy/│   ← 상호 미import(INV-2)
   └────┬─────┘   └────┬─────┘   └────┬─────┘
        └──────┬───────┴───────┬──────┘
               ▼               ▼
        quant_krx.factors  quant_krx._jsonnorm   (허용 leaf 참조만 — INV-1)
        (R01 레지스트리)    (정규화·canonical·오류 계층)
```

- **INV-1 강제(NFR-03)**: 세 도메인 패키지 하위 모든 모듈은 백테스트 엔진(`vectorbt`)·평가/실행 계층(`quant_krx.workspace`·`quant_krx.jobs`·`quant_krx.quant`)·storage(`quant_krx.storage`, DuckDB)를 **런타임 import하지 않는다**. 허용 참조는 R01 팩터 레지스트리(`quant_krx.factors`)와 `_jsonnorm` leaf뿐이다.
- **INV-2 강제**: `formula`·`rule`·`strategy` 패키지는 **서로를 import하지 않는다**. 타 엔티티 객체는 **주입 리졸버가 반환한 것을 duck typing으로만** 소비한다(예: `rule.FormulaOperand`는 `formula` 패키지를 참조하지 않고 `formula_id` 문자열만 보유; 리졸버가 돌려준 formula-like 객체는 태그 속성 `.node`/`.kind`로만 순회, §3.9).
- **INV-3 강제**: 타입 주석 목적 import는 `if TYPE_CHECKING:` 블록 하에서만 허용(런타임 미로딩 → 스캔 제외).
- **AST 스캔 규칙(AC-R02-07)**: 테스트가 세 패키지 import 그래프를 재귀 순회하여 (a) 금지 모듈 `{vectorbt, quant_krx.workspace, quant_krx.jobs, quant_krx.quant, quant_krx.storage}` 참조 0건, (b) 패키지 상호 참조(`formula`↔`rule`↔`strategy`) 0건을 강제한다. `if TYPE_CHECKING:` guard 내부 import는 별도 판정으로 예외 처리한다.

---

## 3. 도메인 타입 시그니처 ★확정 원천★

> 본 절의 시그니처는 **R03이 인용하는 계약**이며 본 문서가 확정 원천이다. 타입은 `from __future__ import annotations` 전제. R01 인터페이스(`ParamSpec`·`validate_params`·`FactorMetadata`·`get_factor`·`list_factors`)는 `DESIGN-R01 §3`이 원천이며 여기서 재정의하지 않는다.

### 3.1 공통 형상 — `ValidationResult` · 오류 계층 (REQ-V1, REQ-V4)

```python
@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()          # 한국어 메시지 + 행동 가능 힌트, 순서 결정론(§6.4)

    def __bool__(self) -> bool:            # if result: 관용 지원
        return self.ok
```

```python
class DefinitionError(Exception): ...              # 기반(공유 leaf)
class MalformedDefinitionError(DefinitionError): ...   # from_dict 구조 거부(미지 태그/kind·arity·bool 상수·비-str 키)
class SchemaVersionError(DefinitionError): ...     # 미래 schema_version 거부(REQ-C4)
class DefinitionValidationError(DefinitionError): ...   # 엄격 검증기 첫 오류 예외(REQ-V1)
```

- **비발생/엄격 이원화(REQ-V1)**: 각 엔티티는 **비발생 검증기**(`validate_*` → `ValidationResult`, 전 오류 수집)와 **엄격 변형**(`validate_*_strict` → `None`, 첫 오류에서 `DefinitionValidationError` raise)을 제공한다. 저장 게이트(§7)는 엄격 변형을 소비한다.
- **구조 거부 vs 검증 실패 분리**: 태그·arity·kind·상수 타입 등 **직렬 구조 위반**은 `from_dict`/생성 시점에 `MalformedDefinitionError`(즉시 raise) — 정상 도메인 객체가 아예 만들어지지 않는다. **참조·형상 정합** 위반(미존재 id·column 불일치·순환·factor_refs 불일치)은 검증기가 `ValidationResult.errors`로 수집(또는 엄격 변형 raise)한다.
- 모든 메시지는 한국어 + 행동 가능 힌트(§6.4, REQ-V4).

### 3.2 공유 정규화 leaf — `_jsonnorm` (REQ-C2/C5/C6, B1-i)

```python
JSONScalar = int | float | str | bool | None      # 자유형 매핑이 허용하는 스칼라(bool 포함)

def normalize_mapping(m: Mapping[str, Any]) -> dict[str, JSONScalar | list | dict]:
    #   자유형 매핑(metadata, operand params)을 JSON-native로 정규화.
    #   규약: str 키만 허용(위반 → MalformedDefinitionError) · 중첩 tuple → list 재귀 변환
    #        · 값은 JSONScalar 또는 정규화된 list/dict만(그 외 타입 → 거부).
    #   ※ 이 매핑 값의 bool은 허용(JSON 스칼라). 상수 피연산자 값의 bool 거부는 §3.3에서 별도 판정.
    ...

def normalize_value(v: Any) -> JSONScalar | list | dict:
    #   단일 값 재귀 정규화(tuple → list, 스칼라 검증). 위반 → MalformedDefinitionError.
    ...

def canonical_json(obj: Mapping[str, Any] | Sequence[Any]) -> str:
    #   결정론 canonical 직렬화. json.dumps(obj, sort_keys=True, ensure_ascii=False,
    #   separators=(",", ":")) 상당. int/float 타입 보존(30 → "30", 30.0 → "30.0", §6.1).
    ...

class CanonicalEq:
    #   믹스인: __eq__/__hash__ 를 canonical_json(self.to_dict()) 기반으로 제공(REQ-C5).
    #   전 도메인 타입은 @dataclass(frozen=True, eq=False) + CanonicalEq 로 배치(§6.1).
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...
```

- `_jsonnorm`은 도메인 패키지가 아니므로 세 패키지가 공유해도 INV-2를 위반하지 않는다(R01 레지스트리와 동급 허용 leaf, B1-i).

### 3.3 Formula 패키지 도메인 타입 (§5.1, REQ-C1/C6/C7)

```python
# 리프 피연산자 3종 (kind 판별 태그)
@dataclass(frozen=True, eq=False)
class FactorOperand(CanonicalEq):
    factor_id: str
    column: str
    params: Mapping[str, JSONScalar] = field(default_factory=dict)   # __post_init__에서 normalize_mapping
    kind: ClassVar[str] = "factor"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FactorOperand: ...

@dataclass(frozen=True, eq=False)
class ConstantOperand(CanonicalEq):
    value: int | float                       # bool 거부·비유한(nan/inf) 거부(§6.1)
    kind: ClassVar[str] = "constant"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ConstantOperand: ...

@dataclass(frozen=True, eq=False)
class FormulaOperand(CanonicalEq):
    formula_id: str
    column: str = "value"                    # 직렬 본문 누락 시 "value" 관대 복원(REQ-C4)
    kind: ClassVar[str] = "formula"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FormulaOperand: ...

# 내부 노드 (node 판별 태그)
@dataclass(frozen=True, eq=False)
class BinaryOp(CanonicalEq):
    op: str                                  # "+" | "-" | "*" | "/"
    left: Expr
    right: Expr
    node: ClassVar[str] = "binary"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> BinaryOp: ...

@dataclass(frozen=True, eq=False)
class UnaryOp(CanonicalEq):
    op: str                                  # "neg"
    operand: Expr
    node: ClassVar[str] = "unary"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> UnaryOp: ...

Expr = BinaryOp | UnaryOp | FactorOperand | ConstantOperand | FormulaOperand

def expr_from_dict(d: Mapping[str, Any]) -> Expr:
    #   태그 판별 디스패치: "node"("binary"|"unary") 우선, 없으면 "kind"("factor"|"constant"|"formula").
    #   미지 태그·태그 부재/중복 → MalformedDefinitionError(§6.3).
    ...

@dataclass(frozen=True, eq=False)
class Formula(CanonicalEq):
    id: str
    name: str
    version: str
    expression: Expr
    output_column: str = "value"             # 단일, snake_case
    metadata: Mapping[str, JSONScalar] = field(default_factory=dict)
    schema_version: int = 1
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Formula: ...    # schema_version 관대/엄격(§5.3)
```

- 이항 연산자 `+`/`-`/`*`/`/`, 단항 `neg`. 가중합은 별도 연산자 없이 상수곱+덧셈으로 표현(§5.1). 미지 연산자·arity 위반(`BinaryOp.left` 누락 등)·태그 부재/중복은 `from_dict` 거부(AC-R02-02).
- `output_column`은 단일(snake_case). `FormulaOperand.column` 누락 시 `"value"` 관대 복원.
- `required_data`는 **저장 필드가 아니다**(§3.4 `derive_required_data`로 파생).

### 3.4 Formula 검증기 · required_data 파생 (REQ-V1~V3, §5.1 DAG)

```python
FormulaResolver = Callable[[str], FormulaLike | None]   # formula_id → 리졸브된 formula(또는 None), §3.9

def validate_formula(
    formula: Formula,
    *,
    resolve_formula: FormulaResolver | None = None,
) -> ValidationResult: ...
#   비발생. 검증 항목(전 오류 수집, 순서 결정론):
#   (1) 구조 well-formedness(연산자·arity·kind·태그) — 이미 from_dict가 강제하므로 재확인 성격.
#   (2) id/name/output_column 형식(snake_case·비공백).
#   (3) factor 참조: FactorOperand.factor_id 레지스트리 존재 + column ∈ FactorMetadata.output
#       + params 검증(§3.8 params 규약과 동일 — DESIGN-R01 §3.2 ParamSpec 대조 + §3.3 validate_params 훅).
#   (4) formula 참조(resolve_formula 주입 시): FormulaOperand.formula_id 존재
#       + FormulaOperand.column == 참조 Formula.output_column.
#   (5) DAG 순환 거부(resolve_formula 주입 시): 자기참조·2-사이클·장주기(§6.2).
#   ※ resolve_formula=None → (4)(5) 참조·순환 검증 생략(부분 조립·단위 테스트 완화, REQ-P3).
#      factor 레지스트리 기반 (3)은 항상 수행(레지스트리는 데이터 무관 상시 존재 — DESIGN-R01 §3.8 FR-11).

def validate_formula_strict(
    formula: Formula, *, resolve_formula: FormulaResolver | None = None,
) -> None: ...          # 첫 오류에서 DefinitionValidationError raise. 저장 게이트가 소비.

def derive_required_data(
    formula: Formula,
    resolve_formula: FormulaResolver,
) -> tuple[str, ...]: ...
#   expression 순회: FactorOperand → 레지스트리에서 FactorMetadata.required_data(DESIGN-R01 §3) 조회,
#   FormulaOperand → resolve_formula로 참조 Formula 확장 후 재귀. 전체 합집합을 정렬 튜플로 반환(결정론).
#   진실 원천 = expression + 레지스트리(저장 필드 아님 → drift 원천 제거).
```

### 3.5 Rule 패키지 도메인 타입 (§5.2, REQ-C1/C6/C7)

```python
# 피연산자 3종 — formula 패키지와 별개 클래스(INV-2). rule.FormulaOperand는 formula_id 문자열만 보유.
@dataclass(frozen=True, eq=False)
class FactorOperand(CanonicalEq):
    factor_id: str
    column: str
    params: Mapping[str, JSONScalar] = field(default_factory=dict)
    kind: ClassVar[str] = "factor"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FactorOperand: ...

@dataclass(frozen=True, eq=False)
class ConstantOperand(CanonicalEq):
    value: int | float                       # bool·비유한 거부
    kind: ClassVar[str] = "constant"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ConstantOperand: ...

@dataclass(frozen=True, eq=False)
class FormulaOperand(CanonicalEq):
    formula_id: str
    column: str = "value"
    kind: ClassVar[str] = "formula"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FormulaOperand: ...

Operand = FactorOperand | ConstantOperand | FormulaOperand

@dataclass(frozen=True, eq=False)
class Predicate(CanonicalEq):
    left: Operand
    operator: str        # 비교 ">"|">="|"<"|"<="|"=="|"!=" + 교차 "crosses_above"|"crosses_below"
    right: Operand
    node: ClassVar[str] = "predicate"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Predicate: ...

@dataclass(frozen=True, eq=False)
class Composition(CanonicalEq):
    op: str              # "AND" | "OR"(피연산자 ≥2) | "NOT"(정확히 1)
    operands: tuple[Node, ...]
    node: ClassVar[str] = "composition"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Composition: ...

Node = Predicate | Composition

def node_from_dict(d: Mapping[str, Any]) -> Node:
    #   "node"("predicate"|"composition") 태그 디스패치. 미지 태그·arity 위반 → MalformedDefinitionError.
    ...

@dataclass(frozen=True, eq=False)
class Rule(CanonicalEq):
    id: str
    name: str
    version: str
    root: Node
    metadata: Mapping[str, JSONScalar] = field(default_factory=dict)
    schema_version: int = 1
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Rule: ...
```

- 논리 `AND`/`OR`(피연산자 ≥2), `NOT`(정확히 1). arity 위반은 `from_dict`/생성 거부(AC-R02-02).
- `==`/`!=`는 **원소별 엄밀 비교**(부동소수점 시계열 간에는 일반적으로 항상 False → 주 용도 상수·정수형 지표). 정의 계층은 이 의미론을 **문서·CLI 도움말에 명시**하는 책임까지(평가 동작은 R03, §6.5).

### 3.6 Rule 검증기 (REQ-V1~V3, §5.2 교차 가드)

```python
def validate_rule(
    rule: Rule,
    *,
    resolve_formula: FormulaResolver | None = None,
) -> ValidationResult: ...
#   비발생. 검증 항목:
#   (1) 구조 well-formedness(연산자·arity·kind·태그 재확인).
#   (2) id/name 형식.
#   (3) 교차 연산자 구조 가드: crosses_above/crosses_below 는 좌/우 중 최소 1개가
#       factor 또는 formula 피연산자(상수 crosses 상수 → 구조 거부, §6.5).
#   (4) factor 참조: FactorOperand.factor_id 존재 + column ∈ output + params 검증(§3.8).
#   (5) formula 참조(resolve_formula 주입 시): FormulaOperand.formula_id 존재
#       + column == 참조 Formula.output_column. 리졸버 반환 객체는 duck typing으로만 소비(INV-2).
#   ※ resolve_formula=None → (5) 생략(완화).

def validate_rule_strict(
    rule: Rule, *, resolve_formula: FormulaResolver | None = None,
) -> None: ...          # 첫 오류 DefinitionValidationError. 저장 게이트 소비.
```

### 3.7 Strategy 패키지 도메인 타입 (§5.3, D4/D5)

```python
@dataclass(frozen=True, eq=False)
class FactorRef(CanonicalEq):
    factor_id: str
    params: Mapping[str, JSONScalar] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FactorRef: ...

@dataclass(frozen=True, eq=False)
class Universe(CanonicalEq):
    symbols: tuple[str, ...] = ()            # KRX 6자리 숫자 형식. 빈 튜플 = watchlist 전체(D5)
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Universe: ...

@dataclass(frozen=True, eq=False)
class RuleBinding(CanonicalEq):
    #   rule 슬롯의 roles 단일 형상(D4)을 타입으로 고정. to_dict → {"roles": {"entry":[...], "exit":[...]}}.
    entry: tuple[str, ...]                    # rule id, 비어있지 않아야 함(무거래 전략 구조적 차단)
    exit: tuple[str, ...] = ()                # 생략/빈 허용(청산 규칙 없음 = 보유 지속)
    def to_dict(self) -> dict[str, Any]: ...  # {"roles": {"entry": list(entry), "exit": list(exit)}}
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> RuleBinding: ...
    #   whitelist fail-closed: {"roles": {...}} 외 형상(인라인 본문·{"rule_ids":[...]}·미지 키) → MalformedDefinitionError.
    #   역할 키는 entry/exit만. entry 빈 리스트 거부. 역할 내 중복 rule id 거부. 순서 보존.

@dataclass(frozen=True, eq=False)
class StrategyDefinition(CanonicalEq):
    id: str
    name: str
    version: str
    factor_refs: tuple[FactorRef, ...]       # 최소 1개(빌더 UX·가용성 판정용)
    universe: Universe
    rule: RuleBinding | None = None          # None(초안) 또는 RuleBinding(roles). 리밸런싱 필드 부재(D5)
    metadata: Mapping[str, JSONScalar] = field(default_factory=dict)
    schema_version: int = 1
    def to_dict(self) -> dict[str, Any]: ...  # rule=None → "rule": null, 아니면 RuleBinding.to_dict()
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> StrategyDefinition: ...
    #   rule 슬롯 누락/null → None(초안 관대 복원). 그 외는 RuleBinding.from_dict로 whitelist 강제.
```

- **리밸런싱 필드는 정의 스키마에 두지 않는다**(D5 — "정의는 되지만 해석되지 않는" 필드 금지). 후속 Portfolio Epic에서 `schema_version` 증가와 함께 additive 도입.

### 3.8 Strategy 검증기 · runnable 판정 (REQ-V1~V5, §5.3/§5.4, D1/D4/D5)

```python
RuleResolver = Callable[[str], RuleLike | None]        # rule_id → 리졸브된 rule(또는 None), §3.9

def validate_definition(
    defn: StrategyDefinition,
    *,
    resolve_rule: RuleResolver | None = None,
    resolve_formula: FormulaResolver | None = None,
) -> ValidationResult: ...
#   비발생. 검증 항목:
#   (1) id/name 형식 · factor_refs 최소 1개 · universe 심볼 KRX 6자리 형식(위반 거부).
#   (2) FactorRef.params 검증(§5.4 params 규약: ParamSpec 대조 + validate_params 훅 + column 무관).
#   (3) rule 슬롯 whitelist(D4)는 RuleBinding.from_dict가 이미 강제(구조 거부는 생성 시점).
#   (4) rule 존재(resolve_rule 주입 시): entry/exit 의 rule_id 가 rules store에 존재.
#   (5) factor_refs 일관성(rule 슬롯 존재 시): factor_refs.factor_id 집합 ==
#       rule 슬롯이 전이 참조하는 factor 집합(참조 Rule의 FactorOperand ∪ 참조 Formula 전이 factor).
#       정확 일치(초과·부족 양방향 거부). 초안(rule=None)은 이 검증 보류(§6.4). resolve_rule/resolve_formula 필요.
#   ※ resolve_rule=None → (4)(5) 생략(완화). params/universe/형식 검증은 항상 수행.

def validate_definition_strict(
    defn: StrategyDefinition, *,
    resolve_rule: RuleResolver | None = None,
    resolve_formula: FormulaResolver | None = None,
) -> None: ...          # 첫 오류 DefinitionValidationError. 저장 게이트 소비.

def is_runnable(defn: StrategyDefinition) -> bool: ...
#   반환: defn.rule is not None and len(defn.rule.entry) >= 1.
#   RuleBinding이 entry 비어있지 않음을 생성 시점에 강제하므로(§3.7), 실질 판정은 "rule 슬롯이 roles 형상인가".
#   "정의 검증은 통과하나 실행 시점 거부되는" 상태를 구조적으로 금지(D4).
#   소비자: PRD-R03 §4(활성화·백테스트 전제 조건).
```

### 3.9 리졸버 타입 계약 (INV-2 duck typing)

- `FormulaResolver = Callable[[str], FormulaLike | None]`: `formula_id`로 리졸브. 반환 객체는 **duck-typed** `FormulaLike` — 최소 표면 `output_column: str`, `expression`(태그 속성 `.node`/`.kind`로 순회 가능한 표현 트리). 미존재 시 `None`.
- `RuleResolver = Callable[[str], RuleLike | None]`: `rule_id`로 리졸브. 반환 객체는 duck-typed `RuleLike` — 최소 표면 `root`(순회 가능한 Node 트리). 미존재 시 `None`.
- **INV-2 준수**: `rule`/`strategy` 검증기는 `formula`/`rule` 패키지를 import하지 않고, 리졸버가 돌려준 객체를 **태그 속성으로만** 순회한다(`.node`, `.kind`, `.left`/`.right`, `.operand`, `.operands`, `.factor_id`, `.formula_id`). 태그 문자열은 코드 의존이 아닌 **직렬화 어휘**이므로 duck typing으로 성립한다.
- **주입 원천**: 리졸버는 저장 게이트(§7)가 자기 store 기반으로 default-on 주입한다(B2-i). `None` 전달 = 해당 참조 검증 완화(부분 조립·단위 테스트).

---

## 4. 데이터 구조 결정 (옵션 비교·ADR 연계)

| 결정 축 | 옵션 | 채택 | 근거 |
|---|---|---|---|
| 표현 형식 | 재귀 태그 트리 vs. 수식 **문자열**(`"PER*ROE"`) vs. 후위식 | **재귀 태그 트리** (ADR-R02-01) | REQ-C1 선언성(코드·문자열식 금지) 정면 충족. 문자열식은 파싱=eval 경로 유발로 배제 |
| 노드 판별 | `node`/`kind` 태그 필드 vs. 클래스명 직결 vs. 위치 규약 | **태그 판별(`node`/`kind`)** (ADR-R02-02) | JSON 왕복 시 클래스 복원 결정론 + 미지 태그 거부로 폐집합 강제(REQ-C2/AC-R02-02) |
| eq/hash 수단 | **canonical JSON** vs. 필드 기반 dataclass eq | **canonical JSON** (ADR-R02-05) | `30`==`30.0` 필드 eq는 해시 계약 붕괴(REQ-C5). canonical은 `30`/`30.0`을 다른 정의로 취급(set 크기 2) |
| rule 슬롯 표현 | `RuleBinding` frozen 타입 vs. raw dict `{"roles":…}` | **`RuleBinding` 타입** (ADR-R02-06) | D4 whitelist fail-closed를 타입 생성 시점에 강제 + `is_runnable`을 필드 접근으로 단순화 |
| 순환 검출 | **DFS gray/black** vs. Kahn 위상정렬 vs. 재귀 깊이 제한 | **DFS gray/black** (ADR-R02-03) | 순환 경로 힌트(REQ-V4) 자연 산출 + 리졸버 지연 확장과 정합 |
| 저장 표현 | 3테이블 **동형**(JSON definition + 비정규 컬럼) vs. 엔티티별 정규화 스키마 | **3테이블 동형** (ADR-R02-04) | REQ-P1 동형 계약 + additive 진화(신규 필드=JSON 본문) + 마이그레이션 프레임워크 불요 |
| 컨테이너 타입 | frozen dataclass(+`eq=False`) vs. `NamedTuple` vs. dict | **frozen dataclass** (ADR-R02-01) | REQ-C7 불변성 + canonical eq/hash 믹스인 주입 여지 + 기본값/`__post_init__` 정규화 |

---

## 5. 직렬화 규약 + DuckDB DDL

### 5.1 additive 진화 원칙

baseline DuckDB 8테이블(`symbols`, `ohlcv_daily`, `data_fetch_runs`, `strategy_runs`, `signals`, `reports`, `notification_outbox`, `run_events`)과 R01 2테이블(`fundamental_daily`, `financial_statements`)은 **무변경**이다. R02는 아래 **3테이블만 additive 추가**한다(원칙 6). 모든 DDL은 `CREATE TABLE IF NOT EXISTS`로 멱등(AC-R02-07 재연결 무오류).

### 5.2 3테이블 동형 DDL (REQ-P1)

`strategies`·`rules`·`formulas`는 동형이다: 단일 JSON `definition` 본문(**진실 원천**) + 비정규화 식별 컬럼(질의 편의, 진실 원천 아님).

```sql
CREATE TABLE IF NOT EXISTS formulas (
    id             VARCHAR   NOT NULL,
    name           VARCHAR,          -- 비정규(definition.name 사본)
    version        VARCHAR,          -- 비정규
    schema_version INTEGER,          -- 비정규
    definition     JSON      NOT NULL,   -- 진실 원천(to_dict 직렬화)
    created_at     TIMESTAMP,        -- 신규 시 now, 갱신 시 보존
    updated_at     TIMESTAMP,        -- 갱신 시 now
    PRIMARY KEY (id)
);
-- rules · strategies 는 테이블명만 다르고 컬럼 형상 동일(동형).
CREATE TABLE IF NOT EXISTS rules      ( /* 위와 동일 컬럼 */ id VARCHAR NOT NULL, ..., PRIMARY KEY (id) );
CREATE TABLE IF NOT EXISTS strategies ( /* 위와 동일 컬럼 */ id VARCHAR NOT NULL, ..., PRIMARY KEY (id) );
```

- `name`/`version`/`schema_version`은 `definition` JSON에서 비정규화한 조회용 컬럼이다. 검증·평가·왕복 복원은 **항상 `definition`**을 원천으로 한다.
- **additive 진화**: 신규 연산자=열거 추가, 신규 피연산자=`kind` 추가, 신규 필드=JSON 본문 + `schema_version` 증가, 신규 저장=테이블 추가. 기존 3테이블 DDL·공개 정의 형상은 변경하지 않는다(TR-R02-017).

### 5.3 직렬화 규약 — 왕복·결정론·타입 보존·schema_version

- **결정론(REQ-C3)**: `to_json = canonical_json(to_dict())` — 키 정렬 고정(`sort_keys=True`), 동일 정의 → **바이트 동일**. 2회 직렬화 바이트 동일(AC-R02-01).
- **int/float 타입 보존(REQ-C5, 핵심)**: `to_dict`는 Python `int`/`float`를 native로 방출하고, canonical 직렬화가 타입을 보존한다 — `30 → "30"`, `30.0 → "30.0"`. `from_dict`(`json.loads`) 복원 시 `"30" → int 30`, `"30.0" → float 30.0`으로 타입 왕복한다. 따라서 `ConstantOperand(30)`과 `ConstantOperand(30.0)`은 **서로 다른 정의**이며 `{Formula(…30…), Formula(…30.0…)}`의 set 크기 = 2(§6.1).
- **schema_version 관대/엄격 복원(REQ-C4)**: 각 패키지는 현재 코드 `SCHEMA_VERSION`(초기값 1)을 보유. `from_dict`는 본문 `schema_version`이
  - 코드 버전보다 **크면 `SchemaVersionError` raise**(다운그레이드 차단 — 미래 버전 안전 해석 불가),
  - **같거나 작으면 누락 필드를 기본값으로 관대 복원**한다. 구체 예: `FormulaOperand.column` 누락 → `"value"`, strategy `rule` 슬롯 누락/null → `None`(초안), `metadata` 누락 → `{}`, `output_column` 누락 → `"value"`.
- **왕복 무손실(REQ-C2, NFR-04)**: 자유형 매핑(`metadata`, operand `params`)은 **생성 시점**에 `_jsonnorm.normalize_mapping`으로 JSON-native 정규화(중첩 tuple→list·str 키·JSON 스칼라)하여 `from_dict(to_dict(x)) == x`를 구조적으로 폐색한다.

---

## 6. 알고리즘·검증 설계

### 6.1 canonical-JSON eq/hash (REQ-C5, NFR-06)

전 도메인 타입은 `@dataclass(frozen=True, eq=False)` + `CanonicalEq` 믹스인으로 배치한다(dataclass 자동 `__eq__`/`__hash__` 억제 후 믹스인이 canonical 기반 제공).

```
def __eq__(self, other):
    if type(self) is not type(other) or not hasattr(other, "to_dict"):
        return NotImplemented / False       # 타 타입은 불일치
    return canonical_json(self.to_dict()) == canonical_json(other.to_dict())

def __hash__(self):
    return hash(canonical_json(self.to_dict()))
```

- **타입 보존 근거**: `canonical_json`은 `int`/`float`를 구분 방출(`30` vs `30.0`)하므로 자유 수치 상수 리프에서 필드 기반 eq의 `30==30.0` 문제를 회피한다. `30`과 `30.0`은 다른 canonical 문자열 → 다른 해시 → set 크기 2(AC-R02-01).
- **비유한 float 차단**: `ConstantOperand`는 생성 시 `bool`(REQ-C6) 및 **비유한 float(nan/inf)**를 거부한다. 근거: `json.dumps(nan)`은 비표준 `NaN`을 산출하고 `nan != nan`이 canonical eq/hash 결정론(REQ-C3/C5)을 깨므로, 결정론 보존을 위해 정의 시점 차단한다(REQ-C3·REQ-C5 역추적 유도 결정, §10 ADR-R02-05).
- **bool 이중 판정(REQ-C6)**: Python에서 `bool ⊂ int`이므로 `ConstantOperand.value`는 `isinstance(value, bool)` 선차단으로 거부한다. 반면 자유형 매핑(`metadata`/`params`) 내부 `bool`은 JSON 스칼라로 **허용**된다 — 두 경로의 판정 지점을 분리한다(TR-R02-002).

### 6.2 Formula DAG 순환 검출 — DFS gray/black (§5.1 DAG, AC-R02-04)

```
검출 대상: Formula 참조 그래프(FormulaOperand.formula_id 간선), resolve_formula로 지연 확장.
색상: WHITE(미방문) · GRAY(방문 중, 현재 DFS 경로) · BLACK(완료)

def detect_cycle(root_formula, resolve_formula):
    color: dict[str, str] = {}     # formula_id → 색상
    path:  list[str] = []          # 현재 경로(순환 힌트용)

    def visit(fid):
        color[fid] = GRAY; path.append(fid)
        f = resolve_formula(fid)           # None이면 참조 존재 오류(별도 판정)
        for ref_id in formula_operand_ids(f.expression):   # 태그 순회로 FormulaOperand.formula_id 수집
            if color.get(ref_id) == GRAY:                  # back-edge → 순환
                raise cycle(path[path.index(ref_id):] + [ref_id])   # 순환 경로 힌트(REQ-V4)
            if color.get(ref_id) != BLACK:
                visit(ref_id)
        color[fid] = BLACK; path.pop()

    visit(root_formula.id)   # root는 아직 미저장일 수 있으므로 expression을 직접 시드
```

- 자기참조(1-사이클)·2-사이클·3-노드 이상 장주기 전부 GRAY back-edge로 검출. 다이아몬드 DAG(공유 참조·비순환)는 BLACK 재방문으로 통과(중복 방문 없음).
- root Formula는 upsert 시점에 아직 store에 없으므로, `visit`은 root의 `expression`을 직접 시드하고 참조 확장만 리졸버로 수행한다(저장 게이트 §7.2).
- 순환 발견 시 `DefinitionValidationError`(경로 힌트) — 저장 게이트에서 예외 + store 무변경(AC-R02-04).

### 6.3 태그 판별 `from_dict` 복원 (REQ-C1/C2, AC-R02-02)

```
expr_from_dict(d):
    if "node" in d:  dispatch on d["node"] ∈ {"binary","unary"}       # 내부 노드
    elif "kind" in d: dispatch on d["kind"] ∈ {"factor","constant","formula"}  # 리프
    else: raise MalformedDefinitionError("태그 부재 …")
    # "node"와 "kind" 동시 존재(중복) → raise. 미지 태그 값 → raise.
    # 재귀: BinaryOp.left/right, UnaryOp.operand 를 expr_from_dict로 복원.
    # arity 위반(BinaryOp.left 누락 등) → raise.
```

- 복원은 **오직 태그 분기**로만 수행한다 — 산술식 문자열·람다·eval 경로 부재(REQ-C1 선언성). Rule은 `node_from_dict`(`"predicate"`/`"composition"`)로 동형 배선.

### 6.4 검증기 3종 알고리즘 + 오류 순서 결정론 (REQ-V1~V4)

- **비발생 검증기**: 트리를 **좌→우·깊이 우선** 고정 순회하며 오류를 append → `ValidationResult(ok=not errors, errors=tuple(errors))`. 순회 순서 고정으로 오류 순서 결정론(REQ-C3·REQ-V1).
- **엄격 변형**: 동일 순회 중 **첫 오류에서 `DefinitionValidationError` raise**. 저장 게이트(§7)가 소비.
- **factor_refs 전이 일관성(§5.3, TR-R02-011)**:
  ```
  transitive_factors(defn, resolve_rule, resolve_formula):
      acc = set()
      for rid in defn.rule.entry + defn.rule.exit:
          r = resolve_rule(rid)               # None → rule 미존재 오류
          for op in walk_operands(r.root):    # 태그 순회(duck typing)
              if op.kind == "factor":  acc.add(op.factor_id)
              elif op.kind == "formula":
                  f = resolve_formula(op.formula_id)
                  acc |= collect_factor_ids(f.expression)   # 전이 확장(§3.4 동일 순회, 단 factor_id 수집)
      return acc
  # 비교: acc == {fr.factor_id for fr in defn.factor_refs} (정확 일치)
  # 불일치 → 누락(acc − refs)·잉여(refs − acc) id 목록 힌트(REQ-V4). 초안(rule=None) → 보류.
  ```
  일관성은 **factor_id 집합 단위**다(params 차이는 무관 — 동일 factor_id·상이 params는 D1 독립 참조이나 집합 원소로는 1개).
- **오류 메시지(REQ-V4, TR-R02-016)**: 누락 factor/formula/rule id → "사용 가능: …"(레지스트리 `list_factors`·리졸버 목록), `column ∉ output` → 유효 컬럼 목록, params 범위 위반 → 허용 범위(ParamSpec min/max), 순환 → 순환 경로, factor_refs 불일치 → 누락/잉여 id. 전부 한국어.

### 6.5 도메인 형상 가드 (§5.2/§5.3, AC-R02-02/03/05)

- **교차 연산자 구조 가드(§5.2)**: `crosses_above`/`crosses_below` Predicate는 좌/우 `kind` 조합을 판정 — **최소 1개가 `factor` 또는 `formula`**여야 한다. `상수 crosses 상수`는 축퇴로 `MalformedDefinitionError`(생성/`from_dict`) 또는 검증 오류.
- **float 비교 의미론 명시(§5.2)**: `==`/`!=`는 원소별 엄밀 비교. 정의 계층은 이 의미론을 **CLI 도움말·문서에 명시**(평가 동작은 R03 — 소비자: PRD-R03 §5).
- **rule 슬롯 whitelist(D4)**: `RuleBinding.from_dict`가 `{"roles": {"entry":[…], "exit":[…]}}` 외 형상(인라인 Rule 본문·`{"rule_ids":[…]}`·미지 역할 키)을 `MalformedDefinitionError`로 거부. `entry` 빈 리스트 거부, 역할 내 rule id 중복 거부, 순서 보존(왕복).
- **universe 형식(D5)**: `Universe.symbols`는 KRX 6자리 숫자 형식(정규식 `^\d{6}$` 상당) 위반 시 거부. 빈 튜플 허용(=watchlist 전체, 실행 의미는 소비자: PRD-R03 §7).

### 6.6 params 오버라이드 검증 (§5.4, D1, R01 소비)

- `FactorRef.params`·`FactorOperand.params`(Rule/Formula 공통)는 해당 factor의 **`ParamSpec`(DESIGN-R01 §3.2) 정적 대조**로 검증한다: 미지 파라미터 이름 거부, 타입 불일치 거부(int 자리 float 등), min/max·choices 범위 위반 거부. **정의 검증은 인스턴스화 없이 정적 대조**로 수행한다(실행 없음 — REQ-C1; 실 인스턴스화는 R03).
- 팩터가 **`validate_params` 훅(DESIGN-R01 §3.3)**을 노출하면 교차 제약(예: `macd` fast<slow)도 정의 시점에 함께 검증한다. R02는 훅을 **링크 인용으로 재사용**하며 신규 검증 로직을 두지 않는다(B3-i, D1 단일 원천). 훅 미노출 팩터는 빈 제약으로 간주.
- `column ∈ metadata.output` 검증은 params와 무관하게 항상 수행(파라미터는 출력 컬럼 집합을 바꾸지 않음 — R01 계약). 유효 컬럼은 `FactorMetadata.output`(DESIGN-R01 §3)에서 조회.
- 빈 매핑 = 전부 기본값.

---

## 7. 영속화/CRUD + 호출자 책임 경계

### 7.1 책임 경계 개요

- **storage 계층**(`storage/db.py` `Database`)이 CRUD·저장 게이트를 제공한다. **방향은 storage → 도메인**(도메인 패키지는 storage를 모른다, INV-1).
- **도메인 검증기**는 storage를 모르고 **주입된 리졸버(콜러블)만** 소비한다 — 저장 게이트가 자기 store를 리졸버로 감싸 주입(B2-i).

### 7.2 CRUD + 저장 게이트 (REQ-P2/P3, B2-i)

```python
# storage/db.py Database 메서드 (엔티티 3종 동형; formula 예시)
def upsert_formula(self, formula: Formula, *, now: datetime, check_formula_store: bool = True) -> None: ...
def get_formula(self, formula_id: str) -> Formula | None: ...
def list_formulas(self) -> tuple[Formula, ...]: ...            # id 오름차순 정렬
def delete_formula(self, formula_id: str) -> None: ...          # 비계단식

# rule: upsert_rule(rule, *, now, check_formula_store=True) — FormulaOperand 참조 리졸버 주입
# strategy: upsert_strategy(defn, *, now, check_rule_store=True, check_formula_store=True)
#           — rules store 리졸버 + factor_refs 전이 확장용 formulas store 리졸버 주입
```

- **저장 게이트(REQ-P3)**: 모든 `upsert_*`는 저장 **전** 해당 **엄격 검증기**(`validate_*_strict`)를 호출한다. 무효 정의는 **부분 저장 없이** 예외로 차단(트랜잭션 경계에서 저장 미수행 → store 무변경, AC-R02-04/06).
- **리졸버 주입(B2-i)**: `upsert_formula`는 `formulas` store 기반 `resolve_formula`를 formula 참조 존재·DAG 순환 검증에 주입(default-on). `upsert_rule`은 `formulas` store 리졸버 주입. `upsert_strategy`는 `rules`·`formulas` store 리졸버 주입.
- **완화 플래그**: `check_formula_store`·`check_rule_store`(기본 True) off → 해당 store 리졸버 주입을 생략(검증기에 `resolve_*=None` 전달) → 참조 존재·순환 검증만 완화, **구조 검증은 항상 수행**(부분 조립·단위 테스트용). factor 레지스트리 기반 검증은 상시 수행(레지스트리는 데이터 무관 상시 존재, DESIGN-R01 §3.8).
- **CRUD 배선(REQ-P2)**: `INSERT OR REPLACE` 멱등, 신규 시 `created_at=now`·갱신 시 `created_at` 보존·`updated_at` 갱신, `now`는 **주입**으로 결정론. `list_*`는 `id` 오름차순.
- **DDL 멱등(REQ-P1)**: `CREATE TABLE IF NOT EXISTS` 재연결 무오류(AC-R02-07).

### 7.3 dangling 정책 + 호출자 책임 경계 (REQ-P4)

- 참조 무결성 보장 시점은 **저장 시점**(§7.2 게이트). 참조된 엔티티의 **사후 삭제는 계단식 정리하지 않는다**(`delete_*` 비계단식) — 남은 dangling 참조는 실행 시점에 R03 평가 진입의 명확 실패(`EvaluationError`)로 격리(소비자: PRD-R03 §5).
- **활성 참조 보호는 본 계층 책임이 아니다**: 활성 전략이 참조 중인 Formula/Rule의 수정·삭제 차단은 활성 상태(activation)를 아는 상위 계층 책임 — **소비자: PRD-R03 §4(FR-04a)**. 본 문서는 정책 경계만 고정하고 상세를 위임한다.

---

## 8. 마일스톤 (M0..M5 — 논리 단위)

| M | 범위 | 완료 신호 |
|---|---|---|
| M0 | 3패키지 골격 + `_jsonnorm` leaf(정규화·canonical·`CanonicalEq`·오류 계층) + INV-1~3 AST 스캔 | AST green(AC-R02-07 부분) |
| M1 | 공통 표현 계약(왕복·정규화·canonical eq/hash·schema_version 관대/엄격) + Formula 도메인 타입·표현 트리·`from_dict`/`to_dict` | AC-R02-01/02 부분 |
| M2 | Formula 검증기(구조·참조·DAG DFS) + `derive_required_data` 전이 파생 | AC-R02-03/04 부분 |
| M3 | Rule 도메인 타입·검증기(피연산자 3종 별개 클래스·교차 가드·params 검증 R01 소비) | AC-R02-02/03 |
| M4 | Strategy 도메인 타입·검증기(RuleBinding roles D4·universe D5·factor_refs 일관성·`is_runnable`) | AC-R02-05 |
| M5 | 3테이블 DDL + CRUD + 저장 게이트(리졸버 주입·`check_*` 플래그) | AC-R02-06/07 |

> 마일스톤은 문서상 논리 단위다(스프린트 분할은 구현 계획 시점 확정).

---

## 9. 문서화 체크리스트

- [ ] §3 도메인 타입 시그니처 전부 확정(R03 인용 원천): `Formula`·`Rule`·`StrategyDefinition` + `from_dict`/`to_dict`, 피연산자 3종(패키지별 별개 클래스), `validate_formula`/`validate_rule`/`validate_definition`(+엄격), `is_runnable`, `derive_required_data`, `ValidationResult`, 리졸버 타입.
- [ ] `_jsonnorm` 공유 leaf 계약(정규화·canonical_json·`CanonicalEq`·bool 이중 판정) 명시(B1-i).
- [ ] INV-1~3 AST 스캔 규칙(금지 모듈 목록 + 패키지 상호 미import + `TYPE_CHECKING` 예외).
- [ ] canonical eq/hash `30`≠`30.0`(set 크기 2) + int/float 타입 보존 직렬화 규약.
- [ ] schema_version 관대/엄격 복원(미래 버전 거부·누락 기본값·`FormulaOperand.column`→"value").
- [ ] Formula DAG 순환 검출 DFS gray/black + 순환 경로 힌트.
- [ ] 검증기 3종 오류 순서 결정론(좌→우 깊이 우선) + 한국어 힌트 모델.
- [ ] factor_refs 전이 참조 집합 정확 일치(초안 보류) + 교차 구조 가드 + universe KRX 6자리.
- [ ] params 검증 = R01 `ParamSpec`/`validate_params` 훅 재사용(신규 로직 0, B3-i).
- [ ] 3테이블 동형 DDL + CRUD 멱등(`created_at` 보존·id 정렬) + 저장 게이트(부분 저장 없음·리졸버 주입·`check_*`).
- [ ] dangling 정책(저장 시점 차단·비계단식 삭제) + 활성 참조 보호 "소비자: PRD-R03 FR-04a" 포인터.
- [ ] additive 진화(기존 DDL 무변경, 3테이블 추가만).
- [ ] §11 테스트: 합성 Fixture + 격리 DuckDB + pytest 결정론(2회 동일), 기대값 하드코딩 금지.
- [ ] TRD-R02 B1/B2/B3·TR-R02-001~018과 모순 없음, DESIGN-R01 §3 재정의 없음.

---

## 10. ADR

### ADR-R02-01 — 도메인 타입을 frozen dataclass(+`eq=False`)로
- **Decision**: 전 도메인 타입을 `@dataclass(frozen=True, eq=False)` + `CanonicalEq` 믹스인으로.
- **Drivers**: REQ-C7 불변성 · canonical eq/hash 주입 · 기본값/`__post_init__` 정규화.
- **Alternatives**: `NamedTuple`(검증·믹스인 유연성 열위), dict(형상 계약 강제 불가).
- **Consequences**: `params`/`metadata` 프레임 내부 가변성은 `__post_init__` 정규화 + 읽기전용 매핑으로 완화(참조 재바인딩은 frozen이 차단).

### ADR-R02-02 — 노드 판별을 `node`/`kind` 태그로
- **Decision**: 내부 노드 `node`("binary"|"unary"|"predicate"|"composition"), 리프 `kind`("factor"|"constant"|"formula") 태그 판별.
- **Drivers**: JSON 왕복 결정론 복원(REQ-C2) · 미지 태그 거부로 폐집합 강제(AC-R02-02).
- **Alternatives**: 클래스명 직결(직렬화 결합), 위치 규약(가독성·확장성 열위).
- **Consequences**: `from_dict`는 오직 태그 분기 — 코드·문자열식 경로 부재(REQ-C1). INV-2 duck typing 순회의 어휘가 됨.

### ADR-R02-03 — 순환 검출을 DFS gray/black으로
- **Decision**: Formula DAG 순환을 DFS 3색(WHITE/GRAY/BLACK) back-edge 판정으로.
- **Drivers**: 순환 경로 힌트(REQ-V4) 자연 산출 · 리졸버 지연 확장과 정합 · 다이아몬드 DAG 통과.
- **Alternatives**: Kahn 위상정렬(경로 힌트 부자연), 재귀 깊이 제한(장주기 오탐/미탐).

### ADR-R02-04 — 저장 표현을 3테이블 동형(JSON definition)으로
- **Decision**: `strategies`·`rules`·`formulas`를 `id` PK + JSON `definition` 진실 원천 + 비정규 식별 컬럼으로 동형 배치.
- **Drivers**: REQ-P1 동형 · additive 진화(신규 필드=JSON 본문+`schema_version`) · 마이그레이션 프레임워크 불요.
- **Alternatives**: 엔티티별 정규화 스키마(트리 구조 정규화 폭증·additive 마찰).
- **Consequences**: 질의 편의 컬럼(`name`/`version`/`schema_version`)은 비정규 사본 — 진실 원천은 항상 `definition`.

### ADR-R02-05 — eq/hash를 canonical JSON 기반으로 (+비유한 상수 차단)
- **Decision**: `__eq__`/`__hash__`를 `canonical_json(to_dict())` 기반으로. `ConstantOperand`는 `bool`·비유한 float(nan/inf) 거부.
- **Drivers**: REQ-C5(`30`≠`30.0` — 필드 eq는 `30==30.0`으로 해시 계약 붕괴) · REQ-C3 결정론(nan은 canonical·eq 결정론 붕괴).
- **Alternatives**: 필드 기반 dataclass eq(해시 계약 붕괴), float 허용(nan 비결정성).
- **Consequences**: `{Formula(…30…), Formula(…30.0…)}` set 크기 2(AC-R02-01). 비유한 차단은 REQ-C3/C5 역추적 유도 결정.

### ADR-R02-06 — rule 슬롯을 `RuleBinding` 타입으로
- **Decision**: strategy `rule` 슬롯을 `RuleBinding | None`(roles 단일 형상)로 타입 고정.
- **Drivers**: D4 whitelist fail-closed를 타입 생성 시점 강제 · `is_runnable`을 필드 접근으로 단순화 · 인라인 본문/`rule_ids` 형상 구조 차단.
- **Alternatives**: raw dict `{"roles":…}`(형상 강제 산발), 인라인 Rule 본문 허용(D4 위반).
- **Consequences**: `is_runnable(defn) = defn.rule is not None`(entry 비어있지 않음은 생성 시 강제).

> 본 계획 메타 결정(6편 분할·계층 순차)은 상위 계획 문서 ADR 소관이며 여기서 다루지 않는다.

---

## 11. 픽스처 및 테스트 매핑

### 11.1 합성 Fixture

- **정의 Fixture(코드 산출)**: 세 엔티티 대표 정의를 **파이썬 팩토리로 산출**한다(중첩 표현 트리·다이아몬드 DAG·roles 전략 포함). 기대값 하드코딩 금지 — 왕복·canonical·구조 거부는 산출·재구성하여 대조(NFR-01, 원칙 3).
- **factor/formula 참조 검증**: R01 팩터 레지스트리(상시 등록) + `tmp_path` 격리 DuckDB store 리졸버 주입으로 검증(실데이터 불요, NFR-02). `now`는 주입.
- **경계 케이스 의도 포함**: `30` vs `30.0` 상수 쌍(set 크기 2), `FormulaOperand.column` 누락 본문(관대 복원), 자기참조·2-사이클·3-노드 장주기·다이아몬드(DAG), 빈 entry·미지 역할 키·`rule_ids`·인라인 본문(roles 거부), factor_refs 초과/부족(일관성), `상수 crosses 상수`(교차 가드), `macd` fast≥slow(validate_params 훅).

### 11.2 AC → 테스트 모듈 매핑

| AC | 테스트(예시 경로) | 검증 핵심 |
|---|---|---|
| AC-R02-01 | `tests/unit/definition/test_roundtrip.py` | 왕복·2회 바이트 동일·canonical eq/hash(`30`vs`30.0` set 2)·frozen·미래 버전 거부 |
| AC-R02-02 | `tests/unit/definition/test_structural_reject.py` | 미지 연산자/kind/태그·arity·bool 상수·비-str 키·비-snake_case id |
| AC-R02-03 | `tests/unit/definition/test_reference_validation.py` | factor/formula/rule 참조·column∈output·params(validate_params)·factor_refs 일관성 |
| AC-R02-04 | `tests/unit/definition/test_formula_dag.py` | 자기참조·사이클·다이아몬드·저장 게이트 순환 upsert 무변경 |
| AC-R02-05 | `tests/unit/definition/test_strategy_roles.py` | roles whitelist·`is_runnable`·중복·순서 보존 |
| AC-R02-06 | `tests/unit/storage/test_definition_crud.py` | CRUD 멱등·`created_at` 보존·id 정렬·저장 게이트·공유 참조 |
| AC-R02-07 | `tests/unit/definition/test_purity_ast.py`, `tests/unit/storage/test_definition_schema.py` | AST 스캔(금지 모듈+상호 참조)·3테이블 멱등 |

- 통합·CRUD 테스트는 `tmp_path` 격리 DuckDB + 격리 store 리졸버로 네트워크·실데이터·LLM 없이 실행(NFR-02). 결정론은 **2회 실행 동일**(직렬 바이트·오류 순서)로 판정(NFR-01).

---

**추적성 요약**: REQ-C1~C7 · REQ-P1~P4 · REQ-V1~V5 · §5.1~§5.4 도메인 형상 · INV-1~3 · D1/D4/D5 · AC-01~07이 §3 시그니처 + §5 DDL + §6 알고리즘 + §7 CRUD + §11 테스트로 매핑된다. §3 시그니처(검증기 3종·`is_runnable`·`from_dict`/`to_dict`·`derive_required_data`·리졸버 타입)는 R03가 인용하는 확정 원천(§D-2, **소비자: PRD-R03 §4/§5**). 본 문서는 TRD-R02 B1(`_jsonnorm` 단일 leaf §2/§3.2)·B2(저장 게이트 self-store 리졸버 default-on + `check_*` §7.2)·B3(params 검증 R01 훅 재사용 §6.6)·TR-R02-001~018과 정합하며, `DESIGN-R01 §3`(ParamSpec §3.2·validate_params §3.3·get_factor §3.7·레지스트리 §3.8)을 재정의 없이 링크 인용한다.

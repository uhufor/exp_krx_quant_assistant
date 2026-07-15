# DESIGN-R03 : Workspace & Execution

**대응 PRD**: `PRD-R03-WORKSPACE_AND_EXECUTION.md` / **짝 TRD**: `TRD-R03-WORKSPACE_AND_EXECUTION.md`
**계층**: R03 (최상위, impure — 전 계층 소비·오케스트레이션) / **의존**: R02(정의·영속·검증), R01(팩터 계산·펀더멘털 데이터) / **소비자**: 없음(최상위 — CLI·운영자)
**Status**: Draft for review
**전제**: 본 문서는 main 브랜치 시점에서 No-Code Strategy Workspace의 실행·오케스트레이션 계층을 **처음 구현한다**고 가정한다. 모든 설계 서술은 PRD-R03 + `README.md`(§4 D1~D5 · §5 공통 불변 원칙 7) + 짝 TRD-R03(TR-R03-001~027) + 하위 계층 확정 인터페이스(`DESIGN-R01 §3` · `DESIGN-R02 §3`) 역추적으로만 정당화한다. 이 네 원천 밖의 문서·산출물을 설계 근거로 두지 않는다.

> **인터페이스 인용 규약(§D-2)**: R03가 소비하는 하위 시그니처의 **확정 원천은 각 하위 DESIGN §3**이며, 본 문서는 이를 **재정의하지 않고 링크 인용**한다(요약 1줄까지). R01: `FactorInput`(`DESIGN-R01 §3.4`) · `compute_factor`(`§3.6`) · `get_factor`(`§3.7`) · `get_factor_notes`(`§3.9`) · `FactorMetadata.required_data`(`§3` 레지스트리) · `FundamentalProvider`(`§3.11`). R02: `validate_formula`/`validate_rule`/`validate_definition`(+엄격)(`DESIGN-R02 §3.4/§3.6/§3.8`) · `is_runnable`(`§3.8`) · `derive_required_data`(`§3.4`) · `from_dict`/`to_dict`(`§3.3/§3.5/§3.7`, `§5.3`) · `ValidationResult`(`§3.1`) · 리졸버 계약(`§3.9`). baseline 재사용 자산은 `TRD-R01 §8.2` 앵커 표 명칭으로만 인용한다.
>
> **하위 문서 규율(§D-1)**: 본 문서는 최상위 계층이므로 인용할 상위 문서가 없다. 하위(R01/R02)를 단방향 인용만 하며 역주입하지 않는다(INV-1).

---

## 1. 개요

### 1.1 목적

정의 코어(R01/R02) 위에 얹는 **impure 실행·오케스트레이션 계층**의 구현 형상(모듈 구조·파사드 API 시그니처·평가 알고리즘·백테스트 어댑터·DDL 2테이블·Daily 통합 삽입 지점·Template/Import·Export·ADR)을 확정한다. 본 계층은 하위 CRUD·검증·팩터 계산·백테스트 엔진·다운스트림 파이프라인을 **소비·조합**하며 신규 검증 로직·신규 백테스트 엔진·신규 다운스트림 경로를 만들지 않는다.

### 1.2 PRD/TRD와의 관계

- **PRD-R03**: 요구사항 원천(FR-01~23·INV-1~4·AC-01~09·§10 CLI). 재논쟁 대상 아님.
- **TRD-R03**: 배선·강제 방식 확정(TR-R03-001~027, 결정 축 C1 활성 참조 보호 온디맨드 폐포 / C2 전환 시드 Daily 부트스트랩 인라인 멱등 / C3 평가 캐시 (전략,종목) 컨텍스트 소유).
- **본 DESIGN-R03**: TR의 배선 결정을 **실제 타입 시그니처·DDL·알고리즘 의사코드·ADR**로 구체화한다. PRD가 이미 확정한 FR-08 수치 규약·Built-in 5종 정의 표·CLI 목록·Import 충돌 3분기는 **재정의 없이 구현 형상(강제점 배치·번들 조립·라우팅)으로 번역**한다.

### 1.3 자기완결성·오염 가드 선언

본 문서의 모든 설계 서술은 PRD-R03 + TRD-R03 + README §4/§5 + 하위 계층 확정 인터페이스(`DESIGN-R01 §3` · `DESIGN-R02 §3`) 역추적으로만 정당화된다. main 시점 최초 구현("앞으로 만들 것")의 관점으로만 서술하며, 이 네 원천 밖의 문서·산출물을 설계 근거로 두지 않는다. 하위 시그니처·수치 규약·Built-in 정의·CLI 목록의 **소비·조합·강제·오케스트레이션 방식**만 확정하고 그 원천을 재정의하지 않는다.

### 1.4 결정론 범위 선결 고지 (INV-3)

R03의 결정론 범위는 **평가·백테스트·신호 분류·Report A(결정론)까지**다. LLM Report B는 mock Provider 주입 시에만 결정론 범위에 포함된다. 모든 시각은 **주입**(injected `now`)이며 네트워크·현재시각 의존을 두지 않는다. 이 범위가 평가 캐시 격리(§6.2)·전환 시드 멱등(§7.4)·수치 규약 단일 강제점(§6.1)의 설계 축이다.

---

## 2. 모듈 구조 및 의존 방향

### 2.1 패키지 트리

```
quant_krx/
├── workspace/                    # impure 상위 계층 (INV-1: 하위에 역주입 없음)
│   ├── __init__.py               #   공개 API 재노출(WorkspaceService, EvaluationError 계층,
│   │                             #   evaluate_formula, evaluate_rule)
│   ├── service.py                #   WorkspaceService 파사드 (§3.2)
│   │                             #     - CRUD 위임(R02 저장 게이트) + 전이 검증 조합(§3.3)
│   │                             #     - 활성화(strategy_activation) + 활성 참조 보호 게이트(§3.4/§7.2)
│   │                             #     - 백테스트 오케스트레이션(§3.6)
│   │                             #     - Template·Import/Export 조합(§3.7/§3.8)
│   ├── evaluation.py             #   평가 엔진: EvaluationContext·evaluate_formula·evaluate_rule (§3.5)
│   ├── numeric.py                #   수치 규약 단일 강제점 헬퍼 (FR-08, §6.1) — 공유 leaf
│   ├── errors.py                 #   EvaluationError 계층 (§3.9)
│   ├── backtest.py               #   DeclarativeStrategy 백테스트 어댑터 (§3.6) — baseline 엔진 위임
│   ├── templates.py              #   Built-in 5종 번들 상수 + create_from_template/save_as_template (§3.7)
│   └── bundle.py                 #   Export/Import 번들 직렬화·위상 순서·충돌 3분기 (§3.8)
├── jobs/
│   └── daily.py                  #   DailyJob.run() — 전략 원천을 활성 선언형 단일로 수렴(§6.5, §7.4)
│                                 #     코드형 5종 조립 표현 부재 · 전환 시드 인라인 · universe 해석
└── (소비 대상 — 무변경 참조)
    ├── quant_krx.factors         #   get_factor·compute_factor·get_factor_notes·FactorMetadata (R01 §3)
    ├── quant_krx.strategy/rule/formula  # from_dict/to_dict·검증기·is_runnable·리졸버 (R02 §3)
    ├── quant_krx.data            #   DataProvider(OHLCV)·FundamentalProvider (baseline·R01)
    ├── quant_krx.quant           #   Portfolio.from_signals 연결·BacktestMetrics·SignalClassifier (baseline)
    └── quant_krx.storage.db      #   Database CRUD·저장 게이트 + strategy_activation·strategy_templates (§5)
```

- `workspace/`(파사드·평가·백테스트·Template·Import/Export)와 `jobs/`(Daily 오케스트레이션)가 impure 상위 계층이다(TR-R03-001).
- `workspace/numeric.py`는 도메인 로직이 아닌 **수치 규약 공유 leaf**로, evaluate_formula·evaluate_rule·백테스트 시그널 사상이 모두 이 단일 강제점을 경유한다(§6.1, drift 차단).

### 2.2 의존 방향과 INV-1 (계층 단방향 AST 스캔)

```
        (CLI / 운영자 — Typer 얇은 래퍼)
                 │
                 ▼
        quant_krx.workspace / quant_krx.jobs      ← impure 최상위
                 │  소비만(역주입 0)
   ┌─────────────┼──────────────┬───────────────┐
   ▼             ▼              ▼               ▼
 R02 정의      R01 팩터      baseline 실행     storage
 (strategy/    (factors/     (quant/ ·        (storage/db.py
  rule/         레지스트리)    data/)           + 2 신규 테이블)
  formula/)
```

- **INV-1 강제(NFR-03, TR-R03-001)** — 단방향 AST 스캔 규칙:
  - (a) **하위 순수성 무변경 green**: R01/R02 순수성 AST 스캔(`DESIGN-R01 §2.2` / `DESIGN-R02 §2.2`)이 그대로 통과 — 정의 패키지(`factors`/`formula`/`rule`/`strategy`)가 `workspace`·`jobs`를 import하지 않는다.
  - (b) **역주입 부재 별도 스캔**: 정의 패키지 import 그래프를 재귀 순회하여 `quant_krx.workspace`·`quant_krx.jobs` 참조 **0건**을 강제한다(순방향 하위→상위 역주입 금지).
  - (c) 역방향(상위→하위 소비)은 허용. 평가·실행·백테스트·Template·Import/Export 코드는 전부 `workspace`/`jobs` 하위에만 존재하며 하위 계층은 평가·실행 코드를 보유하지 않는다.
- **의존 대상은 소비만**: R01/R02 확정 인터페이스·baseline 엔진·storage를 재정의·우회 없이 그대로 호출한다(NFR-06 재사용 무변조).

---

## 3. 도메인 타입 시그니처

> 본 절은 R03가 **하위 계약을 조합해 노출하는 상위 API**를 확정한다. 하위 시그니처(R01 `FactorInput`/`compute_factor`/`get_factor`, R02 검증기/`is_runnable`/`from_dict`/리졸버)는 각 하위 DESIGN §3이 원천이며 여기서 재정의하지 않고 링크 인용한다(§D-2). 타입은 `from __future__ import annotations` 전제. `pd = pandas`.

### 3.1 공통 별칭 · 리졸버 배선

```python
# R02 리졸버 계약(DESIGN-R02 §3.9)을 storage store 기반으로 감싸 주입하는 팩토리.
# 파사드가 자기 Database를 리졸버로 감쌀 뿐, 검증·전이 알고리즘을 중복 구현하지 않는다.
FormulaResolver = Callable[[str], "FormulaLike | None"]   # DESIGN-R02 §3.9 (재정의 없음)
RuleResolver    = Callable[[str], "RuleLike | None"]       # DESIGN-R02 §3.9 (재정의 없음)

def _formula_resolver(db: Database) -> FormulaResolver: ...  # fid → db.get_formula(fid)
def _rule_resolver(db: Database) -> RuleResolver: ...        # rid → db.get_rule(rid)
```

### 3.2 `WorkspaceService` 파사드 (FR-01)

```python
class WorkspaceService:
    def __init__(self, db: Database, *, factor_registry: FactorRegistry | None = None) -> None: ...
    #   storage(Database) 주입. factor_registry 미지정 시 R01 전역 레지스트리 소비(DESIGN-R01 §3.8).
    #   파사드는 신규 저장 로직을 두지 않는다 — CRUD는 R02 저장 게이트로 위임(§3.3).

    # ── 도메인 CRUD 위임 (R02 저장 게이트, DESIGN-R02 §7.2) ──────────────────
    #   활성 참조 보호 게이트(§3.4)를 upsert/delete 진입에서 저장 게이트 호출 '전' 적용.
    def upsert_strategy(self, defn: StrategyDefinition, *, now: datetime) -> None: ...
    def get_strategy(self, strategy_id: str) -> StrategyDefinition | None: ...
    def list_strategies(self) -> tuple[StrategyDefinition, ...]: ...     # id 오름차순
    def delete_strategy(self, strategy_id: str) -> None: ...
    def upsert_rule(self, rule: Rule, *, now: datetime) -> None: ...
    def get_rule(self, rule_id: str) -> Rule | None: ...
    def list_rules(self) -> tuple[Rule, ...]: ...
    def delete_rule(self, rule_id: str) -> None: ...
    def upsert_formula(self, formula: Formula, *, now: datetime) -> None: ...
    def get_formula(self, formula_id: str) -> Formula | None: ...
    def list_formulas(self) -> tuple[Formula, ...]: ...
    def delete_formula(self, formula_id: str) -> None: ...

    # ── 전이 검증 (§3.3, R02 검증기 조합만) ─────────────────────────────────
    def validate_strategy(self, defn: StrategyDefinition) -> ValidationResult: ...

    # ── 활성화 (§3.4, strategy_activation) ─────────────────────────────────
    def activate(self, strategy_id: str, *, now: datetime) -> None: ...
    def deactivate(self, strategy_id: str, *, now: datetime) -> None: ...
    def is_active(self, strategy_id: str) -> bool: ...
    def list_active(self) -> tuple[str, ...]: ...                        # 활성 id 오름차순

    # ── 백테스트 (§3.6) ────────────────────────────────────────────────────
    def backtest(
        self, strategy_id: str, *, data: dict[str, FactorInput],
        start: date | None = None, end: date | None = None,
        fees: float, slippage: float, benchmark: str | None = None,
    ) -> BacktestReport: ...

    # ── Template (§3.7) ────────────────────────────────────────────────────
    def create_from_template(self, template_id: str, new_id: str, *, now: datetime) -> StrategyDefinition: ...
    def save_as_template(self, strategy_id: str, template_id: str, *, now: datetime) -> None: ...
    def list_templates(self) -> tuple[TemplateInfo, ...]:  ...           # builtin+user 통합 열거(출처 구분)
    def get_template(self, template_id: str) -> StrategyBundle | None: ...
    def delete_template(self, template_id: str) -> None: ...             # user Template만(builtin 삭제 거부)

    # ── Import/Export (§3.8) ───────────────────────────────────────────────
    def export_strategy(self, strategy_id: str) -> StrategyBundle: ...
    def import_strategy(self, bundle: StrategyBundle, *, now: datetime,
                        on_conflict: Literal["reject", "overwrite"] = "reject") -> None: ...
```

- 파사드가 추가하는 것은 **활성 상태 게이트(§3.4)·전이 검증 조합(§3.3)·평가/백테스트 오케스트레이션(§3.5/§3.6)·Template·Import/Export 조합**뿐이다. CRUD·검증기·직렬화 자체는 R02 위임(신규 로직 0, TR-R03-002).
- I/O(입력 파싱·표 출력·종료 코드)는 CLI에 두고 로직은 파사드에 둔다(FR-01). CLI는 baseline Typer 관례(`TRD-R01 §8.2` 앵커)를 계승한다(§9).

### 3.3 전이 검증 — R02 검증기 조합 (FR-02, TR-R03-003)

```python
def validate_strategy(self, defn: StrategyDefinition) -> ValidationResult:
    #   R02 검증기를 '조합만' 한다(신규 검증 로직 0). 리졸버는 자기 store 기반 주입.
    #   1) validate_definition(defn, resolve_rule=_rule_resolver(db),
    #                          resolve_formula=_formula_resolver(db))  # DESIGN-R02 §3.8
    #   2) rule 슬롯 존재 시 전이 참조 Rule 각각 validate_rule(..., resolve_formula=...)  # §3.6
    #   3) 전이 참조 Formula 각각 validate_formula(..., resolve_formula=...)              # §3.4 (순환 포함)
    #   전 오류를 수집해 ValidationResult(ok, errors)로 반환(비발생 — 실행 없는 사전 진단).
    ...
```

- runnable 판정은 R02 `is_runnable(defn)`(`DESIGN-R02 §3.8`)을 **소비**한다(자체 판정 금지). dangling 참조는 R02 저장 게이트가 이미 엄격 검증으로 차단하므로(`DESIGN-R02 §7.2`), `validate_strategy`는 저장 전 **사전 진단**(전 오류 수집) 역할이다.
- 리졸버 소비: 전이 확장은 R02 리졸버 계약(`FormulaResolver`/`RuleResolver`, `DESIGN-R02 §3.9`)을 storage store로 감싸 주입할 뿐 검증 알고리즘을 중복 구현하지 않는다.

### 3.4 활성화 · 활성 참조 보호 (FR-03/FR-04/FR-04a)

```python
def activate(self, strategy_id: str, *, now: datetime) -> None:
    #   전제(TR-R03-005): (a) 전략 존재, (b) is_runnable(defn) == True(DESIGN-R02 §3.8),
    #   (c) validate_strategy(defn).ok == True. 미충족 시 WorkspaceError(한국어 사유) raise.
    #   통과 시 strategy_activation upsert(active=True, updated_at=now). idempotent.
    ...

def deactivate(self, strategy_id: str, *, now: datetime) -> None: ...   # active=False upsert, idempotent
def is_active(self, strategy_id: str) -> bool: ...                       # 미존재 행 → False
def list_active(self) -> tuple[str, ...]: ...                           # active=True인 id 오름차순

# 활성 참조 보호 게이트(FR-04a, C1-i) — upsert/delete 진입에서 저장 게이트 호출 전 호출.
def _guard_active_reference(self, target_kind: str, target_id: str) -> None:
    #   blockers = _active_blockers(target_kind, target_id)  (§7.2 알고리즘)
    #   blockers 비어있지 않으면 WorkspaceError raise —
    #     메시지: "활성 전략 {blockers}가 참조 중입니다. 먼저 비활성화하십시오." (차단 전략 id 목록 포함)
    ...
```

- 활성 상태는 `strategy_activation`(`strategy_id` PK, `active`, `updated_at`)에 영속(§5). `updated_at`은 **주입 시각**(결정론, INV-3).
- 활성 참조 보호는 **Workspace 파사드 책임**(저장 계층은 활성 상태를 모름 — `DESIGN-R02 §7.3`이 "활성 참조 보호는 R03 위임"으로 명시). 판정은 상태 무보유 온디맨드 전이 폐포(§7.2, C1-i)로 색인 테이블 없이 drift 0.

### 3.5 평가 엔진 — `EvaluationContext` · `evaluate_formula` · `evaluate_rule` (FR-05/06/07, §6)

```python
@dataclass
class EvaluationContext:
    #   단일 (전략, 종목) 평가 컨텍스트 — 캐시 소유(C3-i). 컨텍스트 종료 시 캐시 폐기.
    data: FactorInput                                    # DESIGN-R01 §3.4 (재정의 없음)
    index: pd.DatetimeIndex                              # 기준 인덱스 = data.ohlcv.index (close 캘린더)
    resolve_formula: FormulaResolver
    resolve_rule: RuleResolver                           # DESIGN-R02 §3.9 — rule id → Rule 리졸브(§3.6 build_signals·§6.4와 대칭)
    _factor_cache: dict[tuple[str, str], pd.Series] = field(default_factory=dict)   # (factor_id, canonical(params)) → 컬럼 Series
    _formula_cache: dict[str, pd.Series] = field(default_factory=dict)              # formula_id → Series (메모)
    _visiting: set[str] = field(default_factory=set)     # 방어적 순환 가드(§6.3)

def evaluate_formula(formula: FormulaLike, ctx: EvaluationContext) -> pd.Series:
    #   산술 트리 재귀 평가 → pd.Series (기준 인덱스 정렬). formula_id 메모이제이션.
    #   리프: FactorOperand → _eval_factor_operand(ctx), ConstantOperand → 스칼라 브로드캐스트(§6.1),
    #         FormulaOperand → resolve_formula 후 재귀 evaluate_formula + 메모.
    #   내부: BinaryOp/UnaryOp → numeric 헬퍼(§6.1) 원소별 연산(div0→NaN 전파).
    ...

def evaluate_rule(rule: RuleLike, ctx: EvaluationContext) -> pd.Series:  # dtype=bool
    #   Predicate → 좌/우를 Series/스칼라로 평가 후 numeric 비교·교차 헬퍼(§6.1) → 불리언(NaN→False),
    #   Composition → 자식 불리언 시계열 AND(전항 논리곱)/OR/NOT.
    #   피연산자 라우팅: FactorOperand → 레지스트리 기전, FormulaOperand → evaluate_formula.
    ...

def _eval_factor_operand(op: FactorOperandLike, ctx: EvaluationContext) -> pd.Series:
    #   key = (op.factor_id, canonical_json(op.params))   # DESIGN-R02 §3.2 canonical
    #   캐시 히트 시 반환. 미스 시:
    #     factor = get_factor(op.factor_id, **op.params)          # DESIGN-R01 §3.7 (오버라이드 인스턴스)
    #     result_df = compute_factor(factor, ctx.data)            # DESIGN-R01 §3.6
    #     notes = get_factor_notes(result_df)                     # DESIGN-R01 §3.9 (반환 직후 판독, OT-2)
    #     series = result_df[op.column].reindex(ctx.index)        # §6.1 정렬만(보간 없음)
    #   컬럼 단위로 _factor_cache 저장 후 반환.
    ...
```

- 캐시 키·수명(FR-07, D1): 팩터 계산 캐시 키 = `(factor_id, canonical(params))` — `sma(5)≠sma(20)` 별개 시계열. 캐시(팩터·Formula 메모) 수명은 단일 `EvaluationContext`(전략×종목)로 한정 — 종목·전략·실행 간 공유 금지(C3-i, NFR-05). 컨텍스트 객체가 캐시 dict를 소유하고 종료 시 폐기한다.
- `FormulaLike`/`RuleLike`/`FactorOperandLike`는 R02 리졸버가 반환하는 **duck-typed** 표면(`.node`/`.kind`/`.factor_id`/`.params`/`.column`/`.expression`/`.root`)으로만 순회한다(`DESIGN-R02 §3.9`, INV 정합). Formula를 factor 레지스트리에 병합하지 않는다(별도 네임스페이스, FR-06).

### 3.6 백테스트 어댑터 — `DeclarativeStrategy` (FR-10/11/12)

```python
@dataclass(frozen=True)
class BacktestReport:
    metrics: BacktestMetrics                 # 산식 원천 = baseline BacktestMetrics (TRD-R01 §8.2 앵커, 재사용)
    per_symbol: dict[str, BacktestMetrics]   # 종목별 지표
    benchmark: str | None = None
    benchmark_note: str | None = None        # 벤치마크 산출 불가 시 사유(값 NaN + 문자열)

def build_signals(defn: StrategyDefinition, ctx: EvaluationContext) -> tuple[pd.Series, pd.Series]:
    #   시그널 사상(FR-10, TR-R03-012). defn.rule.entry/exit는 rule id 문자열 튜플(DESIGN-R02 §3.7
    #   RuleBinding)이므로 ctx.resolve_rule로 Rule 객체를 리졸브한 뒤 평가한다(§6.4와 대칭):
    #     entries = AND(evaluate_rule(ctx.resolve_rule(rid), ctx) for rid in defn.rule.entry)   # 모든 entry 조건 충족
    #     exits   = AND(evaluate_rule(ctx.resolve_rule(rid), ctx) for rid in defn.rule.exit) if defn.rule.exit else all_False
    #   entries/exits: close 인덱스 정렬 + NaN→False 보장 불리언 Series(§6.1). 반환 (entries, exits).
    ...

def run_backtest(
    defn: StrategyDefinition, data: dict[str, FactorInput], *,
    fees: float, slippage: float, benchmark: str | None = None,
    resolve_formula: FormulaResolver, resolve_rule: RuleResolver,
    start: date | None = None, end: date | None = None,
) -> BacktestReport:
    #   종목별 EvaluationContext 생성 → build_signals → baseline 엔진 위임:
    #     Portfolio.from_signals(close, entries, exits, fees=fees, slippage=slippage,
    #                            freq="D", ...)   # TRD-R01 §8.2 앵커 — long-only·전량·신규 엔진 0
    #   → BacktestMetrics 재사용 산출. 체결·동시신호 처리는 엔진 기본 의미론(커스텀 규칙 0).
    ...
```

- 어댑터는 R02 `StrategyDefinition`을 소비해 종목별 `(close, entries, exits, fees, slippage)`를 구성하고 baseline 엔진에 위임하는 **얇은 연결 계층**이다(신규 지표·체결 규칙 0, INV-2). runnable 아님·검증 실패는 실행 전 거부(FR-13, §9 CLI).

### 3.7 Template — Built-in 5종 번들 + 생성/저장 (FR-19/20/21)

```python
@dataclass(frozen=True)
class StrategyBundle:
    #   Export/Import·Template 공통 번들 형상(전이 참조 폐포 포함).
    strategy: StrategyDefinition
    rules: tuple[Rule, ...]                   # 전이 참조 Rule 전부
    formulas: tuple[Formula, ...]             # 전이 참조 Formula 전부
    schema_version: int = 1
    def to_dict(self) -> dict[str, Any]: ...  # 결정론 canonical(키 정렬) — R02 to_dict 소비(§3.8)
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> StrategyBundle: ...

@dataclass(frozen=True)
class TemplateInfo:
    template_id: str
    origin: Literal["builtin", "user"]        # 출처 구분 통합 열거(FR-21)
    name: str

# Built-in 5종 상수 번들(templates.py) — 정의 표는 PRD-R03 §8이 확정(재서술 없음).
#   R02 from_dict(DESIGN-R02 §3) 형상으로 코드 상수 조립, 즉시 검증 통과·runnable.
BUILTIN_TEMPLATES: dict[str, StrategyBundle]   # {"ma_crossover", "rsi_breakout", "bollinger_band", "macd", "momentum"}
```

- Built-in 5종은 전부 D1(파라미터 오버라이드)·D2(`price` 팩터 — `bollinger_band` entry가 `price.close` 참조)로 표현되며 코드 상수 번들로 제공한다(신규 정의 형식 0, TR-R03-020).
- `create_from_template(template_id, new_id, now)`: 번들 복제 → 새 id 사용자 전략으로 저장(참조 Rule/Formula가 store에 없으면 함께 upsert). 일반 저장 게이트·검증 통과·즉시 runnable(FR-20).
- `save_as_template(strategy_id, template_id, now)`: 전략+전이 참조를 `StrategyBundle` 형상으로 `strategy_templates`에 저장. 사용자 Template id는 Built-in id와 충돌 거부(한국어 사유). `list_templates`는 builtin+user 출처 구분 통합 열거(FR-21).

### 3.8 Import / Export (FR-22/23)

```python
def export_strategy(self, strategy_id: str) -> StrategyBundle:
    #   Strategy + 전이 참조된 모든 Rule·Formula를 폐포 수집 → StrategyBundle.
    #   결정론 직렬화는 R02 canonical to_dict(DESIGN-R02 §5.3) 소비(신규 직렬화 0). 키 정렬·스키마 버전 포함.
    ...

def import_strategy(self, bundle: StrategyBundle, *, now: datetime,
                    on_conflict: Literal["reject", "overwrite"] = "reject") -> None:
    #   위상 순서 Formula → Rule → Strategy 로 검증·저장(§7.3).
    #   참조 무결성(dangling·순환·컬럼 불일치·params 위반)은 R02 저장 게이트(DESIGN-R02 §7.2)로 거부.
    #   충돌 3분기(id 공통: 동일 canonical 멱등 통과 / 상이 거부 / --overwrite 대체) — 규약 PRD-R03 §9 확정.
    #   --overwrite라도 활성 참조 보호(§3.4)가 우선(FR-04a) — 활성 전이 참조 대상은 대체 전 비활성화 요구.
    ...
```

- 동일성 판정은 R02 canonical eq(`DESIGN-R02 §6.1`) 소비. Export→Import 왕복은 동일 정의를 복원한다(§11 AC-08).

### 3.9 오류 모델 — `EvaluationError` · `WorkspaceError` 계층 (원칙 7, INV-4)

```python
class WorkspaceError(Exception): ...              # 파사드 기반(활성화 전제·활성 참조 보호·Template 충돌·Import 충돌)
class EvaluationError(WorkspaceError): ...         # 평가·데이터 계약 실행 시점 실패(격리 단위)
class MissingDataError(EvaluationError): ...        # required_data 미충족(누락 프레임 종류 + 요구 id 힌트, §6.4)
```

- 모든 메시지는 **한국어 + 행동 가능 힌트**: 미존재 id → 사용 가능 id 목록, 활성 참조 차단 → 차단 전략 id 목록(§3.4), 데이터 미충족 → 누락 데이터 종류(valuation/financials) + 요구 factor/formula id(§6.4), 검증 실패 → R02 `ValidationResult.errors`(`DESIGN-R02 §3.1`) 승계, runnable 아님 → 활성화·백테스트 전제 안내. CLI 실패는 non-zero 종료(§9).
- `EvaluationError`는 실행 시점 격리 단위(전략×종목, §6.5)이며 저장·활성화·Import 시점 차단(R02 게이트 + §3.4)과 함께 INV-4 참조 무결성을 완성한다.

---

## 4. 데이터 구조 결정 (옵션 비교·ADR 연계)

| 결정 축 | 옵션 | 채택 | 근거 |
|---|---|---|---|
| 평가 캐시 수명 | (전략,종목) 컨텍스트 소유 dict vs. 모듈 전역 LRU/dict | **컨텍스트 소유 dict** (ADR-R03-01, C3-i) | FR-07 캐시 수명 (전략,종목) 한정 — 전역 캐시는 종목·전략·실행 간 공유로 데이터 오염(비결정) |
| 캐시 키 구조 | `(factor_id, canonical(params))` vs. `(factor_id, frozenset(params))` | **`(factor_id, canonical_json(params))`** (ADR-R03-01) | R02 canonical 직렬화(`DESIGN-R02 §3.2`) 재사용 — `30`≠`30.0` 타입 보존 일관, frozenset은 타입 보존 미흡 |
| 활성 참조 보호 판정 | 온디맨드 전이 폐포 재계산 vs. 역참조 인덱스 테이블 | **온디맨드 폐포** (ADR-R03-02, C1-i) | 상태 무보유 → drift 0(색인 동기화 불요). 단일 종목·소규모 활성 집합에서 재계산 비용 무시 |
| 전환 시드 배치 | Daily 부트스트랩 인라인 멱등 vs. 별도 마이그레이션 CLI | **Daily 인라인 멱등** (ADR-R03-03, C2-i) | FR-14a "자동 시드"·D3 연속성 보장 — 별도 CLI는 운영자 누락 시 활성 0건 실패 위험 |
| 번들 포맷 | 단일 `StrategyBundle`(strategy+rules+formulas) vs. 엔티티별 분리 파일 | **단일 번들** (ADR-R03-04) | Export→Import 왕복 원자성·위상 순서 자연 표현. R02 to_dict 조립(신규 직렬화 0) |
| 수치 규약 강제 | 단일 공유 헬퍼(`numeric.py`) vs. 각 평가 경로 인라인 | **단일 공유 헬퍼** (ADR-R03-05) | FR-08 6종을 evaluate_formula·evaluate_rule·백테스트 사상이 동일 함수 경유 → drift·우회 차단 |
| 실패 격리 단위 | 전략×종목 try 경계 vs. 전략 단위 / 배치 전체 | **전략×종목 단위** (ADR-R03-06, FR-17) | 한 종목·전략 실패가 배치를 중단하지 않음(부분 실패 격리, NFR-07) |

---

## 5. 직렬화 규약 + DuckDB DDL

### 5.1 additive 진화 원칙 (TR-R03-027)

baseline 8테이블 + R01 2테이블(`fundamental_daily`, `financial_statements`) + R02 3테이블(`strategies`, `rules`, `formulas`)은 **무변경**이다. R03는 아래 **2테이블만 additive 추가**한다(원칙 6). 모든 DDL은 `CREATE TABLE IF NOT EXISTS`로 멱등(재연결 무오류, NFR-08). 신규 활성 상태=행 upsert, 신규 Template=행 추가로만 확장한다.

### 5.2 `strategy_activation` (FR-03)

```sql
CREATE TABLE IF NOT EXISTS strategy_activation (
    strategy_id  VARCHAR   NOT NULL,
    active       BOOLEAN   NOT NULL,        -- 활성 여부
    updated_at   TIMESTAMP,                 -- 전이 시각(주입 — 결정론, INV-3)
    PRIMARY KEY (strategy_id)
);
```

- `strategy_id` PK. 미존재 행 = 비활성(누락 조회 시 False, TR-R03-004). `strategies` 테이블 DDL은 무변경 — 활성 상태를 별도 테이블로 분리해 정의 진실 원천을 침범하지 않는다.
- `active`/`updated_at`은 `activate`/`deactivate` upsert로만 변경. idempotent(동일 전이 반복 무효과).

### 5.3 `strategy_templates` (FR-21)

```sql
CREATE TABLE IF NOT EXISTS strategy_templates (
    template_id  VARCHAR   NOT NULL,
    name         VARCHAR,                   -- 비정규(bundle.strategy.name 사본, 조회용)
    bundle       JSON      NOT NULL,        -- 진실 원천 = StrategyBundle.to_dict (canonical, §3.7)
    created_at   TIMESTAMP,                 -- 신규 시 now
    updated_at   TIMESTAMP,                 -- 갱신 시 now(주입)
    PRIMARY KEY (template_id)
);
```

- 사용자 Template 번들만 저장한다(Built-in 5종은 코드 상수 `BUILTIN_TEMPLATES`, DB 미저장). `list_templates`는 두 원천을 union하여 출처(builtin/user) 구분과 함께 열거(FR-21).
- `bundle`은 R02 canonical 직렬화(`DESIGN-R02 §5.3`) 기반 `StrategyBundle.to_dict` — 저장 Template로 재생성 시 동등 정의 복원(왕복 무손실).

### 5.4 직렬화 규약

- Export 번들·Template 번들은 R02 `to_dict`/`canonical_json`(`DESIGN-R02 §5.3`)을 소비해 **키 정렬·바이트 결정론**을 상속한다(신규 직렬화 0). 2회 Export 바이트 동일(§11 AC-08).
- `strategy_activation`은 정의 본문을 담지 않으므로 canonical 직렬화 대상이 아니다(원자 컬럼).

---

## 6. 알고리즘·검증 설계 ★핵심★

### 6.1 수치 규약 단일 강제점 (FR-08, TR-R03-010, ADR-R03-05)

> 규약 6종의 **전문은 PRD-R03 §5.4가 확정**하므로 재서술하지 않는다. 본 절은 이를 `workspace/numeric.py` 단일 강제점에 배치하는 구현 형상을 확정한다. evaluate_formula·evaluate_rule·build_signals가 모두 이 헬퍼를 경유한다(drift·우회 차단).

```python
# 기준 인덱스 정렬 — 정렬만(보간·ffill 금지). 저빈도→일별 변환은 R01 as-of 정렬(FR-17)이 유일 지점.
def align(series: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    return series.reindex(index)                         # 결측은 NaN(아래 규약 적용)

# 스칼라 상수 → 기준 인덱스 Series 브로드캐스트(스칼라 .shift 크래시 구조적 차단).
def broadcast(value: float, index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(value, index=index)

# 이항 산술 — NaN 전파, div0 → NaN(무예외).
def binary_arith(op: str, l: pd.Series, r: pd.Series) -> pd.Series:
    #   "+"/"-"/"*" 원소별; "/" 는 r==0 위치를 NaN으로(0 분모 → NaN, 예외 없음).
    ...

# 비교 — 불리언화 직전 NaN → False.
def compare(op: str, l: pd.Series, r: pd.Series) -> pd.Series:   # dtype=bool
    #   ">"/">="/"<"/"<="/"=="/"!=" 원소별 → (result & l.notna() & r.notna()) 로 NaN→False.
    ...

# 교차 — crosses_above(l,r) = (l>r) & (l.shift(1)<=r.shift(1)); below 대칭. shift 첫 원소 NaN→False.
def crosses(direction: str, l: pd.Series, r: pd.Series) -> pd.Series:   # dtype=bool
    #   both 입력은 이미 broadcast/align 된 Series(스칼라 진입 없음). 결과 NaN→False.
    ...
```

- **단일 강제 규약**: 비교·교차·논리의 NaN→False는 이 헬퍼 **한 지점**에서만 수행(불리언화 직전). 산술 단계는 NaN 전파(비교·논리 진입 전까지 결측 유지). div0→NaN은 `binary_arith`가 소관.
- **결정론(INV-3)**: 동일 (정의, 데이터) → 2회 평가 동일. 헬퍼는 네트워크·현재시각·전역 상태에 의존하지 않는다. 테스트는 §5.4 규약을 pandas로 독립 재도출해 대조한다(골든 상수 금지, §11).

### 6.2 평가 캐시 수명·격리 (FR-07, C3-i, NFR-05)

```
평가 진입(전략 defn, 종목 sym):
    ctx = EvaluationContext(data=input[sym], index=input[sym].ohlcv.index,
                            resolve_formula=_formula_resolver(db))
    entries, exits = build_signals(defn, ctx)      # ctx 캐시 공유(팩터·Formula 메모)
    # ctx 폐기 → 캐시 dict GC. 다음 (전략, 종목)은 새 ctx로 격리.
```

- 캐시 키 `(factor_id, canonical_json(params))`는 파라미터 오버라이드를 구분(`sma(5)≠sma(20)`, D1). Formula 메모는 `formula_id`로 다단 DAG의 공유 참조를 1회만 계산(위상 재사용).
- **격리 보장**: 캐시 소유권을 `EvaluationContext`에 두어 GC 경계 == 수명 경계. 종목·전략·실행 간 캐시 히트 부재를 테스트로 검증(NFR-05, OT-1).

### 6.3 평가 재귀 · 방어적 순환 가드 (FR-05, DAG 저장 시점 보장)

```
evaluate_formula(expr, ctx):
    match expr.node / expr.kind (태그 순회 — duck typing, DESIGN-R02 §3.9):
      "binary": binary_arith(op, evaluate_formula(left), evaluate_formula(right))   # §6.1
      "unary" : -evaluate_formula(operand)
      "factor": _eval_factor_operand(expr, ctx)                                     # §3.5
      "constant": broadcast(expr.value, ctx.index)                                  # §6.1
      "formula":
          if expr.formula_id in ctx._formula_cache: return 캐시
          if expr.formula_id in ctx._visiting: raise EvaluationError(순환 힌트)      # 방어적 가드
          ctx._visiting.add(fid); f = ctx.resolve_formula(fid)
          series = evaluate_formula(f.expression, ctx)[f.output_column 상당]
          ctx._visiting.discard(fid); ctx._formula_cache[fid] = series; return series
```

- DAG 비순환은 R02 저장 시점 보장(`DESIGN-R02 §6.2` DFS)이나 **방어적 `_visiting` 가드**를 유지한다(FR-05, 미검증 리졸버 대비). 다이아몬드(공유 참조)는 메모 히트로 1회만 계산.
- `evaluate_rule`은 R02 Rule 트리(`Node`, `DESIGN-R02 §3.5`)를 `.node`("predicate"/"composition") 태그 순회로 평가: Predicate→좌/우 평가 후 §6.1 비교·교차, Composition→AND/OR/NOT.

### 6.4 데이터 계약 — required_data 전이 합집합 파생 (FR-09, TR-R03-011)

```
strategy_required_data(defn, resolve_rule, resolve_formula):
    acc: set[str] = set()
    # (1) factor_refs 직접 — R01 FactorMetadata.required_data(DESIGN-R01 §3) 조회
    for fr in defn.factor_refs: acc |= set(FactorMetadata(fr.factor_id).required_data)
    # (2) rule 슬롯 전이 — entry+exit rule 각각, FormulaOperand는 R02 derive_required_data 소비
    for rid in defn.rule.entry + defn.rule.exit (rule 슬롯 존재 시):
        for op in walk_operands(resolve_rule(rid).root):     # 태그 순회(duck typing)
            if op.kind == "factor":  acc |= set(FactorMetadata(op.factor_id).required_data)
            elif op.kind == "formula":
                acc |= set(derive_required_data(resolve_formula(op.formula_id), resolve_formula))  # DESIGN-R02 §3.4
    return acc     # {"ohlcv","valuation","financials"} 부분집합

평가 전 게이트:
    need = strategy_required_data(...)
    for kind in need:
        if kind == "valuation" and ctx.data.valuation is None: raise MissingDataError(kind + 요구 id)
        if kind == "financials" and ctx.data.financials is None: raise MissingDataError(kind + 요구 id)
```

- 파생은 R02 `derive_required_data`(`DESIGN-R02 §3.4`) + R01 `FactorMetadata.required_data`(`DESIGN-R01 §3`)를 **조합만** 한다(신규 파생 로직 0). `MissingDataError`는 누락 프레임 종류 + 이를 요구한 factor/formula id를 힌트에 포함(§3.9). ohlcv-only 전략 집합은 valuation/financials 부재 → 부가 로딩 스킵(§6.5, AC-04).

### 6.5 Daily 통합 삽입 지점 (FR-14~18, §7.4와 연계)

```
DailyJob.run(now, ...):                                # 단일 진입점·run_id 관례 유지(TRD-R01 §8.2)
    seed_builtin_strategies(svc, now)                  # 전환 시드 인라인 멱등(§7.4, C2-i)
    active = svc.list_active()                          # 실행 집합(id 정렬)
    if not active: raise WorkspaceError("활성 전략 0건")  # 조용한 no-op 금지(FR-14, OT-8)
    active_defns = [svc.get_strategy(sid) for sid in active]

    # universe 해석(D5, FR-15): 수집 대상 = watchlist ∪ ⋃ 활성 universe.symbols
    collect_symbols = set(watchlist) | union(d.universe.symbols for d in active_defns)
    # 부가 데이터 자동 수집(FR-16): 활성 required_data 합집합에 valuation/financials 있으면
    #   R01 FundamentalProvider·upsert·품질 게이트 경로 재사용(fetch-fundamental 동일 경로). 없으면 스킵.
    ohlcv = DataProvider.fetch(collect_symbols); fundamentals = 조건부 수집(§6.4)

    for defn in active_defns:                            # 전략별
        run_symbols = defn.universe.symbols or watchlist  # 빈 목록 = watchlist 전체(D5)
        for sym in run_symbols:                          # 실패 격리 단위(전략×종목, FR-17)
            try:
                input_sym = build_factor_input(sym, ohlcv, fundamentals)  # FactorInput 구성(R01 로더)
                report = run_backtest(defn, {sym: input_sym}, ...)         # §3.6
                signal = SignalClassifier(report)         # baseline 다운스트림(TRD-R01 §8.2 앵커)
                report_a = ReportA(signal); report_b = ReportB(signal, llm)  # Report A 결정론·B는 mock 시
                notify(outbox, ...)                       # content-hash outbox 재사용(FR-18)
            except (EvaluationError, DataError) as e:
                log_run_event(run_id, defn.id, sym, e)    # run_events 격리 기록, 배치 계속
```

- 코드형 5종 조립 표현은 **부재**한다(중복 구현하지 않음) — 전략 원천이 활성 선언형 단일로 수렴(D3, FR-14). `settings.strategy.enabled` 선택 기전은 두지 않는다. 다운스트림(신호→Report A/B→outbox)은 baseline 재사용·무변경(FR-18, INV-2).
- 실패 격리(FR-17): 전략×종목 try 경계로 한 단위 실패가 배치를 중단하지 않는다(ADR-R03-06). 격리 오류는 `EvaluationError`·수집 실패를 포괄하고 사유·전략 id·종목을 `run_events`(baseline 8테이블)로 기록.

### 6.6 검증 설계 요약

| 검증 지점 | 소비 계약 | 신규 로직 |
|---|---|---|
| 전이 검증(`validate_strategy`) | R02 `validate_definition`/`validate_rule`/`validate_formula`(+리졸버) | 0(조합만) |
| runnable 판정 | R02 `is_runnable` | 0(소비) |
| 저장 게이트 | R02 `upsert_*`(엄격 검증 내장) | 0(위임) |
| 활성 참조 보호 | R02 리졸버 + `list_active` 폐포(§7.2) | 폐포 순회(파사드 책임) |
| 데이터 계약 | R01 `FactorMetadata.required_data` + R02 `derive_required_data` | 0(조합) |
| Import 무결성 | R02 저장 게이트(dangling·순환·params) | 위상 순서·충돌 3분기(파사드) |

---

## 7. 영속화/CRUD + 호출자 책임 경계

### 7.1 책임 경계 개요

- **storage 계층**(`storage/db.py` `Database`)이 R02 3엔티티 CRUD·저장 게이트(`DESIGN-R02 §7.2`)와 R03 2테이블(`strategy_activation`·`strategy_templates`) 접근을 제공한다.
- **파사드**(`WorkspaceService`)는 CRUD를 storage에 위임하고, storage가 알 수 없는 **활성 상태 게이트·전이 검증 조합·평가/백테스트 오케스트레이션**만 추가한다(TR-R03-002). 저장 계층은 활성 상태를 모르므로 활성 참조 보호는 파사드 책임(`DESIGN-R02 §7.3` 위임 명시).

### 7.2 활성 참조 보호 — 온디맨드 전이 폐포 (FR-04a, C1-i)

```
_active_blockers(target_kind, target_id):        # 반환: 차단 활성 전략 id 목록(정렬)
    blockers = []
    for sid in list_active():                     # 활성 전략 각각
        defn = get_strategy(sid)
        if target_kind == "strategy" and sid == target_id:
            blockers.append(sid); continue
        closure = transitive_closure(defn)         # 참조 Rule ∪ 참조 Formula(리졸버로 확장)
        if (target_kind, target_id) in closure:
            blockers.append(sid)
    return sorted(blockers)

transitive_closure(defn):                          # (kind, id) 집합
    #   rule 슬롯 entry+exit rule id 수집 → 각 Rule의 FormulaOperand.formula_id 수집 →
    #   Formula 전이 참조(resolve_formula) 확장. duck typing 태그 순회(DESIGN-R02 §3.9).
```

- upsert/delete 진입점(`upsert_strategy`/`upsert_rule`/`upsert_formula`/`delete_*`)이 저장 게이트 호출 **전** `_guard_active_reference`(§3.4)를 호출한다. blockers 비어있지 않으면 차단(전략 id 목록 사유). 상태 무보유(색인 테이블 없음) → drift 0.
- Import `--overwrite`도 이 게이트를 우선 적용(FR-04a 우선, §3.8/§7.3).

### 7.3 Import 위상 순서·충돌 처리 (FR-23)

```
import_strategy(bundle, now, on_conflict):
    for entity in (bundle.formulas ++ bundle.rules ++ [bundle.strategy]):   # 위상 순서 Formula→Rule→Strategy
        existing = get_*(entity.id)
        if existing is None:            upsert_*(entity, now)               # 신규
        elif canonical_eq(existing, entity):   pass                        # 동일 → 멱등 통과(DESIGN-R02 §6.1)
        elif on_conflict == "overwrite":
            _guard_active_reference(kind, entity.id)                       # FR-04a 우선(§7.2)
            upsert_*(entity, now)                                          # 대체
        else:                           raise WorkspaceError("id 충돌 …")   # 상이 → 거부
```

- 참조 무결성(dangling·순환·컬럼 불일치·params 위반)은 각 `upsert_*` 저장 게이트(R02 엄격 검증)가 거부한다(신규 검증 0). 위상 순서로 Formula가 Rule보다, Rule이 Strategy보다 먼저 저장되어 저장 시점 참조 존재를 보장.

### 7.4 전환 시드 멱등 (FR-14a, C2-i)

```
seed_builtin_strategies(svc, now):                 # Daily 부트스트랩 인라인(§6.5)
    for tid, bundle in BUILTIN_TEMPLATES.items():   # 5종
        if svc.get_strategy(bundle.strategy.id) is not None:
            continue                                # 멱등 가드 — 존재 시 정의·활성 무변경(사용자 결정 보존)
        for f in bundle.formulas: svc.upsert_formula(f, now=now)
        for r in bundle.rules:    svc.upsert_rule(r, now=now)
        svc.upsert_strategy(bundle.strategy, now=now)
        svc.activate(bundle.strategy.id, now=now)   # 자동 활성화(운영 연속성, D3)
```

- 멱등·1회성: 각 Template 전략 id 존재 검사가 멱등 판정 지점. 이미 존재하면 정의·활성 상태를 **일절 변경하지 않는다**(재실행이 사용자의 비활성화·수정을 덮어쓰지 않음, OT-4). 최초 전환 시에만 5종 생성+활성.

---

## 8. 마일스톤 (M0..M5 — 논리 단위)

| M | 범위 | 완료 신호 |
|---|---|---|
| M0 | 모듈 골격(`workspace/`·`jobs/`) + INV-1 단방향 AST 스캔 + 2테이블 DDL | 스캔 green·DDL 멱등(AC-R03-09 부분) |
| M1 | `WorkspaceService` 파사드 + CRUD 위임 + 전이 검증 조합 + 활성화·활성 참조 보호 게이트 | AC-R03-01/02 |
| M2 | 평가 엔진(`evaluate_formula`·`evaluate_rule`) + 파라미터 해석·캐시(`EvaluationContext`) + 수치 규약 강제점(`numeric.py`) + 데이터 계약 | AC-R03-03/04 |
| M3 | 백테스트 어댑터(`build_signals`·`run_backtest`, baseline 엔진·지표 재사용) + 백테스트 CLI | AC-R03-05 |
| M4 | Daily 통합(실행 집합·코드형 선택 기전 부재·전환 시드·universe 해석·부가 수집·실패 격리·다운스트림 동형) | AC-R03-06 |
| M5 | Template 5종·`create_from_template`·사용자 Template + Import/Export 위상 순서·충돌 3분기 | AC-R03-07/08 |

> 마일스톤은 문서상 논리 단위다(스프린트 분할은 구현 계획 시점 확정). Daily 통합(M4)은 하위 평가·백테스트(M2/M3) 확정 후 마지막 배선 단계다.

---

## 9. 문서화 체크리스트

- [ ] §3 파사드 API 전부 확정: `WorkspaceService`(CRUD 위임·`validate_strategy`·`activate`/`deactivate`/`is_active`/`list_active`·`backtest`·Template·Import/Export), `evaluate_formula`/`evaluate_rule`/`EvaluationContext`, `build_signals`/`run_backtest`/`BacktestReport`, `StrategyBundle`/`TemplateInfo`, `EvaluationError` 계층.
- [ ] INV-1 단방향 AST 스캔 규칙(하위 순수성 무변경 green + 정의 패키지 `workspace`/`jobs` import 부재).
- [ ] 수치 규약 6종을 `numeric.py` 단일 강제점 배치(FR-08, evaluate_formula·evaluate_rule·백테스트 공유).
- [ ] 캐시 키 `(factor_id, canonical(params))`·수명 (전략,종목) 컨텍스트 한정(FR-07).
- [ ] required_data 전이 합집합 파생(R01·R02 조합) + `MissingDataError`(누락 종류+id).
- [ ] 백테스트 baseline `Portfolio.from_signals`/`BacktestMetrics` 재사용(신규 엔진·산식 0, TRD-R01 §8.2 앵커).
- [ ] Daily 삽입 지점(코드형 5종 부재·활성 선언형 단일·전환 시드 멱등·universe 해석·부가 수집·실패 격리·다운스트림 동형).
- [ ] Built-in 5종 번들(D1·D2, 즉시 runnable)·`create_from_template`·`save_as_template`(Built-in id 충돌 거부·출처 구분 열거).
- [ ] Import/Export 위상 순서(Formula→Rule→Strategy)·충돌 3분기·FR-04a 우선.
- [ ] 2테이블 additive DDL(`strategy_activation`·`strategy_templates`, 기존 DDL 무변경).
- [ ] 오류 모델 한국어 + 행동 힌트, CLI non-zero 종료.
- [ ] **CLI 변경 시 README 사용법 동기화**(AC-09) — `strategy-*`/`rule-*`/`formula-*` 명령 목록(PRD-R03 §10 확정)과 대조. 편집 의미론=전체 JSON 교체.
- [ ] §11 테스트: 합성 Fixture + 격리 DuckDB + LLM mock + pytest 결정론(2회 동일), 기대값 하드코딩 금지(수치 규약 재도출).
- [ ] TRD-R03 TR-R03-001~027과 모순 없음, `DESIGN-R01 §3`·`DESIGN-R02 §3` 재정의 없음.

---

## 10. ADR

### ADR-R03-01 — 평가 캐시를 (전략,종목) 컨텍스트 소유 dict로 (캐시 키 = canonical params)
- **Decision**: 팩터·Formula 캐시를 `EvaluationContext`가 소유(수명 = 단일 (전략,종목)), 캐시 키 = `(factor_id, canonical_json(params))`.
- **Drivers**: FR-07 캐시 수명 한정·D1 파라미터 오버라이드 구분(`sma(5)≠sma(20)`) · 데이터 오염·비결정 차단.
- **Alternatives**: 모듈 전역 LRU/dict(종목·전략·실행 간 공유 → 오염, FR-07 위반), `frozenset(params)` 키(`30`vs`30.0` 타입 보존 미흡).
- **Consequences**: 컨텍스트 GC 경계 == 캐시 수명 경계. 재실행 캐시 히트 없음(의도된 격리, NFR-05).

### ADR-R03-02 — 활성 참조 보호를 상태 무보유 온디맨드 전이 폐포로
- **Decision**: upsert/delete 진입에서 `list_active` 각 전략의 전이 참조 폐포를 리졸버로 산출해 대상 포함 여부 판정.
- **Drivers**: 상태 무보유 → drift 0(색인 동기화 불요) · R02 리졸버 재사용 · 결정론.
- **Alternatives**: 역참조 인덱스 테이블(색인 동기화 필요 → dangling 색인 drift, 신규 DDL·트리거).
- **Consequences**: 변경마다 활성 폐포 재계산(단일 종목·소규모 활성 집합에서 무시). store가 유일 진실 원천.

### ADR-R03-03 — 전환 시드를 Daily 부트스트랩 인라인 멱등으로
- **Decision**: Daily 실행 집합 조회 직전 `seed_builtin_strategies` 인라인 호출, 각 Template id 존재 검사로 멱등.
- **Drivers**: FR-14a 자동 시드·D3 운영 연속성("끊김 없이") · 멱등·1회성 국소화.
- **Alternatives**: 별도 마이그레이션 CLI(운영자 누락 시 활성 0건 실패, FR-14a 이탈).
- **Consequences**: Daily 경로에 시드 판정 1회 추가(id 존재 검사 5회). 사용자 비활성화·수정 결정 비덮어쓰기(OT-4).

### ADR-R03-04 — Export/Import·Template 번들을 단일 `StrategyBundle`로
- **Decision**: strategy + 전이 참조 rules·formulas를 하나의 `StrategyBundle`(canonical to_dict)로 직렬화.
- **Drivers**: 왕복 원자성·위상 순서 자연 표현 · R02 to_dict 재사용(신규 직렬화 0).
- **Alternatives**: 엔티티별 분리 파일(왕복·위상 순서 관리 복잡).
- **Consequences**: Built-in Template도 동일 번들 형상 — 단일 실행 경로(INV-2)와 정합.

### ADR-R03-05 — 수치 규약을 단일 공유 헬퍼(`numeric.py`)로
- **Decision**: FR-08 6종을 `workspace/numeric.py` 단일 강제점에 배치, 전 평가·백테스트 사상이 경유.
- **Drivers**: 규약 drift·우회 차단(OT-6) · 결정론(INV-3) 단일 원천.
- **Alternatives**: 각 평가 경로 인라인(NaN·교차 처리 불일치 → 경계 오답).
- **Consequences**: reindex 정렬만(보간 없음)·NaN→False 불리언화 직전·div0→NaN·교차 shift·스칼라 브로드캐스트가 한 지점에서 강제됨.

### ADR-R03-06 — 실패 격리 단위를 전략×종목으로
- **Decision**: Daily 평가·백테스트 루프를 전략×종목 try 경계로 감싸 부분 실패 격리.
- **Drivers**: FR-17 부분 실패 격리 · NFR-07 배치 완주.
- **Alternatives**: 전략 단위(한 종목 실패가 전략 전체 중단), 배치 전체(한 단위 실패가 전량 중단).
- **Consequences**: 격리 오류를 `run_events`(baseline)로 기록, 배치 계속. `EvaluationError`·수집 실패 포괄.

> 본 계획 메타 결정(6편 분할·계층 순차)은 상위 계획 문서 ADR 소관이며 여기서 다루지 않는다.

---

## 11. 픽스처 및 테스트 매핑

### 11.1 합성 Fixture

- **데이터 Fixture**: R01 OHLCV/펀더멘털 픽스처(합성 CSV, 종목 정합) + R02 정의 팩토리(코드 산출)를 재사용한다. `FixtureAdapter`(OHLCV)·`FixtureFundamentalAdapter`(`DESIGN-R01 §3.11`)로 네트워크 없이 `FactorInput` 구성.
- **격리·주입**: `tmp_path` 격리 DuckDB + `LLM_MOCK=true`(MockProvider) + `now`·`run_id` 주입으로 실데이터·실LLM·시각 의존 0(NFR-02). 결정론은 **2회 실행 동일**(신호·Report A 범위, INV-3).
- **경계 케이스 의도 포함**: `sma(5)` vs `sma(20)` 파라미터 오버라이드(상이 시계열 + 골든크로스 교차 발생), NaN→False·div0→NaN·스칼라 교차, 다단 DAG 위상, ohlcv-only 전략 집합(부가 로딩 0), valuation/financials 요구 전략(`MissingDataError`), 활성 참조 수정·삭제 거부, 전환 시드 재실행 무변경, Import 충돌 3분기.
- **기대값 하드코딩 금지**: 평가 결과(Formula 파생 시계열·Rule 불리언·교차)는 테스트가 §5.4 수치 규약을 pandas로 **독립 재도출**해 대조한다(골든 상수 금지, TR-R03-026).

### 11.2 AC → 테스트 모듈 매핑

| AC | 테스트(예시 경로) | 검증 핵심 |
|---|---|---|
| AC-R03-01 | `tests/unit/workspace/test_facade_crud.py` | 파사드/CLI 왕복(생성→조회→수정→삭제 DB 재조회 일치)·오류 non-zero |
| AC-R03-02 | `tests/unit/workspace/test_activation.py` | 활성화 idempotent·초안/검증실패/미존재 거부·활성 참조 수정·삭제 거부(전략 id 포함·비활성 후 허용) |
| AC-R03-03 | `tests/unit/workspace/test_evaluation.py` | Formula 다단 DAG 위상·Rule 비교/AND/OR/NOT/교차·params 오버라이드(sma5≠sma20+골든크로스)·NaN→False·div0→NaN·스칼라 교차·2회 동일 |
| AC-R03-04 | `tests/unit/workspace/test_data_contract.py` | required_data 미충족 `MissingDataError`(누락 종류+id)·ohlcv-only 부가 로딩 0(spy) |
| AC-R03-05 | `tests/unit/workspace/test_backtest.py` | fixture 최소 지표 산출(baseline 엔진·지표)·CLI 표시·runnable 아님 실행 전 거부 |
| AC-R03-06 | `tests/integration/test_daily_declarative.py` | 활성 집합 id 정렬·universe 해석(부분 종목+수집 합집합)·전략×종목 실패 격리 완주·활성 0건 실패·펀더멘털 자동 수집·전환 시드 멱등·신호→리포트→알림 통과(LLM mock) |
| AC-R03-07 | `tests/unit/workspace/test_templates.py` | Built-in 5종 즉시 검증·runnable·fixture 백테스트 완주·`save_as_template`→`create_from_template` 왕복 canonical 동등 |
| AC-R03-08 | `tests/unit/workspace/test_import_export.py` | export 2회 바이트 동일·위상 순서 저장·dangling/순환 거부·충돌 3분기(FR-04a 우선) |
| AC-R03-09 | `tests/unit/workspace/test_purity_ast.py` | R01/R02 순수성 스캔 무변경 green + 정의 패키지 `workspace`/`jobs` import 부재·README 동기화·`ruff` 0 위반 |

- 통합 테스트(`test_daily_declarative.py`)는 `tmp_path` 격리 DuckDB + `FixtureAdapter` + `LLM_MOCK=true` + 주입 `now`/`run_id`로 외부 의존 없이 전체 Daily 파이프라인을 결정론 검증한다(2회 실행 동등, NFR-01).

---

**추적성 요약**: FR-01~23(FR-04a·FR-14a 포함) · AC-01~09 · INV-1~4 · D1~D5 전건이 §3 파사드 API + §5 DDL + §6 알고리즘 + §7 CRUD·게이트 + §11 테스트로 매핑된다(공백 0). §3은 상위 파사드 API(`WorkspaceService`·`evaluate_formula`·`evaluate_rule`·`EvaluationContext`·`build_signals`/`run_backtest`·`StrategyBundle`·`EvaluationError` 계층)를 확정하고, 하위 시그니처(`DESIGN-R01 §3`·`DESIGN-R02 §3`)는 재정의 없이 링크 인용한다(§D-2). baseline 재사용 자산은 `TRD-R01 §8.2` 앵커 명칭으로만 인용한다(§D-5). FR-08 수치 규약·Built-in 5종 정의 표·CLI 목록·Import 충돌 3분기는 PRD-R03이 확정한 항목으로 §6/§7에서 소비·강제 형상만 확정하고 재서술하지 않는다(§D-9). 본 문서는 TRD-R03 TR-R03-001~027(C1-i/C2-i/C3-i 배선)과 정합한다.

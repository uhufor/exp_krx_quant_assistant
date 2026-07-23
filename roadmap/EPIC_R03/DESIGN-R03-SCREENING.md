# DESIGN-R03 : No-Code Stock Screening

**대응 PRD**: `PRD-R03-SCREENING.md` / **짝 TRD**: `TRD-R03-SCREENING.md`
**계층**: 신규 독립 패키지(`screening/`) / **의존**: `factors/`(계산 위임)·`data/`(DI)·`workspace/numeric`(leaf 공유) / **소비자**: 없음(최상위, CLI/GUI)
**Status**: Approved for implementation
**전제**: 본 문서는 main 브랜치 시점에서 No-Code Stock Screening을 처음 구현한다고 가정한다. 모든 설계 서술은 PRD-R03 + TRD-R03 + README §4/§5 역추적으로만 정당화한다.

---

## 1. 개요

### 1.1 목적

`screening/` 패키지의 구현 형상(모듈 구조·타입 시그니처·DDL·알고리즘 의사코드·ADR)을 확정한다.

### 1.2 결정론 범위

스크리닝 실행은 (조건 정의 + as-of 데이터) → 통과 종목 리스트로 결정론적이다. 단, "최근 거래일" 기준 실행은 실행 시각에 의존하므로(스크리닝의 본질 — 매번 최신 시장 상태를 조회), 결정론은 **동일 as-of 날짜 + 동일 데이터**를 전제로 한다(신호·백테스트의 "동일 정의+데이터=동일 출력"과 같은 원칙, 시각만 as-of 날짜로 명시 고정).

---

## 2. 모듈 구조 및 의존 방향

```
quant_krx/
├── screening/                        # 완전 신규 독립 패키지
│   ├── __init__.py                   #   공개 API 재노출
│   ├── errors.py                     #   MalformedDefinitionError, EmptyUniverseError,
│   │                                 #   UnsupportedFilterError (rule/errors.py 패턴 참고, 독립)
│   ├── definition.py                 #   Predicate/Composition/Operand/WindowPredicate/
│   │                                 #   RankPredicate/ScreeningCondition (rule.definition 미참조)
│   ├── dispatch.py                   #   node_from_dict (4개 태그, rule과 독립)
│   ├── evaluation.py                 #   _eval_screening_node — leaf는 workspace.numeric 공유,
│   │                                 #   폴딩(AND/OR/NOT)은 독립 구현
│   ├── ranking.py                    #   compute_cross_sectional_rank — fetch_market_snapshot DI 소비
│   ├── universe.py                   #   resolve_scan_universe — list_symbols + 4종 필터
│   ├── universe_data.py              #   OHLCV 캐시(신규) — ohlcv_daily 갭필
│   └── service.py                    #   ScreeningService 파사드(WorkspaceService 패턴 참고)
├── factors/catalog/technical.py      #   (확장) TradingValueFactor/VolumeFactor/RollingHighFactor
├── data/base.py                      #   (확장) DataProvider.fetch_market_snapshot
├── data/pykrx_adapter.py             #   (확장) PyKrxAdapter.fetch_market_snapshot
├── data/fixture_adapter.py           #   (확장) FixtureAdapter.fetch_market_snapshot
├── data/screening_schema.py          #   screening_conditions additive DDL
├── api/routers/screenings.py         #   (신규) GUI API
├── __main__.py                       #   (확장) screen-* typer 커맨드
└── (소비 대상 — 무변경 참조)
    ├── quant_krx.factors             #   get_factor·compute_factor (R01, 무변경)
    ├── quant_krx.workspace.numeric   #   compare·crosses (leaf 공유, 무변경)
    └── quant_krx.data                #   DataProvider(확장, 기존 메서드 무변경)
```

- **`rule/`, `formula/`, `strategy/`, `workspace/evaluation.py`, `workspace/service.py`는 본 EPIC에서 코드 한 줄도 변경하지 않는다**(Non-Goal, 확정).
- `screening/`은 `factors/`·`data/`·`workspace/numeric`을 **소비만** 한다(역주입 없음).

### 2.2 의존 방향

```
        (CLI / GUI)
             │
             ▼
      quant_krx.screening              ← 신규 독립 최상위
             │  소비만(역주입 0), rule/formula/strategy 미참조
   ┌─────────┼─────────────┬───────────────┐
   ▼         ▼              ▼               ▼
 R01 팩터  workspace.numeric  data(DI)    storage
 (계산 위임) (leaf 공유)      (프로토콜 확장)  (신규 테이블)
```

- **격리 스캔**: `screening/` import 그래프에 `quant_krx.rule`, `quant_krx.formula`, `quant_krx.strategy`, `quant_krx.workspace.evaluation`, `quant_krx.workspace.service`가 **0건**임을 정적 스캔으로 강제(신규 AST 테스트, `tests/unit/screening/test_isolation_ast.py`). `quant_krx.workspace.numeric`만 허용 예외.

---

## 3. 도메인 타입 시그니처

### 3.1 스키마 (`screening/definition.py`)

```python
SCHEMA_VERSION = 1

@dataclass(frozen=True, eq=False)
class FactorOperand(CanonicalEq):
    factor_id: str
    column: str
    params: Mapping[str, Any] = field(default_factory=dict)
    kind: ClassVar[str] = "factor"

@dataclass(frozen=True, eq=False)
class ConstantOperand(CanonicalEq):
    value: int | float
    kind: ClassVar[str] = "constant"

@dataclass(frozen=True, eq=False)
class FormulaOperand(CanonicalEq):
    formula_id: str
    column: str = "value"
    kind: ClassVar[str] = "formula"

Operand = FactorOperand | ConstantOperand | FormulaOperand

@dataclass(frozen=True, eq=False)
class Predicate(CanonicalEq):
    left: Operand
    operator: str          # ">", ">=", "<", "<=", "==", "!=", "crosses_above", "crosses_below"
    right: Operand
    node: ClassVar[str] = "predicate"

@dataclass(frozen=True, eq=False)
class WindowPredicate(CanonicalEq):
    inner: "Node"
    n_bars: int             # >= 0
    include_current_bar: bool
    node: ClassVar[str] = "window_predicate"

@dataclass(frozen=True, eq=False)
class RankPredicate(CanonicalEq):
    factor_id: str           # "trading_value" | "volume" | 기타
    column: str
    params: Mapping[str, Any] = field(default_factory=dict)
    rank_metric: str = "desc"   # "asc" | "desc"
    top_n: int = 100
    node: ClassVar[str] = "rank_predicate"

@dataclass(frozen=True, eq=False)
class Composition(CanonicalEq):
    op: str                  # "AND" | "OR" | "NOT"
    operands: tuple["Node", ...]
    node: ClassVar[str] = "composition"

Node = Predicate | WindowPredicate | RankPredicate | Composition

@dataclass(frozen=True, eq=False)
class ScanUniverse(CanonicalEq):
    market: str = "KRX"                              # KOSPI+KOSDAQ 합산
    exclusion_filters: frozenset[str] = frozenset()   # {"etf","etn","preferred","spac", ...예약 6종}

@dataclass(frozen=True, eq=False)
class ScreeningCondition(CanonicalEq):
    id: str
    name: str
    version: str
    universe: ScanUniverse
    root: Node
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
```

- `rule.definition`을 어디에도 import하지 않는다(정적 스캔 강제, §2.2). 각 타입의 `to_dict`/`from_dict`는 `rule/definition.py:31-225` 패턴을 참고해 독립 구현한다.
- **6종 예약 필드 검증**: `ScanUniverse.__post_init__`(또는 `ScreeningCondition` 저장 게이트)이 `exclusion_filters ∩ {administrative_issue, investment_alert, trading_halt, liquidation_trading, market_alert, unfaithful_disclosure}`가 비어있지 않으면 `UnsupportedFilterError`를 raise한다(TR-R03S-011).

### 3.2 디스패치 (`screening/dispatch.py`)

```python
_NODE_DISPATCH: dict[str, type] = {
    "predicate": Predicate,
    "window_predicate": WindowPredicate,
    "rank_predicate": RankPredicate,
    "composition": Composition,
}

def node_from_dict(d: Mapping[str, Any]) -> Node:
    #   rule.definition.node_from_dict와 완전 독립 — 별도 함수, 별도 dict.
    #   Composition.from_dict는 이 함수를 재귀 호출해 자식을 구성한다(rule.definition.Composition.from_dict를
    #   사용하지 않음 — 그쪽은 predicate/composition 2개 태그만 알아 여기서 재사용 불가, TRD 결정 축 A 근거).
    ...
```

### 3.3 평가 엔진 (`screening/evaluation.py`)

```python
from quant_krx.workspace.numeric import compare, crosses   # leaf 공유(A2', 유일한 외부 참조)

@dataclass
class ScreeningEvaluationContext:
    ohlcv: pd.DataFrame              # 종목별 OHLCV(동적 lookback으로 잘라낸 구간)
    index: pd.DatetimeIndex
    _factor_cache: dict[tuple[str, str, str], pd.Series] = field(default_factory=dict)

def _eval_screening_node(node: Node, ctx: ScreeningEvaluationContext) -> pd.Series:
    if isinstance(node, Predicate):
        left = _eval_operand(node.left, ctx)
        right = _eval_operand(node.right, ctx)
        if node.operator in ("crosses_above", "crosses_below"):
            return crosses(node.operator, left, right)        # leaf 공유
        return compare(node.operator, left, right)             # leaf 공유
    if isinstance(node, WindowPredicate):
        inner_result = _eval_screening_node(node.inner, ctx)   # bool Series
        window = node.n_bars + (1 if node.include_current_bar else 0)
        return inner_result.rolling(window, min_periods=1).max().astype(bool)
        #   현재봉 포함 시 window=n_bars+1(t..t-n_bars), 미포함 시 shift(1) 후 동일 rolling(TR-R03S-004)
    if isinstance(node, Composition):
        children = [_eval_screening_node(c, ctx) for c in node.operands]
        #   AND/OR/NOT 폴딩 — workspace/evaluation.py::_eval_rule_node(:121-133)와
        #   동일 의미론을 독립 구현(코드 비공유, 크로스-패리티 테스트로 동등성 보증, A2').
        if node.op == "AND":
            result = children[0]
            for c in children[1:]: result = result & c
            return result
        if node.op == "OR":
            result = children[0]
            for c in children[1:]: result = result | c
            return result
        return ~children[0]   # NOT
    if isinstance(node, RankPredicate):
        raise ScreeningError("RankPredicate는 universe 단위 평가 전용 — ranking.py로 위임")
    raise ScreeningError(f"미지의 노드: {node!r}")
```

- **RankPredicate는 종목별 시계열 평가 대상이 아니다** — `ScreeningService.run()`이 조건 트리에서 `RankPredicate` 리프를 별도로 추출해 `ranking.py::compute_cross_sectional_rank()`로 유니버스 전체에 대해 1회 계산한 뒤, 그 결과(통과 종목 집합)를 나머지 시계열 조건 결과와 AND/OR로 결합한다(트리 evaluate 도중 인라인 호출이 아님 — 순위는 유니버스 단위, 나머지는 종목 단위이므로 평가 스테이지가 분리됨).

### 3.4 순위 엔진 (`screening/ranking.py`)

```python
def compute_cross_sectional_rank(
    provider: DataProvider, symbols: list[str], *, as_of: date, market: str,
    rank_predicate: RankPredicate,
) -> set[str]:
    #   TR-R03S-005 — provider DI로 스냅샷 1콜(또는 KOSPI/KOSDAQ 2콜), 종목별 순차 fetch 없음.
    snapshot = provider.fetch_market_snapshot(as_of, market)     # columns: symbol, close, volume, trading_value
    snapshot = snapshot[snapshot["symbol"].isin(symbols)]
    ascending = rank_predicate.rank_metric == "asc"
    ranks = snapshot.set_index("symbol")[rank_predicate.column].rank(method="min", ascending=ascending)
    return set(ranks[ranks <= rank_predicate.top_n].index)
```

### 3.5 유니버스 (`screening/universe.py`, `screening/universe_data.py`)

```python
_IMMEDIATE_FILTERS = frozenset({"etf", "etn", "preferred", "spac"})
_RESERVED_UNSUPPORTED = frozenset({
    "administrative_issue", "investment_alert", "trading_halt",
    "liquidation_trading", "market_alert", "unfaithful_disclosure",
})

def resolve_scan_universe(provider: DataProvider, exclusion_filters: frozenset[str]) -> list[str]:
    unsupported = exclusion_filters & _RESERVED_UNSUPPORTED
    if unsupported:
        raise UnsupportedFilterError(sorted(unsupported))     # TR-R03S-011
    symbols = set(provider.list_symbols(market="KRX"))          # KOSPI+KOSDAQ 합산(확인됨)
    if "etf" in exclusion_filters: symbols -= set(_krx_stock().get_etf_ticker_list())
    if "etn" in exclusion_filters: symbols -= set(_krx_stock().get_etn_ticker_list())
    if "preferred" in exclusion_filters: symbols -= _preferred_by_name_pattern(provider, symbols)
    if "spac" in exclusion_filters: symbols -= _spac_by_name_pattern(provider, symbols)
    if not symbols:
        raise EmptyUniverseError()          # TR-R03S-009 — 조용한 빈 결과 금지
    return sorted(symbols)
```

```python
def fetch_universe_ohlcv_cached(
    db: Database, provider: DataProvider, symbols: list[str], *, start: date, end: date,
) -> dict[str, pd.DataFrame]:
    #   TR-R03S-010 — ohlcv_daily 커버리지 조회 → 갭만 provider.fetch_ohlcv로 채움 → upsert.
    #   data_loading.py의 fundamental gap-fill 패턴(:28-61) 참고, OHLCV용 신규 구현.
    ...
```

### 3.6 데이터 프로토콜 확장 (`data/base.py`, `data/pykrx_adapter.py`, `data/fixture_adapter.py`)

```python
@runtime_checkable
class DataProvider(Protocol):
    # ... 기존 메서드(list_symbols/fetch_ohlcv/fetch_benchmark/fetch_metadata) 무변경 ...
    def fetch_market_snapshot(self, date: date, market: str = "KRX") -> pd.DataFrame: ...
    #   반환 컬럼 계약: symbol, close, volume, trading_value(네이티브 거래대금)

# PyKrxAdapter (신규 메서드)
def fetch_market_snapshot(self, date: date, market: str = "KRX") -> pd.DataFrame:
    s = _krx_stock()
    date_str = date.strftime("%Y%m%d")
    if market in ("KOSPI", "KRX"):
        df = pd.concat([
            s.get_market_ohlcv_by_ticker(date_str, market="KOSPI"),
            s.get_market_ohlcv_by_ticker(date_str, market="KOSDAQ"),
        ])
    else:
        df = s.get_market_ohlcv_by_ticker(date_str, market=market)
    #   컬럼 정규화: 종가/거래량/거래대금 → close/volume/trading_value, symbol=인덱스
    ...

# FixtureAdapter (신규 메서드) — 합성 스냅샷(테스트 결정론)
def fetch_market_snapshot(self, date: date, market: str = "KRX") -> pd.DataFrame: ...
```

### 3.7 서비스 (`screening/service.py`)

```python
class ScreeningService:
    def __init__(self, db: Database, provider: DataProvider) -> None: ...

    def upsert_condition(self, cond: ScreeningCondition, *, now: datetime) -> None: ...
    def get_condition(self, id: str) -> ScreeningCondition | None: ...
    def list_conditions(self) -> tuple[ScreeningCondition, ...]: ...
    def delete_condition(self, id: str) -> None: ...
    def validate_condition(self, cond: ScreeningCondition) -> ValidationResult: ...

    def run(self, condition_id: str, *, as_of: date | None = None) -> list[tuple[str, str]]:
        #   FR-13 — (동적 lookback 산정 → resolve_scan_universe → RankPredicate 유니버스 평가
        #   → 종목별 시계열 조건 평가 → AND/OR 결합) 후 (symbol, name) 리스트 반환. DB 저장 없음.
        ...
```

## 4. 데이터 구조 결정 (ADR 연계)

| 결정 축 | 옵션 | 채택 | 근거 |
|---|---|---|---|
| 조건 트리 구현 | rule import 재사용 vs 완전 독립 재구현 vs **폴딩 독립+leaf 공유** | **폴딩 독립+leaf 공유**(ADR-R03S-01, A2') | rule import는 기술적으로 불가능(하드바인딩), 완전 독립은 leaf 드리프트 위험 방치 |
| 순위 데이터 경로 | 종목별 순차 fetch vs PyKrx 하드코딩 vs **프로토콜 확장 DI** | **프로토콜 확장**(ADR-R03S-02, C3) | 성능(1~2콜)과 DI 원칙을 동시 충족 |
| 제외 필터 범위 | 10종 no-op vs **4종만 v1 + 6종 하드 비활성화** vs 6종 신규 데이터소스 통합 | **4종+하드 비활성화**(ADR-R03S-03, B2) | 안전(선택했는데 무효과 방지), 범위 통제 |
| 실행 결과 영속화 | 이력 테이블 추가 vs **조건 정의만 저장** | **조건 정의만**(ADR-R03S-04) | 사용자 확정, 재사용은 조건 재실행으로 충분 |
| OHLCV 재조회 | 매번 전체 재조회 vs **갭필 캐시**(신규) | **갭필 캐시**(ADR-R03S-05) | 반복 스크리닝 성능, 기존 fundamental 패턴 준용(신규 구현) |

## 5. 직렬화 규약 + DuckDB DDL

### 5.1 additive 진화 원칙

baseline 8테이블 + R01 2테이블 + R02 3테이블 + R03(워크스페이스) 2테이블은 **무변경**이다. 본 EPIC은 아래 **1테이블만 additive 추가**한다.

### 5.2 `screening_conditions`

```sql
CREATE TABLE IF NOT EXISTS screening_conditions (
    id            VARCHAR   NOT NULL,
    name          VARCHAR,
    body          JSON      NOT NULL,   -- ScreeningCondition.to_dict() canonical
    created_at    TIMESTAMP,
    updated_at    TIMESTAMP,
    PRIMARY KEY (id)
);
```

- 실행 결과/이력 테이블은 추가하지 않는다(FR-14, 사용자 확정).

## 6. 알고리즘 설계 요약

| 단계 | 소비 계약 | 신규 로직 |
|---|---|---|
| 조건 검증 | 독립 저장 게이트(왕복 무손실·6종 필터 거부) | 신규(schema-scoped) |
| 폴딩(AND/OR/NOT) | 독립 구현 | 신규(크로스-패리티 테스트로 rule과 동등성 보증) |
| leaf(compare/crosses) | `workspace.numeric` | 0(공유) |
| 순위 계산 | `DataProvider.fetch_market_snapshot`(신규 프로토콜 메서드) | 신규(엔진), 데이터는 프로토콜 확장 |
| 유니버스 필터 | pykrx `get_etf_ticker_list`/`get_etn_ticker_list`/명명 패턴 | 신규 |
| OHLCV 캐시 | `ohlcv_daily`(기존 테이블, 신규 갭필 로직) | 신규 |

## 7. ADR (요약)

- **Decision**: §4 표의 5개 결정 축(A2'/C3/B2/영속화/캐시) 채택.
- **Drivers**: rule 하드바인딩으로 인한 재사용 불가, leaf-폴딩 위험 비대칭, pykrx 데이터 한계, DI-성능 모순.
- **Alternatives considered**: A1(rule 전체 재사용, 불가능), A3(공유 트리워커+rule 리팩터링, Non-Goal 위반), B1(10종 no-op, 안전 이슈), B3(6종 신규 데이터소스, 범위초과), C1/C2(순차fetch/하드코딩, 성능·DI 위반).
- **Consequences**: `screening/`↔`rule/` 간 폴딩 로직만 형태적 중복(크로스-패리티 테스트 보증), leaf는 코드 공유로 드리프트 불가. `DataProvider` 프로토콜 확장이 모든 어댑터에 파급되나 screening이 실제 주입하는 PyKrx/Fixture만 필수 구현.
- **Follow-ups**: 6종 필터 사용자 재확인 / A3 향후 재검토 여지 / 성능 벤치마크 실측 / `FDRAdapter.fetch_market_snapshot` 조사.

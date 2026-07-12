# DESIGN-R01 : Factor Platform

**대응 PRD / TRD**: `PRD-R01-FACTOR_PLATFORM.md` · `TRD-R01-FACTOR_PLATFORM.md`
**계층**: R01 (최하위, 순수 — 실행·저장·백테스트 무의존) / **소비자**: R02(참조 검증), R03(평가·실행)
**Status**: Draft for review
**전제**: 본 문서는 main 브랜치 시점에서 팩터 플랫폼을 **처음 구현한다**고 가정한다. 모든 설계 서술은 PRD-R01 + `README.md`(§4 D1~D5 · §5 공통 불변 원칙 7) + TRD-R01 역추적으로만 정당화한다.

> **문서 지위(§D-2)**: 본 문서의 **§3(도메인 타입 시그니처)은 상위 계층(R02/R03)이 인용하는 확정 원천**이다. R02/R03 DESIGN·TRD는 시그니처를 재정의하지 않고 "DESIGN-R01 §3 `<이름>` 참조"로만 링크한다. 따라서 §3의 정밀도·완결성이 본 문서의 최우선 산출물이다.
>
> **범위 규율(R5)**: 본 문서는 시그니처·DDL·알고리즘 의사코드·핵심 로직 서술·ADR까지만 확정한다. 완전한 함수 본문은 두지 않는다(산식 자체는 PRD §4 표가 권위 원천이므로 재서술하지 않고 구현 규칙만 명시).

---

## 1. 개요

### 1.1 목적

팩터(투자 지표)를 플랫폼 1급 자원으로 제공하는 **순수 계산 계층**과 이를 뒷받침하는 **펀더멘털 데이터 계층**의 구현 형상을 확정한다. 구체적으로:

- `factors/`·`data/` 두 패키지의 모듈 트리·의존 방향·INV-1 AST 스캔 규칙을 확정한다(§2).
- 상위 계층이 인용할 도메인 타입 시그니처 10군을 Python 시그니처로 확정한다(§3, 확정 원천).
- 데이터 구조 선택(frozen dataclass · str-Enum · Protocol · attrs 채널)의 대안 비교와 ADR 연계를 서술한다(§4).
- 저장 2테이블 DDL과 직렬화(DB↔DataFrame) 규약을 확정한다(§5).
- as-of `merge_asof` 정렬, 32종 산식 구현 규칙, 품질 게이트 4종, 결측 채널의 알고리즘·검증 설계를 확정한다(§6).
- 수집·upsert 경로와 `FundamentalProvider` 어댑터 3종의 책임 경계를 확정한다(§7).
- 마일스톤·문서화 체크리스트·ADR·픽스처/테스트 매핑을 확정한다(§8~§11).

### 1.2 PRD/TRD와의 관계

| 원천 | 본 문서에서의 취급 |
|---|---|
| PRD-R01 §3 계약 (FR-01~18) | 시그니처·계약을 §3에서 **정밀 확정**(PRD가 형상만 고정한 것을 Python 시그니처로 구체화) |
| PRD-R01 §4 카탈로그 32종 | **산식의 권위 원천**. 본 문서는 재서술하지 않고 §6에서 구현 규칙(kernel 헬퍼 공유·parity 재도출)만 확정 |
| PRD-R01 §6 DDL·수집 | §5(DDL)·§7(수집/CRUD)에서 배치·직렬화·책임 경계 확정 |
| TRD-R01 TR-R01-001~018 | 기술 결정(A1-i 품질 게이트 단일 강제점, A2-i merge_asof backward + tie-break 정렬)을 설계로 구체화. **본 문서는 TRD 결정과 모순되지 않는다** |
| README §4 D1~D5 / §5 원칙 7 | 결정 인용(재논쟁 금지). D1(파라미터 완전 해석)·D2(price 팩터)가 R01 관련 |

### 1.3 자기완결성·오염 가드 선언

- 본 문서의 모든 설계는 PRD-R01 + README + TRD-R01 역추적으로만 정당화한다. main 시점 최초 구현을 가정하며, 과거 산출물·타 브랜치 자산에 앵커링하지 않고 항상 "앞으로 만들 것"의 관점으로 서술한다.
- 하위 계층이므로 상위(R02/R03)를 인용하지 않는다. 상위 소비 지점은 "소비자: PRD-R0x §y" 포인터만 둔다(§D-1).
- baseline 재사용 자산(OHLCV `DataProvider`, DuckDB 기존 8테이블, Typer CLI, Pydantic Settings)은 TRD-R01 §8.2 앵커 표 명칭으로만 인용한다.

### 1.4 결측 사유 명칭 확정(선결 고지)

`FactorNote`의 4종 확정 명칭은 **PRD-R01 FR-12** 원천을 따른다: `MISSING_INPUT`, `NON_POSITIVE_DENOMINATOR`, `ZERO_DENOMINATOR`, `INSUFFICIENT_HISTORY`. 이는 TRD-R01-006과 바이트 정합하며, `ZERO_DENOMINATOR`는 카탈로그 §4.3 `interest_coverage`(`interest_expense == 0`)가 실제 사용한다. 본 문서 전체가 이 4종만 사용한다.

---

## 2. 모듈 구조 및 의존 방향

### 2.1 패키지 트리

```
quant_krx/
├── factors/                     # 순수 계산 계층 (INV-1: 실행·저장·백테스트·수집 미import)
│   ├── __init__.py              #   공개 API 재노출 (get_factor, list_factors, compute_factor,
│   │                            #   get_factor_notes, FactorMetadata, ParamSpec, FactorInput,
│   │                            #   FactorCategory, FactorNote, Factor)
│   ├── metadata.py              #   FactorMetadata · ParamSpec · FactorCategory (§3.1~3.2)
│   ├── base.py                  #   Factor Protocol · FactorInput (§3.4~3.5)
│   ├── notes.py                 #   FactorNote · get_factor_notes · attrs 부착 헬퍼 (§3.9)
│   ├── dispatch.py              #   compute_factor 단일 인가 디스패치 (§3.6)
│   ├── registry.py              #   register_factor · get_factor · list_factors · _REGISTRY (§3.7~3.8)
│   ├── kernels.py               #   순수 산식 헬퍼(파생 팩터 공유 단일 원천, get_factor 미참조) (§6.2)
│   ├── asof.py                  #   as-of 정렬(merge_asof) 순수 헬퍼 + 연결/별도 폴백 (§6.3)
│   ├── errors.py                #   FactorError 계층(한국어 메시지 + 행동 힌트) (§3.10)
│   └── catalog/
│       ├── __init__.py          #   32종 일괄 등록(import 시 register_factor 호출) (§6.1)
│       ├── technical.py         #   가격·기술 7종 (price 포함, required_data=("ohlcv",))
│       ├── valuation.py         #   밸류에이션 11종 (required_data=("valuation",))
│       └── financial.py         #   재무제표 14종 (required_data 포함 ("financials",))
└── data/                        # 펀더멘털 데이터 조달·저장 계층 (factors/ 역참조 금지)
    ├── __init__.py
    ├── fundamental_base.py      #   FundamentalProvider Protocol · FundamentalKind (§3.11)
    ├── pykrx_fundamental.py     #   PyKrxFundamentalAdapter (pykrx 함수 내부 lazy import)
    ├── dart_fundamental.py      #   DartFundamentalAdapter (Deferred — §7.4)
    ├── fixture_fundamental.py   #   FixtureFundamentalAdapter (합성 CSV)
    ├── schema.py                #   2테이블 DDL (additive, CREATE TABLE IF NOT EXISTS) (§5)
    ├── quality.py               #   품질 게이트 4검사 · QualityViolation (§6.5)
    ├── upsert.py                #   upsert_fundamental 단일 강제점 (A1-i) (§7.2)
    └── loader.py                #   DB → 단일종목 FactorInput 재구성 로더 (§7.3)
```

### 2.2 의존 방향과 INV-1

```
              (호출자: R03 평가 엔진 / CLI)
                        │  FactorInput 주입
                        ▼
   ┌──────────────┐         ┌──────────────┐
   │  factors/    │◀─(무참조)─│   data/      │   data/는 factors/를 import하지 않는다(단방향)
   │  순수 계산    │         │  조달·저장    │   ─▶ DuckDB connection(주입) · pykrx(lazy)
   └──────────────┘         └──────────────┘
        │
        └─ 오직 표준 라이브러리 · pandas · numpy 만 참조
```

- **INV-1(FR-09)**: `factors/` 하위 모든 모듈은 백테스트 엔진(`vectorbt`), 실행 계층(`quant_krx.jobs`·`quant_krx.quant`), 데이터 수집·저장 계층(`quant_krx.data`·`quant_krx.storage`, DuckDB)을 import하지 않는다. 데이터는 호출자가 `FactorInput`으로 주입한다.
- **단방향**: `data/`는 저장(DuckDB connection 주입)·수집을 담당하되 `factors/`를 역참조하지 않는다. 두 패키지는 상호 leaf 독립이며, 유일한 접점은 `FactorInput`·`fundamental_daily`/`financial_statements`의 **형상 계약**(코드 의존이 아닌 데이터 계약)이다.
- **AST 스캔 규칙**: 테스트가 `factors/` import 그래프를 재귀 순회하여 금지 모듈 참조를 0건으로 강제한다. 금지 목록 = `{vectorbt, quant_krx.jobs, quant_krx.quant, quant_krx.storage, quant_krx.data}`. `if TYPE_CHECKING:` 블록의 타입 전용 import는 런타임 미로딩이므로 예외 허용(스캔은 `TYPE_CHECKING` guard 내부를 별도 판정). 검증: `AC-R01-07`.

---

## 3. 도메인 타입 시그니처 ★확정 원천★

> 본 절의 시그니처는 R02/R03이 인용하는 계약이다. 타입은 `from __future__ import annotations` 전제. `pd = pandas`, `np = numpy`.

### 3.1 `FactorCategory` — 카테고리 열거 (FR-03)

```python
class FactorCategory(str, Enum):
    PRICE = "price"
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    MEAN_REVERSION = "mean_reversion"
    VOLUME = "volume"
    VALUE = "value"
    QUALITY = "quality"
    GROWTH = "growth"
    STABILITY = "stability"
    SIZE = "size"
```

- 11종 확정. **additive 진화**(원칙 6): 신규 카테고리는 열거 추가로만. 기존 값 개명·제거 금지.
- `str` 혼합 상속으로 직렬화 시 값(`"price"` 등)이 문자열과 동일 취급되어 R02 참조·CLI 출력이 안정.

### 3.2 `ParamSpec` — 파라미터 명세 (FR-02)

```python
@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: type[int] | type[float]          # int 또는 float (FR-02)
    default: int | float
    description: str
    min: int | float | None = None         # 하한(포함), 선택
    max: int | float | None = None         # 상한(포함), 선택
    choices: tuple[int | float, ...] | None = None  # 열거 제약(additive, 선택)
```

- **default 단일 원천 불변식(FR-02, TR-R01-004)**: `ParamSpec.default`는 팩터 생성자 시그니처의 기본값과 **단일 원천**이어야 한다. 전수 대조 테스트(§11, `AC-R01-03`)가 introspection으로 불일치 0건을 강제한다. 팩터 구현은 생성자 기본값을 `ParamSpec.default`로 재사용하는 방식(예: 생성자가 `ParamSpec.default`를 참조)으로 이중 원천을 원천 차단한다.
- **완전성(D1 전제)**: `min`/`max`/`choices`는 상위 계층이 오버라이드 값을 **실행 없이** 검증할 완전 정보를 담는다. 교차 파라미터 제약(예: `macd` `fast<slow`)은 min/max로 표현 불가하므로 §3.3 훅으로 분리한다.
- `choices`는 min/max와 배타적으로 사용(둘 다 지정 시 both 적용은 정의하지 않음 — 카탈로그 32종은 min/max만 사용, choices는 additive 여지).

### 3.3 `validate_params` — 교차 제약 훅 (FR-02a)

```python
# Factor의 선택적(optional) 메서드. 미구현 팩터는 제약 없음으로 간주.
def validate_params(self, params: Mapping[str, Any]) -> tuple[str, ...]: ...
#   반환: 위반 사유 문자열 튜플(한국어 + 행동 힌트). 빈 튜플 = 통과.
```

- **이중 호출 지점(TR-R01-005)**:
  1. `get_factor(id, **params)` 인스턴스화 경로(§3.7)에서 호출 → 위반 시 §3.10 예외.
  2. 정의 시점 검증(오버라이드 params 검증) — **소비자: PRD-R02 §5.4**. R02는 본 훅을 DESIGN-R01 §3 링크로 인용해 재사용하며 신규 검증 로직을 두지 않는다.
- 훅 미노출 팩터는 빈 제약으로 간주(호출 안전). 예: `macd`는 `("fast(12)는 slow(26)보다 작아야 합니다.",)` 형태를 반환.

### 3.4 `FactorInput` — 입력 번들 (FR-05, FR-05a)

```python
@dataclass(frozen=True)
class FactorInput:
    ohlcv: pd.DataFrame                    # 필수(항상 존재) — 정렬 기준 daily 캘린더 원천
    valuation: pd.DataFrame | None = None
    financials: pd.DataFrame | None = None
```

**프레임 형상 계약(단일 종목, 오름차순 인덱스 — R02/R03 공유 유일 입력 계약)**:

| 프레임 | 인덱스 | 컬럼 | 비고 |
|---|---|---|---|
| `ohlcv` | 오름차순 `DatetimeIndex` | `open, high, low, close, volume` | **수정주가** 기준. as-of 정렬의 daily 기준 캘린더 |
| `valuation` | 오름차순 `DatetimeIndex` (= ohlcv 캘린더) | `close, per, pbr, eps, bps, div, dps, market_cap, shares` | `fundamental_daily` 값 컬럼을 일자 인덱스로 재구성 |
| `financials` | 오름차순 `RangeIndex`(행 순서) | 계정 컬럼 전체 + `period_end, disclosure_date, fiscal_year, fiscal_quarter, statement_scope` | `financial_statements` 행들을 `disclosure_date` **오름차순**으로 담음. 미정렬(raw) 상태 |

- `financials`는 **원본 분기 프레임**(as-of 미정렬)이다. 일별 정렬은 compute 시점 §6.3에서 수행한다.
- `valuation.index`는 FR-05a 단일 종목 계약상 `ohlcv.index`와 동일 trading 캘린더다. as-of 정렬 target 인덱스는 항상 `ohlcv.index`(항상 존재)로 확정한다(§6.3 설계 결정, ADR-R01-06).
- frozen dataclass는 프레임 참조를 불변화하나 pandas 프레임 내부 가변성은 막지 못하므로, **입력 비변조(NFR-04)**는 compute 구현이 copy-on-write/비파괴 연산으로 보장한다(§6.2).

### 3.5 `Factor` — 팩터 Protocol (FR-01, FR-05, FR-06)

```python
@runtime_checkable
class Factor(Protocol):
    @property
    def metadata(self) -> FactorMetadata: ...

    # required_data == ("ohlcv",) 이면 data: pd.DataFrame(= ohlcv),
    # 그 외에는 data: FactorInput. 호출자는 직접 호출하지 않고 compute_factor로만 진입.
    def compute(self, data: pd.DataFrame | FactorInput) -> pd.DataFrame: ...

    # 선택적: 교차 제약이 있는 팩터만 구현(§3.3). Protocol에는 명시하되 optional.
    # def validate_params(self, params: Mapping[str, Any]) -> tuple[str, ...]: ...
```

- `metadata`는 인스턴스 속성(파라미터 오버라이드 인스턴스는 자기 params가 반영된 `FactorMetadata`를 노출할 수 있으나, `output`/`required_data`/`id`는 불변).
- `compute`는 **직접 호출 금지 계약**: 유일 인가 진입점은 `compute_factor`(§3.6). 레지스트리 전수 스캔이 `required_data ≠ ("ohlcv",)` 팩터의 `compute`가 `FactorInput`을 수용하는지 강제(`AC-R01-04`).

### 3.6 `compute_factor` — 유일 인가 디스패치 (FR-06, FR-07)

```python
def compute_factor(
    factor: Factor,
    data: FactorInput | pd.DataFrame,
) -> pd.DataFrame: ...
```

- **디스패치 규칙(FR-06 확정)**:
  - `data`가 bare `pd.DataFrame`이면 `FactorInput(ohlcv=data)`로 승격.
  - `factor.metadata.required_data == ("ohlcv",)` → `factor.compute(data.ohlcv)`.
  - 그 외 → `factor.compute(data)`(전체 `FactorInput`).
  - 이 두 분기 외 경로는 없다.
- **반환 형상 보존(FR-07)**: 항상 `DataFrame`(단일 출력도 1컬럼), `set(result.columns) == set(factor.metadata.output)`, 인덱스는 입력 daily `DatetimeIndex` 보존. 디스패치는 형상을 변조하지 않는다.
- **결측 사유 통과(TR-R01-002, AC-05)**: 디스패치는 `factor.compute` 반환 프레임의 `attrs["notes"]`를 **재구성·소실 없이 그대로 통과**시킨다. 이것이 "디스패치 경계 통과 후 `get_factor_notes` 판독" 요구의 배선이다.
- **소비자**: R03 평가 엔진의 유일 팩터 실행 API — **소비자: PRD-R03 §5**.

### 3.7 `get_factor` — 오버라이드 인스턴스 생성 (FR-10, D1)

```python
def get_factor(factor_id: str, **params: Any) -> Factor: ...
```

- 레지스트리에서 `factor_id`의 생성자를 조회하여 `**params` 오버라이드를 적용한 인스턴스를 생성한다.
- **검증 순서(D1)**:
  1. `factor_id` 미존재 → §3.10 `UnknownFactorError`(사용 가능 id 목록 힌트 포함).
  2. 미지의 파라미터 키 / `type` 불일치 / `min`·`max`·`choices` 위반 → `ParamSpec` 기반 예외(허용 범위 힌트).
  3. `validate_params` 훅(있으면) 호출 → 위반 시 예외(위반 조건 힌트).
- 파라미터가 다른 두 호출은 **독립 인스턴스**를 반환한다(`get_factor("sma", window=5)` ≠ `get_factor("sma", window=20)`, FR-08/D1).
- **소비자**: R03 평가 시 파라미터 해석 — **소비자: PRD-R03 §5.3**.

### 3.8 레지스트리 등록·조회 (FR-10, FR-11)

```python
def register_factor(factor_id: str, constructor: Callable[..., Factor]) -> None: ...
#   중복 factor_id 등록 → DuplicateFactorError(§3.10).

def list_factors(category: FactorCategory | str | None = None) -> tuple[FactorMetadata, ...]: ...
#   category=None 이면 전체. 반환은 id 오름차순 정렬(결정적).
```

- **데이터 무관 결정성(FR-11)**: 등록은 데이터·환경에 의존하지 않는다. 재무 팩터도 DART 미설정과 무관하게 항상 등록·노출된다. 카탈로그 크기 == 32(`AC-R01-01`).
- **id 안정 앵커(FR-04, TR-R01-013)**: 공개된 `id`는 불변(개명 시 신규 id additive 추가). 회귀 테스트가 기존 id 존재를 강제. R02 직렬화 참조·왕복 무손실의 전제.
- 등록은 `catalog/__init__.py` import 시점에 32회 `register_factor` 호출로 완결(OCP: 신규 팩터 = Protocol 구현 + 1회 등록).

### 3.9 `FactorNote` · `get_factor_notes` — 결측 채널 (FR-12, FR-13)

```python
class FactorNote(str, Enum):
    MISSING_INPUT = "missing_input"                     # 입력 프레임/컬럼 부재
    NON_POSITIVE_DENOMINATOR = "non_positive_denominator"  # 분모 ≤ 0
    ZERO_DENOMINATOR = "zero_denominator"               # 분모 == 0 (예: interest_expense)
    INSUFFICIENT_HISTORY = "insufficient_history"       # warm-up / 최초 공시 이전

def get_factor_notes(df: pd.DataFrame) -> dict[str, FactorNote]:
    #   유일 접근자. df.attrs["notes"](컬럼→사유 매핑) 사본 반환. 없으면 {}.
    ...
```

- **채널 규약(TR-R01-006)**: NaN 셀이 진실 원천, 사유는 **자문(advisory)**. 반환 프레임 `attrs["notes"]: dict[str, FactorNote]`에 **컬럼 단위 단일 사유**로 실린다(한 컬럼에 복수 사유 시 §4 표의 지정 사유 = 가장 구체적 원인 1개만 기록). 다중 사유 목록화는 out(additive 후보).
- **판독 시점(FR-13)**: 후속 pandas 연산이 `attrs`를 소실시킬 수 있으므로, 소비자는 `compute_factor` 반환 **직후·변환 이전** 판독한다. 인용 계약에 명시(§6.4).
- **소비자**: R03 평가 엔진의 사유 판독 — **소비자: PRD-R03 §5**.

### 3.10 오류 모델 — `FactorError` 계층 (원칙 7)

```python
class FactorError(Exception): ...                 # 기반
class UnknownFactorError(FactorError): ...         # 미존재 id (사용 가능 id 목록 힌트)
class DuplicateFactorError(FactorError): ...       # 중복 등록
class ParamValidationError(FactorError): ...       # 범위/타입/교차 제약 위반 (허용 범위·위반 조건 힌트)
```

- 모든 메시지는 **한국어 + 행동 가능 힌트**(누락 id → 사용 가능 id 목록, 범위 위반 → 허용 범위, 교차 제약 → 위반 조건 예: `fast < slow`). CLI 실패는 non-zero 종료(§7.5).

### 3.11 `FundamentalProvider` — 조달 Protocol (FR-16)

```python
FundamentalKind = Literal["valuation", "financials"]

@runtime_checkable
class FundamentalProvider(Protocol):
    #   밸류에이션 일별: fundamental_daily 형상의 long-form 프레임 반환(symbol, date + 값 컬럼).
    def fetch_valuation(
        self, symbols: Sequence[str], start: date, end: date,
    ) -> pd.DataFrame: ...

    #   재무제표 분기: financial_statements 형상의 long-form 프레임 반환.
    def fetch_financials(
        self, symbols: Sequence[str], start: date, end: date,
    ) -> pd.DataFrame: ...
```

- **OHLCV `DataProvider`와 분리 정의(FR-16)**: baseline OHLCV `DataProvider`는 무변경, 펀더멘털 조달은 별도 계약. 반환은 upsert 대상 long-form(다종목), 단일종목 `FactorInput` 재구성은 §7.3 로더가 수행.
- 어댑터 3종: `PyKrxFundamentalAdapter`(밸류에이션, pykrx 함수 내부 lazy import) · `DartFundamentalAdapter`(재무제표, Deferred §7.4) · `FixtureFundamentalAdapter`(합성 CSV, OHLCV 픽스처와 종목 정합).
- **소비자**: R03 Daily 자동수집 — **소비자: PRD-R03 §7**.

---

## 4. 데이터 구조 결정 (옵션 비교·ADR 연계)

| 결정 축 | 옵션 | 채택 | 근거 |
|---|---|---|---|
| 메타·입력 컨테이너 | frozen dataclass vs. `NamedTuple` vs. dict | **frozen dataclass** (ADR-R01-01) | 불변성 + 타입 명시 + 기본값/후처리(`__post_init__`) 지원. dict는 형상 계약 강제 불가, NamedTuple은 기본값·검증 유연성 열위 |
| 카테고리·사유 열거 | `str, Enum` vs. plain str 상수 vs. `IntEnum` | **`str, Enum`** (ADR-R01-02) | 직렬화 시 문자열 동형(R02 참조·CLI 안정) + 열거 폐집합 강제 + additive 확장 용이 |
| 팩터 계약 | `Protocol`(구조적) vs. ABC(명목적) | **`Protocol` + `@runtime_checkable`** (ADR-R01-03) | 신규 팩터가 상속 없이 duck-typing으로 계약 충족(OCP), 레지스트리 전수 스캔으로 `compute` 시그니처 검증 |
| 결측 사유 채널 | `attrs["notes"]` 사이드카 vs. MultiIndex 컬럼 vs. 별도 반환 | **`attrs["notes"]`** (ADR-R01-04) | 반환 형상(컬럼==output) 불변 유지(FR-07) + advisory 분리. 단점(pandas 연산 시 소실)은 "직후 판독" 계약으로 완화(§6.4) |
| as-of 정렬 수단 | `merge_asof(backward)` vs. 수동 groupby+ffill | **`merge_asof`** (ADR-R01-05, TRD A2-i) | 벡터 결정론 + 경계 자연 NaN. tie-break은 병합 전 정렬로 보장 |
| as-of target 인덱스 | `ohlcv.index` vs. `valuation.index` | **`ohlcv.index`** (ADR-R01-06) | 항상 존재 → `("financials",)`-only 팩터도 정의됨. valuation 결측 시에도 daily 캘린더 확보 |

세부 근거는 §10 ADR.

---

## 5. 직렬화 규약 + DuckDB DDL

### 5.1 additive 진화 원칙

baseline DuckDB 8테이블(`symbols`, `ohlcv_daily`, `data_fetch_runs`, `strategy_runs`, `signals`, `reports`, `notification_outbox`, `run_events`)은 **무변경**이다. R01은 아래 **2테이블만 additive 추가**한다(원칙 6). 모든 DDL은 `CREATE TABLE IF NOT EXISTS`로 멱등(`AC-R01-07` 재연결 무오류).

### 5.2 `fundamental_daily` (FR-14)

```sql
CREATE TABLE IF NOT EXISTS fundamental_daily (
    symbol      VARCHAR   NOT NULL,
    date        DATE      NOT NULL,
    close       DOUBLE,          -- OHLCV와 동일 조정 종가 원천(주가 정합 불변식)
    per         DOUBLE,
    pbr         DOUBLE,
    eps         DOUBLE,
    bps         DOUBLE,
    div         DOUBLE,          -- 배당수익률(원천 제공 값)
    dps         DOUBLE,          -- 주당배당금
    market_cap  DOUBLE,          -- 음수 불가(품질 게이트)
    shares      DOUBLE,          -- 음수 불가(품질 게이트)
    source      VARCHAR,
    fetched_at  TIMESTAMP,
    PRIMARY KEY (symbol, date)
);
```

- **주가 정합 불변식(FR-14, TR-R01-010)**: `fundamental_daily.close`는 `ohlcv_daily.close`와 동일 (symbol, date)에서 동등. 밸류에이션 어댑터가 종가 병합 시 OHLCV 파이프라인과 동일 수정주가 계열을 참조. 정합 테스트가 강제(`AC-R01-06`).

### 5.3 `financial_statements` (FR-15)

```sql
CREATE TABLE IF NOT EXISTS financial_statements (
    symbol                    VARCHAR  NOT NULL,
    fiscal_year               INTEGER  NOT NULL,
    fiscal_quarter            INTEGER  NOT NULL CHECK (fiscal_quarter IN (1,2,3,4)),
    statement_scope           VARCHAR  NOT NULL CHECK (statement_scope IN ('consolidated','separate')),
    -- 계정 컬럼(§4.3 산식이 요구하는 전건)
    revenue                   DOUBLE,
    gross_profit              DOUBLE,
    operating_income          DOUBLE,
    net_income                DOUBLE,
    pretax_income             DOUBLE,
    income_tax                DOUBLE,
    total_assets              DOUBLE,
    total_debt                DOUBLE,
    total_equity              DOUBLE,
    current_assets            DOUBLE,
    current_liabilities       DOUBLE,
    operating_cash_flow       DOUBLE,
    interest_expense          DOUBLE,
    depreciation_amortization DOUBLE,
    cash_and_equivalents      DOUBLE,
    invested_capital          DOUBLE,   -- 원장 부재 파생 계정: 어댑터가 산출·저장
    -- 기간 메타
    period_end                DATE,
    disclosure_date           DATE,
    source                    VARCHAR,
    fetched_at                TIMESTAMP,
    PRIMARY KEY (symbol, fiscal_year, fiscal_quarter, statement_scope)
);
```

- 저장은 `INSERT OR REPLACE` 멱등 upsert(§7.2). 재실행 중복 0(`AC-R01-08`).
- **파생 계정 단일 산출(TR-R01-008, OT-3)**: `invested_capital` 등 원장에 직접 없는 파생 계정은 **어댑터가 산출·저장**하고 팩터는 저장값을 소비한다(계산 계층 재계산 금지). `roic`의 `tax_rate = income_tax/pretax_income`은 팩터 계층 계산(원장 계정 조합).

### 5.4 직렬화(DB ↔ DataFrame) 규약

- **valuation 로더**(§7.3): `fundamental_daily`에서 단일 symbol을 조회 → `date`를 `DatetimeIndex`(오름차순)로, 값 컬럼(`close, per, pbr, eps, bps, div, dps, market_cap, shares`)을 프레임 컬럼으로 재구성 → `FactorInput.valuation`.
- **financials 로더**(§7.3): `financial_statements`에서 단일 symbol을 조회 → `disclosure_date` 오름차순 정렬한 raw 행 프레임(RangeIndex) → `FactorInput.financials`. as-of 정렬은 하지 않음(compute 시점 §6.3).
- 왕복 결정성: 동일 DB 상태 → 동일 프레임(정렬·컬럼 순서 고정). NFR-01 검증(2회 동일).

---

## 6. 알고리즘·검증 설계

### 6.1 카탈로그 등록 및 산식 권위 원천

- **PRD §4 표 = 산식의 권위 원천**. 본 문서는 산식을 재서술하지 않고 아래 구현 규칙만 확정한다.
- 32종 분포: 가격·기술 7(`price, sma, ema, rsi, macd, bollinger, momentum`) + 밸류에이션 11(`per, pbr, earnings_yield, dividend_yield, eps, bps, roe_approx, payout_ratio, eps_growth, peg, market_cap`) + 재무제표 14(`psr, pcr, ev_ebitda, roa, roic, gross_margin, operating_margin, net_margin, gp_to_assets, revenue_growth, op_income_growth, debt_to_equity, current_ratio, interest_coverage`).
- 각 팩터는 `catalog/`의 해당 모듈에 `metadata` + `compute`를 구현하고 `catalog/__init__.py`가 등록.

### 6.2 순수 산식 헬퍼(kernels) — 파생 팩터 단일 원천 (PRD §5, TR-R01-017)

- 파생 팩터(`peg`, `roe_approx`, `eps_growth`, `earnings_yield` 등)는 **다른 Factor 인스턴스를 `get_factor`로 참조하지 않는다**(레지스트리 결합·순서 의존 금지).
- 산식은 `factors/kernels.py`의 순수 함수(입력 Series/DataFrame → 출력 Series)에 **단일 원천**으로 두고 공유한다. 예: `peg`가 `per` kernel과 `eps_growth` kernel을 **함수 호출**로 재사용.
- `eps_growth`(스텝 정의): 일별 EPS 스텝함수에서 "직전 **상이한** EPS 스텝 값 대비 증가율"을 산출하는 kernel. 스텝 갱신 시점에만 값 갱신, 사이 구간은 직전 성장률 유지. 첫 스텝 이전 = NaN+`INSUFFICIENT_HISTORY`, 직전 스텝 ≤ 0 = NaN+`NON_POSITIVE_DENOMINATOR`.
- **입력 비변조(NFR-04)**: kernel은 입력 프레임을 in-place 변경하지 않고 새 Series를 반환. compute 진입 시 필요하면 명시적 사본 사용.
- **NFR-05(루프 부재)**: 모든 산식은 벡터 연산(`rolling`/`ewm`/`shift`/`diff`/`merge_asof`)으로 수행하고 파이썬 행-루프를 두지 않는다.

### 6.3 as-of 정렬 알고리즘 (FR-17, TRD A2-i)

재무제표 팩터의 compute 내부에서 raw 분기 `financials`를 daily 인덱스에 정렬하는 순수 헬퍼 `asof.py`. **의사코드**:

```
align_financials(financials: DataFrame, daily_index: DatetimeIndex) -> DataFrame:
    # 1) 연결/별도 폴백으로 단일 계열 구성(PRD §4.3)
    #    - statement_scope == 'consolidated' 우선.
    #    - 특정 (fiscal_year, fiscal_quarter)에 consolidated 부재 시 separate 폴백.
    unified = pick_consolidated_first_else_separate(financials)

    # 2) tie-break 정렬(TR-R01-011): (disclosure_date asc, period_end desc)
    #    동일 disclosure_date 그룹은 period_end 최신(최상단)만 남김.
    unified = unified.sort_values(["disclosure_date", "period_end"],
                                  ascending=[True, False])
    unified = unified.drop_duplicates(subset=["disclosure_date"], keep="first")

    # 3) merge_asof backward: daily_index(left) ← unified(right, key=disclosure_date)
    left  = DataFrame(index=daily_index).reset_index(names="date")
    aligned = merge_asof(left, unified, left_on="date",
                         right_on="disclosure_date", direction="backward")

    # 4) 최초 공시 이전 구간(좌측 미매치)은 자연 NaN → INSUFFICIENT_HISTORY 기록.
    return aligned.set_index("date")   # daily_index 재부여
```

- **경계(FR-17)**: 최초 공시(`disclosure_date`) 이전 daily 구간은 `merge_asof` 좌측 미매치로 자연 NaN, 사유 `INSUFFICIENT_HISTORY`.
- **tie-break(OT-2)**: 동일 `disclosure_date` 복수 레코드는 `period_end` 최신 선택(병합 전 정렬로 결정론 보장).
- **연결 우선 폴백(§4.3)**: 단일 계열 구성을 정렬·병합보다 먼저 수행(scope 혼재 방지).
- **target 인덱스(ADR-R01-06)**: `daily_index = FactorInput.ohlcv.index`. `("financials",)`-only 팩터도 daily 캘린더 확보. `("valuation","financials")` 팩터는 valuation 컬럼(daily)과 aligned 재무를 같은 인덱스에서 결합.

### 6.4 결측 채널 설계 (FR-12, FR-13, TR-R01-006/007)

- **부착**: compute가 NaN을 산출한 컬럼에 대해 `result.attrs["notes"][col] = FactorNote.<사유>`를 설정. 헬퍼 `notes.attach_note(df, column, note)`(`factors/notes.py`)로 단일 경로 부착.
- **디스패치 통과**: `compute_factor`는 `attrs["notes"]`를 그대로 반환(§3.6). 소비자는 반환 직후 `get_factor_notes(df)` 판독(변환 전).
- **degrade(TR-R01-007)**: `financials=None`(또는 `valuation=None`)이면 해당 데이터 요구 팩터는 **예외 없이** 전 구간 NaN + `MISSING_INPUT`. 배선:
  - 필요 프레임 부재 감지 → 입력 daily 인덱스(가용 시 `ohlcv.index`) 형상의 전-NaN DataFrame(컬럼==output) 반환 + `attrs["notes"]` 전 컬럼 `MISSING_INPUT`.
  - 인덱스 참조조차 불가(전 프레임 None) → 빈 DataFrame + 사유. 데이터 미연동이 카탈로그·타 팩터를 차단하지 않음(NFR-06).
- **사유 매핑 규약(§4 표)**: 각 팩터 compute는 §4 표의 NaN 조건(예: `eps ≤ 0` → `NON_POSITIVE_DENOMINATOR`, `interest_expense == 0` → `ZERO_DENOMINATOR`, warm-up → `INSUFFICIENT_HISTORY`)을 지정 사유로 부착.

### 6.5 품질 게이트 4종 (FR-17b, TRD A1-i)

`data/quality.py`가 upsert 직전 단일 게이트에서 4검사 수행. **위반 행은 저장에서 제외 + 사유 기록**, 수집 전체 중단 없음.

```python
class QualityViolation(str, Enum):
    DUPLICATE_PK = "duplicate_pk"           # PK 중복
    NON_ASCENDING_DATE = "non_ascending_date"  # 일자 비오름차순
    FUTURE_DATE = "future_date"             # 미래 일자(주입된 as_of 초과)
    NEGATIVE_FIELD = "negative_field"       # 음수 불가 필드 위반(market_cap, shares)
```

- **as_of 주입(NFR-01, OT-5)**: 미래 일자 검사 기준 시각은 **주입**(`as_of: date`). 시스템 현재시각·네트워크 미참조 → 결정론·재현성.
- 음수 불가 필드: `fundamental_daily`의 `market_cap`, `shares`(FR-17b). 재무 테이블은 음수 허용 계정(예: `net_income`) 존재하므로 음수 검사 대상 아님.
- 반환: 수용 행 + `ExcludedRow` 목록(§7.2). CLI가 제외 행·사유 요약 출력(§7.5).

### 6.6 검증 설계 요약

| 검증 | 방법 | AC |
|---|---|---|
| 산식 parity | §4 표 산식을 테스트가 pandas로 **독립 재도출** → `assert_frame_equal`(골든 상수 금지) | AC-R01-02 |
| 결정론 | 2회 호출 프레임 동등 | AC-R01-02 |
| 입력 비변조 | 계산 전후 입력 해시 동등 | AC-R01-02, NFR-04 |
| default 단일 원천 | introspection 전수 대조 | AC-R01-03 |
| 교차 제약 | `macd` fast≥slow 인스턴스화 거부 | AC-R01-03 |
| 디스패치 라우팅 | ohlcv/FactorInput 분기 + required_data≠("ohlcv",) 전수 호환 스캔 | AC-R01-04 |
| 결측 사유 | 경계 Fixture NaN 위치·사유 일치, degrade 무예외 | AC-R01-05 |
| as-of | 공시 이전 NaN·tie-break·주가 정합 | AC-R01-06 |
| INV-1 | AST 스캔 0 위반 | AC-R01-07 |
| 품질 게이트 | 위반 행 제외+기록, 멱등 재수집 | AC-R01-08 |

---

## 7. 영속화/CRUD + 호출자 책임 경계

### 7.1 책임 경계 개요

```
CLI(fetch-fundamental) / R03 Daily 자동수집
        │  (동일 경로 공유 — FR-17a)
        ▼
FundamentalProvider.fetch_*()  ──▶  upsert_fundamental(conn, table, frame, as_of=...)
   (data/*_fundamental.py)              │  (data/upsert.py: 품질 게이트 → INSERT OR REPLACE)
                                        ▼
                                   DuckDB(fundamental_daily / financial_statements)
                                        │
                                        ▼
                                   load_factor_input(conn, symbol, ...)  ──▶ FactorInput
                                        (data/loader.py)                       │
                                                                               ▼
                                                                   compute_factor(factor, input)
```

### 7.2 upsert 단일 강제점 (A1-i, TR-R01-009)

```python
@dataclass(frozen=True)
class ExcludedRow:
    symbol: str
    key: str                 # date 또는 (fiscal_year, fiscal_quarter, scope) 문자열
    reason: QualityViolation
    detail: str              # 한국어 사유

@dataclass(frozen=True)
class UpsertResult:
    table: str
    accepted: int
    excluded: tuple[ExcludedRow, ...]

def upsert_fundamental(
    conn,                    # DuckDB connection (주입 — data/는 storage 미import)
    table: str,              # "fundamental_daily" | "financial_statements"
    frame: pd.DataFrame,     # provider long-form
    *,
    as_of: date,             # 미래 일자 검사 기준(주입)
) -> UpsertResult: ...
```

- **단일 강제점**: 어댑터 3종이 이 함수를 우회할 수 없는 유일 저장 경로. `fetch-fundamental`·Daily 자동수집이 동일 경로 공유(FR-17a).
- 순서: (1) 품질 게이트 4검사(§6.5) → 위반 행 제외·`ExcludedRow` 수집 → (2) 수용 행 `INSERT OR REPLACE` → (3) `UpsertResult` 반환.
- 멱등: 재실행 시 `INSERT OR REPLACE`로 중복 0(`AC-R01-08`).

### 7.3 로더 — DB → FactorInput (§5.4)

```python
def load_factor_input(
    conn,
    symbol: str,
    *,
    start: date | None = None,
    end: date | None = None,
    ohlcv: pd.DataFrame,     # OHLCV는 baseline 파이프라인이 제공(주입)
) -> FactorInput: ...
```

- `fundamental_daily`·`financial_statements`에서 단일 symbol 조회 → §5.4 규약으로 `valuation`/`financials` 재구성 → `FactorInput(ohlcv, valuation, financials)`.
- 데이터 부재 시 해당 프레임 `None`(degrade 경로 §6.4로 이어짐).

### 7.4 어댑터 3종 배치 (FR-16)

| 어댑터 | 대상 | 핵심 배선 |
|---|---|---|
| `PyKrxFundamentalAdapter` | valuation | pykrx 일별 fundamental + 시가총액 + 종가 병합. **pykrx는 함수 내부 lazy import**(setuptools 충돌 회피, baseline PyKrx 관례 계승). 종가는 OHLCV와 동일 수정주가 계열 참조(FR-14 불변식) |
| `DartFundamentalAdapter` | financials | **Deferred(§7.6)**. 인터페이스만 확정, 실연동은 후속 |
| `FixtureFundamentalAdapter` | valuation + financials | 합성 CSV 판독. OHLCV 픽스처와 **동일 종목 정합**. 오프라인 결정론 검증 원천(`AC-R01-08`, NFR-02) |

### 7.5 CLI 3계약 (FR-18, TR-R01-012)

| 명령 | 인자 | 출력 | 오류 |
|---|---|---|---|
| `list-factors [--category <c>]` | 카테고리 필터(선택) | id·표시명·카테고리·설명 표 | 미존재 카테고리 → 힌트 + non-zero |
| `show-factor <id>` | 팩터 id | 설명·파라미터 명세(기본값·제약)·산출 컬럼·`required_data`·데이터 가용성 힌트 | 미존재 id → 사용 가능 id 힌트 + non-zero |
| `fetch-fundamental` | 심볼 목록(기본 watchlist)·기간·종류(valuation/financials)·provider | 수용/제외 행·사유 요약 | 실패 → 한국어 힌트 + non-zero |

- **환경 힌트(FR-11, TR-R01-014)**: `show-factor`가 재무 팩터에 대해 DART 미설정 시 "값은 NaN" 힌트 표시(조회 표시용, 등록 여부 불변).
- Typer CLI 관례 계승(baseline 앵커). 오류 모델은 §3.10 준수.

### 7.6 Deferred — Phase F2-b DART 실데이터 연동 (본 완료 정의 밖)

본 문서 완료 정의는 합성 Fixture 결정론 검증까지(TRD §4.7 승계). DART 실연동은 후속 단계이며, 착수 시 선행 명세 4항목(TR-R01-D01~D04): corp_code 해결·account_nm 완전 매핑·disclosure_date/period_end 추출 규약·연결(CFS) 우선 별도(OFS) 폴백. 미확정 시 어댑터 공전. **본 완료 판정에 미포함**.

---

## 8. 마일스톤 (M0..M4 — 논리 단위)

| M | 범위 | 완료 신호 |
|---|---|---|
| **M0** | 모듈 골격(`factors/`·`data/`) + INV-1 AST 스캔 | AST green(AC-R01-07 부분) |
| **M1** | `metadata`·`ParamSpec`·`FactorCategory`·`Factor` Protocol·레지스트리·`compute_factor` 디스패치 + 가격·기술 7종 | AC-R01-01~04 부분 |
| **M2** | 결측 채널(`FactorNote`·attrs·`get_factor_notes`) + kernels + 밸류에이션 11종 | AC-R01-05 부분 |
| **M3** | 저장 2테이블 DDL + `FundamentalProvider` + Fixture 어댑터 + 로더 + as-of(`asof.py`) + 재무 14종 | AC-R01-05/06 |
| **M4** | 수집 경로(`upsert`)·품질 게이트·CLI 3계약 | AC-R01-07/08 |
| (Deferred) | Phase F2-b DART 실연동 | §7.6, 본 완료 정의 밖 |

> 마일스톤은 문서상 논리 단위(스프린트 분할은 구현 계획 시점 확정).

---

## 9. 문서화 체크리스트

- [ ] §3 시그니처 10군 전부 확정(R02/R03 인용 원천): `FactorMetadata`·`ParamSpec`·`validate_params`·`FactorInput`·`Factor`·`compute_factor`·`get_factor`·`list_factors`/레지스트리·`get_factor_notes`·`FundamentalProvider`.
- [ ] INV-1 AST 스캔 규칙 명시(금지 모듈 목록 + `TYPE_CHECKING` 예외).
- [ ] 32종 산식 = PRD §4 표 권위 원천 인용, kernel 헬퍼 공유(get_factor 미참조), parity 재도출 규칙.
- [ ] `ParamSpec.default` == 생성자 기본값 단일 원천(전수 대조 테스트).
- [ ] `validate_params` 이중 호출 지점(get_factor + R02 정의 검증 — 후자는 "소비자: PRD-R02 §5.4" 포인터만).
- [ ] 결측 채널 attrs["notes"] 디스패치 경계 통과 설계.
- [ ] 주가 정합 불변식(`fundamental_daily.close` == OHLCV close) 강제 지점.
- [ ] as-of: 최초 공시 이전 NaN+INSUFFICIENT_HISTORY, tie-break(period_end 최신), 연결 우선→별도 폴백 단일 계열.
- [ ] 품질 게이트 4종 위반 행 제외+기록(수집 중단 없음), as_of 주입.
- [ ] 오류 모델: 한국어 메시지 + 행동 힌트, CLI non-zero.
- [ ] additive 진화(기존 8테이블 무변경, 2테이블 추가만).
- [ ] §11 테스트: 합성 Fixture + 격리 DuckDB + pytest 결정론(2회 동일), 기대값 하드코딩 금지.
- [ ] TRD-R01 TR-R01-001~018(특히 A1-i/A2-i)와 모순 없음.

---

## 10. ADR

### ADR-R01-01 — 메타·입력 컨테이너를 frozen dataclass로
- **Decision**: `FactorMetadata`·`ParamSpec`·`FactorInput`을 `@dataclass(frozen=True)`로.
- **Drivers**: 불변성(안정 앵커 FR-04) · 형상 계약 강제 · 기본값/후처리.
- **Alternatives**: `NamedTuple`(기본값·검증 유연성 열위), dict(형상 계약 강제 불가).
- **Consequences**: 프레임 참조는 불변, 프레임 내부 가변성은 compute 비파괴 연산으로 별도 보장(NFR-04).

### ADR-R01-02 — 카테고리·사유를 `str, Enum`으로
- **Decision**: `FactorCategory`·`FactorNote`·`QualityViolation`을 `str, Enum`으로.
- **Drivers**: R02 직렬화 참조 안정 · CLI 문자열 출력 동형 · 폐집합 강제 · additive 확장.
- **Alternatives**: plain str 상수(폐집합 강제 불가), `IntEnum`(직렬화 가독성 열위).

### ADR-R01-03 — 팩터 계약을 `Protocol`로
- **Decision**: `Factor`를 `@runtime_checkable Protocol`로(ABC 상속 아님).
- **Drivers**: OCP(신규 팩터 = 구현 + 1회 등록, 상속 불요) · 레지스트리 전수 스캔으로 `compute` 시그니처 검증.
- **Alternatives**: ABC(명목적 상속 강제 → OCP 마찰).
- **Consequences**: `compute` 시그니처 이형(ohlcv vs FactorInput)은 `required_data` 전수 스캔으로 강제(AC-R01-04).

### ADR-R01-04 — 결측 사유를 `attrs["notes"]` 사이드카로
- **Decision**: 컬럼→사유 매핑을 반환 프레임 `attrs["notes"]`에.
- **Drivers**: 반환 형상(컬럼==output, FR-07) 불변 유지 · advisory 분리.
- **Alternatives**: MultiIndex 컬럼(형상 변조), 별도 반환(디스패치 시그니처 복잡화).
- **Consequences(OT-1)**: pandas 연산 시 attrs 소실 위험 → "반환 직후 판독" 계약 + 디스패치 통과 보장으로 완화.

### ADR-R01-05 — as-of를 `merge_asof(backward)`로 (TRD A2-i)
- **Decision**: 일별 인덱스에 `disclosure_date` 기준 `merge_asof` backward 병합, tie-break은 병합 전 `(disclosure_date asc, period_end desc)` 정렬.
- **Drivers**: 벡터 결정론(NFR-01/05) · 경계 자연 NaN · PRD FR-17 "merge_asof 계열" 충족.
- **Alternatives**: 수동 groupby+ffill(루프 비결정성·경계 수기 처리).

### ADR-R01-06 — as-of target 인덱스 = `ohlcv.index`
- **Decision**: as-of 정렬 target daily 인덱스를 `FactorInput.ohlcv.index`로 확정.
- **Drivers**: `ohlcv`는 항상 존재 → `required_data=("financials",)`-only 팩터도 daily 캘린더 확보. PRD §4.3의 "밸류에이션 일별 인덱스"는 FR-05a 단일 종목 계약상 `ohlcv.index`와 동일 trading 캘린더이므로 정합.
- **Alternatives**: `valuation.index`(valuation=None 시 정의 불가).
- **Consequences**: 이 결정은 PRD 미명세 경계(financials-only 팩터의 정렬 기준)를 FR-05a+FR-17 역추적으로 해소한다.

> 본 계획 메타 결정(6편 분할·계층 순차)은 상위 계획 문서 ADR 소관이며 여기서 다루지 않는다.

---

## 11. 픽스처 및 테스트 매핑

### 11.1 합성 Fixture

- **OHLCV**: baseline 합성 픽스처(5종목 × 다수 거래일) 계승.
- **valuation 합성 CSV**: OHLCV와 **동일 종목·동일 일자 인덱스**. `close`는 OHLCV close와 동등(주가 정합 불변식 검증용). `eps≤0`, `bps≤0`, `close≤0`, div0 경계 케이스를 의도적으로 포함(결측 사유 검증).
- **financials 합성 CSV**: 동일 종목. 분기 레코드에 (a) 동일 `disclosure_date` 복수 레코드(tie-break용), (b) 최초 공시 이전 구간 확보(INSUFFICIENT_HISTORY용), (c) 연결/별도 혼재(폴백용), (d) `total_equity≤0`(자본잠식), `interest_expense==0`(ZERO_DENOMINATOR) 경계 포함.
- **기대값 하드코딩 금지**: parity 테스트가 §4 표 산식을 pandas로 독립 재도출(NFR-01, 원칙 3).

### 11.2 AC → 테스트 모듈 매핑

| AC | 테스트(예시 경로) | 검증 핵심 |
|---|---|---|
| AC-R01-01 | `tests/unit/factors/test_registry.py` | 32종 등록·중복 0·카테고리 분포·중복 등록 예외 |
| AC-R01-02 | `tests/unit/factors/test_catalog_parity.py` | 산식 재도출 parity·2회 동일·입력 비변조·컬럼==output·warm-up NaN |
| AC-R01-03 | `tests/unit/factors/test_params.py` | default 전수 대조·범위 위반 거부·macd 교차 제약·상이 파라미터 독립 |
| AC-R01-04 | `tests/unit/factors/test_dispatch.py` | ohlcv/FactorInput 라우팅·required_data≠("ohlcv",) 전수 호환 스캔 |
| AC-R01-05 | `tests/unit/factors/test_notes.py` | 경계 Fixture NaN·사유 일치·degrade 무예외·경계 통과 판독 |
| AC-R01-06 | `tests/unit/data/test_asof.py`, `test_price_consistency.py` | 공시 이전 NaN·tie-break·주가 정합 |
| AC-R01-07 | `tests/unit/factors/test_purity_ast.py`, `tests/unit/data/test_schema.py`, `tests/cli/test_factor_cli.py` | AST 스캔·2테이블 멱등·CLI 3계약 |
| AC-R01-08 | `tests/integration/test_fetch_fundamental.py` | fetch 멱등·품질 게이트 제외+기록·Fixture 오프라인 |

- 통합 테스트는 `tmp_path` 격리 DuckDB + `FixtureFundamentalAdapter`로 네트워크·실데이터·LLM 없이 실행(NFR-02).
- 결정론은 **2회 실행 동일**(`assert_frame_equal`)로 판정(NFR-01).

---

**추적성 요약**: FR-01~18 · AC-01~08 · INV-1 · D1/D2가 §3 시그니처 + §5 DDL + §6 알고리즘 + §11 테스트로 매핑. §3 시그니처 10군은 R02/R03이 인용하는 확정 원천(§D-2). 본 문서는 TRD-R01 TR-R01-001~018(A1-i 품질 게이트 단일 강제점 §6.5/§7.2, A2-i merge_asof backward + tie-break §6.3)과 모순 없이 정합한다.

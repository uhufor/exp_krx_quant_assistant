# PRD-R01 : Factor Platform

**Milestone**: Milestone 2 — No-Code Quant Strategy Platform
**Status**: Approved for implementation
**의존**: 없음 (최하위 계층) / **소비자**: PRD-R02 (참조 검증), PRD-R03 (평가·실행)

---

## 1. Background & Goal

전략의 기본 구성 요소인 Factor(투자 지표)를 플랫폼이 관리하는 1급 자원으로 제공한다. 상위 계층(정의 코어·Workspace)은 레지스트리에 질의하여 "어떤 지표를, 어떤 파라미터로, 어떤 입력 데이터로 조합할 수 있는가"를 **기계적으로** 판정할 수 있어야 한다.

목표:
1. 모든 Factor를 단일 레지스트리에서 등록·조회·계산한다.
2. 각 Factor는 구조화된 메타데이터(정의·**파라미터 명세**·산출 컬럼·필요 데이터)를 노출한다. 파라미터 명세는 상위 계층의 오버라이드 검증(D1)의 진실 원천이다.
3. 신규 Factor 추가 = (a) Protocol 구현 + (b) 레지스트리 1회 등록, 2단계로 완결(OCP).
4. 계산 불가 셀은 NaN + 조회 가능한 사유로 처리한다.

## 2. Scope

**In**: Factor 메타데이터·계산 Protocol·레지스트리 / 팩터 카탈로그 32종(§4) / 펀더멘털 데이터 계층(테이블 2, Provider Protocol, 어댑터) / 다중 입력 계약(`FactorInput` + 단일 디스패치) / 결측 규약 / 조회 CLI(`list-factors`, `show-factor`).

**Out (확정)**: Formula/Rule/Strategy 정의·평가(→ R02/R03) / 팩터 계산값의 영속화·캐싱(입력 데이터만 DB 저장) / 복합 점수형 팩터(F-Score·Z-Score 등, 확장 후보) / 실시간·해외 데이터 / **DART 실데이터 연동은 별도 후속 단계**(§8 — 본 PRD의 완료 정의는 Fixture 검증까지).

## 3. 핵심 계약 (Functional Requirements)

### 3.1 메타데이터
- **FR-01** 각 Factor는 불변 `FactorMetadata`를 노출한다: `id`(snake_case, 전역 유일), `display_name`, `category`, `description`, `params: tuple[ParamSpec, ...]`, `output: tuple[str, ...]`(산출 컬럼), `required_data: tuple[str, ...]`(기본 `("ohlcv",)`).
- **FR-02** `ParamSpec` = `name`, `type`(`int`|`float`), `default`, `description`, + **제약**(`min`/`max` 선택). 각 default는 팩터 생성자 기본값과 단일 원천이어야 한다(이중 원천 금지 — 전수 대조 테스트로 강제). ParamSpec은 상위 계층이 **오버라이드 값을 실행 없이 검증**할 수 있는 완전한 정보를 담는다(D1의 전제).
- **FR-02a (교차 파라미터 제약)** 파라미터 간 제약(예: `macd`의 `fast < slow`)은 min/max로 표현되지 않으므로, 해당 팩터는 선택적 훅 `validate_params(params) -> tuple[str, ...]`(오류 목록, 빈 튜플=통과)을 노출한다. 이 훅은 (a) `get_factor(id, **params)` 인스턴스화와 (b) 정의 검증(PRD-R02 §5.4) **양쪽에서 호출**된다 — 파라미터 위반은 실행 시점이 아니라 정의 시점에 거부된다.
- **FR-03** `category` 열거: `price`, `trend`, `momentum`, `volatility`, `mean_reversion`, `volume`, `value`, `quality`, `growth`, `stability`, `size`. 확장은 열거 추가만으로.
- **FR-04** 팩터 식별자는 `id`이며, 직렬화된 정의(R02)가 참조하는 안정 앵커다 — 한번 공개된 id는 변경하지 않는다(개명이 필요하면 신규 id 추가).

### 3.2 계산 계약
- **FR-05** 입력 번들 `FactorInput(ohlcv, valuation, financials)` — 각 필드는 `pd.DataFrame | None`. OHLCV 팩터는 `compute(ohlcv: DataFrame)`, 펀더멘털 팩터는 `compute(data: FactorInput)`을 구현한다.
- **FR-05a (입력 프레임 형상)** `FactorInput`은 **단일 종목** 데이터 번들이며, 각 프레임은 오름차순 `DatetimeIndex`를 가진다. `ohlcv`: 컬럼 `open, high, low, close, volume`(수정주가 기준). `valuation`: `fundamental_daily`의 값 컬럼(`close, per, pbr, eps, bps, div, dps, market_cap, shares`)을 일자 인덱스로 재구성한 프레임. `financials`: `financial_statements` 행들을 `disclosure_date` 오름차순으로 담은 프레임(계정 컬럼 + `period_end`/`disclosure_date`/`fiscal_year`/`fiscal_quarter`/`statement_scope`). 이 형상이 팩터 구현·픽스처·평가 엔진(PRD-R03)이 공유하는 유일한 입력 계약이다.
- **FR-06** **유일 인가 실행 API는 `compute_factor(factor, data: FactorInput) -> pd.DataFrame`** 디스패치다: `required_data == ("ohlcv",)`이면 `factor.compute(data.ohlcv)`, 그 외 `factor.compute(data)`. 호출자는 `factor.compute()`를 직접 호출하지 않는다. `required_data ≠ ("ohlcv",)`인 모든 등록 팩터는 `FactorInput` 시그니처를 구현해야 한다(레지스트리 전수 스캔 강제).
- **FR-07** 반환은 **항상 DataFrame**(단일 출력도 1컬럼), 컬럼 집합 == `metadata.output`, 인덱스는 입력의 DatetimeIndex 보존.
- **FR-08** 계산은 결정론적(동일 입력·파라미터 → 동일 출력, 네트워크·현재시각 의존 금지)이고 입력을 변조하지 않는다. 파라미터가 다른 두 인스턴스는 독립 계산된다(**동일 팩터 상이 파라미터 동시 사용 지원** — D1).
- **FR-09** `factors/` 패키지는 백테스트 엔진·실행 계층·데이터 수집·저장 계층을 import하지 않는다(**INV-1**, AST 스캔 강제). 데이터는 호출자가 주입한다.

### 3.3 레지스트리
- **FR-10** `id → 팩터 생성자` 매핑. 중복 등록 예외. `list_factors(category=None)`, `get_factor(id, **params)`(미존재 시 사용 가능 id 힌트 포함 예외; **params로 파라미터 오버라이드 인스턴스 생성** — 범위 위반 시 ParamSpec 기반 예외).
- **FR-11** 데이터 가용성과 무관하게 카탈로그는 결정적이다 — 재무 팩터도 항상 등록·노출되며, `show-factor`가 환경 힌트(예: DART 미설정 → "값은 NaN")를 표시한다.

### 3.4 결측 규약
- **FR-12** 계산 불가 셀 = NaN. 사유는 `FactorNote` str-Enum — `MISSING_INPUT`(입력 프레임/컬럼 부재), `NON_POSITIVE_DENOMINATOR`, `ZERO_DENOMINATOR`, `INSUFFICIENT_HISTORY`(warm-up/공시 이전). 사유는 반환 프레임의 `attrs["notes"]`(컬럼→사유)에 실리고 `get_factor_notes(result)`가 유일 접근자다.
- **FR-13** 사유 채널은 **자문(advisory)** — 진실 원천은 NaN 셀 자체이며, 사유는 반환 직후·변환 이전에 판독한다. `financials=None`이면 재무 팩터는 예외 없이 전 구간 NaN + `MISSING_INPUT`으로 degrade한다(데이터 미연동이 카탈로그·타 팩터를 차단하지 않음).

## 4. 팩터 카탈로그 (32종, 산식·결측 조건 확정)

> 본 표가 산식의 권위 원천이다. 기대값 하드코딩 없는 산식 재도출 테스트로 각 행을 검증한다.

### 4.1 가격·기술 팩터 (7종, `required_data=("ohlcv",)`)

| id | 카테고리 | 파라미터 (기본/제약) | 산출 | 산식 (pandas 규약) |
|---|---|---|---|---|
| `price` | price | — | `close` | **수정주가** 종가 패스스루 (D2 — Rule/Formula가 가격 자체를 참조 가능하게 함) |
| `sma` | trend | `window:int=20 (≥1)` | `sma` | `close.rolling(window).mean()` |
| `ema` | trend | `span:int=20 (≥1)` | `ema` | `close.ewm(span=span, adjust=False).mean()` |
| `rsi` | momentum | `window:int=14 (≥1)` | `rsi` | `delta=close.diff()`; `gain=delta.clip(lower=0).rolling(window).mean()`; `loss=(-delta.clip(upper=0)).rolling(window).mean()`; `rs=gain/loss.replace(0,NaN)`; `100-100/(1+rs)` — **rolling 단순평균 변형(Wilder EMA 아님)** |
| `macd` | trend | `fast:int=12, slow:int=26, signal:int=9 (fast<slow)` | `macd`,`signal` | `macd = ema(fast) - ema(slow)` (adjust=False); `signal = macd.ewm(span=signal, adjust=False).mean()` |
| `bollinger` | volatility | `window:int=20 (≥2), num_std:float=2.0 (>0)` | `middle`,`upper`,`lower` | `middle=rolling.mean()`; `upper/lower = middle ± num_std × rolling.std(ddof=1)` |
| `momentum` | momentum | `lookback:int=252 (≥1), skip:int=21 (0≤skip<lookback)` | `momentum` | `close.shift(skip)/close.shift(lookback) - 1` |

warm-up 구간(rolling/shift 미충족)은 NaN + `INSUFFICIENT_HISTORY`.

### 4.2 펀더멘털 Phase F1 — 밸류에이션 기반 (11종, `required_data=("valuation",)`)

입력: `valuation` 일별 프레임(§6.1). 파라미터 없음.

| id | 카테고리 | 산출 | 산식 | NaN 조건 (사유) |
|---|---|---|---|---|
| `per` | value | `per` | `close / eps` | `eps ≤ 0` (NON_POSITIVE_DENOMINATOR) |
| `pbr` | value | `pbr` | `close / bps` | `bps ≤ 0` (〃) |
| `earnings_yield` | value | `earnings_yield` | `eps / close` | `close ≤ 0` (〃) |
| `dividend_yield` | value | `dividend_yield` | `dps / close` | `close ≤ 0` (〃) |
| `eps` | quality | `eps` | 패스스루 | 입력 결측 (MISSING_INPUT) |
| `bps` | quality | `bps` | 패스스루 | 〃 |
| `roe_approx` | quality | `roe_approx` | `eps / bps` | `bps ≤ 0` |
| `payout_ratio` | quality | `payout_ratio` | `dps / eps` | `eps ≤ 0` |
| `eps_growth` | growth | `eps_growth` | **스텝 정의**: 일별 EPS는 공시 갱신 전까지 상수인 스텝함수이므로, "직전 **상이한** EPS 스텝 값 대비 증가율"로 정의. 스텝 갱신 시점에만 값이 갱신되고 그 사이는 직전 성장률 유지. 스텝 = 값의 임의 변경(별도 임계 없음 — 원천 데이터가 스텝형임을 전제) | 첫 스텝 이전(INSUFFICIENT_HISTORY), 직전 스텝 ≤ 0(NON_POSITIVE_DENOMINATOR) |
| `peg` | growth | `peg` | `per / (eps_growth × 100)` | per NaN 또는 `eps_growth ≤ 0` |
| `market_cap` | size | `market_cap` | 패스스루 | 입력 결측 |

### 4.3 펀더멘털 Phase F2 — 재무제표 기반 (14종)

입력: `financials`(분기, §6.2)를 밸류에이션 일별 인덱스에 **as-of 정렬**(FR-17) 후 계산. `psr`/`pcr`/`ev_ebitda`는 `required_data=("valuation","financials")`, 나머지는 `("financials",)` 포함. 연결/별도 재무가 공존하면 **연결(consolidated) 우선, 부재 시 별도(separate) 폴백**으로 단일 계열을 구성한 뒤 계산한다.

| id | 카테고리 | 산식 | NaN 조건 |
|---|---|---|---|
| `psr` | value | `market_cap / revenue` | `revenue ≤ 0` |
| `pcr` | value | `market_cap / operating_cash_flow` | `ocf ≤ 0` |
| `ev_ebitda` | value | `(market_cap + total_debt − cash_and_equivalents) / (operating_income + depreciation_amortization)` | EBITDA ≤ 0 |
| `roa` | quality | `net_income / total_assets` | `total_assets ≤ 0` |
| `roic` | quality | `operating_income × (1 − tax_rate) / invested_capital`, `tax_rate = income_tax/pretax_income`를 `[0,1]` 클램프 | `invested_capital ≤ 0` |
| `gross_margin` | quality | `gross_profit / revenue` | `revenue ≤ 0` |
| `operating_margin` | quality | `operating_income / revenue` | 〃 |
| `net_margin` | quality | `net_income / revenue` | 〃 |
| `gp_to_assets` | quality | `gross_profit / total_assets` | `total_assets ≤ 0` |
| `revenue_growth` | growth | 전년 동기 분기 대비: `(Q_t − Q_{t-4}) / Q_{t-4}` | `Q_{t-4} ≤ 0` 또는 부재(INSUFFICIENT_HISTORY) |
| `op_income_growth` | growth | 〃 (operating_income) | 〃 |
| `debt_to_equity` | stability | `total_debt / total_equity` | `total_equity ≤ 0` (자본잠식) |
| `current_ratio` | stability | `current_assets / current_liabilities` | `current_liabilities ≤ 0` |
| `interest_coverage` | stability | `operating_income / interest_expense` | `interest_expense == 0` (ZERO_DENOMINATOR) |

## 5. 파생 팩터 구현 규칙

파생 팩터(`peg`, `roe_approx` 등)는 다른 Factor 인스턴스를 `get_factor`로 참조하지 않는다(레지스트리 결합·순서 의존 금지). 산식은 순수 헬퍼 모듈에 단일 원천으로 두고 공유한다.

## 6. 펀더멘털 데이터 계층

### 6.1 저장 (additive DDL, `CREATE TABLE IF NOT EXISTS` 멱등)
- **FR-14** `fundamental_daily` — PK `(symbol, date)`. 컬럼: `close, per, pbr, eps, bps, div, dps, market_cap, shares, source, fetched_at`. `close`는 OHLCV 테이블과 **동일한 조정 종가 원천**(두 테이블 간 주가 정합 불변식).
- **FR-15** `financial_statements` — PK `(symbol, fiscal_year, fiscal_quarter, statement_scope)`. 핵심 계정 컬럼(§4.3 산식이 요구하는 전체): `revenue, gross_profit, operating_income, net_income, pretax_income, income_tax, total_assets, total_debt, total_equity, current_assets, current_liabilities, operating_cash_flow, interest_expense, depreciation_amortization, cash_and_equivalents, invested_capital` + 기간 메타 `period_end, disclosure_date` + `source, fetched_at`. 저장은 `INSERT OR REPLACE` 멱등 upsert. 도메인: `statement_scope ∈ {"consolidated","separate"}`, `fiscal_quarter ∈ {1,2,3,4}`. `invested_capital` 등 원장에 직접 없는 파생 계정은 **어댑터가 산출·저장**하며 팩터는 저장값을 소비한다.

### 6.2 수집
- **FR-16** `FundamentalProvider` Protocol(밸류에이션·재무제표 조회)을 OHLCV `DataProvider`와 분리 정의한다. 어댑터 3종: `PyKrxFundamentalAdapter`(밸류에이션 — PyKrx 일별 fundamental + 시가총액 + 종가 병합, PyKrx는 함수 내부 lazy import), `DartFundamentalAdapter`(재무제표, §8), `FixtureFundamentalAdapter`(테스트 — 합성 CSV, OHLCV 픽스처와 동일 종목 정합).
- **FR-17 (as-of 정렬, look-ahead 방지)** 분기 재무 값은 일별 인덱스에 **공시일(`disclosure_date`) 기준 as-of 정렬**한다: 각 일자에 "그 시점까지 공시된 가장 최근 값"을 forward-fill하고, 최초 공시 이전 구간은 NaN + `INSUFFICIENT_HISTORY`. 동일 `disclosure_date`에 복수 레코드가 있으면 `period_end`가 최신인 레코드가 우선한다. 벡터 연산(`merge_asof` 계열)으로 수행한다.

### 6.3 수집 실행 경로·품질 게이트

- **FR-17a (수동 수집 CLI)** `fetch-fundamental` 명령을 제공한다: 심볼 목록(기본 watchlist)·기간·데이터 종류(valuation/financials)·provider를 옵션으로 받아 수집·upsert한다. 재실행은 멱등이다. Daily 파이프라인의 자동 수집(PRD-R03 §7)은 본 명령과 **동일한 Provider·upsert 경로를 공유**한다.
- **FR-17b (수집 품질 게이트)** 수집 데이터는 저장 전 최소 검증을 통과해야 한다: PK 중복 없음, 일자 오름차순·미래 일자 없음, 음수 불가 필드(`market_cap`, `shares`) 위반 없음. 위반 행은 저장에서 제외하고 사유와 함께 수집 결과에 기록한다(수집 전체를 중단하지 않음).

## 7. CLI

- **FR-18** `list-factors [--category <c>]`: id·표시명·카테고리·설명 표. `show-factor <id>`: 설명·파라미터 명세(기본값·제약)·산출 컬럼·`required_data`·데이터 가용성 힌트. 미존재 id는 힌트와 non-zero 종료. `fetch-fundamental`: FR-17a.

## 8. Phase F2-b — DART 실데이터 연동 (후속 단계, 본 PRD 완료 정의에서 제외)

본 PRD의 재무 팩터 완료 정의는 **합성 Fixture 결정론 검증**까지다. 실연동 단계는 별도 진행하되, 착수 시 다음 4개 항목의 명세 확정이 선행되어야 한다(미확정 시 어댑터 구현이 공전하는 지점):
1. 종목코드 → DART `corp_code`(8자리) 해결 — `corpCode.xml` 다운로드·캐싱·조회 규약.
2. FR-15 전 계정에 대한 DART `account_nm` 완전 매핑 열거(누락 계정은 해당 팩터 영구 NaN).
3. `disclosure_date`/`period_end` 추출 규약(`rcept_dt` 등) — as-of 정렬(FR-17)의 조인 키.
4. 연결(`CFS`) 우선 → 별도(`OFS`) 폴백 정책 — 별도재무만 공시하는 종목 누락 방지.
완료 정의: 실 종목에서 F2 14종이 NaN 아닌 값 산출 + 실데이터 통합 테스트.

## 9. Acceptance Criteria (pytest 기계 검증, 기대값 하드코딩 금지)

- **AC-01** 레지스트리 32종(§4) 등록, 중복 0, 카테고리 분포 일치. 중복 id 등록 예외.
- **AC-02** 전 팩터: 산식 재도출 parity(§4 표 기준) · 결정론(2회 동일) · 입력 비변조 · 컬럼==output · warm-up NaN.
- **AC-03** 파라미터: ParamSpec default==생성자 기본값(전수) · 범위 위반 오버라이드 거부 · 교차 제약 위반(`macd` fast≥slow) 인스턴스화 거부(FR-02a) · **동일 팩터 상이 파라미터 2인스턴스 독립 계산**(예: sma(5)≠sma(20)).
- **AC-04** 디스패치: `compute_factor`가 양 시그니처 올바르게 라우팅, `required_data≠("ohlcv",)` 전 팩터가 FactorInput 호환(전수 스캔).
- **AC-05** 결측: §4 표의 각 NaN 조건 → NaN + 지정 사유, `financials=None` → F2 전 구간 NaN+MISSING_INPUT 무예외, `get_factor_notes`가 디스패치 경계 통과 후 판독 가능.
- **AC-06** as-of: 공시일 이전 셀 미반영(경계 픽스처), 동일 공시일 복수 레코드 tie-break(`period_end` 최신), `fundamental_daily.close`==OHLCV close 정합.
- **AC-07** INV-1 AST 스캔 green. 2테이블 존재 + 멱등 재연결. CLI 3계약(목록/상세/미존재 non-zero).
- **AC-08** 수집: `fetch-fundamental` 멱등 재실행(중복 0) · 품질 게이트 위반 행 제외+기록(FR-17b) · Fixture provider로 오프라인 검증.

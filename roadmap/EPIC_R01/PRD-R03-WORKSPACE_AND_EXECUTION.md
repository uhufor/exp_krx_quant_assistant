# PRD-R03 : No-Code Strategy Workspace & Execution

**Milestone**: Milestone 2 — No-Code Quant Strategy Platform (본 PRD가 완결)
**Status**: Approved for implementation
**의존**: PRD-R01 (팩터 계산), PRD-R02 (정의·영속·검증) / 플랫폼 기반 인프라(OHLCV 파이프라인·리포트·Telegram 알림)는 기존 자산으로 전제

---

## 1. Background & Goal

R01/R02는 정의+영속+검증까지만 제공한다. 본 계층은 그 위의 **impure 실행·오케스트레이션 계층**으로, 사용자가 코드 없이 전략을 **설계 → 검증 → 백테스트 → Daily 운영 → 재사용**까지 하나의 흐름으로 완결하게 한다.

**Workspace의 실체 = 오케스트레이션 파사드(`WorkspaceService`) + CLI 명령 표면.** GUI/웹은 없다. "No-Code"의 의미: 사용자는 선언형 데이터(factor/formula/rule id 참조 + 파라미터)만으로 전략을 완성하며, Python·백테스트 엔진 지식을 요구받지 않는다.

**전략 모델은 선언형 단일이다(D3).** Baseline의 하드코딩 전략 5종은 등가 Built-in Template(§8)로 대체되며, 본 기능 완성 후 Daily의 전략 원천은 활성 선언형 전략 단일이 된다. 따라서 전략 열거·활성화·실행 경로는 각각 하나뿐이다.

## 2. User Journey

```
1. strategy-create (--template <id> 가능) → 초안 생성
2. 지표 선택: Built-in Factor(list-factors) | Custom Factor(list-formulas) — 동형 UX(id+컬럼+파라미터)
3. (선택) formula-create — 파생 지표 정의
4. rule-create — 조건 정의 (기존 Rule 재사용 가능)
5. Rule을 entry/exit 역할로 Strategy에 조합
6. strategy-validate — 실행 없는 전이 검증
7. strategy-backtest — 지표 확인 (수익률·MDD·Sharpe 등)
8. strategy-activate — Daily 운영 편입
9. (선택) Template 저장 / strategy-export / strategy-import
```

## 3. Scope

**In**: `WorkspaceService` 파사드 / CLI 명령 표면 / 활성화 영속(`strategy_activation`) / 선언형 평가 엔진(Formula compute + Rule 평가) / 백테스트 실행 / Daily 파이프라인 연결(universe 해석 포함, D5) / Built-in Template 5종 + 사용자 Template(`strategy_templates`) / JSON Import·Export.

**Out (확정)**: GUI·웹 / Portfolio·리밸런싱 집행 / 실시간·주문 집행 / AI 생성·최적화 / 신규 백테스트 지표·리스크 모델(§8 최소 지표 집합만) / 정규화·순위 함수(R02 Out 유지).

## 4. 파사드·검증·활성화

- **FR-01** `WorkspaceService`는 storage를 주입받아 도메인 CRUD·검증·평가·백테스트·Template·Import/Export를 하나의 사용자 API로 조합한다. CLI는 이를 얇게 감싼다(로직은 파사드에, I/O는 CLI에).
- **FR-02 (전이 검증)** `validate_strategy`는 **실행 없이** R02 검증기를 조합한다: Strategy 구조·rule 슬롯 → 참조 Rule 각각(factor/formula/params 검증 포함) → 참조 Formula 각각(순환 포함)의 전이 검증. dangling 참조는 저장·활성화 전에 거부된다. 신규 검증 로직을 만들지 않는다(R02 재사용) — 단 하나의 예외도 없다: runnable 판정도 R02 `is_runnable`을 소비한다.
- **FR-03 (활성화)** 활성 상태는 `strategy_activation`(`strategy_id` PK, `active`, `updated_at`) 테이블에 영속된다. `activate`/`deactivate`/`is_active`/`list_active`(id 정렬). 전이는 idempotent, 미존재 행 = 비활성.
- **FR-04 (활성화 전제)** 활성화는 (a) 전략 존재, (b) `is_runnable == True`(roles + entry ≥1), (c) 전이 검증 통과를 요구한다. 초안(rule=None)·검증 실패 전략의 활성화는 거부된다. **활성화된 전략은 항상 실행 가능하다**(D4).
- **FR-04a (활성 참조 보호)** 활성 전략 자신, 그리고 활성 전략이 전이적으로 참조하는 Rule/Formula의 **수정(upsert)·삭제는 거부**된다 — 해당 전략을 비활성화한 후에만 가능하다. 거부 메시지에는 차단 사유인 활성 전략 id 목록을 포함한다. (운영 중 전략의 행동이 조용히 바뀌는 것을 차단. 저장 계층은 활성 상태를 모르므로 이 게이트는 Workspace 파사드의 책임이다 — R02 REQ-P4 정합.)

## 5. 평가 엔진 (선언형 → 시계열)

### 5.1 Formula compute
- **FR-05** `evaluate_formula(formula, data: FactorInput, resolve_formula) -> pd.Series`: 산술 트리를 재귀 평가한다. 리프 — factor 피연산자는 **파라미터 적용 인스턴스**로 계산(§5.3), 상수는 브로드캐스트, formula 참조는 재귀 평가 + formula_id 메모이제이션(DAG는 저장 시점에 비순환 보장, 방어적 visited 가드 유지).

### 5.2 Rule 평가
- **FR-06** `evaluate_rule(rule, data, resolve_formula) -> pd.Series(bool)`: Predicate는 좌/우를 시계열/스칼라로 평가 후 비교, Composition은 자식 불리언 시계열의 AND(전항 논리곱)/OR/NOT. `FactorOperand`는 팩터 레지스트리 기전으로, `FormulaOperand`는 `evaluate_formula`로 라우팅된다 — **Formula는 factor 레지스트리에 병합하지 않는다**(별도 네임스페이스, 사용자에게는 동형 "지표 선택" UX로만 통합 노출).

### 5.3 파라미터 해석 (D1)
- **FR-07** `FactorOperand(factor_id, column, params)` 평가는 `get_factor(factor_id, **params)`로 **오버라이드 적용 인스턴스**를 생성해 계산한다(빈 params = 기본값). 계산 결과 캐시 키는 `(factor_id, canonical(params))` — 동일 팩터·상이 파라미터는 별개 시계열이다(SMA(5) ≠ SMA(20)). 캐시(팩터 계산·Formula 메모)의 **수명은 단일 (전략, 종목) 평가 컨텍스트로 한정**된다 — 종목 간·전략 간·실행 간 공유 금지(데이터 오염 차단).

### 5.4 수치 규약 (전 평가 공통, 결정론의 핵심)
- **FR-08** 다음 규약을 고정한다:
  - **인덱스**: 모든 시계열을 공통 기준 인덱스(대상 종목 close의 DatetimeIndex)에 reindex 후 연산. reindex는 **정렬만 수행하며 보간·forward-fill을 하지 않는다** — 저빈도→일별 변환은 팩터 계산 단계의 as-of 정렬(R01 FR-17)이 유일한 지점이며, reindex로 생긴 결측은 아래 NaN 규약을 따른다.
  - **NaN**: 산술에서는 전파. **비교·논리의 불리언화 직전에 NaN → False**(warm-up·결측 구간이 신호를 만들지 않음).
  - **div0**: 0 분모 → NaN (무예외 — 결측 허용 값 산출).
  - **교차**: `crosses_above(l, r) = (l > r) & (l.shift(1) <= r.shift(1))`, below 대칭. shift 첫 원소 NaN → False.
  - **스칼라 브로드캐스트**: 비교·교차 진입 시 상수 피연산자를 기준 인덱스 Series로 브로드캐스트(스칼라 `.shift` 크래시 구조적 차단).
  - **결정론**: 동일 (정의, 데이터) → 2회 평가 동일.

### 5.5 데이터 계약
- **FR-09** 평가 전에 전략이 전이적으로 참조하는 factor/formula의 `required_data` 합집합(`ohlcv`/`valuation`/`financials`)을 파생하고, `FactorInput`에 해당 프레임이 없으면 **`EvaluationError`로 명확히 실패**한다(누락 데이터 종류 + 요구 id 포함). 조용한 오작동 금지.

## 6. 백테스트 실행

- **FR-10 (시그널 사상)** `roles` 슬롯을 소비한다: entry 역할의 각 Rule을 평가해 **AND 결합** → `entries`, exit 역할 동일 → `exits`("모든 조건 충족 시" 의미론 — 조건 간 OR는 Rule 내부 논리로 표현). exit 부재/빈 리스트 → `exits = all False`(청산 신호 없음 = 보유 지속). entries/exits는 close 인덱스 정렬 + NaN→False가 보장된 불리언 Series다.
- **FR-11 (백테스트 계약)** 종목별로 `(close, entries, exits, fees, slippage)`를 **Baseline의 시그널 백테스트 엔진(vectorbt `Portfolio.from_signals`, long-only·전량 진입/청산·일봉 `freq="D"`)에 투입**해 지표를 산출한다 — 신규 엔진을 만들지 않는다. 체결 시점·동시 entry/exit 신호 처리는 해당 엔진의 기본 의미론을 따르며 커스텀 규칙을 추가하지 않는다. 벤치마크 지정 시 상대 성과를 함께 산출한다.
- **FR-12 (최소 지표 집합)** 백테스트 결과는 최소 다음을 포함한다: 총수익률, CAGR, 최대낙폭(MDD), Sharpe, 승률, 거래 횟수, 총 비용(수수료+슬리피지), (벤치마크 지정 시) 초과수익률. 벤치마크 산출 불가 시 값 NaN + 사유 문자열. 지표 산식의 진실 원천은 **Baseline의 기존 지표 산출 구현(BacktestMetrics)** 이며, 본 PRD는 신규 산식을 정의하지 않는다(재사용·무변경).
- **FR-13 (CLI)** `strategy-backtest <id>`: 대상 종목(universe 해석, §7)·기간·비용(fees/slippage 기본값 설정 파일)·데이터 소스(fixture 포함)를 옵션으로 받아 지표를 표로 표시한다. runnable이 아니거나 검증 실패면 실행 전 거부.

## 7. Daily 운영 통합

- **FR-14 (실행 집합)** Daily의 전략 실행 집합 = `list_active()`(id 정렬 — 순서 결정론). 활성 전략이 0건이면 명확한 오류로 실패한다(조용한 no-op 금지). 기존 `settings.strategy.enabled` 기반 코드형 전략 선택 기전은 본 기능 완성과 함께 제거된다(전략 원천 단일화, D3).
- **FR-14a (전환 시드)** 최초 전환(마이그레이션) 시 Built-in Template 5종(§8)을 **자동으로 전략 인스턴스화하고 활성화**하여 Baseline과 동일한 전략 세트가 끊김 없이 운영되게 한다. 시드는 멱등·1회성이다: 해당 전략 id가 이미 존재하면 정의·활성 상태를 일절 변경하지 않는다(사용자의 비활성화·수정 결정을 재실행이 덮어쓰지 않음).
- **FR-15 (universe 해석, D5)** 각 전략의 실행 대상 = `universe.symbols`(비어 있으면 파이프라인 watchlist 전체). Daily의 **데이터 수집 대상 = watchlist ∪ (활성 전략들의 universe 합집합)** 이므로 universe 심볼은 watchlist 포함 여부와 무관하게 실행된다. 수집 실패·데이터 부재 종목은 해당 전략×종목 오류로 격리 기록된다.
- **FR-16 (부가 데이터 자동 수집·공급)** Daily는 활성 전략들의 required_data 합집합에 따라 필요한 펀더멘털 데이터(valuation/financials)를 **파이프라인 선행 단계에서 자동 수집·저장**한 뒤 `FactorInput`으로 공급한다 — R01의 `FundamentalProvider`·upsert·품질 게이트 경로를 재사용하며 `fetch-fundamental` CLI(R01 FR-17a)와 동일 경로다. 수집 실패는 전략×종목 단위로 격리된다(FR-17). ohlcv만 요구하는 전략 집합에서는 수집·로딩이 발생하지 않는다.
- **FR-17 (실패 격리)** 전략×종목 단위 평가·데이터 실패는 해당 단위의 오류로 기록되고 나머지 실행은 계속된다(부분 실패 격리). 실행 단계 이벤트는 기존 run 이벤트 로깅 관례로 남긴다.
- **FR-18 (다운스트림 동형)** 백테스트 결과 → 신호 분류 → Report A(결정론)/Report B(LLM) → 알림의 기존 파이프라인 경로를 그대로 통과한다. 신호·리포트·중복 발송 방지(content-hash outbox) 규약은 플랫폼 기반 인프라의 것을 재사용하며 신규 경로를 만들지 않는다.

## 8. Template (재사용)

- **FR-19 (Built-in Template 5종, D3)** Baseline의 하드코딩 전략 5종과 등가인 다음 5종을 코드 상수 번들(Strategy 정의 + 참조 Rule, 즉시 검증 통과 상태)로 제공한다. 전부 D1(파라미터)·D2(price 팩터)로 표현되며, 기존 코드형 전략 구현은 Template 제공과 함께 실행 경로에서 제거된다:

| template id | 전략 | entry | exit |
|---|---|---|---|
| `ma_crossover` | 이동평균 골든크로스 | `sma(window=20)` crosses_above `sma(window=60)` | crosses_below 대칭 |
| `rsi_breakout` | RSI 과매도 반등 | `rsi(window=14) < 30` | `rsi > 70` |
| `bollinger_band` | 볼린저 평균회귀 | `price.close` crosses_below `bollinger(20, 2.0).lower` | `price.close` crosses_above `bollinger.middle` |
| `macd` | MACD 크로스 | `macd(12,26,9).macd` crosses_above `.signal` | crosses_below 대칭 |
| `momentum` | 절대 모멘텀 | `momentum(252, 21) > 0` | `momentum < 0` |

- **FR-20 (Template 생성)** `create_from_template(template_id, new_id)`는 번들을 복제해 새 id의 사용자 전략으로 저장한다(참조 Rule이 store에 없으면 함께 upsert). 산출물은 일반 저장 게이트·검증을 통과해야 하며 즉시 runnable이다.
- **FR-21 (사용자 Template)** `save_as_template(strategy_id, template_id)`는 전략+전이 참조를 Export 번들 형상으로 `strategy_templates` 테이블에 저장한다. 저장한 Template로 재생성 시 동등한 정의가 복원된다. CRUD(목록·조회·삭제) 제공. 사용자 Template id는 Built-in Template id와 충돌할 수 없다(거부). `strategy-template-list`는 Built-in과 사용자 Template를 출처(builtin/user) 구분과 함께 통합 열거한다.

## 9. Import / Export

- **FR-22** `export_strategy(id)` → Strategy + 전이 참조된 모든 Rule·Formula를 하나의 결정론적 JSON 번들로 직렬화(키 정렬, 스키마 버전 포함).
- **FR-23** `import_strategy(bundle, on_conflict="reject")` → **Formula → Rule → Strategy 의존 위상 순서**로 검증·저장. 참조 무결성(dangling·순환·컬럼 불일치·params 위반)은 기존 저장 게이트로 거부. id 충돌 처리(Strategy/Rule/Formula 공통): 기존 엔티티와 canonical JSON이 **동일하면 재사용(통과, 멱등)**, 다르면 기본 거부·`--overwrite` 명시 시 대체(단 FR-04a 활성 참조 보호가 우선한다). Export→Import 왕복은 동일 정의를 복원한다.

## 10. CLI 명령 표면 (확정 목록)

`strategy-create [--template]` / `strategy-show` / `strategy-edit` / `strategy-delete` / `strategy-list` / `strategy-validate` / `strategy-activate` / `strategy-deactivate` / `strategy-backtest` / `strategy-template-list` / `strategy-export` / `strategy-import` · `rule-create` / `rule-show` / `rule-delete` / `list-rules` · `formula-create` / `formula-show` / `formula-delete` / `list-formulas` (+ R01의 `list-factors`/`show-factor`/`fetch-fundamental`).

규약: 정의 입력은 JSON 파일 경로 또는 stdin. `strategy-edit` 등 편집 명령의 의미론은 **전체 정의 JSON 교체**다(부분 필드 패치 없음 — 왕복 무손실 계약과 정합). rich 표/패널 출력, 한국어 오류 + non-zero 종료, CLI 변경 시 README 사용법 동기화.

## 11. 아키텍처 불변식

| INV | 내용 | 강제 |
|---|---|---|
| **INV-1 (계층 단방향)** | workspace는 R01/R02·storage·백테스트 엔진을 **소비만** 한다. R01/R02 패키지에 평가·실행·storage 의존을 역주입하지 않는다 | R01/R02 순수성 AST 스캔 무변경 green + 정의 패키지의 workspace import 부재 스캔 |
| **INV-2 (단일 실행 경로)** | 모든 전략(Built-in Template 포함)은 동일한 평가→시그널→백테스트→Daily 경로를 통과한다. 전략별 특수 분기 금지 | 설계 리뷰 + Template 실행 테스트 |
| **INV-3 (결정론)** | 동일 (정의+데이터+주입 시각) → 평가·백테스트·Daily 산출 동일. 범위는 신호·Report A까지 — LLM 기반 Report B는 결정론 범위 밖(mock Provider 주입 시에만 결정론) | 2회 실행 동등 테스트(run_id·시각 주입 고정, LLM mock) |
| **INV-4 (참조 무결성)** | 저장·활성화·Import 시점 차단 + 실행 시점 `EvaluationError` 격리 | 저장 게이트 + AC |

## 12. Acceptance Criteria (pytest, 합성 Fixture + 격리 DB + LLM mock)

- **AC-01 파사드/CLI**: 전 명령 왕복(생성→조회→수정→삭제, DB 재조회 일치), 오류 시 non-zero.
- **AC-02 활성화**: idempotent 전이·재조회 보존, 초안/검증 실패/미존재 전략 활성화 거부, 활성 참조 엔티티 수정·삭제 거부(FR-04a — 차단 사유에 전략 id 포함, 비활성화 후 허용).
- **AC-03 평가**: 알려진 fixture 입력에 대한 Formula 파생 시계열·다단 DAG 위상, Rule 비교/AND/OR/NOT/교차 정확성, **params 오버라이드 반영(sma(5) vs sma(20) 상이 + 골든크로스 교차 발생)**, NaN→False·div0→NaN·스칼라 교차 케이스, 2회 평가 동일.
- **AC-04 데이터 계약**: required_data 미충족 → EvaluationError(누락 종류+id 포함), ohlcv-only 전략 집합에서 부가 로딩 0.
- **AC-05 백테스트**: fixture로 최소 지표 집합 산출, CLI 표시, runnable 아님 → 실행 전 거부.
- **AC-06 Daily**: 활성 집합 실행·id 정렬 순서, universe 해석(전략별 부분 종목 + 수집 대상 합집합), 전략×종목 실패 격리 후 완주, 활성 0건 명확 실패, 펀더멘털 요구 전략의 자동 수집 경로(FR-16, Fixture provider), 전환 시드 멱등(FR-14a — 최초 1회 생성+활성, 기존 id 존재 시 무변경), 신호→리포트→알림 경로 통과.
- **AC-07 Template**: Built-in 5종 전부 즉시 검증 통과 + fixture 백테스트 완주, 생성물 runnable, 사용자 Template 저장→재생성 동등.
- **AC-08 Import/Export**: 왕복 동일 정의 복원, 위상 순서 저장, dangling/순환 거부, 충돌 처리 3분기(동일 내용 멱등 통과 / 상이 내용 거부 / `--overwrite` 대체) 검증.
- **AC-09 순수성·문서**: INV-1 스캔 green, README 사용법 동기화, `pytest`·`ruff` 전량 통과.

## 13. 저장 스냅샷

본 PRD가 추가하는 테이블: `strategy_activation`, `strategy_templates` (additive). R02의 3종(`strategies`/`rules`/`formulas`)과 플랫폼 기반 테이블(OHLCV·신호·리포트·알림 등)은 각 소관 유지.

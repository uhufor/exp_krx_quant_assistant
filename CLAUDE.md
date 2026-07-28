# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 언어 규칙

**모든 응답, 설명, 질문은 한국어로 작성한다.** 코드·명령어·파일 경로는 영어 그대로 유지.

## 프로젝트 현황 (개발 우선순위)

이 저장소는 두 축으로 구성된다.

| 축 | 범위 | 상태 |
|---|---|---|
| **데일리 어시스트** | `jobs/daily.py` → `signals/` → `reports/` → `notify/` (watchlist 기반 일일 리포트 + Telegram) | **1차 완성 · 홀딩**. 회귀만 방지하고 신규 기능은 추가하지 않는다. 예외는 **플랫폼 산출물을 소비하기 위한 배선**(R05 포트폴리오 리밸런싱 권고) — 데일리 고유 기능을 늘리는 것이 아니라 플랫폼이 만든 결과를 흘려보내는 작업이다. |
| **퀀트 플랫폼** | `factors/` · `formula/` · `rule/` · `strategy/` · `workspace/` · `screening/` · `api/` · `web/` (노코드 전략 설계·백테스트·전종목 스크리닝·GUI) | **활성 개발**. 신규 작업은 기본적으로 이쪽이다. |

작업 지시가 모호할 때는 플랫폼 축을 우선 가정하고, 데일리 파이프라인은 "플랫폼 산출물을
소비하는 다운스트림"으로만 취급한다(전략 원천은 이미 활성 선언형 전략 단일 — D3).

## Commands

```bash
# Lint
uv run ruff check src/

# Test (all)
uv run pytest tests/ -q

# Test (single file)
uv run pytest tests/unit/test_signals.py -q

# Test (single case)
uv run pytest tests/integration/test_daily_job.py::test_daily_job_dry_run -q

# Web(GUI 프론트엔드) 테스트/빌드
cd web && npm test && npm run build

# CLI — 데일리(홀딩)
uv run python -m quant_krx validate-config
uv run python -m quant_krx run-daily --dry-run       # 알림 없이 전체 파이프라인 실행
uv run python -m quant_krx run-daily --no-dry-run    # Telegram 실제 발송
uv run python -m quant_krx run-daily --dry-run --data-source fixture --as-of 2024-12-02
                                                     # 오프라인·과거 시점 재현(검증용)
uv run python -m quant_krx show-reports --type all
uv run python -m quant_krx data-health          # 데이터 신선도 점검(조회 전용)

# CLI — 플랫폼(활성 개발)
uv run python -m quant_krx list-factors              # 팩터 35종 목록
uv run python -m quant_krx show-factor <id>          # 팩터 상세
uv run python -m quant_krx fetch-fundamental --provider fixture  # 펀더멘털 오프라인 수집
uv run python -m quant_krx formula-create / rule-create / strategy-create <file.json|->
uv run python -m quant_krx strategy-backtest <id> --data-source fixture [--no-cache]
uv run python -m quant_krx backtest-list / backtest-show <run_id> / backtest-compare <id> <id>
uv run python -m quant_krx validation-run <id> [--spec spec.json] [--mode holdout|walkforward]
uv run python -m quant_krx validation-list / validation-show <validation_id>
uv run python -m quant_krx strategy-activate / strategy-deactivate <id>
uv run python -m quant_krx strategy-export / strategy-import   # 전이 참조 포함 JSON 번들
uv run python -m quant_krx screen-create / screen-validate / screen-run <id> --as-of <date>
uv run python -m quant_krx serve-gui                 # http://127.0.0.1:8765 (API + web/dist)
```

CLI는 총 40여 개 커맨드(`__main__.py`)이며 접두사로 계층이 갈린다: `formula-*` / `rule-*` /
`strategy-*` / `screen-*` / `validation-*`. GUI는 동일 서비스 계층(`WorkspaceService`, `ScreeningService`)을
`api/routers/`를 통해 소비하므로 CLI·GUI 결과는 항상 일치해야 한다.

**Python 3.10 필수** (`vectorbt`가 `python_requires="<3.11"` 제약). `.python-version` 참고.

## Architecture

### 계층 지도 (의존은 항상 아래→위 단방향)

```
factors/          순수 계산 35종            ← 실행·저장 계층 import 금지(INV-1, AST 강제)
formula/ rule/ strategy/   선언형 정의·검증  ← 평가·실행 없음(순수 데이터)
workspace/        평가·백테스트·템플릿 파사드  → WorkspaceService
screening/        전종목 조건 스크리닝(독립)   → ScreeningService (rule/formula/strategy 미참조,
                                              workspace.numeric leaf만 공유 — EPIC-03 D2)
api/ + web/       FastAPI 라우터 + React GUI  → 위 두 서비스만 소비
jobs/daily.py     데일리 어시스트(다운스트림)   → 활성 선언형 전략만 실행
```

`screening/`과 `workspace/`는 **형제 관계이며 서로를 import하지 않는다**. 스크리닝은
조건 정의만 영속(`screening_conditions`)하고 실행 결과는 저장하지 않는다(휘발성, D5).

### 파이프라인 (jobs/daily.py)

```
watchlist → fetch_ohlcv → validate → VectorBT backtest → Signal → Report A + B → Telegram
```

`DailyJob.run()` 가 단일 진입점. `run_id = YYYYMMDD-{uuid4[:8]}` 가 실행 단위 키.

### 핵심 프로토콜

| 프로토콜 | 위치 | 구현체 |
|---------|------|--------|
| `DataProvider` | `data/base.py` | `PyKrxAdapter`, `FixtureAdapter` (테스트 전용) |
| `Strategy`(레거시) | `quant/base.py` | `quant/strategies/*.py` 5종 — **프로덕션 경로에서 미사용**(D3로 선언형 Built-in Template 5종에 흡수). `tests/unit/test_quant.py`만 참조하는 사실상 dead code이며, 신규 전략은 여기 추가하지 않는다. `quant/base.py`의 `BacktestResult`/`BacktestMetrics`와 `quant/metrics.py`는 `workspace/backtest.py`가 계속 재사용한다. |
| `LLMProvider` | `llm/base.py` | `AnthropicProvider`, `OpenAICompatibleProvider`, `MockProvider` |
| `Factor` | `factors/base.py` | 35종 (`factors/catalog/` — 카테고리 10종, `list-factors`로 조회) |
| `FundamentalProvider` | `data/fundamental_base.py` | `PyKrxFundamentalAdapter`(밸류에이션), `DartFundamentalAdapter`(재무제표, DART Open API), `FixtureFundamentalAdapter`(테스트) |

### 팩터 플랫폼 (factors/, data/ — refined_epics/*-R01-FACTOR_PLATFORM.md)

`factors/`는 실행·저장·수집 계층을 import하지 않는 순수 계산 계층(INV-1,
`tests/unit/factors/test_purity_ast.py`로 AST 강제)이다. 유일 인가 실행 API는
`compute_factor(factor, data)` — `required_data==("ohlcv",)`면 `factor.compute(ohlcv_df)`,
그 외에는 `factor.compute(FactorInput)`으로 분기한다. 팩터는 `get_factor(id, **params)`로
파라미터 오버라이드 인스턴스를 생성하고, `list_factors(category=None)`으로 카탈로그를 조회한다.

결측 셀은 NaN이 진실 원천이며 사유(`FactorNote`: `MISSING_INPUT` / `NON_POSITIVE_DENOMINATOR`
/ `ZERO_DENOMINATOR` / `INSUFFICIENT_HISTORY`)는 반환 프레임의 `attrs["notes"]`에 실리고
`get_factor_notes(df)`가 유일 접근자다(반환 직후·변환 이전에 판독).

`data/`는 `factors/`를 역참조하지 않는다(단방향, `data/loader.py`가 `FactorInput`을 직접
import하지 않고 구조적으로 동일한 로컬 `FundamentalBundle`을 반환하는 이유). 재무제표
as-of 정렬은 `factors/asof.py`(`merge_asof` backward, tie-break은 `(disclosure_date asc,
period_end desc)` 정렬 후 그룹 최상단 선택)가 담당하며, 수집 품질 게이트 4종(PK 중복·
일자 오름차순·미래 일자·음수 필드)은 `data/quality.py` → `data/upsert.py::upsert_fundamental`
단일 강제점에서 수행된다(위반 행 제외+기록, 수집 중단 없음, 재실행 멱등).

### 데이터 흐름

- `DataProvider` → `OHLCVData(df, meta)` → `DataValidator` → DuckDB `ohlcv_daily`
- `Strategy.run()` → `BacktestResult(metrics, trades, equity_curve)` → `SignalClassifier` → `Signal`
- `Signal` → DuckDB `signals` 저장 → `ReportARenderer`(결정론적) + `ReportBRenderer`(LLM)
- `RenderedReport` → DuckDB `reports` 저장 → `TelegramNotifier.send()` → `notification_outbox`

### DuckDB 스키마 (19개 테이블, `Database.connect()`에서 모두 실행)

| 그룹 | 파일 | 테이블 |
|---|---|---|
| baseline(데일리, 무변경) | `storage/schema.py` | `symbols`, `ohlcv_daily`, `data_fetch_runs`, `strategy_runs`, `signals`, `reports`, `notification_outbox`, `run_events` |
| 펀더멘털 | `data/schema.py` | `fundamental_daily`(밸류에이션 일별, `close`는 `ohlcv_daily.close`와 동일 원천), `financial_statements`(분기, PK `(symbol, fiscal_year, fiscal_quarter, statement_scope)`) |
| 선언형 정의 | `storage/definition_schema.py` | `formulas`, `rules`, `strategies` |
| 워크스페이스 | `storage/workspace_schema.py` | `strategy_activation`, `strategy_templates` |
| 스크리닝 | `data/screening_schema.py` | `screening_conditions` (조건 정의) |
| 스크리닝 캐시 | `data/screening_cache_schema.py` | `screening_result_cache` (P2 — 동적 유니버스 반복 실행 비용 절감용) |
| 백테스트 이력 | `storage/backtest_schema.py` | `backtest_runs` (P3 — 파라미터·지표·자산곡선, 거래내역은 미저장) |
| 검증 이력 | `storage/validation_schema.py` | `validation_runs` (P4 — 폴드별 IS/OOS + 과최적화 요약, 캐시 키 없음) |

스키마 진화는 **additive만** — 신규 테이블 추가는 되고 기존 DDL 변경은 금지(공통 불변식 6).
`strategy_runs`는 데일리 전용이고, `strategy-backtest`/GUI 백테스트 결과는 `backtest_runs`에
쌓인다(두 테이블은 별개 — 데일리 경로는 P3 이력에 관여하지 않는다).

`notification_outbox`의 UNIQUE 키는 `(channel, content_hash)` — `run_id`가 아님. 동일 내용은 재실행해도 재발송되지 않음.

### 설정 (config/settings.py)

Pydantic Settings, `.env` 자동 로드. 네스티드 설정:
- `settings.evaluation.name` — 평가 프로필 (`balanced` | `aggressive` | `conservative` | `research`)
- `settings.llm.mock` — `True`면 `MockProvider` 사용 (테스트/드라이런)
- `settings.llm.model` — Anthropic 모델 ID (기본: `claude-sonnet-4-6`)

## 중요 제약사항

**vectorbt 1.0.0 API**: `pf.trades.records["fees"]` 없음 → `entry_fees + exit_fees` 사용 (`quant/metrics.py` 참조).

**PyKrx lazy import**: `pykrx`는 `pkg_resources` 모듈 레벨 임포트 시 setuptools 82와 충돌(`pkg_resources`는 setuptools 82부터 제거됨) → `setuptools>=70,<82`로 캡핑. `pykrx_adapter.py`/`pykrx_fundamental.py`는 `_krx_stock()` 내부에서 lazy import(단, 이 자체가 setuptools 충돌을 막지는 않음 — 캡핑이 실제 해결책).

**PyKrx KRX 로그인**: `pykrx>=1.2.8`부터 `data.krx.co.kr` 밸류에이션/시가총액 엔드포인트(`get_market_fundamental_by_date`, `get_market_cap_by_date`)가 로그인 세션을 요구한다(OHLCV는 비로그인도 동작). 환경변수 `KRX_ID`/`KRX_PW`(`.env`)가 필요하며, pykrx가 `os.getenv()`로 직접 읽으므로 `__main__.py`의 `load_dotenv()` 호출이 선행되어야 `.env` 값이 적용된다. 미설정/만료 시 `PyKrxFundamentalAdapter.fetch_valuation`이 명확한 `RuntimeError`로 실패한다.

**DART 재무제표 연동** (`roadmap/EPIC_R01/TRD-R01-D-DART_FINANCIALS.md`): `DartFundamentalAdapter.fetch_financials`는 opendart.fss.or.kr Open API로 재무제표 14계정을 실수집한다. 환경변수 `DART_API_KEY`(`.env`)가 필요하며 DART도 `os.getenv()`로 직접 읽는다(KRX_ID/PW와 동일 관례). 종목코드→`corp_code` 매핑은 `data/dart_corp_code.py`(`corpCode.xml` 로컬 캐시, 7일 경과 시 재다운로드), 계정 매핑은 `data/dart_account_mapping.py`(account_id 우선, account_nm 폴백)가 담당한다. 연결(CFS) 우선 → 별도(OFS) 폴백. `invested_capital`은 DART 원천 태그가 없는 파생 컬럼으로 `total_assets`를 그대로 대입한다. `fetch_valuation`은 DART가 제공하지 않는 시장 데이터라 `NotImplementedError` 유지(PyKrxFundamentalAdapter 사용). `strategy-backtest`/`screen-run`의 `--data-source`는 `fixture`(OHLCV+펀더멘털 전부 오프라인 합성) | `krx_dart`(OHLCV·밸류에이션=PyKrx, 재무제표=DART 조합 실데이터) 둘뿐이다 — `fdr`은 pykrx가 기능을 완전히 포괄해 제거됨(FDRAdapter 삭제). 증분 수집 시 API 호출 전 `_worth_attempting()`이 `[start,end]` 범위 밖(계산상 공시 불가능)인 분기를 걸러내고, "아직 미공시"로 확인된 분기는 `DartMissingPeriodCache`(`~/.cache/quant_krx/dart_missing_periods.parquet`)가 1시간 TTL로 재확인을 생략한다(TRD-R04 부록 — 재호출 버그 2건 수정).

**포트폴리오 백테스트(P1)**: `StrategyDefinition.portfolio`(schema_version 2, additive)가 있으면
`run_backtest`가 `run_portfolio_backtest`로 분기한다 — 없으면 기존 종목별 경로 그대로(하위호환).
핵심은 `from_signals`가 아니라 **목표 비중 행렬 → `from_orders(size_type='targetpercent',
cash_sharing=True, call_seq='auto')`** 라는 점이다(신호로는 "최대 N종목" 제약을 표현할 수 없음).
비중 계산은 `workspace/portfolio.py`(순수, vectorbt 미import). 확정 규칙: 거래는 리밸런싱일에만 ·
균등 분배는 선택 수 k 기준 1/k · 진입/청산 동시 발생 시 청산 우선 · 랭킹 NaN 종목 제외 ·
동점은 종목코드 오름차순. 포트폴리오 모드 결과는 `results["__portfolio__"]` 하나뿐이고
`per_symbol`은 빈 dict다(자본 공유라 종목별 독립 성과가 정의되지 않음).
`portfolio.ranking`이 참조하는 factor/formula는 **factor_refs 일치 검사·활성 참조 보호·데이터
계약 게이트 세 곳 모두에 배선되어 있다**(`strategy/validation.py`, `workspace/service.py::
_transitive_closure`, `workspace/evaluation.py::_required_data_by_kind`) — 새 참조 슬롯을 추가할
때 이 세 곳을 함께 고치지 않으면 저장은 되는데 실행에서 터지거나 조용히 빈 결과가 나온다.

**동적 유니버스(P2)**: `Universe.kind="screening"`이면 리밸런싱 시점마다 스크리닝을 재평가해
대상 종목을 교체한다. **`portfolio` 정책이 없으면 저장이 거부된다**(종목별 독립 모드에서는
시점별 교체가 의미를 갖지 않음). 닭-달걀 문제(대상 종목을 알아야 OHLCV를 수집하는데 종목은
시점마다 정해짐)는 `workspace/dynamic_universe.py`가 푼다 — 달력 기준 **앵커** 날짜마다 미리
스크리닝해 합집합을 수집 대상으로 삼고, 엔진이 실제 거래일로 물으면 **그 이하 최근 앵커
결과를 backward 매칭**해 돌려준다(매칭이 없으면 수집하지 않은 종목이 후보에 올라 조용히
탈락한다). `workspace`는 `screening`을 import하지 않고 `UniverseResolver`를 주입받는다(형제
관계 유지) — 주입은 CLI(`__main__.py`)와 API(`api/routers/backtests.py`)가 담당한다.

**생존 편향**: `DataProvider.list_symbols(market, as_of=None)`의 `as_of`는 과거 구간 백테스트에서
필수다 — 없으면 현재 상장 종목만 후보가 되어 상장폐지 종목이 빠지고 성과가 부풀려진다.
`resolve_scan_universe(..., as_of=)` → `PyKrxAdapter.list_symbols`가 `get_market_ticker_list(date)`로
전달한다. **ETF/ETN 제외 목록도 `DataProvider.list_etf_symbols`/`list_etn_symbols`(as_of 지원)로
provider를 통해 조회한다** — 예전에는 `screening/universe.py`가 pykrx를 직접 호출해서
`--data-source fixture`로 오프라인 실행을 해도 이 필터가 켜져 있으면 KRX 로그인을 시도하고
자격증명이 없으면 스크리닝이 죽었다. 제외 목록 조회 실패는 빈 집합으로 흡수한다(제외가 덜
적용될 뿐, 일시적 조회 오류로 매일 잡이 죽지 않게).
스크리닝 결과는 `screening_result_cache`에 `(condition_id, 조건 본문 해시, as_of)`로 캐시된다 —
EPIC-03 D5(결과 미저장)를 반복 백테스트 비용 때문에 완화한 것이며, 조건 수정 시 해시가 바뀌어
자동 무효화되고 조건 삭제 시 함께 지워진다.

**OOS/워크포워드 검증(P4)**: `workspace/validation.py`가 폴드마다 **학습 구간에서만** 그리드를
돌려 목적함수 최댓값 파라미터를 고르고 **검증 구간에서 그 파라미터로만** 성과를 잰다. 폴드
분할은 `workspace/walkforward.py`(순수, 달력 기준, `train_end = test_start - 1일`로 무중첩),
파라미터 오버레이는 `workspace/overlay.py`(순수)다. 네 가지가 설계상 중요하다.
① **저장된 정의를 절대 건드리지 않는다** — 파생 `StrategyDefinition` + `resolve_rule`/
`resolve_formula` 래퍼를 메모리에서만 만든다(활성 참조 보호와 충돌하지 않게).
② **팩터 파라미터는 `factor_refs`만 바꿔서는 반영되지 않는다** — 실행 시 실제로 쓰이는 값은
Rule/Formula 피연산자와 `portfolio.ranking`에 적힌 것이라(`_eval_factor_operand`) 리졸버 쪽까지
같이 덮어써야 한다. 안 그러면 저장은 되는데 계산은 그대로인 **조용한 무효 스윕**이 된다.
③ **`factor.<id>@<현재값>.<param>` 선택자**가 있는 이유는 골든크로스처럼 같은 팩터를 두 번
쓰는 전략에서 선택자 없이 스윕하면 단기·장기 창이 같아져 신호가 영영 발생하지 않기 때문이다.
④ **폴드 내부 실행은 `backtest_runs`에 기록하지 않는다**(그리드×폴드만큼 쌓이면 사용자 이력이
파묻힘) — 검증 1회 = `validation_runs` 1행. 검증에는 캐시가 없다(비싸고 명시적인 작업이라
조용한 캐시 히트가 더 혼란스럽다). 데이터는 전 구간을 한 번만 조립하고 폴드는 `start`/`end`로만
자른다 — 팩터가 전 구간에서 계산된 뒤 잘린 인덱스로 정렬되므로(`numeric.align`) **워밍업 손실이
없다**. 임계값 스윕은 단일 Predicate 룰만 허용하고 AND/OR 결합 룰은 거부한다(어느 상수인지
모호한 채 통과하면 결과 전체가 거짓이 된다). 상세는 `docs/VALIDATION.md`.

**스키마 마이그레이션**: `Database._ensure_schema()`는 누락 테이블이 있을 때만 DDL을 실행한다
(요청마다 커넥션을 여는 GUI에서 동시 `CREATE TABLE`이 DuckDB 카탈로그 write-write 충돌을
일으켰기 때문). 따라서 **기존 테이블에 컬럼을 추가할 때는 `CREATE TABLE` 수정이 아니라
`BACKTEST_MIGRATION_SQL` 같은 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 목록에 넣어야 한다** —
그러지 않으면 이미 테이블이 있는 DB에서는 영영 적용되지 않는다.

**데일리 × 포트폴리오(R05)**: `jobs/daily.py`는 전략마다 분기한다 — `portfolio`가 없으면 기존
`run_single_symbol_backtest` 루프 그대로, 있으면 `run_backtest`로 계좌 단위 실행 후 **리밸런싱
권고 신호 1건**을 낸다(`symbol=__portfolio__`, `SignalType.REBALANCE`는 열거 추가라 DDL 무변경).
두 가지가 순서·의미상 중요하다. ① **동적 유니버스 계획은 OHLCV 수집보다 먼저** 세워야 한다
— 안 그러면 `symbols`가 비어 `or watchlist`가 걸려 엉뚱한 종목이 조용히 실행된다(R05가 고친
결함). ② **매매 지시는 리밸런싱 당일에만 렌더한다** — 지나간 지시를 매일 반복하면 이미 실행한
매매를 다시 하라는 뜻이 되므로, 그 외 날에는 `RebalancePlan.targets`(현재 목표 배분)만 보여준다.
"현재 보유"는 실제 계좌가 아니라 **직전 리밸런싱 목표 비중**이며 리포트가 이 가정을 명시한다.

**데이터 신선도(D3)**: `data/freshness.py::check_freshness`가 시세·밸류에이션·재무제표·자격증명을
점검해 **이상이 있을 때만** 리포트 상단 한 줄로 알린다(`ReportInput.freshness_warning`).
세 가지가 원칙이다. ① **전략이 실제로 쓰는 데이터만 점검**한다(`required_data` 기준) — 안 쓰는
데이터의 지연을 알리면 잡음이다. ② **실행을 막지 않는다** — 펀더멘털 수집 실패도 흡수하고
계속 진행한다(세션 만료 하나로 매일 잡이 멈추면 안 된다). ③ **신호가 0건이면 경고를 실을
리포트가 없으므로** 경고만 담은 알림 1건을 폴백으로 낸다(데이터가 없어 전 전략이 실패했을 때
아무 연락도 못 받는 침묵 방지). 판정 기준(`is_financials_stale`)은 `data/coverage.py`에 두어
증분 수집(`screening/fundamental_sync.py`)과 공유한다 — 기준이 갈리면 "수집은 건너뛰는데
점검은 경고하는" 모순이 생긴다.

**스크리닝 제약(EPIC-03)**: `screening/`은 `rule/`·`formula/`·`strategy/`·`workspace/evaluation.py`·
`workspace/service.py`를 import하지 않는다(`workspace/numeric.py` leaf만 예외). 제외 필터 10종 중
6종(관리종목/투자경고·위험/거래정지/정리매매/환기종목/불성실공시)과 `FormulaOperand`는
**하드 비활성화**(선택 가능한 no-op 금지) — GUI에서 disabled 렌더 + 백엔드 400 이중 방어.
빈 유니버스는 조용히 통과시키지 않고 `EmptyUniverseError`. 스크리닝은 watchlist와 무관하다
(`strategy-backtest`도 동일 — watchlist는 데일리 전용).

**로드맵 문서**: PRD/TRD/DESIGN은 `roadmap/EPIC_R0X/`에 `PRD-R0X-TOPIC.md` 규칙으로 둔다
(`.omc/specs`는 작업용 임시 산출물). R01=팩터 플랫폼+선언형 코어+워크스페이스, R02=GUI,
R03=노코드 스크리닝, R04=펀더멘털 증분 수집+팩터 순위 스크리닝,
R05=데일리 포트폴리오 리밸런싱 권고(`roadmap/EPIC_R05/DESIGN-R05-DAILY_PORTFOLIO.md`).
P4=OOS/워크포워드 검증(`docs/VALIDATION.md`).
차기 과제(P3 백테스트 이력 영속 → P1 포트폴리오 백테스트 → P2 스크리닝→유니버스 연결)와
그 근거·미결 결정 사항은 **`roadmap/BACKLOG.md`** 참고 — 새 세션에서 플랫폼 작업을 시작할 때
여기부터 읽는다.

**Report A vs B**: 동일 `signal.id`를 참조해야 함. Report A = LLM 없음, 결정론적. Report B = LLM 보조, 동일 신호 기반.

**드라이런**: `TelegramNotifier.send(dry_run=True)` 는 outbox에 아무것도 쓰지 않고 즉시 반환.

## 테스트 픽스처

`tests/fixtures/sample_ohlcv.csv`: 5종목 × 252거래일 합성 데이터. `FixtureAdapter`가 이 파일을 읽어 네트워크 없이 전체 파이프라인 테스트.

`tests/fixtures/sample_valuation.csv`(1260행, `close`는 OHLCV와 정확히 일치) /
`sample_financials.csv`(60행, 5종목×12분기): `FixtureFundamentalAdapter`가 읽으며
eps/bps 비양수·tie-break(동일 disclosure_date)·자본잠식·이자비용 0·연결재무 부재 폴백
등 경계 케이스를 포함한다.

통합 테스트는 `tmp_path` 격리 DuckDB + `LLM_MOCK=true` + `FixtureAdapter`/`FixtureFundamentalAdapter` 조합으로 외부 의존성 없이 실행됨.

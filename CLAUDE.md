# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 언어 규칙

**모든 응답, 설명, 질문은 한국어로 작성한다.** 코드·명령어·파일 경로는 영어 그대로 유지.

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

# CLI
uv run python -m quant_krx validate-config
uv run python -m quant_krx run-daily --dry-run       # 알림 없이 전체 파이프라인 실행
uv run python -m quant_krx run-daily --no-dry-run    # Telegram 실제 발송
uv run python -m quant_krx list-factors              # 팩터 32종 목록
uv run python -m quant_krx show-factor <id>          # 팩터 상세
uv run python -m quant_krx fetch-fundamental --provider fixture  # 펀더멘털 오프라인 수집
```

**Python 3.10 필수** (`vectorbt`가 `python_requires="<3.11"` 제약). `.python-version` 참고.

## Architecture

### 파이프라인 (jobs/daily.py)

```
watchlist → fetch_ohlcv → validate → VectorBT backtest → Signal → Report A + B → Telegram
```

`DailyJob.run()` 가 단일 진입점. `run_id = YYYYMMDD-{uuid4[:8]}` 가 실행 단위 키.

### 핵심 프로토콜

| 프로토콜 | 위치 | 구현체 |
|---------|------|--------|
| `DataProvider` | `data/base.py` | `FDRAdapter`, `PyKrxAdapter`, `FixtureAdapter` (테스트 전용) |
| `Strategy` | `quant/base.py` | `MACrossoverStrategy`, `RSIBreakoutStrategy` |
| `LLMProvider` | `llm/base.py` | `AnthropicProvider`, `OpenAICompatibleProvider`, `MockProvider` |
| `Factor` | `factors/base.py` | 32종 (가격·기술 7 + 밸류에이션 11 + 재무제표 14, `factors/catalog/`) |
| `FundamentalProvider` | `data/fundamental_base.py` | `PyKrxFundamentalAdapter`(밸류에이션), `DartFundamentalAdapter`(재무제표, Deferred), `FixtureFundamentalAdapter`(테스트) |

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

### DuckDB 스키마 (storage/schema.py, data/schema.py)

10개 테이블. baseline 8개(`storage/schema.py`, 무변경): `symbols`, `ohlcv_daily`,
`data_fetch_runs`, `strategy_runs`, `signals`, `reports`, `notification_outbox`, `run_events`.
펀더멘털 additive 2개(`data/schema.py`, `Database.connect()`에서 함께 실행):
`fundamental_daily`(밸류에이션 일별, `close`는 `ohlcv_daily.close`와 동일 원천),
`financial_statements`(재무제표 분기, PK `(symbol, fiscal_year, fiscal_quarter, statement_scope)`).

`notification_outbox`의 UNIQUE 키는 `(channel, content_hash)` — `run_id`가 아님. 동일 내용은 재실행해도 재발송되지 않음.

### 설정 (config/settings.py)

Pydantic Settings, `.env` 자동 로드. 네스티드 설정:
- `settings.provider.primary` — 데이터 소스 (`fdr` | `pykrx`)
- `settings.evaluation.name` — 평가 프로필 (`balanced` | `aggressive` | `conservative` | `research`)
- `settings.llm.mock` — `True`면 `MockProvider` 사용 (테스트/드라이런)
- `settings.llm.model` — Anthropic 모델 ID (기본: `claude-sonnet-4-6`)

## 중요 제약사항

**vectorbt 1.0.0 API**: `pf.trades.records["fees"]` 없음 → `entry_fees + exit_fees` 사용 (`quant/metrics.py` 참조).

**PyKrx lazy import**: `pykrx`는 `pkg_resources` 모듈 레벨 임포트 시 setuptools 82와 충돌(`pkg_resources`는 setuptools 82부터 제거됨) → `setuptools>=70,<82`로 캡핑. `pykrx_adapter.py`/`pykrx_fundamental.py`는 `_krx_stock()` 내부에서 lazy import(단, 이 자체가 setuptools 충돌을 막지는 않음 — 캡핑이 실제 해결책).

**PyKrx KRX 로그인**: `pykrx>=1.2.8`부터 `data.krx.co.kr` 밸류에이션/시가총액 엔드포인트(`get_market_fundamental_by_date`, `get_market_cap_by_date`)가 로그인 세션을 요구한다(OHLCV는 비로그인도 동작). 환경변수 `KRX_ID`/`KRX_PW`(`.env`)가 필요하며, pykrx가 `os.getenv()`로 직접 읽으므로 `__main__.py`의 `load_dotenv()` 호출이 선행되어야 `.env` 값이 적용된다. 미설정/만료 시 `PyKrxFundamentalAdapter.fetch_valuation`이 명확한 `RuntimeError`로 실패한다.

**Report A vs B**: 동일 `signal.id`를 참조해야 함. Report A = LLM 없음, 결정론적. Report B = LLM 보조, 동일 신호 기반.

**드라이런**: `TelegramNotifier.send(dry_run=True)` 는 outbox에 아무것도 쓰지 않고 즉시 반환.

## 테스트 픽스처

`tests/fixtures/sample_ohlcv.csv`: 5종목 × 252거래일 합성 데이터. `FixtureAdapter`가 이 파일을 읽어 네트워크 없이 전체 파이프라인 테스트.

`tests/fixtures/sample_valuation.csv`(1260행, `close`는 OHLCV와 정확히 일치) /
`sample_financials.csv`(60행, 5종목×12분기): `FixtureFundamentalAdapter`가 읽으며
eps/bps 비양수·tie-break(동일 disclosure_date)·자본잠식·이자비용 0·연결재무 부재 폴백
등 경계 케이스를 포함한다.

통합 테스트는 `tmp_path` 격리 DuckDB + `LLM_MOCK=true` + `FixtureAdapter`/`FixtureFundamentalAdapter` 조합으로 외부 의존성 없이 실행됨.

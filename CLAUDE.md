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

### 데이터 흐름

- `DataProvider` → `OHLCVData(df, meta)` → `DataValidator` → DuckDB `ohlcv_daily`
- `Strategy.run()` → `BacktestResult(metrics, trades, equity_curve)` → `SignalClassifier` → `Signal`
- `Signal` → DuckDB `signals` 저장 → `ReportARenderer`(결정론적) + `ReportBRenderer`(LLM)
- `RenderedReport` → DuckDB `reports` 저장 → `TelegramNotifier.send()` → `notification_outbox`

### DuckDB 스키마 (storage/schema.py)

8개 테이블: `symbols`, `ohlcv_daily`, `data_fetch_runs`, `strategy_runs`, `signals`, `reports`, `notification_outbox`, `run_events`.

`notification_outbox`의 UNIQUE 키는 `(channel, content_hash)` — `run_id`가 아님. 동일 내용은 재실행해도 재발송되지 않음.

### 설정 (config/settings.py)

Pydantic Settings, `.env` 자동 로드. 네스티드 설정:
- `settings.provider.primary` — 데이터 소스 (`fdr` | `pykrx`)
- `settings.evaluation.name` — 평가 프로필 (`balanced` | `aggressive` | `conservative` | `research`)
- `settings.llm.mock` — `True`면 `MockProvider` 사용 (테스트/드라이런)
- `settings.llm.model` — Anthropic 모델 ID (기본: `claude-sonnet-4-6`)

## 중요 제약사항

**vectorbt 1.0.0 API**: `pf.trades.records["fees"]` 없음 → `entry_fees + exit_fees` 사용 (`quant/metrics.py` 참조).

**PyKrx lazy import**: `pykrx`는 `pkg_resources` 모듈 레벨 임포트 시 setuptools 82와 충돌. `pykrx_adapter.py`는 `_krx_stock()` 내부에서 lazy import.

**Report A vs B**: 동일 `signal.id`를 참조해야 함. Report A = LLM 없음, 결정론적. Report B = LLM 보조, 동일 신호 기반.

**드라이런**: `TelegramNotifier.send(dry_run=True)` 는 outbox에 아무것도 쓰지 않고 즉시 반환.

## 테스트 픽스처

`tests/fixtures/sample_ohlcv.csv`: 5종목 × 252거래일 합성 데이터. `FixtureAdapter`가 이 파일을 읽어 네트워크 없이 전체 파이프라인 테스트.

통합 테스트는 `tmp_path` 격리 DuckDB + `LLM_MOCK=true` + `FixtureAdapter` 조합으로 외부 의존성 없이 실행됨.

# Autopilot Implementation Plan: KRX Quant Trading Assistant v1

## Source

- Spec: `.omc/specs/deep-dive-krx-quant-trading-assistant-dev.md`
- Prior ralplan consensus: `old-base-v1/plans/ralplan-consensus-korean-stock-quant-assistant-v1.md` (APPROVE)
- Prior PRD: `old-base-v1/plans/prd-korean-stock-quant-assistant-v1.md`
- Consensus gate: Architect APPROVE (×2), Critic APPROVE

## Resolved Configuration (this session)

- Python: 3.12 via `uv` on Apple Silicon arm64
- VectorBT: `vectorbt` free PyPI (~0.26.x)
- Storage: DuckDB
- Notification: Telegram Bot API
- Data: FinanceDataReader + PyKrx (DataProvider protocol)
- LLM: Anthropic Claude (primary), OpenAI-compatible (fallback)
- Scheduler: macOS launchd
- run_id format: `YYYYMMDD-{uuid4[:8]}`

## Project Structure

```
quant-krx/
├── pyproject.toml          # uv managed, Python 3.12
├── .env.example
├── README.md
├── src/
│   └── quant_krx/
│       ├── __init__.py
│       ├── config/         # Settings, watchlist, profiles
│       ├── data/           # DataProvider protocol + adapters
│       ├── storage/        # DuckDB schema + queries
│       ├── quant/          # VectorBT strategy runners
│       ├── signals/        # Signal classification engine
│       ├── reports/        # Report A (deterministic) + B (LLM)
│       ├── llm/            # LLM provider abstraction
│       ├── notify/         # Telegram + outbox manager
│       └── jobs/           # Daily orchestration entrypoint
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── ops/
    └── launchd/            # plist template
```

## Implementation Steps

### Step 1: Python 프로젝트 스캐폴드 + 설정 (독립, 즉시 착수)

Tasks:
- `uv init --python 3.12` + `pyproject.toml` 설정
- 핵심 의존성 추가: `vectorbt`, `FinanceDataReader`, `pykrx`, `duckdb`, `pandas`, `numpy`, `anthropic`, `python-telegram-bot`, `pydantic`, `pydantic-settings`
- 개발 의존성: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`
- `src/quant_krx/config/` 구현:
  - `settings.py`: Pydantic Settings 기반 (`.env` 로드)
  - `watchlist.yaml.example`: 샘플 종목 코드
  - 환경변수: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DUCKDB_PATH`
- `app validate-config` CLI 진입점 (Typer 또는 argparse)

Acceptance: `uv run python -m quant_krx validate-config` 성공 (네트워크 없이)

### Step 2: DataProvider 인터페이스 + 어댑터 (Step 1 완료 후)

Tasks:
- `src/quant_krx/data/base.py`: `DataProvider` Protocol 정의
  ```python
  class DataProvider(Protocol):
      source_name: str
      def list_symbols(self, market: str) -> list[str]: ...
      def fetch_ohlcv(self, symbol: str, start: date, end: date) -> DataFrame: ...
      def fetch_benchmark(self, symbol_or_market: str, start: date, end: date) -> DataFrame: ...
      def fetch_metadata(self, symbols: list[str]) -> dict[str, Any]: ...
  ```
- `src/quant_krx/data/fdr_adapter.py`: FinanceDataReader 구현
- `src/quant_krx/data/pykrx_adapter.py`: PyKrx 구현
- 캐싱: 수집 타임스탬프, 소스명, 조정 가정 기록
- 테스트 fixtures: 5개 종목 × 1년 OHLCV CSV

Acceptance: 픽스처로 두 어댑터 모두 정규화된 OHLCV 반환

### Step 3: DuckDB 스토리지 + 데이터 검증 (Step 1 완료 후, Step 2와 병행 가능)

Tasks:
- `src/quant_krx/storage/schema.py`: CREATE TABLE 문 정의
  ```sql
  symbols, ohlcv_daily, data_fetch_runs, strategy_runs,
  signals, reports,
  notification_outbox (UNIQUE(run_id, channel, content_hash)),
  run_events
  ```
- `src/quant_krx/storage/db.py`: DuckDB 연결 관리자 + CRUD
- `src/quant_krx/storage/validation.py`: 데이터 품질 검증
  - 누락 바 (거래일 기준)
  - 중복 날짜
  - 음수/0 가격
  - 오래된 데이터 (N 거래일 이상)
- 스토리지 라운드트립 통합 테스트

Acceptance: 불량/오래된 데이터가 quant 실행 전 플래그됨

### Step 4: VectorBT 전략 러너 (Step 2+3 완료 후)

Tasks:
- `src/quant_krx/quant/base.py`: 전략 인터페이스
- `src/quant_krx/quant/strategies/ma_crossover.py`:
  - 단기/장기 이동평균 교차 전략
  - 파라미터: `short_window`, `long_window`, `fees`, `slippage`
- `src/quant_krx/quant/strategies/rsi_breakout.py`:
  - RSI 과매수/과매도 전략
  - 파라미터: `rsi_window`, `oversold`, `overbought`
- `src/quant_krx/quant/metrics.py`: 균형 평가 메트릭 추출
  ```python
  @dataclass
  class BacktestMetrics:
      total_return: float
      benchmark_return: float
      mdd: float            # Maximum Drawdown
      sharpe: float
      sortino: float
      trade_count: int
      fees_paid: float
      slippage_cost: float
      recent_6m_return: float
      recent_12m_return: float
  ```
- 결정론적 픽스처 테스트 (같은 입력 → 같은 결과)

Acceptance: MA 교차 전략이 픽스처 데이터로 재현 가능한 통계 + 거래 기록 생성

### Step 5: 신호 엔진 (Step 4 완료 후)

Tasks:
- `src/quant_krx/signals/classifier.py`:
  ```python
  @dataclass
  class Signal:
      symbol: str
      date: date
      signal_type: Literal["buy", "sell", "hold", "watch", "no_signal"]
      strategy_name: str
      score: float
      position_recommendation: str
      evidence_metrics: BacktestMetrics
      risk_flags: list[str]
      source_run_id: str  # YYYYMMDD-{uuid4[:8]}
  ```
- 균형 프로필 규칙:
  - MDD > 30% → risk_flag 추가
  - Sharpe < 0.5 → score 감점
  - 최근 6개월 수익률 < -10% → hold/watch 고려
  - 벤치마크 대비 수익률 계산
- 신호 → DuckDB `signals` 테이블 저장

Acceptance: 각 신호에 evidence_metrics, risk_flags, source_run_id 포함

### Step 6: 리포트 생성 (Step 5 완료 후)

Tasks:
- `src/quant_krx/reports/report_a.py`: 결정론적 텍스트 렌더러
  - DuckDB `signals` 테이블에서 읽기
  - LLM 호출 없음, 외부 컨텍스트 없음
  - Markdown 형식 출력
- `src/quant_krx/reports/report_b.py`: LLM 보조 렌더러
  - 동일 `signal_id` 사용
  - 허용 컨텍스트: 티커 메타데이터, 수동 테마 레이블, 시스템 생성 레짐 요약
  - LLM 프롬프트: fact / inference / recommendation 명시적 분리 요구
- 두 리포트가 동일 `signal_id` 참조 검증 테스트

Acceptance: Report A 결정론적 (LLM 없음), Report B 동일 신호 참조

### Step 7: LLM 제공자 추상화 (Step 6과 병행 가능)

Tasks:
- `src/quant_krx/llm/base.py`: `LLMProvider` Protocol
- `src/quant_krx/llm/anthropic_provider.py`: Anthropic SDK 구현
- `src/quant_krx/llm/openai_provider.py`: OpenAI 호환 구현
- `LLM_MOCK=true` 환경변수로 mock 응답 반환
- 프롬프트 템플릿 + 모델 설정 config에서 관리

Acceptance: `LLM_MOCK=true`로 전체 파이프라인 실행 가능

### Step 8: 일일 작업 + Telegram 알림 (Step 5~7 완료 후)

Tasks:
- `src/quant_krx/jobs/daily.py`: 오케스트레이션
  ```
  run_id = YYYYMMDD-{uuid4[:8]}
  fetch → validate → quant → signal → [report_a, report_b] → notify
  ```
- `src/quant_krx/notify/telegram.py`: Bot API 발송
- `src/quant_krx/notify/outbox.py`: durable outbox 관리
  - `pending → sent | failed` 상태 전환
  - `UNIQUE(run_id, channel, content_hash)` 제약으로 중복 방지
  - 실패 재시도 지원
- CLI: `uv run python -m quant_krx run-daily [--dry-run]`
- 통합 테스트:
  - `--dry-run`: 알림 없이 리포트 생성
  - 동일 run_id 재실행: 중복 발송 없음
  - 실패 후 재시도: 발송 성공

Acceptance: dry-run 완료, live-run 정확히 1건 발송, 중복 없음

### Step 9: Mac mini 운영 패키징 (Step 8 완료 후)

Tasks:
- `ops/launchd/com.quant-krx.daily.plist.template`:
  - `StartCalendarInterval`: 한국 시장 마감 후 (Asia/Seoul 15:35 KST)
  - 로그 경로 설정
- `ops/setup.sh`: uv 설치, 환경 설정 체크리스트
- 로그/리포트 보존 설정 (config에서)

Acceptance: plist 로드 후 스케줄 실행 가능, 로그로 관찰 가능

### Step 10: 문서화 (Step 9와 병행 가능)

Tasks:
- `README.md`:
  - 설치 (uv, API 키 설정)
  - 설정 (watchlist.yaml, .env)
  - 일일 운영 (dry-run, launchd)
  - v2/v3 로드맵

Acceptance: 새 클론에서 문서만으로 dry-run 설정 가능

## Execution Lanes (병렬화)

```
Lane A (즉시):   Step 1 (scaffold)
Lane B (Step1 후 병행):  Step 2 (data) + Step 3 (storage)
Lane C (Step2+3 후):     Step 4 (quant)
Lane D (Step4 후):       Step 5 (signals)
Lane E (Step5 후 병행):  Step 6 (reports) + Step 7 (llm)
Lane F (Step5~7 후):     Step 8 (daily job + notify)
Lane G (Step8 후 병행):  Step 9 (launchd) + Step 10 (docs)
```

## Test Matrix Summary

- Unit: config 검증, OHLCV 정규화/검증, 신호 분류, Report A/B 입력 구성, LLM mock
- Integration: 어댑터 계약(픽스처), DuckDB 라운드트립, VectorBT 픽스처 실행, dry-run E2E, 중복 실행, Telegram 재시도, 스케줄러 타임존
- Smoke: `validate-config`, `fetch --dry-run`, `run-daily --dry-run`, `render-report --latest`

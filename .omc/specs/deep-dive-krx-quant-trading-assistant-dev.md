# Execution Spec: KRX Quant Trading Assistant

## Metadata

- Source workflow: deep-dive (trace + interview)
- Profile: standard
- Context type: greenfield-with-prior-plan
- Prior session: `./old-base-v1/` (deep-interview + ralplan consensus, 2026-06-27)
- Final ambiguity: ~8%
- Threshold: 20%
- Trace artifact: `.omc/specs/deep-dive-trace-krx-quant-trading-assistant-dev.md`
- Prior spec: `old-base-v1/specs/deep-interview-korean-stock-quant-assistant.md`

---

## Goal

로컬 Mac mini에서 매일 한 번 실행되는 KRX 한국 주식 퀀트 어시스턴트를 구축한다. 사용자가 정의한 관심 종목(watchlist)에 대해 VectorBT 기반 퀀트 전략을 실행하고, 두 가지 일일 리포트를 생성해 Telegram으로 발송한다:

- **Report A**: 순수 퀀트 결과 기반의 결정론적 해석 (LLM 없음)
- **Report B**: 동일한 퀀트 신호 + 허용된 컨텍스트를 사용한 LLM 보조 해석

사용자가 최종 투자 결정을 내린다. v1은 주문 실행 없음.

---

## Desired Outcome

매일 장 마감 후 또는 다음 장 개장 전, 시스템이 자동으로:
1. KRX 주식 데이터 갱신 (FinanceDataReader + PyKrx 어댑터)
2. VectorBT 퀀트 전략 실행 및 신호 평가
3. Report A (결정론적) + Report B (LLM 보조) 생성
4. Telegram으로 일일 리포트 발송
5. 리포트와 실행 기록을 DuckDB에 저장 (이후 신호 품질 검토용)

---

## In Scope

- 로컬 Mac mini 배치 런타임 (launchd 스케줄러)
- Python + `vectorbt` (free PyPI) 퀀트/백테스트 엔진
- FinanceDataReader + PyKrx 어댑터 (공통 인터페이스 뒤)
- v1 유니버스: 사용자 정의 watchlist (설정 파일로 코드 변경 없이 수정)
- v2 방향: 테마별 리포트
- v3+ 방향: KOSPI/KOSDAQ 전체 스크리닝
- 균형 잡힌 신호 평가 프로필 (기본값): 벤치마크 대비 수익률 + MDD 가이드레일 + Sharpe/Sortino + 거래 빈도 + 수수료/슬리피지 + 최근 6~12개월 로버스트니스
- DuckDB 로컬 스토리지 (단일 파일, 분석 쿼리 최적화)
- 외부 LLM API (Anthropic Claude 우선, OpenAI 호환 폴백)
- Report A/B 비교를 통한 LLM 유용성 측정
- Telegram 알림 채널 (Bot API 토큰)
- 재조정 최적화는 권고 리포트만 (주문 실행 없음)
- 테마 발견은 리포트 출력만

---

## Out of Scope / Non-Goals

- v1 자동 주문 실행
- v1 실시간 장중 알림
- v1 원시 뉴스/공시 크롤링
- 상용/공개 서비스 요구사항
- 법적/컴플라이언스 제품화
- 완전 자율 포트폴리오 리밸런싱
- LLM 출력을 매수/매도의 유일한 판단 근거로 취급

---

## Resolved Decisions (이번 세션 확정)

| 항목 | 결정 | 근거 |
|------|------|------|
| VectorBT 패키지 | `vectorbt` (free PyPI, ~0.26.x) | 라이선스 없음, 오픈소스로 충분 |
| Python 버전 | 3.12 | Apple Silicon arm64에서 numba 바이너리 휠 안정적 |
| Mac 아키텍처 | Apple Silicon (arm64, M1/M2/M3/M4) | numba 설치 경로 및 휠 선택에 반영 |
| 환경 매니저 | `uv` (Homebrew로 설치) | 가장 빠른 Python + venv 관리, lockfile 지원 |
| 스토리지 | DuckDB | OHLCV 분석 쿼리 최적화, 단일 파일, Python 패키지 |
| 알림 채널 | Telegram (Bot API) | 무료, 간단, 한국 사용자에게 친숙 |
| `run_id` 형식 | `YYYYMMDD-{uuid4[:8]}` (예: `20260630-a1b2c3d4`) | 날짜 기반 감사 가능 + 충분한 고유성 |
| notification_outbox 유일성 | 스토리지 레벨 UNIQUE 제약: `run_id + channel + content_hash` | 재시작 후 중복 발송 방지 |
| LLM Report B 컨텍스트 (v1) | 수동 테마 레이블 + 티커 메타데이터 + 시스템 생성 레짐 요약 | 원시 뉴스/공시 크롤링 제외 |

---

## Architecture

```
config/          watchlist, strategy profiles, evaluation profiles, provider/scheduler/report settings
data/            FinanceDataReader + PyKrx 어댑터 (공통 인터페이스)
storage/         DuckDB 영속성 (OHLCV, 신호, 리포트, 알림 outbox, 실행 이벤트)
quant/           vectorbt 전략 러너 (파라미터화된 전략 템플릿)
signals/         전략 출력 → buy/sell/hold/watch/no-signal 변환
reports/         Report A (결정론적, LLM 없음) + Report B (LLM 보조)
llm/             외부 LLM API 추상화 (Anthropic + OpenAI 호환)
notify/          Telegram 발송 + durable outbox 관리
jobs/            일일 오케스트레이션 진입점 (fetch → validate → quant → signal → report → notify)
tests/           단위 / 통합 / 스모크
```

### 데이터 소스 전략

```python
class DataProvider(Protocol):
    def list_symbols(self, market: str) -> list[str]: ...
    def fetch_ohlcv(self, symbol: str, start: date, end: date, interval: str = "1d") -> DataFrame: ...
    def fetch_benchmark(self, symbol_or_market: str, start: date, end: date) -> DataFrame: ...
    def fetch_metadata(self, symbols: list[str]) -> dict: ...
    @property
    def source_name(self) -> str: ...
```

v1 구현: `FinanceDataReaderAdapter`, `PyKrxAdapter`. 설정 파일로 전환 가능.

### DuckDB 스키마 (핵심 테이블)

```sql
symbols, ohlcv_daily, data_fetch_runs, strategy_runs, signals, reports,
notification_outbox (UNIQUE(run_id, channel, content_hash)), run_events
```

### 신호 객체 구조

```
symbol, date, signal_type (buy/sell/hold/watch/no_signal),
strategy_name, score, position_recommendation,
evidence_metrics: {total_return, benchmark_return, mdd, sharpe, trade_count, fees_slippage, recent_6m_return},
risk_flags, source_run_id (YYYYMMDD-{uuid4[:8]})
```

---

## Implementation Steps

1. **Python 프로젝트 스캐폴드 + 설정**
   - `uv init --python 3.12`, `pyproject.toml`, 타입 지정 설정, 샘플 watchlist, `.env.example`
   - Acceptance: `uv run app validate-config` (네트워크 없이 설정 로드 + watchlist 검증)

2. **데이터 제공자 인터페이스 + 첫 어댑터**
   - FinanceDataReader, PyKrx 어댑터를 `DataProvider` 프로토콜 뒤에 구현
   - 캐싱, 소스 메타데이터(소스명, 수집 타임스탬프, 조정 가정) 포함
   - Acceptance: 소규모 watchlist 수집 → 정규화된 일별 OHLCV

3. **DuckDB 스토리지 + 데이터 검증**
   - 스키마 생성, OHLCV/심볼/수집 실행 저장
   - 누락 바, 중복 날짜, 음수 가격, 오래된 데이터 검증
   - `notification_outbox` UNIQUE 제약: `(run_id, channel, content_hash)`
   - Acceptance: 불량/오래된 데이터가 퀀트 실행 전에 플래그됨

4. **VectorBT 기준선 전략 러너**
   - 이동평균 교차 트렌드 기준선 + RSI 또는 변동성 돌파 기준선
   - 균형 평가 메트릭 추출: 총 수익률, 벤치마크 대비, MDD, Sharpe/Sortino, 거래 수, 수수료/슬리피지, 최근 6~12개월 수익률
   - Acceptance: 같은 입력 → 같은 통계 + 거래 기록 (재현 가능)

5. **신호 엔진**
   - 전략 메트릭/현재 포지션 → buy/sell/hold/watch/no_signal
   - 각 신호: 증거 메트릭, 리스크 플래그, `source_run_id`
   - Acceptance: 신호마다 audit trail 포함

6. **리포트 생성**
   - Report A: 저장된 구조화 퀀트 출력의 결정론적 렌더러 (LLM 없음)
   - Report B: 동일 신호 객체 + 허용 컨텍스트 → LLM 제공자 호출
   - Acceptance: 두 리포트가 동일한 `signal_id` 참조, Report A에는 LLM 호출 없음

7. **LLM 제공자 추상화**
   - Anthropic SDK 우선, OpenAI 호환 폴백
   - 프롬프트 + 모델 설정 설정 파일로 관리
   - 모의 모드 + 실제 제공자 모드
   - Acceptance: `LLM_MOCK=true`로 전체 파이프라인 실행 가능

8. **일일 작업 + Telegram 알림 어댑터**
   - 단일 명령: fetch → validate → quant → signal → reports → notify
   - `notification_outbox`: pending → sent/failed 상태 전환, content_hash 기반 중복 방지
   - Acceptance: dry-run은 알림 없이 리포트 작성; live-run은 정확히 1건 발송; 중복 재실행 시 재발송 없음

9. **Mac mini 운영 패키징**
   - `launchd` plist 템플릿 (Asia/Seoul 시장 마감 후 실행)
   - 로그/리포트 보존 설정
   - Acceptance: 스케줄링 가능 + 로그로 관찰 가능

10. **문서화 + 로드맵 노트**
    - README: 설치, 설정, 일일 운영, v2/v3 로드맵
    - Acceptance: 새 로컬 클론에서 문서만으로 dry-run 설정 가능

---

## Acceptance Criteria

- Watchlist 종목을 코드 변경 없이 설정 파일로 변경 가능
- 데이터 레이어가 설정 또는 DI로 두 어댑터 이상 전환 가능
- 일별 OHLCV가 전략 실행 전에 정규화/검증됨
- 같은 입력 데이터+파라미터로 VectorBT 전략 실행이 재현 가능
- 백테스트 출력에 총 수익률, 벤치마크 대비 수익률, MDD, Sharpe/Sortino, 거래 수, 수수료/슬리피지, 최근 기간 성과 포함
- 신호가 결정론적이고 증거 메트릭 저장
- Report A와 B가 동일한 `signal_id` 참조
- Report A가 결정론적이고 LLM 없음
- Report B가 비퀀트 컨텍스트를 명시하고 결정론적 신호를 덮어쓰지 않음
- dry-run 일일 작업이 외부 알림 없이 완료
- live 일일 작업이 정확히 1건 발송
- 동일한 완료된 일일 작업 재실행 시 Telegram 중복 발송 없음
- 실패한 알림을 durable outbox에서 재시도 가능
- 네트워크 의존 테스트에 mock/fixture 대안 있음
- v1에 주문 API 또는 브로커리지 실행 경로 없음

---

## Constraints

- 사용자가 최종 투자 결정을 내린다
- v1 주문 API 연동 없음
- 퀀트 신호 생성은 결정론적이고 감사 가능해야 함
- LLM 출력은 Report A(퀀트 전용)와 B(보조)로 명확히 분리
- 데이터 수집은 어댑터로 대체 가능해야 함
- 미래 자동화가 v1을 브로커리지와 결합하지 않고 가능해야 함

---

## Non-Goals

(In Scope 참조의 반대)

---

## Assumptions Exposed

1. `vectorbt` (free PyPI ~0.26.x)의 API로 균형 평가 메트릭 전부 추출 가능
2. FinanceDataReader + PyKrx가 KRX watchlist 수준의 데이터 품질에 충분
3. Mac mini가 항상 장 마감 후 수분 내 온라인 상태
4. Telegram Bot API가 daily report 발송에 충분한 신뢰성 제공
5. DuckDB 단일 파일이 v1 watchlist 규모(수십~수백 종목)에 충분

---

## Technical Context

- **런타임**: macOS + Apple Silicon (arm64), Python 3.12, uv 환경 관리
- **핵심 의존성**: `vectorbt`, `FinanceDataReader`, `pykrx`, `duckdb`, `pandas`, `numpy`, `anthropic`
- **스케줄러**: macOS `launchd` plist
- **알림**: Telegram Bot API (`python-telegram-bot` 또는 `httpx` 직접 호출)
- **환경 변수**: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- **프로젝트 경로**: `/Users/uhufor/develop/step/quant-krx/`

---

## Roadmap

### v1: Watchlist 일일 퀀트 어시스턴트 (현재 구현 대상)
- Mac mini 로컬 배치 런타임
- Watchlist 설정
- FinanceDataReader + PyKrx 어댑터
- VectorBT 기준선 전략
- 균형 평가 프로필
- 일일 리포트 생성 + Telegram 발송
- Report A/B 분리

### v2: 테마 + 리밸런싱 리포트
- 테마 설정, 테마 구성원 매핑
- 리밸런싱 권고 리포트 (실행 없음)

### v3: 시장 스크리닝
- KOSPI/KOSDAQ 전체 스크리닝
- 상장폐지/관리종목 처리
- 데이터 품질 점수화

### v4: 브로커/API 준비
- 한국투자증권 Open API 어댑터 (선택적)
- 페이퍼 트레이딩 시뮬레이션
- 주문 실행 전 명시적 사용자 승인 게이트

---

## Ontology

- **watchlist**: 사용자가 관심 있는 종목 코드 목록
- **strategy**: VectorBT 기반 파라미터화된 퀀트 전략 (예: MA 교차, RSI)
- **signal**: `buy|sell|hold|watch|no_signal` + 증거 메트릭 + 리스크 플래그 + run_id
- **run_id**: `YYYYMMDD-{uuid4[:8]}` 형식의 일일 실행 식별자
- **Report A**: LLM 없는 결정론적 퀀트 설명 리포트
- **Report B**: 동일 신호 + 컨텍스트 + LLM 해석이 포함된 보조 리포트
- **provider/adapter**: `DataProvider` 프로토콜을 구현하는 데이터 소스 어댑터
- **notification_outbox**: `run_id + channel + content_hash` 기반 exactly-once 발송 보장 테이블

---

## Trace Findings

### 트레이스 요약

Lane 1 (세션 마이그레이션): 기존 6개 Markdown 파일은 내용 변경 없이 그대로 사용 가능. `.omx/` 경로 문자열을 실제 파일 위치로 업데이트하고 `state.spec_path`를 연결하는 것이 전부다.

Lane 2 (스펙 실행 가능성): PRD + ralplan은 아키텍처 관점에서 완전하다. 3가지 사전 결정(VectorBT 버전, 스토리지, 알림 채널)이 이번 세션에서 해결됐다. `run_id` 형식도 확정됐다. NEEDS_MINOR_UPDATE → READY로 전환.

Lane 3 (환경 전제조건): 환경은 완전 미설치 상태 (Xcode Python 3.9.6만 있음). Apple Silicon + Python 3.12 + uv 조합으로 명확한 설치 경로 확보. numba arm64 바이너리 휠은 Python 3.12에서 안정적.

### 이번 인터뷰에서 해결된 Lane Critical Unknowns

- Lane 2: `vectorbt` (free PyPI) 확정 → Step 4부터 올바른 API 사용
- Lane 3: Apple Silicon arm64 확정 → Python 3.12 + uv 설치 경로 확정
- Lane 2: 알림 채널 Telegram 확정 → `python-telegram-bot` 또는 `httpx` 직접 호출
- Lane 2: DuckDB 확정 → Step 3 스키마 UNIQUE 제약 구현 경로 확정
- Lane 2: `run_id` = `YYYYMMDD-{uuid4[:8]}` 확정

### 인터뷰 트랜스크립트 (이번 세션 결정)

- Round 1: VectorBT → `vectorbt` (free), Mac → Apple Silicon (arm64), 알림 → Telegram
- Round 2: 스토리지 → DuckDB

---

## Planning Handoff

이전 세션 계획 문서 위치:
- 스펙: `old-base-v1/specs/deep-interview-korean-stock-quant-assistant.md`
- PRD: `old-base-v1/plans/prd-korean-stock-quant-assistant-v1.md`
- ralplan 컨센서스: `old-base-v1/plans/ralplan-consensus-korean-stock-quant-assistant-v1.md`
- 테스트 스펙: `old-base-v1/plans/test-spec-korean-stock-quant-assistant-v1.md`

현재 스펙 (이 문서): `.omc/specs/deep-dive-krx-quant-trading-assistant-dev.md`

권장 다음 단계: `autopilot` — PRD의 10개 구현 단계가 이미 상세하므로 ralplan 반복 없이 직접 실행.

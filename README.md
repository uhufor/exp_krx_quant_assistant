# KRX 한국 주식 퀀트 어시스턴트

한국 주식 시장(KRX)의 관심 종목에 대해 매일 퀀트 분석을 실행하고 Telegram으로 리포트를 발송하는 개인용 의사결정 지원 도구.

> **중요**: 이 도구는 개인 투자 참고용입니다. 투자 권유가 아니며 최종 투자 결정은 본인이 내립니다.

## 특징

- **Report A**: 순수 퀀트 결과 기반 결정론적 리포트 (LLM 없음)
- **Report B**: 동일 신호 + LLM 컨텍스트 보조 리포트
- **균형 평가**: MDD, Sharpe, 초과수익률, 최근 기간 수익률 종합 평가
- **종목별/리포트별 개별 메시지**: 종목마다, Report A/B마다 별도 Telegram 메시지로 발송 (종목명 병기, 예: `380550 - 뉴로핏`)
- **Exactly-once 알림**: durable outbox로 중복 발송 방지
- **Mac mini 자동 실행**: launchd로 매일 장 마감 후 자동 실행

## 아키텍처

```
데이터 수집 (FDR/PyKrx) → 검증 → DuckDB 저장
    ↓
VectorBT 전략 실행 (MA 교차, RSI 돌파)
    ↓
신호 분류 (buy/sell/hold/watch/no_signal)
    ↓
Report A (결정론적) + Report B (LLM 보조)
    ↓
Telegram 발송 (durable outbox)
```

## 설치

### 요구사항

- macOS (Apple Silicon 권장)
- [Homebrew](https://brew.sh)
- API 키: Anthropic (Claude), Telegram Bot

### 1단계: uv 설치

```bash
brew install uv
```

### 2단계: 프로젝트 클론 및 의존성 설치

```bash
git clone <repository-url>
cd quant-krx
uv sync
```

### 3단계: 환경 설정

```bash
cp .env.example .env
# .env 파일을 편집하여 API 키 설정
```

필수 환경변수:
```env
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### 4단계: 관심 종목 설정

```bash
cp config/watchlist.yaml.example config/watchlist.yaml
# config/watchlist.yaml 편집
```

```yaml
symbols:
  - "005930"   # 삼성전자
  - "000660"   # SK하이닉스
market: KRX
```

### 5단계: 설정 확인

```bash
uv run python -m quant_krx validate-config
```

## 전략

| 이름 | 유형 | 핵심 아이디어 |
|------|------|--------------|
| `ma_crossover` | 추세 추종 | 단기(20일)/장기(60일) MA 골든·데드크로스 |
| `rsi_breakout` | 역추세 | RSI 30 이하 매수 / 70 이상 매도 |
| `bollinger_band` | 평균 회귀 | 가격이 밴드(MA ± 2σ) 이탈 시 신호 |
| `macd` | 모멘텀 | 12/26 EMA 차이의 9일 시그널선 교차 |
| `momentum` | 중장기 추세 | 12-1개월 가격 모멘텀 (Jegadeesh & Titman) |

기본적으로 5개 전략 모두 활성화됩니다.

## 사용법

### 전략 목록 확인

```bash
uv run python -m quant_krx list-strategies
```

### Dry-run (알림 없이 테스트)

```bash
# 전체 전략 실행
LLM_MOCK=true uv run python -m quant_krx run-daily --dry-run

# 특정 전략만 선택 (콤마 구분)
LLM_MOCK=true uv run python -m quant_krx run-daily --dry-run --strategies ma_crossover,macd
```

### 실제 실행 (Telegram 발송)

```bash
uv run python -m quant_krx run-daily --no-dry-run

# 특정 전략만
uv run python -m quant_krx run-daily --no-dry-run --strategies bollinger_band,momentum
```

### 상시 비활성화 (설정 파일)

`.env` 에 원하는 전략만 지정하면 `--strategies` 없이도 해당 전략만 실행됩니다:

```env
# .env — 콤마 구분 또는 JSON 배열 형식 모두 지원
ENABLED_STRATEGIES=ma_crossover,macd,bollinger_band
# ENABLED_STRATEGIES=["ma_crossover","macd","bollinger_band"]
```

### 결과 리포트 조회

`run-daily` 실행 후 종목별 신호와 리포트를 콘솔에 출력합니다.

```bash
# 최근 실행 결과 조회 (Report A, 기본)
uv run python -m quant_krx show-reports

# Report B 조회 (LLM 해석 포함)
uv run python -m quant_krx show-reports --type B

# Report A + B 모두 조회
uv run python -m quant_krx show-reports --type all

# 특정 run_id 조회
uv run python -m quant_krx show-reports --run-id 20260630-e5284252
```

출력 예시:

```
                         신호 요약
┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━━┳━━━━━━━━┓
┃ 종목   ┃ 전략        ┃ 신호  ┃ 점수 ┃ 총수익률 ┃  MDD  ┃ Sharpe ┃
┡━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━━╇━━━━━━━━┩
│ 105190 │ ma_crossover│ BUY   │ 0.95 │  284.6% │ 20.8% │   2.69 │
│ 042700 │ ma_crossover│ SELL  │ 0.31 │  100.7% │ 38.1% │   1.05 │
│ 380550 │ ma_crossover│ WATCH │ 0.00 │  -33.2% │ 40.3% │  -1.08 │
└────────┴─────────────┴───────┴──────┴─────────┴───────┴────────┘
```

### 설정 확인

```bash
uv run python -m quant_krx validate-config
```

## Mac mini 자동 실행 설정

```bash
bash ops/setup.sh
```

- 매일 **15:35 KST** (장 마감 후) 자동 실행
- 로그: `logs/launchd.stdout.log`

### 수동 제어

```bash
# 수동 실행
launchctl start com.quant-krx.daily

# 스케줄 확인
launchctl list com.quant-krx.daily

# 등록 해제
launchctl unload ~/Library/LaunchAgents/com.quant-krx.daily.plist
```

## 리포트 구조

### Report A (순수 퀀트)
- LLM 없음, 항상 동일한 결과
- 백테스트 메트릭: 총수익률, MDD, Sharpe, 초과수익률, 최근 6/12개월 수익률
- 리스크 플래그 표시

### Report B (LLM 보조)
- 동일한 신호 ID 참조 (Report A와 같은 데이터 기반)
- 팩트 / 추론 / 권고 3개 섹션 구조
- LLM 실패 시 자동 폴백

## 테스트

```bash
# 전체 테스트
uv run pytest

# 특정 모듈
uv run pytest tests/unit/test_config.py -v
uv run pytest tests/integration/test_daily_job.py -v
```

## 로드맵

### v1 (현재): Watchlist 일일 퀀트 어시스턴트
- [x] 관심 종목 watchlist 설정
- [x] VectorBT 기반 퀀트 전략 (MA 교차, RSI)
- [x] Report A/B 분리
- [x] Telegram 알림

### v2: 테마 + 리밸런싱 리포트
- [ ] 테마 설정 및 구성원 매핑
- [ ] 포트폴리오 리밸런싱 권고 리포트

### v3: 시장 전체 스크리닝
- [ ] KOSPI/KOSDAQ 전체 스크리닝
- [ ] 데이터 품질 점수화

### v4: 브로커 API 연동 (선택)
- [ ] 한국투자증권 Open API
- [ ] 페이퍼 트레이딩

## 데이터 소스

- **FinanceDataReader**: KRX/KOSPI/KOSDAQ 종목 목록 및 OHLCV
- **PyKrx**: KRX/Naver 스크래핑 기반 OHLCV

## 주의사항

- PyKrx는 스크래핑 기반으로 데이터가 변경될 수 있음
- 백테스트 결과는 과거 데이터 기반이며 미래를 보장하지 않음
- LLM 해석은 참고용이며 퀀트 신호를 대체하지 않음

## 면책 조항

이 소프트웨어는 개인 연구 및 의사결정 지원 목적으로 제작되었습니다.
금융 투자 권유, 법적 조언, 또는 투자 성과를 보장하지 않습니다.
모든 투자 결정과 그 결과에 대한 책임은 사용자 본인에게 있습니다.

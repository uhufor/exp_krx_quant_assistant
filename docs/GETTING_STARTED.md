# 시작하기

설치부터 첫 실행까지의 전체 절차입니다.

| 관련 문서 | 내용 |
|---|---|
| [데일리 어시스트](DAILY_ASSIST.md) | 설치 후 매일 돌릴 파이프라인 |
| [전략 정의](STRATEGY.md) | 나만의 전략 만들기 |
| [GUI](GUI.md) | 웹 화면으로 사용하기 |

---

## 설치

### 요구사항

- macOS (Apple Silicon 권장)
- [Homebrew](https://brew.sh)
- API 키: Anthropic (Claude), Telegram Bot
- (선택, GUI 사용 시) Node.js 18+ / npm — `brew install node`

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

## 첫 실행 시 기본 전략

전략은 코드가 아니라 **선언형 데이터**입니다. 최초 `run-daily` 실행 시 Built-in Template
5종(`ma_crossover`, `rsi_breakout`, `bollinger_band`, `macd`, `momentum`)이 자동 생성·활성화되어
바로 사용할 수 있습니다.

전략 목록·활성화 제어·나만의 전략 작성은 [전략 정의](STRATEGY.md)를 참고하세요.

---

## 환경변수 정리

| 변수 | 필수 여부 | 용도 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Report B 사용 시 | LLM 보조 리포트 생성 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 실제 발송 시 | 알림 전송 |
| `KRX_ID` / `KRX_PW` | 밸류에이션 팩터 사용 시 | KRX 로그인(PER·PBR·시가총액 등) |
| `DART_API_KEY` | 재무제표 팩터 사용 시 | DART Open API |
| `LLM_MOCK=true` | 선택 | LLM 호출 없이 테스트 |

> `--data-source fixture`로 실행하면 위 자격증명 없이도 전 기능을 오프라인으로 시험해 볼
> 수 있습니다. 합성 데이터(5종목 × 252거래일)를 사용합니다.

---

## 테스트


```bash
# 전체 테스트(CLI + GUI API 포함)
uv run pytest

# 특정 모듈
uv run pytest tests/unit/test_config.py -v
uv run pytest tests/integration/test_daily_job.py -v
uv run pytest tests/integration/test_api_backtests.py -v   # GUI 백테스트 API

# GUI 프론트엔드(트리 편집기 등 순수 로직)
cd web && npm test
```


---

## 문제 해결

**`npm install`이 `EACCES`로 실패**: npm 캐시 폴더 권한 문제입니다.
`sudo chown -R $(id -u):$(id -g) ~/.npm` 후 재시도하세요.

**밸류에이션 조회가 `RuntimeError`로 실패**: `KRX_ID`/`KRX_PW`가 없거나 세션이 만료된
경우입니다. `.env`를 확인하세요. PyKrx는 `data.krx.co.kr` 엔드포인트에 로그인을 요구합니다
(OHLCV는 비로그인으로도 동작).

**Python 버전 오류**: `vectorbt`가 `python_requires="<3.11"`이라 **Python 3.10**이 필요합니다.
`.python-version` 파일을 참고하세요.

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
- **No-Code Strategy Workspace**: 코드 없이 팩터·Formula·Rule을 조합해 나만의 전략을 설계·백테스트·운영 ([상세 문서](docs/NO_CODE_STRATEGY_WORKSPACE.md))

## 아키텍처

```
데이터 수집 (FDR/PyKrx) → 검증 → DuckDB 저장
    ↓
VectorBT 전략 실행 (활성 선언형 전략)
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

## 기본 전략

전략은 코드가 아니라 **선언형 데이터**(Formula/Rule/Strategy 정의 + `strategy-activate` 활성화)로
구성됩니다. Daily는 활성 전략 집합만 실행하며(전략 원천 단일화), 최초 실행 시 아래 Built-in
Template 5종이 자동으로 생성·활성화되어 끊김 없이 운영됩니다.

| 이름 | 유형 | 핵심 아이디어 |
|------|------|--------------|
| `ma_crossover` | 추세 추종 | 단기(20일)/장기(60일) MA 골든·데드크로스 |
| `rsi_breakout` | 역추세 | RSI 30 이하 매수 / 70 이상 매도 |
| `bollinger_band` | 평균 회귀 | 가격이 밴드(MA ± 2σ) 이탈 시 신호 |
| `macd` | 모멘텀 | 12/26 EMA 차이의 9일 시그널선 교차 |
| `momentum` | 중장기 추세 | 12-1개월 가격 모멘텀 (Jegadeesh & Titman) |

전략 활성화·비활성화는 `strategy-activate`/`strategy-deactivate` CLI로 제어합니다. 나만의
전략 작성, 팩터 32종 카탈로그, 백테스트·Template·Import/Export 등 전체 워크플로우는
[No-Code Strategy Workspace 문서](docs/NO_CODE_STRATEGY_WORKSPACE.md)를 참고하세요.

## 사용법

### Dry-run (알림 없이 테스트)

```bash
LLM_MOCK=true uv run python -m quant_krx run-daily --dry-run
```

최초 실행 시 Built-in Template 5종이 자동으로 생성·활성화됩니다(전략 선택은
`strategy-activate`/`strategy-deactivate`로 제어 — 위 [기본 전략](#기본-전략) 참고).

### 실제 실행 (Telegram 발송)

```bash
uv run python -m quant_krx run-daily --no-dry-run
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

### 노코드 스크리닝 (`screen-*`)

팩터·순위(거래대금/거래량 Top-N)·시간창(최근 N봉 내 골든크로스 등) 조건을 조합한 JSON
정의로 KRX 전 종목(watchlist 무관)을 스크리닝합니다. Daily 파이프라인과 독립적이며 실행
결과는 저장되지 않습니다(조회 전용).

```bash
# 조건 생성/전체교체 (JSON 파일 또는 '-'로 stdin)
uv run python -m quant_krx screen-create my_screen.json

# 조건 조회 (rich 표/패널)
uv run python -m quant_krx screen-show my_screen

# 저장된 조건 목록
uv run python -m quant_krx screen-list

# 참조 무결성 검증(팩터 id·RankPredicate 컬럼 등, 실행 없이)
uv run python -m quant_krx screen-validate my_screen

# 조건 실행 → 통과 종목(코드+이름) 표 출력
uv run python -m quant_krx screen-run my_screen --as-of 2024-12-18 --data-source fixture

# 조건 전체 교체(부분 패치 없음) / 삭제
uv run python -m quant_krx screen-edit my_screen my_screen_v2.json
uv run python -m quant_krx screen-delete my_screen
```

`--data-source`는 `fixture`(기본값) | `fdr` | `pykrx` 중 선택합니다. 조건 JSON 스키마와
연산자/노드 종류는 [roadmap/EPIC_R03/](roadmap/EPIC_R03/)(PRD/TRD/DESIGN R03) 참고.

### GUI (웹 인터페이스)

CLI의 팩터 조회·공식/규칙/전략 CRUD·백테스트 실행을 로컬 1인용 웹 GUI로도 사용할 수 있습니다
(localhost 전용, 인증 없음). 상세 설계는
[roadmap/EPIC_R02/PRD-R01-QUANT_ASSISTANT_GUI.md](roadmap/EPIC_R02/PRD-R01-QUANT_ASSISTANT_GUI.md),
전체 사용 흐름 예제는
[docs/NO_CODE_STRATEGY_WORKSPACE.md](docs/NO_CODE_STRATEGY_WORKSPACE.md#gui-사용-예제) 참고.

화면은 상단 탭으로 구성됩니다: **팩터**(32종 카탈로그 읽기 전용 조회) · **공식**(Formula, 트리
편집기로 팩터를 조합한 파생 지표 생성) · **규칙**(Rule, 비교/AND·OR·NOT 조건 트리 편집기) ·
**전략**(Strategy, 공식/규칙 참조 + 활성화·템플릿·Export/Import) · **백테스트**(전략 실행 + 지표
요약·equity curve 차트·거래내역).

**최초 설정(1회, 이후 프론트엔드 코드를 바꿨을 때만 다시)**

```bash
cd web
npm install   # package.json이 바뀌지 않는 한 보통 1회만 필요
npm run build # web/dist/ 생성 — 프론트엔드 코드를 수정했다면 매번 다시 실행
cd ..
```

> macOS에서 `npm install`이 `EACCES`(캐시 폴더 권한 오류)로 실패하면
> `sudo chown -R $(id -u):$(id -g) ~/.npm`으로 npm 전역 캐시 소유권을 고친 뒤 다시 시도하세요.

**평소 사용(서버 하나만 실행)**

```bash
# GUI 전체(API+화면)가 http://127.0.0.1:8765/ 에서 동작
uv run python -m quant_krx serve-gui

# 포트 지정(개발 모드 프록시 없이 이 방식으로 쓸 때만 유효 — 아래 참고)
uv run python -m quant_krx serve-gui --port 9000
```

**프론트엔드 코드를 직접 수정하며 개발할 때**(저장 즉시 반영되는 HMR)

```bash
# 터미널 1: 백엔드는 반드시 기본 포트(8765)로 실행
uv run python -m quant_krx serve-gui
# 터미널 2: vite dev server(5173) — /api를 127.0.0.1:8765로 자동 프록시(web/vite.config.ts)
cd web && npm run dev
# 브라우저는 http://localhost:5173/ 로 접속(8765가 아님)
```

> 개발 모드 프록시 대상은 `web/vite.config.ts`에 `127.0.0.1:8765`로 고정돼 있습니다.
> 백엔드를 `--port`로 다른 포트에 띄우면 `npm run dev` 프록시가 깨지므로, 개발 모드에서는
> 항상 기본 포트(8765)를 사용하세요.

프론트엔드 테스트: `cd web && npm test`(Vitest, 트리 편집기 순수 로직 검증).

`run-daily`·`show-reports`·`fetch-fundamental`·`validate-config`와 원본 32종 팩터 카탈로그
자체의 CRUD(생성/수정/삭제)는 GUI 범위에서 제외됩니다(CLI로만 사용).

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
# 전체 테스트(CLI + GUI API 포함)
uv run pytest

# 특정 모듈
uv run pytest tests/unit/test_config.py -v
uv run pytest tests/integration/test_daily_job.py -v
uv run pytest tests/integration/test_api_backtests.py -v   # GUI 백테스트 API

# GUI 프론트엔드(트리 편집기 등 순수 로직)
cd web && npm test
```

## 로드맵

### v1 (완료): Watchlist 일일 퀀트 어시스턴트
- [x] 관심 종목 watchlist 설정
- [x] VectorBT 기반 퀀트 전략 실행
- [x] Report A/B 분리
- [x] Telegram 알림

### v1.5 (완료): No-Code Strategy Workspace
코드 없이 팩터·Formula·Rule을 조합해 전략을 설계·백테스트·운영하는 서브시스템. 상세는
[docs/NO_CODE_STRATEGY_WORKSPACE.md](docs/NO_CODE_STRATEGY_WORKSPACE.md), 설계 문서는
[refined_epics/](refined_epics/README.md)(PRD/TRD/DESIGN R01~R03) 참고.
- [x] 팩터 플랫폼 32종 (가격·기술 7 + 밸류에이션 11 + 재무제표 14)
- [x] Formula/Rule/Strategy 선언형 정의 + CRUD, Template(Built-in 5종 + 사용자)
- [x] 선언형 전략 백테스트(벤치마크 상대 성과 포함)·활성화·Daily 편입
- [x] Import/Export(전이 참조 포함 JSON 번들)

### v1.6 (완료): Quant Assistant GUI
No-Code Strategy Workspace를 로컬 1인용 웹 GUI로 제공. 상세 설계는
[roadmap/EPIC_R02/](roadmap/EPIC_R02/)(PRD/TRD/DESIGN R01) 참고.
- [x] 팩터 조회(읽기 전용) API + 화면
- [x] Formula/Rule 시각적 트리 편집기(중첩 표현식/조건 구성) + 저장 전 실시간 검증
- [x] Strategy CRUD + 활성화/비활성화 + 템플릿 생성 + Export/Import
- [x] 백테스트 실행 + 지표 요약·equity curve 차트·거래내역 표시
- [x] 기존 CLI 27개 명령 회귀 없음

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

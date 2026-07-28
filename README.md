# KRX 한국 주식 퀀트 어시스턴트

코드 없이 퀀트 전략을 **설계 → 검증 → 운용**하는 개인용 도구입니다. 팩터를 조합해 전략을
만들고, 백테스트로 검증하고, 전 종목에서 후보를 찾고, 매일 분석 리포트를 Telegram으로 받습니다.

> **중요**: 이 도구는 개인 투자 참고용입니다. 투자 권유가 아니며 최종 투자 결정은 본인이 내립니다.

## 무엇을 할 수 있나

| | 설명 |
|---|---|
| **전략 설계** | 팩터 35종을 산술 조합(Formula)하고 조건(Rule)으로 엮어 전략을 만듭니다. 코드 없이 JSON 또는 GUI 트리 편집기로 |
| **백테스트** | 과거 데이터로 검증하고, 실행 이력을 남겨 전략끼리 비교합니다 |
| **과최적화 탐지** | 구간을 학습/검증으로 나눠 돌려 "그 성과가 재현될 숫자인지"를 가립니다 |
| **포트폴리오 운용** | 자본을 공유하는 다종목 백테스트. "최대 5종목 균등 보유, 매월 리밸런싱" 같은 정책을 선언합니다 |
| **전종목 스크리닝** | KOSPI/KOSDAQ 전체에서 조건에 맞는 종목을 찾고, 그 결과를 전략의 대상 종목으로 연결합니다 |
| **데일리 어시스트** | 매일 장 마감 후 분석 → 리포트 2종(결정론 + LLM 보조) → Telegram 발송 |

## 빠른 시작

```bash
brew install uv && uv sync          # Python 3.10 필요(vectorbt 제약)
cp .env.example .env                # API 키 설정
cp config/watchlist.yaml.example config/watchlist.yaml

# 네트워크·자격증명 없이 오프라인으로 전체 파이프라인 시험
LLM_MOCK=true uv run python -m quant_krx run-daily --dry-run --data-source fixture
uv run python -m quant_krx show-reports --type all
```

자세한 설치·환경변수·문제 해결은 **[시작하기](docs/GETTING_STARTED.md)** 를 참고하세요.

## 문서

| 문서 | 내용 |
|---|---|
| **[시작하기](docs/GETTING_STARTED.md)** | 설치, 환경변수, 테스트 실행, 문제 해결 |
| **[전략 정의](docs/STRATEGY.md)** | 팩터 · Formula · Rule · Strategy, CLI 레퍼런스, End-to-End 예제 |
| **[백테스트](docs/BACKTEST.md)** | 실행 방법, 실행 이력과 캐시, 결과 비교 |
| **[OOS 검증](docs/VALIDATION.md)** | 워크포워드 분할, 파라미터 스윕, 과최적화 탐지 |
| **[포트폴리오](docs/PORTFOLIO.md)** | 자본 공유 다종목 운용, 리밸런싱, 동적 유니버스 |
| **[스크리닝](docs/SCREENING.md)** | 전종목 조건 검색, 제외 필터, 생존 편향 방지 |
| **[데일리 어시스트](docs/DAILY_ASSIST.md)** | 일일 파이프라인, 리포트 구조, 리밸런싱 권고, 데이터 신선도, 자동 실행 |
| **[GUI](docs/GUI.md)** | 웹 인터페이스 실행과 사용 예제 |

**참고 자료**

- [적용 가능한 전략 가이드](docs/reference/APPLICABLE_STRATEGIES_CLI_GUIDE.md) — 이 플랫폼으로 구현 가능한 전략 목록
- [유명 퀀트 전략 정리](docs/reference/FAMOUS_QUANT_STRATEGIES.md) — 참고용 전략 배경 지식

**개발 문서**

- [roadmap/BACKLOG.md](roadmap/BACKLOG.md) — 진행 상황과 남은 작업(새 작업 시작 전 여기부터)
- [roadmap/EPIC_R01~R05/](roadmap/) — 기능별 PRD·TRD·DESIGN
- [CLAUDE.md](CLAUDE.md) — 아키텍처 요약과 중요 제약사항

## 프로젝트 구조

```
src/quant_krx/
  factors/       팩터 35종 순수 계산 (가격·기술·밸류에이션·재무제표)
  formula/       팩터 산술 조합 정의
  rule/          조건 트리 정의 (비교 · AND/OR/NOT · 크로스)
  strategy/      전략 정의 (팩터 참조 · 대상 종목 · 규칙 바인딩 · 포트폴리오 정책)
  workspace/     평가 · 백테스트 · 템플릿 파사드
  screening/     전종목 조건 스크리닝 (독립 패키지)
  signals/       백테스트 결과 → 매매 신호 분류
  reports/       Report A(결정론) / Report B(LLM 보조) 렌더링
  notify/        Telegram 발송 (중복 방지 outbox)
  jobs/          데일리 파이프라인
  data/          데이터 수집 어댑터 (PyKrx · DART · Fixture)
  storage/       DuckDB 스키마와 저장 게이트
  api/           FastAPI 라우터 (GUI 백엔드)

web/             React + Vite GUI
config/          watchlist 등 사용자 설정
docs/            사용 문서
roadmap/         기획·설계 문서와 백로그
tests/           단위 · 통합 테스트
ops/             launchd 자동 실행 스크립트
```

## 데이터 소스

| 소스 | 제공 데이터 |
|---|---|
| **PyKrx** | OHLCV, 밸류에이션(PER·PBR·시가총액 등), 종목 목록 |
| **DART** | 재무제표 14계정 (Open API) |
| **Fixture** | 합성 데이터(1년치) — 네트워크 없이 오프라인 검증용 |
| **Fixture 10Y** | 실제 KRX 수정주가 10년치(5종목, 2015~2024) — 저장소에 포함, 오프라인 |

## 주의사항

- PyKrx는 스크래핑 기반으로 데이터 구조가 변경될 수 있습니다.
- 백테스트 결과는 과거 데이터 기반이며 미래 성과를 보장하지 않습니다.
- LLM 해석(Report B)은 참고용이며 퀀트 신호를 대체하지 않습니다.
- 포트폴리오 리밸런싱 권고의 "현재 보유"는 직전 리밸런싱 목표 비중을 가정한 값입니다.
  실제 계좌와 연동되지 않으므로 주문 전 잔고를 확인하십시오.

## 면책 조항

이 소프트웨어는 개인 연구 및 의사결정 지원 목적으로 제작되었습니다.
금융 투자 권유, 법적 조언, 또는 투자 성과를 보장하지 않습니다.
모든 투자 결정과 그 결과에 대한 책임은 사용자 본인에게 있습니다.

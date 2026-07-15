# Refined Epics — No-Code Strategy Workspace PRD

**작성일**: 2026-07-08
**Status**: Approved for implementation
**지위**: 본 디렉터리의 PRD-R01~R03이 요구사항의 유일한 진실 원천이며, 외부 문서 없이 자체 완결적으로 TRD → DESIGN → 구현 진행이 가능해야 한다.

---

## 1. 제품 정의 (한 문장)

**No-Code Strategy Workspace** = 사용자가 코드 없이, 플랫폼이 제공하는 지표(Factor)와 산술 조합(Formula), 조건(Rule)을 선언적으로 조합하여 자신의 투자 전략을 **설계 → 검증 → 백테스트 → Daily 운영 → 재사용(Template/Import·Export)** 까지 CLI로 완결하는 KRX 퀀트 트레이딩 플랫폼.

## 2. 기반 전제 (Baseline)

본 PRD는 현 플랫폼(main 브랜치) 위에 구현한다. 전제하는 기존 자산:

- **Daily 분석 파이프라인**: watchlist → OHLCV 수집(FDR/PyKrx)·검증 → vectorbt 백테스트 → 신호 분류 → Report A(결정론)/Report B(LLM) → Telegram 알림. DuckDB 8테이블(symbols, ohlcv_daily, data_fetch_runs, strategy_runs, signals, reports, notification_outbox, run_events), content-hash 기반 중복 발송 방지.
- **하드코딩 전략 5종**: MA크로스오버·RSI돌파·볼린저밴드·MACD·모멘텀이 Python 코드로 구현되어 `settings.strategy.enabled`로 선택 실행된다. 투자 지표는 각 전략 내부에서 인라인 계산되며 플랫폼 차원에서 관리되지 않는다.
- **CLI(Typer) + 설정(Pydantic Settings)**, 합성 Fixture 기반 오프라인 테스트 관례.

이 상태의 공백 — 지표가 1급 자원이 아니고, 전략이 코드에 매몰되어 사용자가 생성·수정할 수 없다 — 을 본 PRD 3부작이 메운다. 기존 파이프라인의 다운스트림(신호→리포트→알림)은 재사용하며 재구축하지 않는다.

## 3. 계층 구조 (3개 PRD, 의존 단방향)

| PRD | 책임 | 코드 경계 | 순수성 |
|---|---|---|---|
| **PRD-R01 Factor Platform** | 지표 계산 계약 + 펀더멘털 데이터 계층 | `factors/`, `data/` | 순수 (실행·저장 무의존) |
| **PRD-R02 Declarative Definition Core** | Strategy/Rule/Formula 정의·영속·검증 | `strategy/`, `rule/`, `formula/` | 순수 (평가·실행 없음) |
| **PRD-R03 Workspace & Execution** | 파사드·CLI·평가 엔진·백테스트·Daily·재사용 | `workspace/`, `jobs/` | impure (전 계층 소비) |

의존 방향: **R03 → R02 → R01**, 역방향 금지(AST import 스캔으로 기계 강제). 이 경계가 곧 TRD/DESIGN의 모듈 경계이며, 각 PRD는 순서대로 독립 구현·검증 가능하다.

## 4. 핵심 제품 결정 (D1~D5)

다음 5개 결정은 설계 전반을 지배하는 확정 사항이다. **재협의 대상이 아니며(relitigate 금지), TRD/DESIGN은 이를 전제로 작성한다.**

### D1. 팩터 파라미터 오버라이드는 1급 기능이다
동일 팩터를 상이한 파라미터로 참조하는 것(예: SMA(5) × SMA(20) 골든크로스)은 전략 표현력의 최소 요건이다. 따라서 지표 참조의 `params`는 정의 검증(ParamSpec 대조)과 평가(오버라이드 적용 인스턴스 생성) 양쪽에서 **완전 해석**된다. "예약만 하고 해석하지 않는" 파라미터 슬롯은 두지 않는다. → PRD-R01 §3.1, PRD-R02 §5.4, PRD-R03 §5.3

### D2. 가격은 참조 가능한 팩터다
"종가가 볼린저 하단을 하향 돌파" 같은 가격 대 지표 비교는 기초 전략의 필수 표현이다. OHLCV 패스스루 팩터 `price`(output: `close`)를 카탈로그에 포함하여 Rule/Formula가 가격 자체를 다른 지표와 동형으로 참조하게 한다. → PRD-R01 §4.1

### D3. 전략 모델은 선언형 단일이다
코드형 전략과 선언형 전략의 병행 실행 경로(이중 디스패치·이중 활성화 기전)를 만들지 않는다. **모든 전략은 선언형**이며, Baseline의 하드코딩 전략 5종은 D1+D2로 완전히 표현 가능하므로 **등가 Built-in Template 5종**으로 대체된다. 본 Epic 완료 후 Daily의 전략 원천은 활성 선언형 전략 단일이 되고, 코드형 전략 구현과 `settings.strategy.enabled` 선택 기전은 제거된다. 전환 시 Template 5종은 자동 시드·활성화되어(멱등·1회성) 운영 연속성이 보장된다. → PRD-R03 §7, §8

### D4. rule 슬롯은 roles 단일 형상이다
Strategy의 rule 슬롯은 `None`(초안) 또는 `{"roles": {"entry": [...], "exit": [...]}}`만 유효하다(whitelist fail-closed). 역할 키는 `entry`/`exit`로 한정하고 "실행 가능(runnable) = entry ≥ 1"을 **정의 검증으로** 판정한다 — "정의 검증은 통과하지만 실행 시점에 거부되는" 상태를 구조적으로 금지한다. 활성화·백테스트는 runnable을 전제 조건으로 요구한다. → PRD-R02 §5.3, PRD-R03 §4

### D5. 선언한 것은 해석되거나 존재하지 않는다
정의 스키마의 모든 필드는 실행 의미를 가진다. **universe(정적 종목 목록)는 실행 대상 필터로 실제 소비**되고(빈 목록 = 파이프라인 watchlist 전체), 실행 의미가 아직 없는 **리밸런싱 정책 필드는 정의에 두지 않는다**(Portfolio Epic에서 `schema_version` 증가와 함께 additive 도입). "정의는 되지만 해석되지 않는" 필드를 금지하여 선언-실행 괴리를 원천 차단한다. → PRD-R02 §5.3, PRD-R03 §7

## 5. 전 계층 공통 불변 원칙 (모든 PRD에 적용)

1. **선언성**: 정의는 순수 데이터(JSON)다. 코드·람다·수식 문자열을 저장·파싱·평가하지 않는다.
2. **결정론**: 동일 입력(데이터+정의) → 동일 출력. 직렬화·검증·평가·백테스트·Daily(신호·Report A까지 — LLM Report B는 mock 주입 시에만) 전부. 네트워크·시간 의존 금지(시각은 주입).
3. **왕복 무손실**: `from_dict(to_dict(x)) == x`. 저장→조회 복원 동일.
4. **참조 무결성은 저장 시점**: dangling factor/formula/rule 참조·순환은 upsert 게이트에서 차단. 실행 시점은 명확 실패(`EvaluationError`)로 격리.
5. **오프라인 검증 가능**: 모든 요구사항은 네트워크·LLM·실데이터 없이 합성 Fixture + 격리 DuckDB + pytest로 결정론 검증 가능해야 한다.
6. **additive 진화**: 신규 연산자=열거 추가, 신규 피연산자=kind 추가, 신규 필드=JSON 본문+`schema_version`, 신규 저장=테이블 추가. 기존 DDL 변경 금지.
7. **오류 메시지는 한국어 + 행동 가능한 힌트**(누락 id·사용 가능 목록 포함). CLI 실패는 non-zero 종료.

## 6. 명시적 전역 Out of Scope

GUI/웹 프론트엔드(CLI + Telegram만) · Portfolio/다자산 비중·리밸런싱 집행 · 실시간/장중 실행·주문 집행 · AI 기반 전략 생성/최적화 · 해외 주식 · Strategy Marketplace · Personalized Assistant. (모두 후속 Epic.)

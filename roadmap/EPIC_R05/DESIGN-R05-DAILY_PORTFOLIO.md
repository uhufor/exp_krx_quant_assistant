# DESIGN-R05 — 데일리 포트폴리오 리밸런싱 권고

**작성일**: 2026-07-28
**Status**: 설계 확정, 구현 착수
**배경**: P1(포트폴리오 백테스트)·P2(동적 유니버스) 완료 후, `jobs/daily.py`가 두 기능을
소비하지 않아 생긴 **조용한 괴리**를 메운다. BACKLOG 2순위 D2(리밸런싱 권고 리포트)를 겸한다.

---

## 0. 해결하는 문제

현재 `jobs/daily.py:180`은 전략마다 `list(defn.universe.symbols) or watchlist`로 대상을 정하고
`run_single_symbol_backtest`를 직접 호출한다. 그 결과:

1. **동적 유니버스 전략을 활성화하면 watchlist로 조용히 대체된다** — `kind="screening"`은
   `symbols`가 빈 튜플이므로 `or watchlist`가 걸린다. 사용자는 "스크리닝 상위 종목"을
   기대하는데 전혀 다른 종목이 실행되고 에러도 경고도 없다.
2. **portfolio 정책이 무시된다** — 자본 공유·보유 수 제한·리밸런싱이 전부 사라지고 종목별
   독립 신호만 나온다.

둘 다 실행은 성공하므로 **틀렸다는 사실 자체가 드러나지 않는다.** D5("선언한 것은 해석되거나
존재하지 않는다") 위반이며, 현 백로그에서 유일하게 조용한 오답을 내는 지점이다.

## 1. 확정 결정 (사용자)

| # | 결정 | 근거 |
|---|---|---|
| D1 | **포트폴리오 1건 요약**으로 신호·리포트를 낸다 | 계좌 단위 개념과 일치. 5종목 리밸런싱에 Telegram 10건이 나가는 것을 피한다 |
| D2 | **매일 현황 보고** | 리밸런싱일이 아니어도 목표 비중과 보유 현황을 확인할 수 있다 |
| D3 | **직전 리밸런싱 목표 비중 = 현재 보유**로 간주 | 시스템은 실제 계좌를 모른다. 전략을 그대로 따랐다는 가정을 리포트에 명시한다 |

## 2. 실행 경로

```
daily.run()
 ├ 활성 전략 로드
 ├ [신규] 포트폴리오 전략의 대상 종목 사전 해석
 │    └ 동적 유니버스면 prepare_dynamic_universe(as_of 기준) → plan.symbols
 ├ collect_symbols = watchlist ∪ 정적 universe ∪ plan.symbols   ← 수집 대상 확장
 ├ OHLCV 수집 / 검증 / 펀더멘털
 └ 전략별 분기
      ├ portfolio 없음 → 기존 run_single_symbol_backtest 루프 (무변경)
      └ portfolio 있음 → run_backtest(포트폴리오 모드, resolve_universe=plan.eligible_at)
                        → weights에서 목표·직전 배분 추출 → 포트폴리오 신호 1건
```

**순서가 중요하다.** 동적 유니버스의 대상 종목은 스크리닝으로 정해지므로 **OHLCV 수집보다
먼저** 계획을 세워야 한다(P2에서 CLI/API가 쓰는 것과 동일한 `prepare_dynamic_universe`).

**의존 방향**: `jobs/`는 최상위 실행 계층이므로 `screening`을 직접 소비해도 무방하다
(CLI `__main__.py`, API 라우터와 같은 자격). `workspace`는 여전히 `screening`을 모른다.

## 3. 리밸런싱 지시 계산

`BacktestReport.weights`(P1 산출물, `{날짜: {종목: 비중}}`)만으로 전부 도출된다 — 신규 계산 없음.

```
L = max(weights)              # as_of 이하 마지막 리밸런싱일
P = 그 직전 리밸런싱일         # 없으면 {} (최초 진입)
target  = weights[L]          # 목표 비중
current = weights[P]          # 현재 보유(D3 가정)

신규 편입 = target.keys() - current.keys()
제외      = current.keys() - target.keys()
유지      = target.keys() & current.keys()   # 비중 변화량 함께 표기
오늘 리밸런싱 여부 = (L == as_of)
```

`weights`는 이미 0 비중을 생략하므로 키 집합이 곧 보유 종목이다.

## 4. 신호 모델

기존 `Signal`을 재사용한다(스키마 변경 없음, 다운스트림 무변경).

| 필드 | 값 |
|---|---|
| `symbol` | `__portfolio__` (`workspace.backtest.PORTFOLIO_KEY` 재사용) |
| `signal_type` | 오늘이 리밸런싱일이고 변경이 있으면 **`REBALANCE`**(신규), 아니면 `HOLD` |
| `score` / `evidence_metrics` | 포트폴리오 전체 지표 — 기존 `SignalClassifier` 로직 그대로 |
| `position_recommendation` | "신규 편입 2 · 제외 1 · 유지 3" 형태 요약 |

`SignalType.REBALANCE`는 열거 추가이며 `signals.signal_type`이 VARCHAR이므로 **DDL 변경이
없다**(additive 진화 원칙). 배분 상세는 리포트 본문에 담기고 `reports.content`로 영속된다 —
`signals` 테이블에는 배분을 저장할 컬럼이 없고, 만들 필요도 없다.

## 5. 리포트

- **Report A**(결정론, LLM 없음): 목표 비중 표 · 매수/매도/유지 지시 · 포트폴리오 지표 ·
  **"현재 보유는 직전 리밸런싱 목표 비중으로 가정했다"는 문구**(D3의 가정을 숨기지 않는다).
- **Report B**(LLM): 동일 신호를 참조해 해석을 덧붙인다. Report A/B가 같은 `signal.id`를
  참조해야 한다는 기존 불변식 유지.
- 리밸런싱일이 아니면 "오늘은 리밸런싱일이 아닙니다(다음 예정일 표시), 현 배분 유지"로 렌더.

`notification_outbox`의 `(channel, content_hash)` 중복 방지가 그대로 적용되므로, 매일 보고해도
**내용이 같으면 재발송되지 않는다**(D2의 "매일" 선택이 실제 알림 폭증으로 이어지지 않는 이유).

## 6. 비목표 (이번 범위 밖)

- 실제 보유 수량 입력·관리(사용자가 3번째 질문에서 선택하지 않음).
- 주문 집행·브로커 연동(v4).
- 포트폴리오 전략의 종목별 기여도 분해(P1 잔여 한계).

---

## 7. 개발 계획

| 단계 | 내용 | 산출물 |
|---|---|---|
| 1 | 리밸런싱 지시 계산 순수 함수 | `jobs/rebalance.py`(신규) — `RebalancePlan`, `diff_weights()` |
| 2 | `SignalType.REBALANCE` + 포트폴리오 신호 생성 | `signals/classifier.py::classify_portfolio()` |
| 3 | 리포트 렌더링(A/B) | `reports/report_a.py`, `report_b.py` 분기 |
| 4 | daily 배선(수집 순서 포함) | `jobs/daily.py` |
| 5 | 문서 동기화 | README·CLAUDE.md·BACKLOG |

## 8. 테스트 계획

**단위 — 지시 계산(`jobs/rebalance.py`)**
- 신규 편입/제외/유지 분류가 정확한가
- 최초 진입(직전 배분 없음) → 전부 신규 편입
- 전량 청산(목표가 빈 배분) → 전부 제외
- 비중만 바뀐 종목은 "유지 + 변화량"으로 분류
- 오늘이 리밸런싱일인지 판정
- 빈 weights(리밸런싱 이력 없음) 방어

**단위 — 신호 생성**
- 리밸런싱일 + 변경 있음 → `REBALANCE`
- 리밸런싱일 아님 → `HOLD`
- symbol이 `__portfolio__`이고 지표가 포트폴리오 전체 지표인가
- 요약 문구에 편입·제외·유지 건수가 담기는가

**단위 — 리포트**
- Report A에 목표 비중·지시·**보유 가정 문구**가 포함되는가
- 리밸런싱일이 아닐 때 "변경 없음" 렌더
- Report A는 LLM 없이 결정론적인가(동일 입력 → 동일 출력)
- Report B가 같은 `signal.id`를 참조하는가

**통합 — daily**
- 포트폴리오 전략 활성화 → 신호 1건 + 리포트 A/B 생성
- **동적 유니버스 전략이 watchlist로 대체되지 않는가**(이번 결함의 회귀 테스트)
- 동적 유니버스의 스크리닝 종목이 OHLCV 수집 대상에 포함되는가
- 포트폴리오 + 종목별 전략 동시 활성화 시 둘 다 정상 동작
- **기존 종목별 전용 경로 무변경**(회귀)
- dry-run에서 outbox 미기록
- 포트폴리오 백테스트 실패 시 다른 전략을 막지 않는가(FR-17 격리)

**결정론**: 동일 입력·동일 `as_of` → 동일 신호·Report A(공통 불변식 2).

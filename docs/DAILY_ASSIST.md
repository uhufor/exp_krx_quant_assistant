# 데일리 어시스트 (분석 · 보고)

매일 장 마감 후 관심 종목과 활성 전략을 분석해 리포트를 만들고 Telegram으로 보냅니다.

| 관련 문서 | 내용 |
|---|---|
| [전략 정의](STRATEGY.md) | 데일리가 실행할 전략 만들기 |
| [포트폴리오](PORTFOLIO.md) | 리밸런싱 권고의 원천이 되는 정책 |
| [시작하기](GETTING_STARTED.md) | Telegram·API 키 설정 |

**파이프라인**

```
watchlist + 활성 전략 universe
  → OHLCV 수집·검증 → 전략 실행 → 신호 분류
  → Report A(결정론) + Report B(LLM 보조) → Telegram(중복 발송 방지)
```

전략 실행 집합은 **활성 선언형 전략**이 유일한 원천입니다(`strategy-activate`로 제어).

---

## 실행

### Dry-run (알림 없이 테스트)

```bash
LLM_MOCK=true uv run python -m quant_krx run-daily --dry-run
```

최초 실행 시 Built-in Template 5종이 자동으로 생성·활성화됩니다(전략 선택은
`strategy-activate`/`strategy-deactivate`로 제어 — [전략 정의](STRATEGY.md#built-in-template) 참고).

### 실제 실행 (Telegram 발송)

```bash
uv run python -m quant_krx run-daily --no-dry-run
```

### 과거 시점 재현 (오프라인 검증)

```bash
# 네트워크·KRX 로그인 없이 특정 날짜의 리포트를 그대로 재현
uv run python -m quant_krx run-daily --dry-run --data-source fixture --as-of 2024-12-02
uv run python -m quant_krx show-reports --type A
```

`--as-of`(기본: 오늘)와 `--data-source`(`krx_dart` 기본 | `fixture`)는 리밸런싱일처럼 특정
시점의 결과를 눈으로 확인하기 위한 검증용 옵션입니다. 기본값은 운영 동작과 동일합니다.

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


---

## 포트폴리오 리밸런싱 권고

`portfolio` 정책이 있는 전략을 활성화하면(`strategy-activate`) 데일리 실행이 **계좌 단위**로
동작합니다. 종목별 신호 대신 **리밸런싱 권고 1건**이 생성되어 Report A/B로 발송됩니다.

- **리밸런싱일**: 매매 지시(🔴 전량 매도 / 🟢 신규 매수 / 🔵 비중 조정 / ⚪ 유지)를 표시합니다.
- **그 외 날**: 지나간 지시를 반복하지 않고 **현재 목표 배분**만 보여줍니다.
- **동적 유니버스 전략**도 그대로 동작합니다 — 데일리가 스크리닝을 먼저 평가해 대상 종목을
  정한 뒤 수집합니다(watchlist로 대체되지 않습니다).

> **현재 보유는 직전 리밸런싱 목표 비중으로 가정**합니다. 시스템은 실제 계좌 잔고를 모르므로,
> 전략을 그대로 따랐다는 전제이며 리포트에도 이 가정이 명시됩니다. 주문 전 실제 잔고를
> 확인하십시오.

포트폴리오 전략과 기존 종목별 전략을 함께 활성화할 수 있으며, 각각 별도 신호로 발송됩니다.


---

## 데이터 신선도 점검

결측은 NaN으로 조용히 degrade되므로, 낡거나 빈 값으로 결론이 나는 것을 막으려면 별도 점검이
필요합니다. 데일리는 실행 중 아래를 점검하고 **이상이 있을 때만** 리포트 상단에 한 줄을 붙입니다.

| 점검 | 판정 |
|---|---|
| 시세 | 대상 종목 중 수집에 실패한 종목 수 |
| 밸류에이션 | 기준일 데이터가 확보되지 않은 종목 수 |
| 재무제표 | 공시 유예(100일)를 지나도 최신 분기가 갱신되지 않은 종목 수 |
| 자격증명 | `KRX_ID`/`KRX_PW`, `DART_API_KEY` 부재 |

**전략이 실제로 쓰는 데이터만 점검합니다.** OHLCV만 쓰는 전략이 도는 날에는 재무제표가
비어 있어도 경고하지 않습니다 — 안 쓰는 데이터의 지연을 알리면 잡음이 되기 때문입니다.

신선도 문제는 **실행을 막지 않습니다.** 펀더멘털 수집이 실패해도 잡은 계속 진행하고 결측은
경고로 드러냅니다(세션 만료나 API 장애 하나로 매일 잡이 멈추면 안 되므로).

> 신호가 하나도 생성되지 않은 경우에는 경고를 실을 리포트가 없으므로, **데이터 경고만 담은
> 알림 1건**이 대신 발송됩니다. 데이터가 없어 전 전략이 실패했을 때 아무 연락도 못 받는
> 상황을 막기 위함입니다.

### 따로 확인하기

```bash
# 데일리를 돌리지 않고 현재 데이터 상태만 조회
uv run python -m quant_krx data-health
uv run python -m quant_krx data-health --symbols 005930,000660 --as-of 2024-12-18
uv run python -m quant_krx data-health --skip-financials   # 특정 점검 생략
```

수집·수정은 하지 않는 조회 전용 명령이며, 경고가 있어도 종료 코드는 0입니다.

---

## 리포트 구조

### Report A (순수 퀀트)
- LLM 없음, 항상 동일한 결과
- 백테스트 메트릭: 총수익률, MDD, Sharpe, 초과수익률, 최근 6/12개월 수익률
- 리스크 플래그 표시

### Report B (LLM 보조)
- 동일한 신호 ID 참조 (Report A와 같은 데이터 기반)
- 팩트 / 추론 / 권고 3개 섹션 구조
- LLM 실패 시 자동 폴백


---

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


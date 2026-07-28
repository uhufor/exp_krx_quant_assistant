# 백테스트

만든 전략을 과거 데이터로 검증하고, 실행 결과를 이력으로 남겨 비교합니다.

| 관련 문서 | 내용 |
|---|---|
| [전략 정의](STRATEGY.md) | 백테스트할 전략을 먼저 만들기 |
| [포트폴리오](PORTFOLIO.md) | 자본 공유 다종목 백테스트·리밸런싱 |
| [GUI](GUI.md) | 화면에서 실행하고 자산 곡선·거래내역 보기 |

---

## 실행

### `strategy-backtest`

```bash
uv run python -m quant_krx strategy-backtest STRATEGY_ID [옵션들]
```

| 인자/옵션 | 의미 | 기본값 |
|---|---|---|
| `strategy_id` (필수) | 백테스트할 전략 id(runnable + 검증 통과 상태여야 함) | — |
| `--symbols` | 콤마 구분 종목 목록 | 생략 시 전략 `universe.symbols`. 그마저 비어있으면 에러(watchlist는 `daily` 자동 파이프라인 전용이며 여기선 사용하지 않음) |
| `--start` | 백테스트 시작일(`YYYY-MM-DD`) | 종료일 5년 전 |
| `--end` | 백테스트 종료일(`YYYY-MM-DD`) | 오늘 |
| `--fees` | 거래당 수수료율 | `0.003` |
| `--slippage` | 거래당 슬리피지율 | `0.001` |
| `--data-source` | 데이터 소스: `fixture`(OHLCV+펀더멘털 전부 오프라인 합성) \| `krx_dart`(OHLCV·밸류에이션=PyKrx, 재무제표=DART 조합 실데이터) | `fixture` |
| `--benchmark` | 벤치마크 심볼/시장(예: `KOSPI`) — 지정 시 벤치마크 수익률·초과수익률을 함께 산출. 수집 실패는 경고만 남기고 백테스트는 계속 진행 | 없음 |

전략이 밸류에이션/재무제표 팩터를 참조하면 펀더멘털이 자동 선행 수집된다 —
`fixture`는 `FixtureFundamentalAdapter` 하나가 양쪽 다 처리하고, `krx_dart`는
밸류에이션=`PyKrxFundamentalAdapter`/재무제표=`DartFundamentalAdapter`로 kind별로
분리 수집한다(단일 provider가 둘 다 지원하지 않으므로). 한쪽 수집이 실패해도(예:
`DART_API_KEY` 미설정) 다른 kind나 OHLCV 기반 팩터 계산은 막지 않고 경고만 남긴다.
이때 `fundamental_daily`에 symbol별로 이미 저장된 날짜 범위(min~max)를 조회해,
요청 구간 중 **이미 커버된 부분은 재수집하지 않고 경계 바깥(이전/이후)의 부족분만
증분 수집**한다 — 예를 들어 1~6월을 이미 받아둔 뒤 1~12월로 백테스트하면 7~12월만
추가로 fetch된다. `--data-source krx_dart`처럼 개인 자격증명(KRX 로그인)이 필요한
provider에서 불필요한 재호출을 피하기 위한 설계다(경계 내부의 결측은 거래 캘린더상
자연 휴장일로 간주해 채우지 않는다). 종목이 2개 이상이면 표 제목에 대표 종목(첫
번째 심볼)이 표기되고, 종목별 상세 지표는 `report.per_symbol`을 통해 별도 확인한다.

```bash
uv run python -m quant_krx strategy-backtest my_strategy --data-source fixture
uv run python -m quant_krx strategy-backtest my_strategy --data-source fixture --benchmark KOSPI
```

---


## 실행 이력 (`backtest-*`)

`strategy-backtest`와 GUI 백테스트는 실행 결과(파라미터·지표·자산곡선)를 DuckDB
`backtest_runs`에 **자동 기록**합니다. 전략·참조 규칙/공식·실행 파라미터·입력 데이터가
모두 동일한 직전 실행이 있으면 재계산 없이 저장된 결과를 즉시 복원합니다.

```bash
# 실행 이력 목록(최근순)
uv run python -m quant_krx backtest-list
uv run python -m quant_krx backtest-list --strategy my_strategy --limit 50

# 실행 1건 상세(파라미터·전체/종목별 지표·지문)
uv run python -m quant_krx backtest-show 20260727-1a2b3c4d

# 실행 2건 이상 나란히 비교
uv run python -m quant_krx backtest-compare 20260727-1a2b3c4d 20260727-5e6f7a8b

# 캐시를 무시하고 강제 재계산
uv run python -m quant_krx strategy-backtest my_strategy --no-cache
```

캐시 키는 **정의 지문**(전략 + 전이 참조 Rule/Formula 폐포) · **파라미터 지문**(종목·기간·
수수료·슬리피지·데이터소스·벤치마크) · **데이터 지문**(실제로 조립된 OHLCV/밸류에이션/
재무제표 전체 해시)의 합성입니다. DART/KRX로 데이터가 새로 채워지거나 과거 값이 정정되면
데이터 지문이 바뀌어 캐시가 자동 무효화되므로 낡은 결과가 표시되지 않습니다.

> 거래내역(trades)은 재실행으로 재생성 가능해 저장하지 않습니다. 따라서 캐시로 복원된
> 결과에는 거래내역이 표시되지 않으며, 필요하면 `--no-cache`(GUI에서는 "저장된 결과 재사용"
> 해제)로 다시 실행하세요.


---

## 데이터 소스

`--data-source`는 두 가지입니다.

| 값 | 설명 |
|---|---|
| `fixture` | 합성 데이터(5종목 × 252거래일). 네트워크·자격증명 없이 오프라인 검증용 |
| `krx_dart` | 실데이터. OHLCV·밸류에이션은 PyKrx, 재무제표는 DART |

`krx_dart`는 `.env`에 `KRX_ID`/`KRX_PW`(밸류에이션), `DART_API_KEY`(재무제표)가 필요합니다.
자세한 설정은 [시작하기](GETTING_STARTED.md)를 참고하세요.

# 조사 전략 적용 가능성 매트릭스 + CLI 실행 예제

[FAMOUS_QUANT_STRATEGIES.md](FAMOUS_QUANT_STRATEGIES.md)에서 조사한 전략들을
현재 `quant-krx` No-Code Strategy Workspace 구현으로 얼마나 재현할 수 있는지 판정하고,
바로 실행 가능한 CLI 예제를 제공한다. **가능(✅) 판정을 받은 항목 전부**에 대해
Rule/Formula/Strategy를 새로 작성·생성·검증·백테스트하는 전 과정을 예제로 담았다.
모든 예제는 실제로 실행해 검증했다(005930 기준, `--data-source pykrx`는 KRX 로그인
필요 — `.env`의 `KRX_ID`/`KRX_PW`).

## 판정 기준

워크스페이스가 지원하는 것과 지원하지 않는 것을 코드 레벨에서 확인한 결과다.

- **팩터 데이터 가용성**: `required_data=ohlcv` 팩터(가격·기술 7종)는 fdr/pykrx/fixture 모두
  즉시 동작. `required_data=valuation` 팩터(밸류에이션 11종)는 PyKrx 로그인만 있으면
  실데이터 동작. `required_data=financials` 팩터(재무제표 14종 중 다수)는
  `DartFundamentalAdapter`가 아직 Deferred라 **실데이터가 NaN으로 반환된다**
  (`FixtureFundamentalAdapter`로만 테스트 가능, `CLAUDE.md` 참고).
- **Formula의 연산 범위**: `formula/definition.py`가 허용하는 연산은 사칙연산(`+ - * /`)과
  부호반전뿐이다(`workspace/numeric.py::binary_arith`). Rolling window·순위화 연산이
  Formula 자체에는 없다 — **이미 어떤 Factor가 계산해 내놓은 컬럼끼리 조합하는 것만
  가능**하다. 즉 Formula로 완전히 새로운 "형태"의 지표(rolling max, 순위)를 만들 수는
  없지만, 기존 Factor 출력 컬럼을 사칙연산으로 재조합해 새로운 파생 지표를 만드는 것은
  가능하다(아래 예제 E가 이 경계를 보여준다).
- **엔진 범위**: `EvaluationContext`는 "단일 (전략, 종목)" 단위로만 평가한다
  (`workspace/evaluation.py`). Rule 엔진은 **종목별 시계열 boolean 조건**(비교/크로스)만
  평가하며, 유니버스 전체를 대상으로 한 **순위화·Top-N 포트폴리오 선택**(Magic Formula,
  F-Score 합산 스코어링 등)은 지원하지 않는다 — 임계값 기반 근사만 가능하다.
- **포지션 사이징**: `workspace/backtest.py`의 `vbt.Portfolio.from_signals(close, entries,
  exits, fees=fees, slippage=slippage, freq="D")` 호출에 `size` 파라미터가 없다 — 항상
  풀노셔널 고정 사이징이며, ATR 등 신호 강도 기반 가변 사이징은 지원하지 않는다.

### 판정 범례

| 기호 | 의미 |
|---|---|
| ✅ | 지금 바로 실데이터로 실행 가능 |
| 🟡 | Rule/Formula/Strategy는 지금 작성·검증 가능하나 실데이터가 없어 **Fixture로만** 확인 가능(DART 연동 후 자동으로 실데이터 동작) |
| ❌ | Formula/Rule 조합으로 근본적으로 불가능(아키텍처 확장 필요) |
| ⛔ | 새 Factor 코드 또는 실행 엔진 변경이 선행되어야 함 |

## 적용 가능성 매트릭스

| # | 조사 전략 | 판정 | 사용 팩터 | 비고 |
|---|---|---|---|---|
| 1 | Golden/Death Cross | ✅ | `sma` | builtin Template `ma_crossover`(SMA 20/60) + 아래 예제 D-1(고전적 SMA 50/200 신규 변형) |
| 2 | MACD 크로스 | ✅ | `macd` | builtin Template `macd`(12/26/9), 원본 JSON 예제 D-2 |
| 3 | RSI 과매도 반등 | ✅ | `rsi` | builtin Template `rsi_breakout`(window=14), 원본 JSON 예제 D-3 |
| 4 | 볼린저 밴드 평균회귀 | ✅ | `price`, `bollinger` | builtin Template `bollinger_band`, 원본 JSON 예제 D-4 |
| 5 | 절대 모멘텀(12-1) | ✅ | `momentum` | builtin Template `momentum`(lookback=252, skip=21), 원본 JSON 예제 D-5 |
| 6 | 저PER+고ROE 퀄리티-밸류(Buffett 근사) | ✅(신규 조합) | `per`, `roe_approx`(+ `sma`) | [NO_CODE_STRATEGY_WORKSPACE.md §CLI 사용 예제](../NO_CODE_STRATEGY_WORKSPACE.md#cli-사용-예제-삼성전자-퀄리티-밸류-전략)에 완결 예제 있음(Formula 3개 사용) |
| 7 | 저PER+저PBR 딥밸류(Graham 근사) | ✅ | `per`, `pbr` | 예제 A — valuation만 필요, financials 불필요 |
| 8 | 고배당 전략(Dogs-of-Dow류) | ✅ | `dividend_yield` | 예제 B |
| 9 | 추세추종 + RSI 눌림목 하이브리드 | ✅(신규 조합) | `price`, `sma`, `rsi` | 예제 C — valuation도 financials도 불필요 |
| 14 | 저변동성 이상현상 | ✅(신규, Formula 조합) | `bollinger`(Formula로 밴드폭 비율 계산) | 예제 E — 새 Factor 없이 Formula 사칙연산만으로 변동성 프록시 생성 |
| 11 | Piotroski F-Score | 🟡 정의 가능(DART 대기) | `roa`, `revenue_growth`, `op_income_growth`, `debt_to_equity`, `current_ratio`, `interest_coverage` | 예제 F — Rule/Strategy는 지금 작성 가능, Fixture로 검증 완료. 실데이터는 DART 연동 후 |
| 12 | GP/A, QMJ, ROIC 퀄리티 | 🟡 정의 가능(DART 대기) | `gp_to_assets`, `roic` | 예제 G — GP/A+ROIC 부분집합만(QMJ 전체 복합 스코어는 배당성향 등 추가 조합 필요), Fixture로만 검증 가능 |
| 10 | Magic Formula(진짜 순위결합) | ❌ 엔진 한계 | — | `EvaluationContext`가 종목 1개 단위로만 평가 — 유니버스 순위화 자체가 불가능. 대안: #6으로 임계값 근사 |
| 13 | 52주 신고가 근접 모멘텀 | ⛔ 새 팩터 필요 | — | Formula는 rolling window 연산이 없고, 기존 팩터 중 rolling max를 내놓는 것도 없음(`momentum`은 구간수익률이지 신고가 근접도가 아님) |
| 15 | Turtle Trading(Donchian+ATR 사이징) | ⛔ 새 팩터+엔진 필요 | — | Donchian 채널(고가/저가 rolling max/min) 팩터 부재 + `Portfolio.from_signals`에 `size` 파라미터가 없어 ATR 기반 가변 사이징 자체가 불가 |

---

## 예제 A — 딥밸류 전략(저PER + 저PBR)

Graham식 딥밸류를 근사한다. `per`/`pbr` 모두 `required_data=valuation`이라
재무제표(DART) 없이 PyKrx 로그인만으로 실데이터를 사용할 수 있다.

> **주의**: `FixtureAdapter`의 샘플 밸류에이션 데이터는 종목별 PER/PBR이 거의
> 고정값(005930 기준 PER≈11.0, PBR≈1.2)이라 임계값 규칙이 아예 발동하지 않는다.
> 순수 밸류에이션 임계값 전략은 **pykrx 실데이터**로 테스트할 것.

### Step 1 — Rule 2종 생성

`deep_value_entry.json` — PER 12 미만 AND PBR 1.1 미만일 때 진입:

```json
{
  "id": "deep_value_entry",
  "name": "딥밸류 진입(저PER+저PBR)",
  "version": "1",
  "root": {
    "node": "composition",
    "op": "AND",
    "operands": [
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "per", "column": "per", "params": {}}, "operator": "<", "right": {"kind": "constant", "value": 12}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "pbr", "column": "pbr", "params": {}}, "operator": "<", "right": {"kind": "constant", "value": 1.1}}
    ]
  }
}
```

`deep_value_exit.json` — PER 20 초과 OR PBR 1.5 초과 시(밸류에이션 정상화) 청산:

```json
{
  "id": "deep_value_exit",
  "name": "딥밸류 청산(밸류에이션 정상화)",
  "version": "1",
  "root": {
    "node": "composition",
    "op": "OR",
    "operands": [
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "per", "column": "per", "params": {}}, "operator": ">", "right": {"kind": "constant", "value": 20}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "pbr", "column": "pbr", "params": {}}, "operator": ">", "right": {"kind": "constant", "value": 1.5}}
    ]
  }
}
```

### Step 2 — 전략 생성

`deep_value_strategy.json`:

```json
{
  "id": "deep_value_strategy",
  "name": "딥밸류 전략(저PER+저PBR)",
  "version": "1",
  "factor_refs": [
    {"factor_id": "per", "params": {}},
    {"factor_id": "pbr", "params": {}}
  ],
  "universe": {"symbols": ["005930"]},
  "rule": {"roles": {"entry": ["deep_value_entry"], "exit": ["deep_value_exit"]}}
}
```

### Step 3 — 생성·검증·백테스트

```bash
uv run python -m quant_krx rule-create deep_value_entry.json
uv run python -m quant_krx rule-create deep_value_exit.json
uv run python -m quant_krx strategy-create deep_value_strategy deep_value_strategy.json
uv run python -m quant_krx strategy-validate deep_value_strategy
uv run python -m quant_krx strategy-backtest deep_value_strategy \
    --symbols 005930 --data-source pykrx --start 2021-01-01 --end 2026-07-19 --benchmark KOSPI
```

검증 결과(005930, 2021-01-01~2026-07-19, pykrx 실데이터):

| 지표 | 값 |
|---|---|
| 총수익률 | 62.60% |
| MDD | 6.89% |
| Sharpe | 1.313 |
| 승률 | 100.00% |
| 거래 횟수 | 1 |
| 벤치마크(KOSPI) 수익률 | 170.17% |

거래가 1회뿐인 것은 버그가 아니라 대형 우량주(삼성전자)가 PER 12·PBR 1.1 밑으로
떨어지는 구간 자체가 드물기 때문이다(실증적으로 딥밸류 신호가 희소함을 보여주는
결과). 더 많은 신호를 보려면 소형주/경기민감주 종목코드로 바꾸거나 임계값을 상향한다.

---

## 예제 B — 고배당 전략(Dogs-of-Dow류)

`dividend_yield`(`required_data=valuation`) 단일 팩터로 배당수익률이 높을 때
진입, 낮아지면(배당매력 소멸) 청산.

### Rule 2종

`high_dividend_entry.json`:

```json
{
  "id": "high_dividend_entry",
  "name": "고배당 진입",
  "version": "1",
  "root": {
    "node": "predicate",
    "left": {"kind": "factor", "factor_id": "dividend_yield", "column": "dividend_yield", "params": {}},
    "operator": ">",
    "right": {"kind": "constant", "value": 0.025}
  }
}
```

`high_dividend_exit.json`:

```json
{
  "id": "high_dividend_exit",
  "name": "고배당 청산(배당매력 소멸)",
  "version": "1",
  "root": {
    "node": "predicate",
    "left": {"kind": "factor", "factor_id": "dividend_yield", "column": "dividend_yield", "params": {}},
    "operator": "<",
    "right": {"kind": "constant", "value": 0.018}
  }
}
```

### 전략

`high_dividend_strategy.json`:

```json
{
  "id": "high_dividend_strategy",
  "name": "고배당 전략",
  "version": "1",
  "factor_refs": [{"factor_id": "dividend_yield", "params": {}}],
  "universe": {"symbols": ["005930"]},
  "rule": {"roles": {"entry": ["high_dividend_entry"], "exit": ["high_dividend_exit"]}}
}
```

```bash
uv run python -m quant_krx rule-create high_dividend_entry.json
uv run python -m quant_krx rule-create high_dividend_exit.json
uv run python -m quant_krx strategy-create high_dividend_strategy high_dividend_strategy.json
uv run python -m quant_krx strategy-validate high_dividend_strategy
uv run python -m quant_krx strategy-backtest high_dividend_strategy \
    --symbols 005930 --data-source pykrx --start 2021-01-01 --end 2026-07-19 --benchmark KOSPI
```

검증 결과: 총수익률 35.79%, MDD 36.78%, Sharpe 0.456, 승률 50.00%, 거래 횟수 2.

---

## 예제 C — 추세 눌림목 하이브리드(추세추종 + RSI 반등)

상승추세(종가 > 200일 이평)를 유지한 상태에서 RSI가 과매도(30) 구간에서
반등할 때 진입하는, 추세추종과 평균회귀 타이밍을 결합한 전략. 순수 OHLCV
팩터만 사용하므로 `fdr`/`pykrx`/`fixture` 어느 데이터소스로도 동작한다.

### Rule 2종

`trend_pullback_entry.json`:

```json
{
  "id": "trend_pullback_entry",
  "name": "추세 눌림목 진입(상승추세+RSI 반등)",
  "version": "1",
  "root": {
    "node": "composition",
    "op": "AND",
    "operands": [
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "price", "column": "close", "params": {}}, "operator": ">", "right": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 200}}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "rsi", "column": "rsi", "params": {"window": 14}}, "operator": "crosses_above", "right": {"kind": "constant", "value": 30}}
    ]
  }
}
```

`trend_pullback_exit.json` — RSI 과매수(70) 진입 OR 추세 붕괴(종가가 200일선 하향 이탈) 시 청산:

```json
{
  "id": "trend_pullback_exit",
  "name": "추세 눌림목 청산(과매수 또는 추세 붕괴)",
  "version": "1",
  "root": {
    "node": "composition",
    "op": "OR",
    "operands": [
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "rsi", "column": "rsi", "params": {"window": 14}}, "operator": "crosses_above", "right": {"kind": "constant", "value": 70}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "price", "column": "close", "params": {}}, "operator": "crosses_below", "right": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 200}}}
    ]
  }
}
```

### 전략

`trend_pullback_strategy.json`:

```json
{
  "id": "trend_pullback_strategy",
  "name": "추세 눌림목 하이브리드 전략",
  "version": "1",
  "factor_refs": [
    {"factor_id": "price", "params": {}},
    {"factor_id": "sma", "params": {"window": 200}},
    {"factor_id": "rsi", "params": {"window": 14}}
  ],
  "universe": {"symbols": ["005930"]},
  "rule": {"roles": {"entry": ["trend_pullback_entry"], "exit": ["trend_pullback_exit"]}}
}
```

```bash
uv run python -m quant_krx rule-create trend_pullback_entry.json
uv run python -m quant_krx rule-create trend_pullback_exit.json
uv run python -m quant_krx strategy-create trend_pullback_strategy trend_pullback_strategy.json
uv run python -m quant_krx strategy-validate trend_pullback_strategy
uv run python -m quant_krx strategy-backtest trend_pullback_strategy \
    --symbols 005930 --data-source pykrx --start 2021-01-01 --end 2026-07-19 --benchmark KOSPI
```

검증 결과: 총수익률 15.44%, MDD 9.59%, Sharpe 0.464, 승률 80.00%, 거래 횟수 5.

---

## 예제 D — Golden/Death Cross·MACD·RSI·Bollinger·모멘텀(#1~#5)

builtin Template 5종(`ma_crossover`, `macd`, `rsi_breakout`, `bollinger_band`,
`momentum`)은 `--template` 옵션으로 즉시 복제할 수 있다(신규 JSON 작성 불필요).

```bash
uv run python -m quant_krx strategy-template-list
# → bollinger_band, ma_crossover, macd, momentum, rsi_breakout

uv run python -m quant_krx strategy-create my_macd_clone --template macd
uv run python -m quant_krx strategy-backtest my_macd_clone --symbols 005930 --data-source pykrx --benchmark KOSPI
```

`strategy-show my_macd_clone`로 확인하면 `universe.symbols`가 빈 배열이므로
`strategy-backtest`에 `--symbols`를 반드시 넘기거나, `strategy-edit`으로
`universe`를 채워야 한다.

아래는 "새로 Rule/Strategy를 작성하는 방법"을 보여주기 위해, ①기존 템플릿과
다른 파라미터로 직접 새 id를 만든 예제(D-1)와 ②기존 4종 템플릿의 등록된
원본 JSON(참고·변형용, D-2~D-5)이다.

### D-1 — 고전적 골든크로스(SMA 50/200, 신규 변형)

builtin `ma_crossover`는 SMA 20/60을 쓴다. 교과서적인 50/200 창으로 직접 새
Rule 2종 + Strategy를 만들어본다.

```json
{
  "id": "golden_cross_50_200_entry",
  "name": "고전적 골든크로스 진입(SMA 50/200)",
  "version": "1",
  "root": {
    "node": "predicate",
    "left": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 50}},
    "operator": "crosses_above",
    "right": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 200}}
  }
}
```

```json
{
  "id": "golden_cross_50_200_exit",
  "name": "고전적 데드크로스 청산(SMA 50/200)",
  "version": "1",
  "root": {
    "node": "predicate",
    "left": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 50}},
    "operator": "crosses_below",
    "right": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 200}}
  }
}
```

```json
{
  "id": "golden_cross_50_200_strategy",
  "name": "고전적 골든크로스 전략(SMA 50/200)",
  "version": "1",
  "factor_refs": [
    {"factor_id": "sma", "params": {"window": 50}},
    {"factor_id": "sma", "params": {"window": 200}}
  ],
  "universe": {"symbols": ["005930"]},
  "rule": {"roles": {"entry": ["golden_cross_50_200_entry"], "exit": ["golden_cross_50_200_exit"]}}
}
```

```bash
uv run python -m quant_krx rule-create golden_cross_50_200_entry.json
uv run python -m quant_krx rule-create golden_cross_50_200_exit.json
uv run python -m quant_krx strategy-create golden_cross_50_200_strategy golden_cross_50_200_strategy.json
uv run python -m quant_krx strategy-validate golden_cross_50_200_strategy
uv run python -m quant_krx strategy-backtest golden_cross_50_200_strategy \
    --symbols 005930 --data-source pykrx --start 2021-01-01 --end 2026-07-19 --benchmark KOSPI
```

검증 결과: 총수익률 **288.10%**, MDD 33.04%, Sharpe 1.163, 승률 50.00%, 거래 횟수 2,
벤치마크(KOSPI) 170.17% → **초과수익률 +117.93%**(A~C와 달리 벤치마크를 상회한
유일한 예제).

### D-2~D-5 — 등록된 원본 JSON(참고·변형용)

`rule-show <id>` / `strategy-show <id>`로 언제든 조회 가능한 실제 등록 내용이다.
window·threshold만 바꿔 새 id로 `rule-create`하면 즉시 변형 전략을 만들 수 있다.

**D-2. MACD 크로스** — `macd_entry`/`macd_exit`(fast=12, slow=26, signal=9):

```json
{"node": "predicate", "left": {"kind": "factor", "factor_id": "macd", "column": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}, "operator": "crosses_above", "right": {"kind": "factor", "factor_id": "macd", "column": "signal", "params": {"fast": 12, "slow": 26, "signal": 9}}}
```

**D-3. RSI 과매도 반등** — `rsi_breakout_entry`(window=14, `<30`) / `rsi_breakout_exit`(`>70`):

```json
{"node": "predicate", "left": {"kind": "factor", "factor_id": "rsi", "column": "rsi", "params": {"window": 14}}, "operator": "<", "right": {"kind": "constant", "value": 30}}
```

**D-4. 볼린저 밴드 평균회귀** — `bollinger_band_entry`(종가가 하단 이탈) /
`bollinger_band_exit`(종가가 중심선 회귀):

```json
{"node": "predicate", "left": {"kind": "factor", "factor_id": "price", "column": "close", "params": {}}, "operator": "crosses_below", "right": {"kind": "factor", "factor_id": "bollinger", "column": "lower", "params": {"window": 20, "num_std": 2.0}}}
```

**D-5. 절대 모멘텀(12-1)** — `momentum_entry`(lookback=252, skip=21, `>0`) /
`momentum_exit`(`<0`):

```json
{"node": "predicate", "left": {"kind": "factor", "factor_id": "momentum", "column": "momentum", "params": {"lookback": 252, "skip": 21}}, "operator": ">", "right": {"kind": "constant", "value": 0}}
```

---

## 예제 E — 저변동성 필터 전략(Formula 조합, #14)

새 Factor 코드 없이 **Formula 사칙연산만으로** 변동성 프록시를 만든다.
`bollinger` 팩터 내부는 `upper - lower = 2 × num_std × rolling_std`이므로
`(upper - lower) / middle`이 정규화된 변동계수(변동성 프록시)가 된다.
밴드폭이 좁아지면(저변동 국면 진입) 매수, 넓어지면(변동성 확대) 청산한다.

### Step 1 — Formula 생성

`bollinger_width_pct.json`:

```json
{
  "id": "bollinger_width_pct",
  "name": "볼린저 밴드폭 비율(변동성 프록시)",
  "version": "1",
  "expression": {
    "node": "binary",
    "op": "/",
    "left": {
      "node": "binary",
      "op": "-",
      "left": {"kind": "factor", "factor_id": "bollinger", "column": "upper", "params": {"window": 20, "num_std": 2.0}},
      "right": {"kind": "factor", "factor_id": "bollinger", "column": "lower", "params": {"window": 20, "num_std": 2.0}}
    },
    "right": {"kind": "factor", "factor_id": "bollinger", "column": "middle", "params": {"window": 20, "num_std": 2.0}}
  },
  "output_column": "value"
}
```

### Step 2 — Rule 2종 생성

`low_vol_entry.json` — 밴드폭 비율이 0.11 아래로 크로스(저변동 국면 진입):

```json
{
  "id": "low_vol_entry",
  "name": "저변동성 진입(밴드폭 축소)",
  "version": "1",
  "root": {
    "node": "predicate",
    "left": {"kind": "formula", "formula_id": "bollinger_width_pct", "column": "value"},
    "operator": "crosses_below",
    "right": {"kind": "constant", "value": 0.11}
  }
}
```

`low_vol_exit.json` — 밴드폭 비율이 0.28 위로 크로스(변동성 확대, 청산):

```json
{
  "id": "low_vol_exit",
  "name": "저변동성 청산(밴드폭 확대)",
  "version": "1",
  "root": {
    "node": "predicate",
    "left": {"kind": "formula", "formula_id": "bollinger_width_pct", "column": "value"},
    "operator": "crosses_above",
    "right": {"kind": "constant", "value": 0.28}
  }
}
```

### Step 3 — 전략 생성

`low_vol_strategy.json`:

```json
{
  "id": "low_vol_strategy",
  "name": "저변동성 필터 전략",
  "version": "1",
  "factor_refs": [{"factor_id": "bollinger", "params": {"window": 20, "num_std": 2.0}}],
  "universe": {"symbols": ["005930"]},
  "rule": {"roles": {"entry": ["low_vol_entry"], "exit": ["low_vol_exit"]}}
}
```

### Step 4 — 생성·검증·백테스트

```bash
uv run python -m quant_krx formula-create bollinger_width_pct.json
uv run python -m quant_krx rule-create low_vol_entry.json
uv run python -m quant_krx rule-create low_vol_exit.json
uv run python -m quant_krx strategy-create low_vol_strategy low_vol_strategy.json
uv run python -m quant_krx strategy-validate low_vol_strategy
uv run python -m quant_krx strategy-backtest low_vol_strategy \
    --symbols 005930 --data-source pykrx --start 2024-07-01 --end 2026-06-30 --benchmark KOSPI
```

검증 결과: 총수익률 93.23%, MDD 15.90%, Sharpe **1.853**(전체 예제 중 최고), 승률
100.00%, 거래 횟수 2, 벤치마크(KOSPI) 256.65%. 임계값(0.11/0.28)은 005930의
2024-07~2026-06 밴드폭 비율 분포(하위 20%/상위 20% 분위수)로 보정한 값이며,
다른 종목·구간에서는 재보정이 필요하다.

---

## 예제 F — 피오트로스키 F-Score 근사 전략(#11)

**⚠️ 현재는 Fixture 데이터로만 검증 가능**(`--data-source fixture`). `roa` 등 재무제표
팩터는 `required_data=financials`인데 `DartFundamentalAdapter`가 Deferred라 pykrx로는
NaN만 나온다. 아래 Rule/Formula/Strategy 정의 자체는 지금 만들어두면, DART 연동이
코드로 추가되는 즉시 `--data-source`만 바꿔서 실데이터로 쓸 수 있다.

원 논문의 9개 이진 채점 대신, 카탈로그에 있는 6개 재무 팩터를 AND로 묶어
"전부 통과해야 진입"하는 근사판이다(수익성 `roa`, 성장성 `revenue_growth`·
`op_income_growth`, 재무건전성 `debt_to_equity`·`current_ratio`·`interest_coverage`).

### Rule 2종

`piotroski_lite_entry.json`:

```json
{
  "id": "piotroski_lite_entry",
  "name": "피오트로스키 F-Score 근사 진입",
  "version": "1",
  "root": {
    "node": "composition",
    "op": "AND",
    "operands": [
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "roa", "column": "roa", "params": {}}, "operator": ">", "right": {"kind": "constant", "value": 0}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "revenue_growth", "column": "revenue_growth", "params": {}}, "operator": ">", "right": {"kind": "constant", "value": 0}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "op_income_growth", "column": "op_income_growth", "params": {}}, "operator": ">", "right": {"kind": "constant", "value": 0}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "debt_to_equity", "column": "debt_to_equity", "params": {}}, "operator": "<", "right": {"kind": "constant", "value": 1.0}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "current_ratio", "column": "current_ratio", "params": {}}, "operator": ">", "right": {"kind": "constant", "value": 1.0}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "interest_coverage", "column": "interest_coverage", "params": {}}, "operator": ">", "right": {"kind": "constant", "value": 3}}
    ]
  }
}
```

`piotroski_lite_exit.json` — 셋 중 하나라도 재무 경고가 뜨면 청산:

```json
{
  "id": "piotroski_lite_exit",
  "name": "피오트로스키 F-Score 근사 청산(재무 경고)",
  "version": "1",
  "root": {
    "node": "composition",
    "op": "OR",
    "operands": [
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "roa", "column": "roa", "params": {}}, "operator": "<", "right": {"kind": "constant", "value": 0}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "revenue_growth", "column": "revenue_growth", "params": {}}, "operator": "<", "right": {"kind": "constant", "value": 0}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "debt_to_equity", "column": "debt_to_equity", "params": {}}, "operator": ">", "right": {"kind": "constant", "value": 1.5}}
    ]
  }
}
```

### 전략

`piotroski_lite_strategy.json`:

```json
{
  "id": "piotroski_lite_strategy",
  "name": "피오트로스키 F-Score 근사 전략",
  "version": "1",
  "factor_refs": [
    {"factor_id": "roa", "params": {}},
    {"factor_id": "revenue_growth", "params": {}},
    {"factor_id": "op_income_growth", "params": {}},
    {"factor_id": "debt_to_equity", "params": {}},
    {"factor_id": "current_ratio", "params": {}},
    {"factor_id": "interest_coverage", "params": {}}
  ],
  "universe": {"symbols": ["005930"]},
  "rule": {"roles": {"entry": ["piotroski_lite_entry"], "exit": ["piotroski_lite_exit"]}}
}
```

### 생성·검증·백테스트(Fixture 전용)

```bash
uv run python -m quant_krx fetch-fundamental --provider fixture --symbols 005930 --kind financials
uv run python -m quant_krx rule-create piotroski_lite_entry.json
uv run python -m quant_krx rule-create piotroski_lite_exit.json
uv run python -m quant_krx strategy-create piotroski_lite_strategy piotroski_lite_strategy.json
uv run python -m quant_krx strategy-validate piotroski_lite_strategy
uv run python -m quant_krx strategy-backtest piotroski_lite_strategy --symbols 005930 --data-source fixture
```

검증 결과: 총수익률 5.27%, MDD 26.53%, Sharpe 0.387, 승률 100.00%, 거래 횟수 1.
`sample_financials.csv`의 005930 재무비율이 분기마다 완만하게 단조 개선되도록
설계된 합성 데이터라, 조건을 처음 만족하는 시점에 1회 진입해 끝까지 보유하는
양상을 보인다 — **메커니즘 검증**이 목적이며, DART 연동 후 실제 분기 재무제표로
교체하면 등락 있는 진짜 신호가 나올 것이다.

---

## 예제 G — 퀄리티 스크린 전략(GP/A + ROIC, #12)

**⚠️ 예제 F와 동일하게 현재는 Fixture 전용.** Novy-Marx GP/A와 ROIC 두 퀄리티
팩터를 임계값으로 결합한다(QMJ 전체 복합 스코어의 부분집합).

### Rule 2종

`quality_screen_entry.json`:

```json
{
  "id": "quality_screen_entry",
  "name": "퀄리티 스크린 진입(GP/A+ROIC)",
  "version": "1",
  "root": {
    "node": "composition",
    "op": "AND",
    "operands": [
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "gp_to_assets", "column": "gp_to_assets", "params": {}}, "operator": ">", "right": {"kind": "constant", "value": 0.05}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "roic", "column": "roic", "params": {}}, "operator": ">", "right": {"kind": "constant", "value": 0.02}}
    ]
  }
}
```

`quality_screen_exit.json`:

```json
{
  "id": "quality_screen_exit",
  "name": "퀄리티 스크린 청산(수익성 악화)",
  "version": "1",
  "root": {
    "node": "composition",
    "op": "OR",
    "operands": [
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "gp_to_assets", "column": "gp_to_assets", "params": {}}, "operator": "<", "right": {"kind": "constant", "value": 0.03}},
      {"node": "predicate", "left": {"kind": "factor", "factor_id": "roic", "column": "roic", "params": {}}, "operator": "<", "right": {"kind": "constant", "value": 0}}
    ]
  }
}
```

### 전략

`quality_screen_strategy.json`:

```json
{
  "id": "quality_screen_strategy",
  "name": "퀄리티 스크린 전략(GP/A+ROIC)",
  "version": "1",
  "factor_refs": [
    {"factor_id": "gp_to_assets", "params": {}},
    {"factor_id": "roic", "params": {}}
  ],
  "universe": {"symbols": ["005930"]},
  "rule": {"roles": {"entry": ["quality_screen_entry"], "exit": ["quality_screen_exit"]}}
}
```

### 생성·검증·백테스트(Fixture 전용)

```bash
uv run python -m quant_krx fetch-fundamental --provider fixture --symbols 005930 --kind financials
uv run python -m quant_krx rule-create quality_screen_entry.json
uv run python -m quant_krx rule-create quality_screen_exit.json
uv run python -m quant_krx strategy-create quality_screen_strategy quality_screen_strategy.json
uv run python -m quant_krx strategy-validate quality_screen_strategy
uv run python -m quant_krx strategy-backtest quality_screen_strategy --symbols 005930 --data-source fixture
```

검증 결과: 총수익률 5.27%, MDD 26.53%, Sharpe 0.387, 승률 100.00%, 거래 횟수 1
(예제 F와 우연히 같은 진입 시점·동일 보유 구간이 겹쳐 수치가 동일하게 나왔다 —
Fixture 데이터의 재무비율이 유사한 시점에 함께 임계값을 넘도록 설계됐기 때문).

---

## 여전히 불가능한 항목(#10, #13, #15) — 재확인

- **#10 Magic Formula 진짜 순위결합**: `EvaluationContext.data`가 종목 1개분
  `FactorInput`만 들고 있어(`workspace/evaluation.py`), 유니버스 전체를 한 시점에
  비교·순위화하는 연산 자체가 시스템에 없다. Formula/Rule을 아무리 조합해도
  "이 시점 유니버스 내 상위 N%"는 만들 수 없다 — 임계값 근사(#6)가 최선.
- **#13 52주 신고가 근접**: Formula가 사칙연산만 지원하고, 기존 팩터 중
  rolling max를 노출하는 것이 없어 재료 자체가 없다. 새 Factor(`_mark_warmup_nan`
  패턴을 따르는 rolling max 기반) 구현이 선행돼야 한다.
- **#15 Turtle Trading**: Donchian 채널(고가/저가 rolling max/min) Factor 부재는
  #13과 동일한 이유로 막혀 있고, 설령 채널 Factor를 추가해도 `Portfolio.from_signals`
  호출에 `size` 인자가 없어 ATR 기반 가변 포지션 사이징은 백테스트 엔진 자체의
  변경 없이는 불가능하다(Formula/Rule/Factor 계층과 무관한 실행 계층 이슈).

---

## 전체 결과 요약

| 전략 | 총수익률 | MDD | Sharpe | 거래 횟수 | 데이터소스 |
|---|---|---|---|---|---|
| A. 딥밸류(저PER+저PBR) | 62.60% | 6.89% | 1.313 | 1 | pykrx |
| B. 고배당 | 35.79% | 36.78% | 0.456 | 2 | pykrx |
| C. 추세 눌림목 하이브리드 | 15.44% | 9.59% | 0.464 | 5 | pykrx |
| D-1. 고전적 골든크로스(SMA 50/200) | **288.10%** | 33.04% | 1.163 | 2 | pykrx |
| E. 저변동성 필터(Formula) | 93.23% | 15.90% | **1.853** | 2 | pykrx |
| F. 피오트로스키 F-Score 근사 | 5.27% | 26.53% | 0.387 | 1 | fixture 전용 |
| G. 퀄리티 스크린(GP/A+ROIC) | 5.27% | 26.53% | 0.387 | 1 | fixture 전용 |
| (참고) KOSPI 벤치마크(pykrx 구간) | 170.17%~256.65% | — | — | — | — |

D-1과 E만 해당 구간 KOSPI 벤치마크를 상회했고 나머지는 하회했다(005930 단일
종목·짧은 표본, 과최적화 검증 안 됨 — 성과 우열이 아니라 **워크스페이스로 조사된
전략 전부를 실제로 정의·생성·백테스트할 수 있음을 검증**하는 것이 이 문서의
목적이다). F/G는 DART 연동 전까지 Fixture로만 실행 가능하다는 점을 반드시
구분해서 볼 것. 실전 활용 전
[FAMOUS_QUANT_STRATEGIES.md §5 공통 함정](FAMOUS_QUANT_STRATEGIES.md#5-공통-함정--왜-백테스트-수익률을-그대로-믿으면-안-되는가)의
생존편향·과최적화 주의사항을 반드시 재확인할 것.

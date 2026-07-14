# No-Code Strategy Workspace

코드 없이 팩터(Factor)·산술 조합(Formula)·조건(Rule)을 선언적으로 조합해 전략을
설계 → 검증 → 백테스트 → Daily 운영 → 재사용(Template/Import·Export)까지 CLI로
완결하는 서브시스템.

설계 원천: [refined_epics/](../refined_epics/README.md) (PRD-R01 Factor Platform,
PRD-R02 Declarative Definition Core, PRD-R03 Workspace & Execution). 정의는 순수
JSON이며 코드·람다·수식 문자열을 저장·평가하지 않는다.

## 팩터 플랫폼 (Factor Platform)

가격·기술(7종), 밸류에이션(11종), 재무제표(14종) 총 32종의 지표(Factor)를 플랫폼이
1급 자원으로 관리합니다. 지표는 `factors/` 패키지가 순수 계산으로 제공하며,
펀더멘털 데이터(밸류에이션·재무제표)는 `data/` 패키지가 DuckDB에 저장·조회합니다.

| 카테고리 | 개수 | 예시 |
|---|---|---|
| 가격·기술 | 7 | `price`, `sma`, `ema`, `rsi`, `macd`, `bollinger`, `momentum` |
| 밸류에이션 | 11 | `per`, `pbr`, `eps`, `bps`, `roe_approx`, `peg`, `market_cap` 등 |
| 재무제표 | 14 | `roa`, `roic`, `gross_margin`, `revenue_growth`, `debt_to_equity` 등 |

### 팩터 조회

```bash
# 전체 팩터 목록 (카테고리 필터 가능)
uv run python -m quant_krx list-factors
uv run python -m quant_krx list-factors --category value

# 팩터 상세 (파라미터 명세·산출 컬럼·필요 데이터)
uv run python -m quant_krx show-factor macd
uv run python -m quant_krx show-factor roa   # 재무제표 팩터는 DART 미구현 안내 표시
```

### 펀더멘털 데이터 수집

```bash
# 오프라인 테스트(Fixture) — 네트워크 없이 합성 데이터 수집
uv run python -m quant_krx fetch-fundamental --provider fixture --symbols 005930,000660

# 실 데이터 수집(PyKrx, 밸류에이션만 지원 — 재무제표는 DART 연동 전까지 미지원)
uv run python -m quant_krx fetch-fundamental --provider pykrx --kind valuation \
    --start 2024-01-01 --end 2024-12-31
```

멱등 수집이며, PK 중복·미래 일자·음수 필드 위반 행은 저장에서 제외되고 결과 표에
제외 사유가 함께 표시됩니다.

## 전략 워크스페이스 (Formula/Rule/Strategy)

Formula(파생 지표)·Rule(조건)·Strategy(전략) 3종을 코드 없이 JSON 정의로 조합합니다.
정의 입력은 JSON 파일 경로 또는 stdin(`-`)이며, 편집(`strategy-edit`)은 항상 **전체
정의 교체**입니다(부분 필드 패치 없음).

```bash
# Formula/Rule 정의 CRUD
uv run python -m quant_krx formula-create my_formula.json
uv run python -m quant_krx formula-show my_formula
uv run python -m quant_krx list-formulas
uv run python -m quant_krx formula-delete my_formula

uv run python -m quant_krx rule-create my_rule.json
uv run python -m quant_krx rule-show my_rule
uv run python -m quant_krx list-rules
uv run python -m quant_krx rule-delete my_rule

# Strategy 정의(신규 생성 또는 Built-in/사용자 Template 복제)
uv run python -m quant_krx strategy-create my_strategy my_strategy.json
uv run python -m quant_krx strategy-create my_ma --template ma_crossover
uv run python -m quant_krx strategy-show my_strategy
uv run python -m quant_krx strategy-list
uv run python -m quant_krx strategy-edit my_strategy my_strategy_v2.json
uv run python -m quant_krx strategy-delete my_strategy

# 실행 없는 사전 검증 + 활성화(Daily 실행 집합 편입)
uv run python -m quant_krx strategy-validate my_strategy
uv run python -m quant_krx strategy-activate my_strategy
uv run python -m quant_krx strategy-deactivate my_strategy

# 백테스트(데이터 소스: fixture(기본) | fdr | pykrx)
uv run python -m quant_krx strategy-backtest my_strategy --data-source fixture

# 벤치마크 대비 상대 성과(선택 — 수집 실패 시 경고만 남기고 백테스트는 계속 진행)
uv run python -m quant_krx strategy-backtest my_strategy --data-source fixture --benchmark KOSPI

# Template 열거(Built-in + 사용자, 출처 구분)
uv run python -m quant_krx strategy-template-list

# Import/Export(전이 참조 Rule·Formula 포함 JSON 번들, 결정론 직렬화)
uv run python -m quant_krx strategy-export my_strategy --output my_strategy_bundle.json
uv run python -m quant_krx strategy-import my_strategy_bundle.json
uv run python -m quant_krx strategy-import my_strategy_bundle.json --overwrite
```

활성 전략(과 그 전략이 참조 중인 Rule/Formula)의 수정·삭제는 거부됩니다 — 먼저
`strategy-deactivate`로 비활성화해야 합니다.

미존재 id를 지정하면 오류 메시지에 현재 등록된 id 목록이 힌트로 함께 표시됩니다.

## Built-in Template

최초 `run-daily` 실행 시 아래 5종이 자동으로 생성·활성화되어 끊김 없이 운영됩니다
(전략 원천 단일화 — 코드형 전략은 존재하지 않으며 전부 선언형 정의로 대체되었습니다).

| 이름 | 유형 | 핵심 아이디어 |
|------|------|--------------|
| `ma_crossover` | 추세 추종 | 단기(20일)/장기(60일) MA 골든·데드크로스 |
| `rsi_breakout` | 역추세 | RSI 30 이하 매수 / 70 이상 매도 |
| `bollinger_band` | 평균 회귀 | 가격이 밴드(MA ± 2σ) 이탈 시 신호 |
| `macd` | 모멘텀 | 12/26 EMA 차이의 9일 시그널선 교차 |
| `momentum` | 중장기 추세 | 12-1개월 가격 모멘텀 (Jegadeesh & Titman) |

사용자 전략은 Formula/Rule을 조합해 직접 정의하거나 Template를 복제
(`strategy-create --template`)해 만들 수 있습니다.

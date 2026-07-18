# Deep Interview Spec: EPIC-R02 Quant Assistant GUI

## Metadata
- Interview ID: epic-r02-gui-20260718
- Rounds: 5 (+ Round 0 토폴로지 확인 3회 왕복)
- Final Ambiguity Score: 15.75%
- Type: brownfield
- Generated: 2026-07-18
- Threshold: 0.2 (20%)
- Threshold Source: default
- Initial Context Summarized: no
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.85 | 35% | 0.2975 |
| Constraint Clarity | 0.85 | 25% | 0.2125 |
| Success Criteria | 0.85 | 25% | 0.2125 |
| Context Clarity | 0.80 | 15% | 0.1200 |
| **Total Clarity** | | | **0.8425** |
| **Ambiguity** | | | **0.1575** |

## Topology

| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| GUI 아키텍처/플랫폼 | active | 웹서버+API+프론트엔드 신규 구축. 프레임워크는 구현 시 자유 선택(로컬 1인용 제약 하에서 결정) | Goal/Acceptance Criteria에 반영 |
| 팩터 조회 + 공식·규칙·전략 관리 | active | 팩터는 읽기 전용(list/show)만 제공. Formula/Rule/Strategy는 기존 CLI CRUD(생성/수정/삭제/검증/활성화/템플릿/Export·Import)를 GUI로 제공 | Acceptance Criteria에 반영 |
| 백테스트 실행 | active | 종목명/코드·시작일·종료일·데이터소스(krx/fixture/fdr)·전략 입력 기반 실행 및 결과 표시(지표 요약·equity curve·거래내역) | Acceptance Criteria에 반영 |
| 기존 CLI 호환성 유지 | active | 27개 기존 CLI 명령이 회귀 없이 계속 동작 | Acceptance Criteria에 반영 |
| 팩터 카탈로그 CRUD(생성/수정/삭제) | **deferred** | 원본 32종 팩터 카탈로그(factors/catalog/) 자체를 GUI에서 생성/수정/삭제하는 기능 | 사용자 확정 보류: "팩터 생성, 삭제, 관리는 제외함. 목록 조회만 제공하면 됨." AST 순수성 제약(INV-1) 위반 우려도 배제 사유 중 하나 |
| Daily Job / 리포트 / 펀더멘털 수집 GUI 노출 (run-daily, show-reports, fetch-fundamental, validate-config) | **deferred** | 텔레그램 발송 트리거, 리포트 조회, 펀더멘털 수집, 설정 검증을 GUI에 노출하는 것 | 사용자 확정 보류: "제외(상세 요구사항 13~20단계만)". 향후 버전에서 재검토 |

## Goal

기존 CLI 기반 "노코드 전략 워크스페이스"(팩터 32종 조회, 공식·규칙·전략 생성/수정/삭제, 전략 기반 백테스트)를
**로컬 1인용 웹 GUI**로 제공한다. 사용자는 JSON 파일을 직접 작성하지 않고 GUI 화면(폼·빌더)을 통해
공식(Formula)·규칙(Rule)·전략(Strategy)을 생성·수정·삭제하고, 종목/기간/데이터소스/전략을 지정해
백테스트를 실행하고 결과를 시각적으로 확인할 수 있어야 한다. GUI는 내부적으로 기존 `WorkspaceService`,
`quant/`, `factors/`, `data/` 계층을 재사용하며 새로운 계산/검증 로직을 만들지 않는다. 기존 CLI 27개
명령은 이번 작업으로 회귀되지 않아야 한다.

## Constraints

- **배포/사용자 규모**: 로컬 1인용. 개인 PC에서 `localhost`로만 접근. 인증/권한 관리 불필요.
- **데이터 저장**: 기존 로컬 DuckDB(`storage/schema.py` + `data/schema.py` 10테이블)를 그대로 사용. 별도 DB 신설 없음.
- **아키텍처 자유도**: GUI 프레임워크(백엔드 API 서버 + 프론트엔드 구성 방식)는 구현 시점에 적절히 선택하되, 위 로컬 1인용/무인증 전제와 Python 3.10 제약(`vectorbt` 의존)을 위반하지 않아야 함. 기술스택(Node.js 빌드 도구 사용 여부 포함)에 대한 사용자 제약은 없음 — 공식/규칙/전략의 트리 구조 표현식(BinaryOp/UnaryOp 중첩)을 시각적으로 편집 가능한 빌더 UI를 표현하기에 적합한 스택을 설계 단계에서 자유롭게 선택.
- **백엔드는 기존 Python 도메인 계층(`WorkspaceService`, `quant/`, `factors/`, `data/`)을 직접 import하여 재사용** — CLI를 subprocess로 감싸는 방식은 지양(중복 프로세스·상태 불일치 위험).
- **AST 순수성 제약(INV-1)**: `factors/`는 계속 순수 계산 계층으로 유지되어야 하며, GUI 어떤 입력도 이 계층에 실행 코드를 주입해서는 안 됨. (팩터 카탈로그 CRUD를 보류한 근거와 동일)
- **팩터 파라미터 오버라이드**는 `get_factor(id, **params)` 경로로만 허용(신규 계산 로직 추가 아님).
- 기존 CLI 테스트(`uv run pytest tests/ -q`)는 이번 작업 후에도 모두 통과해야 함.

## Non-Goals

- 원본 32종 팩터 카탈로그(계산 로직)의 GUI 생성/수정/삭제 — 목록/상세 조회만 제공.
- `run-daily`(일일 파이프라인/텔레그램 발송 트리거)의 GUI 노출.
- `show-reports`(리포트 조회), `fetch-fundamental`(펀더멘털 수집), `validate-config`의 GUI 화면.
- 다중 사용자 동시 접근, 인증/권한 관리, 원격 배포.
- AST 순수성 규칙을 재설계하는 사용자 정의 팩터 DSL.

## Acceptance Criteria

### GUI 아키텍처/플랫폼
- [ ] 백엔드 API 서버 + 프론트엔드로 구성되며 `localhost`에서 별도 인증 없이 접근 가능
- [ ] 백엔드는 기존 `WorkspaceService`/`quant/`/`factors/`/`data/` 모듈을 직접 import하여 사용(신규 계산/검증 로직 재구현 금지)
- [ ] Python 3.10 제약(`vectorbt`) 및 기존 DuckDB 스키마를 그대로 준수

### 팩터 조회 + 공식·규칙·전략 관리
- [ ] 팩터 32종을 카테고리별로 목록 조회 가능(`list-factors` 상당) 및 상세 조회 가능(`show-factor` 상당). 생성/수정/삭제 UI는 제공하지 않음
- [ ] 공식(Formula)/규칙(Rule)/전략(Strategy)을 JSON을 직접 작성하지 않고 GUI 폼/빌더로 생성·수정·삭제 가능(`*-create`/`strategy-edit`은 전체 정의 교체 시맨틱 유지)
- [ ] 저장 전 검증(validate) 결과를 실시간으로 표시(오류/경고, `strategy-validate` 규칙과 동일 소스 사용)
- [ ] 전략 활성화/비활성화 토글 제공(`strategy-activate`/`strategy-deactivate` 상당)
- [ ] `strategy-template-list` 상당의 템플릿 목록에서 선택해 새 전략 생성 가능
- [ ] 전략 Export(JSON 다운로드)/Import(JSON 업로드) 제공(`strategy-export`/`strategy-import` 상당)
- [ ] 존재하지 않는 id 조작 시 CLI와 동일하게 현재 등록된 id 목록 힌트 표시

### 백테스트 실행
- [ ] 종목명 또는 종목코드, 시작일, 종료일, 데이터소스(`fixture`/`fdr`/`pykrx`), 적용 전략을 입력받아 실행 가능
- [ ] 결과 화면에 지표 요약 테이블 표시: 총수익률, MDD, Sharpe, 승률, 거래횟수, 총비용, (벤치마크 지정 시) 벤치마크 수익률/초과수익률 — `strategy-backtest` CLI 출력과 동일 지표 집합
- [ ] 자산곡선(equity curve) 차트 표시
- [ ] 거래 내역(entry/exit) 테이블 표시
- [ ] 백테스트 실패 시(전략 미검증/미존재 등) CLI와 동등한 오류 메시지 표시

### 기존 CLI 호환성 유지
- [ ] 기존 27개 CLI 명령이 이번 변경 이후에도 모두 정상 동작
- [ ] `uv run pytest tests/ -q` 전체 통과
- [ ] GUI 관련 신규 로직에 대한 테스트 추가(필요 범위 내)

## Assumptions Exposed & Resolved

| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| "팩터 생성/수정/삭제"는 32종 고정 카탈로그(코드) 자체를 다루는 것이다 | `factors/catalog/`는 AST 강제 순수 계산 계층(INV-1)이라 외부 입력으로 실행 코드 주입이 불가함을 제시 | 사용자가 의미한 것은 기존 `formula-create` 등 파생 지표(Formula) CRUD였음이 확인됨 → 원본 카탈로그는 조회만 제공, CRUD는 Formula/Rule/Strategy 관리로 통합 |
| "GUI는 CLI의 모든 기능을 사용 가능해야 함" = 27개 전체 CLI 명령 GUI화 | 상세 요구사항(13~20단계)은 팩터/공식/규칙/전략 CRUD와 백테스트만 구체적으로 언급하는 반전을 지적 | `run-daily`/`show-reports`/`fetch-fundamental`/`validate-config`는 이번 범위에서 명시적 제외(향후 버전 보류) |
| GUI는 다중 사용자/원격 접근을 고려해야 할 수도 있다 | 배포 환경이 미정이면 인증·동시성 설계가 필요해 아키텍처 선택에 큰 영향을 줌을 제시 | 로컬 1인용, `localhost` 전용, 인증 불필요로 확정 |
| 백테스트 결과 표시는 CLI와 동일한 지표 표만 있으면 충분하다 | 정확히 무엇을 "성공적인 표시"로 볼지 불명확함을 지적 | 지표 요약 + equity curve 차트 + 거래내역 테이블 + 기존 CLI 지표 집합 전부 필요로 확정 |
| 트리 구조 빌더 UI가 필요하므로 특정 프론트엔드 기술(Node.js 빌드 등)에 제약이 있을 수 있다 | 순수 Python 서버사이드 렌더링만으로는 중첩 표현식 편집 UI 표현력이 제한적일 수 있음을 제시 | 기술스택 제약 없음 — 구현자가 자유롭게 결정(Node.js 빌드 환경 포함 허용) |

## Technical Context

- 기존 CLI 27개 명령(`src/quant_krx/__main__.py`): `run-daily`, `show-reports`, `validate-config`, `version`,
  `list-factors`, `show-factor`, `fetch-fundamental`, `strategy-backtest`,
  `formula-create/show/delete`, `list-formulas`, `rule-create/show/delete`, `list-rules`,
  `strategy-create/show/edit/delete/list/validate/activate/deactivate/template-list/export/import`.
- 팩터는 `factors/catalog/`에 코드로 고정된 32종(가격·기술 7 + 밸류에이션 11 + 재무제표 14). 유일 인가 실행 API는
  `compute_factor(factor, data)`; `get_factor(id, **params)`로 파라미터 오버라이드 인스턴스 생성.
  순수 계산 계층이며 `tests/unit/factors/test_purity_ast.py`가 AST로 강제.
- Formula(`src/quant_krx/formula/definition.py`)는 `FactorOperand`(기존 factor_id 참조) + `ConstantOperand` +
  `FormulaOperand`를 `BinaryOp`(+,-,*,/)/`UnaryOp`(neg)로 조합하는 표현식 트리이며, 이미 CLI CRUD가 존재함
  — 사용자가 말한 "팩터 생성"의 실체.
- `strategy-backtest`는 `WorkspaceService.backtest()`를 호출하며 `BacktestResult(metrics, trades, equity_curve)`를
  반환(CLAUDE.md). 현재 CLI는 `metrics`만 표로 렌더링하고 `trades`/`equity_curve`는 미표시 — GUI가 이 데이터를
  최초로 시각화하는 지점.
- vectorbt 1.0.0 API 제약: `pf.trades.records["fees"]` 없음 → `entry_fees + exit_fees` 사용(`quant/metrics.py`).
- DuckDB 스키마 10테이블(baseline 8 + 펀더멘털 additive 2), `Database.connect()`에서 함께 실행.
- Python 3.10 필수(`vectorbt`의 `python_requires="<3.11"` 제약).

## Ontology (Key Entities)

| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| Factor | supporting (read-only) | id, category, metadata, params | Formula가 FactorOperand로 참조 |
| Formula | core domain | id, name, version, expression(Expr tree), output_column | FactorOperand/ConstantOperand/FormulaOperand로 구성, Rule/Strategy가 참조 가능 |
| Rule | core domain | id, condition(Formula 기반 조건) | Strategy가 참조 |
| Strategy | core domain | id, universe, rules, template 여부, active 상태 | Backtest 실행 대상 |
| Backtest Run | core domain | strategy_id, symbols, start, end, data_source, fees, slippage, benchmark | Strategy를 입력받아 BacktestResult 산출 |
| BacktestResult | supporting | metrics, trades, equity_curve | GUI 결과 화면의 데이터 원천 |
| GUI User | external system(단일) | 로컬 1인, 인증 없음 | 모든 컴포넌트의 유일 행위자 |

## Ontology Convergence

Round별 정식 opus 스코어링 대신 대화 내 실시간 판단으로 진행(요구사항 명확화 위주 인터뷰였으며 신규 도메인 엔티티 발견보다는 기존 코드베이스 엔티티(Factor/Formula/Rule/Strategy)와 사용자 용어 간 매핑 수렴이 핵심이었음).

| Round | 핵심 수렴 내용 |
|-------|----------------|
| Round 0 (3회 왕복) | "팩터"라는 사용자 용어가 코드베이스의 Formula(파생 지표)와 동일함을 확인, 원본 32종 카탈로그는 조회 전용으로 확정 |
| Round 1 | GUI 범위가 CLI 27개 전체가 아닌 13~20단계(CRUD+백테스트)로 확정 |
| Round 2 | GUI User 엔티티가 "로컬 1인, 무인증"으로 확정 |
| Round 3 | BacktestResult의 trades/equity_curve가 GUI에서 처음 노출되는 데이터임을 확인 |
| Round 4 | Strategy 엔티티의 부가 상태(validate/active/template/export)가 GUI CRUD 완료 기준으로 확정 |

## Interview Transcript
<details>
<summary>Full Q&A (Round 0 x3 + Round 1~4)</summary>

### Round 0-1 (토폴로지 확인)
**Q:** 5개 컴포넌트(GUI 아키텍처, 팩터 관리, 공식·규칙·전략 관리, 백테스트 실행, CLI 호환성)로 이해했는데 맞는지?
**A:** "팩터 관리 범위 재정의 필요"

### Round 0-2 (팩터 관리 범위)
**Q:** '팩터 생성/수정/삭제'가 파라미터 오버라이드 인스턴스 수준인지, 진짜 신규 계산 로직(DSL) 추가인지, 이번 범위에서 제외인지?
**A:** "기존 CLI는 팩터 카탈로그 32종을 기반으로 새로운 팩터를 생성하는 기능을 제공함. 기존 32개 팩터 카탈로그는 수정하지 않음. 기존 팩터를 기반으로 하는 신규 팩터를 생성하는 것으로 한정함. CLI에 있는 기능이라 관련 기능의 신규 추가는 아님"
→ 코드 확인 결과 이는 기존 `formula-create` CLI(Formula CRUD)와 정확히 일치함을 확인.

### Round 0-3 (원본 카탈로그 수정 범위)
**Q:** 원본 32종 팩터의 활성화/파라미터 기본값 변경만 허용할지, 계산 로직 자체를 GUI에서 수정 가능하게 할지, 코드로만 수정하고 GUI는 조회만 할지?
**A:** "팩터 생성, 삭제, 관리는 제외함. 목록 조회만 제공하면 됨."
→ 최종 4개 컴포넌트로 토폴로지 확정 (팩터 CRUD는 deferred).

### Round 1
**Q:** '모든 CLI 기능'이 run-daily/show-reports/fetch-fundamental/validate-config도 포함하는지?
**A:** "제외(상세 요구사항 13~20단계만)"
**Ambiguity:** 44% (Goal: 0.75, Constraints: 0.4, Criteria: 0.35, Context: 0.75)

### Round 2
**Q:** GUI는 누가, 어디서 사용하나?
**A:** "로컬 1인용(개인 PC에서 localhost로만 접근)"
**Ambiguity:** 33% (Goal: 0.8, Constraints: 0.75, Criteria: 0.35, Context: 0.75)

### Round 3
**Q:** 백테스트 실행 결과에 GUI에 무엇이 보여야 하나?
**A:** "지표 요약 테이블(수익률/샤프/MDD 등), 자산곡선(equity curve) 차트, 거래 내역 테이블(entry/exit), strategy-backtest 명령어 실행후 표시되는 결과"
**Ambiguity:** 23.25% (Goal: 0.85, Constraints: 0.75, Criteria: 0.65, Context: 0.8)

### Round 4
**Q:** 공식/규칙/전략을 GUI에서 생성·수정할 때 어떤 기능이 함께 필요한가?
**A:** "검증(validate) 결과 실시간 표시, 활성화/비활성화 토글, 템플릿 기반 생성, Export/Import(JSON 파일)"
**Ambiguity:** 18.25% (Goal: 0.85, Constraints: 0.75, Criteria: 0.85, Context: 0.8) → **임계값(20%) 이하 도달, 사용자 요청으로 추가 인터뷰 진행**

### Round 5
**Q:** 기술스택에 선호/제약이 있나?
**A:** "제약 없음 — 구현자가 자유롭게 결정(추천)"
**Ambiguity:** 15.75% (Goal: 0.85, Constraints: 0.85, Criteria: 0.85, Context: 0.8) → **최종 확정**

</details>

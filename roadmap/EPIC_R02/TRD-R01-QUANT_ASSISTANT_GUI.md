# TRD-R01 : Quant Assistant GUI

**대응 PRD**: `PRD-R01-QUANT_ASSISTANT_GUI.md`
**계층**: 신규 최상위 소비 계층(`api/`, `web/`) — 기존 `workspace/`(파사드)·`factors/`·`data/`를 **소비만** 한다. 계산/검증 로직을 재정의하지 않는다.
**Status**: Draft for review
**전제**: 본 문서는 EPIC_R01(No-Code Strategy Workspace, `WorkspaceService` 파사드 및 하위 계층)이 이미 구현·검증된 상태 위에 로컬 1인용 웹 GUI를 추가한다고 가정한다. 모든 서술은 `PRD-R01-QUANT_ASSISTANT_GUI.md` + `CLAUDE.md`(제약사항) + 기존 확정 인터페이스(`workspace/service.py`, `workspace/backtest.py`, `formula/validation.py`, `rule/validation.py`) 역추적으로만 정당화한다.

> **문서 규약**: PRD가 이미 확정한 항목(범위 4개 컴포넌트, Non-Goals, 배포 제약)은 §3 추적성 매트릭스로 축약하고 §4에서 반복하지 않는다. §4 TR은 PRD에 없는 기술 결정(모듈 배치, 백엔드 파사드 결함 수정, 직렬화 계약, 동시성/블로킹 처리)만 담는다.

---

## 0. RALPLAN-DR 요약 (SHORT)

### Principles (원칙 3)

1. **PRD 역추적 유일 정당화**: 모든 TR은 PRD-R01의 Acceptance Criteria 또는 Constraints/Non-Goals로 역추적된다.
2. **소비만·역주입 금지**: `api/`는 `workspace/`·`factors/`·`data/`를 소비만 하며, 이 계층에 웹/HTTP 의존을 역주입하지 않는다(기존 INV-1과 동형 원칙의 신규 계층 적용).
3. **새 계산/검증 로직 금지, 단 반환 계약 결함은 additive로 수정**: `WorkspaceService`가 이미 계산하지만 반환하지 않는 데이터(trades/equity_curve)는 계산을 바꾸지 않고 반환 경로만 additive 확장한다.

### Decision Drivers (상위 3)

1. **equity curve/거래내역 유실**: `workspace/backtest.py::run_backtest()`가 `run_single_symbol_backtest()`의 완전한 결과에서 `.metrics`만 취해 `trades`/`equity_curve`를 버린다 — PRD 핵심 AC를 현재 파사드로는 만족 불가.
2. **CLI/API 오케스트레이션 drift 방지**: `__main__.py`의 데이터 로딩 조립(어댑터 선택·펀더멘털 수집·벤치마크)이 CLI 안에만 있어, API가 복제하면 두 경로가 어긋난다.
3. **단일 품질 게이트(`uv run pytest`) 준수**: 신규 표면(특히 프론트엔드)도 이 원칙에서 완전히 벗어나지 않아야 한다.

### Viable Options

**결정 축 D1 — 프론트엔드 스택**

| 옵션 | 방식 | 장점 | 단점 |
|---|---|---|---|
| **D1-i. FastAPI + React/Vite SPA** ✅채택(사용자 확정) | 백엔드 REST + SPA | 리치 UI 생태계(트리 에디터·차트) | Node.js 빌드체인 신규 도입, 프론트가 기본적으로 pytest 게이트 밖 |
| D1-ii. FastAPI + NiceGUI(순수 Python) | 단일 프로세스 | Node.js 불필요, pytest 커버리지 확대 여지 | 리치 UI 표현력 낮음 |
| D1-iii. FastAPI + HTMX | 경량 서버사이드 렌더링 | 번들러 불요 | 트리 상호작용 구현 부담 |

**무효화 근거**: 사용자가 deep-interview 후속 `/plan` 세션에서 D1-i를 명시적으로 선택(UI 생태계 폭 우선). D1-ii/D1-iii는 트리 편집 요구를 동일하게 충족 가능하나 채택되지 않음. 남은 리스크(프론트 테스트 공백)는 TR-GUI-010(Vitest)로 부분 완화.

**결정 축 D2 — trades/equity_curve 노출 방식**

| 옵션 | 방식 | 장점 | 단점 |
|---|---|---|---|
| **D2-i. `BacktestReport`에 `results` additive 필드** ✅채택 | 파사드 반환값 확장 | 단일 파사드 경로 유지, 회귀 0, 계산 로직 무변경 | 전 종목 결과 메모리 상주(1인용이라 무시 가능) |
| D2-ii. API가 `run_single_symbol_backtest` 직접 호출(파사드 우회) | API가 하위 함수 직접 조합 | 파사드 무변경 | `_require_runnable_and_valid` 게이트 복제 필요 → drift, 파사드 원칙 위반 |

**무효화 근거**: D2-ii는 `WorkspaceService.backtest()`의 runnable/검증 게이트(`service.py:240`)를 API가 재구현해야 하므로 검증 로직이 두 곳에 존재하게 되어(drift) "새 검증 로직 금지" 원칙과 파사드=로직 원칙을 동시에 위반한다. D2-i는 이미 계산되지만 버려지던 값을 반환 경로에 추가할 뿐이므로 원칙을 위반하지 않는다.

### ADR 요약

- **Decision**: 백엔드 `src/quant_krx/api/`(FastAPI)가 `WorkspaceService`/`formula.validation.validate_formula`/`rule.validation.validate_rule`을 얇게 감싼다. `BacktestReport`에 `results` additive 필드 추가, 데이터 로딩 오케스트레이션을 `workspace/data_loading.py::prepare_backtest_data()`로 추출해 CLI/API 공유. 프론트엔드는 `web/`(React/Vite SPA).
- **Drivers**: PRD AC 커버리지, drift 방지, 단일 품질 게이트.
- **Consequences**: Node.js 빌드체인 최초 도입. `strategy_backtest_cmd`가 `prepare_backtest_data()` 호출로 리팩터링(동작 불변, 이미 구현·검증 완료).
- **Follow-ups**: `run-daily` 등 장시간 작업의 GUI 노출은 이번 범위 밖(동기 REST 모델 재설계 필요).

---

## 1. 목적

기존 CLI 전용 No-Code Strategy Workspace(EPIC_R01) 위에 **로컬 1인용 웹 GUI**를 추가하는 기술 요구사항을 확정한다:

- 신규 `api/` 계층이 `WorkspaceService` 파사드·순수 검증기(`validate_formula`/`validate_rule`)를 **어떻게 소비·배선**하는지 확정한다(로직은 파사드/순수 함수에, I/O는 API 라우터에).
- `BacktestReport`가 현재 유실하는 `trades`/`equity_curve`를 additive하게 복원하는 지점을 확정한다.
- CLI(`strategy-backtest`)와 신규 API가 데이터 로딩 오케스트레이션을 공유하는 단일 지점(`prepare_backtest_data`)을 확정한다.
- 동시성(DuckDB 커넥션)·블로킹(장시간 백테스트) 처리 배선을 확정한다.
- 모든 Acceptance Criteria를 오프라인 `uv run pytest` 검증으로 매핑한다.

본 문서는 `WorkspaceService`의 기존 시그니처·정의 스키마를 재정의하지 않는다(EPIC_R01 확정 원천). 그것들의 **소비·조합 방식**만 확정한다.

## 2. 범위 (In / Out)

### In
- `api/` 패키지의 라우터·스키마·의존성 배선(FastAPI).
- `BacktestReport.results` additive 필드 추가(`workspace/backtest.py`).
- `prepare_backtest_data()` 추출(`workspace/data_loading.py`) 및 CLI 리팩터링.
- `GuiConfig` 설정 추가, `serve-gui` CLI 명령.
- 프론트엔드(`web/`) React/Vite SPA — 팩터 조회, Formula/Rule/Strategy 빌더, 백테스트 실행/결과 시각화.
- 백테스트 응답 직렬화 계약(equity_curve/trades JSON 스키마, 신규 정의 — 이 GUI가 최초 소비자).
- 동시성/블로킹 처리, 오류 계약(`WorkspaceError`→HTTP).

### Out (확정, PRD 승계)
- 원본 32종 팩터 카탈로그 자체 CRUD(PRD Non-Goals).
- `run-daily`/`show-reports`/`fetch-fundamental`/`validate-config`의 GUI 노출(PRD Non-Goals).
- 다중 사용자·인증·원격 배포(PRD 제약: 로컬 1인용).
- 새 팩터 계산 DSL(PRD Non-Goals, AST 순수성 INV-1 유지).
- 신규 계산/검증 로직 일체 — 전부 기존 `workspace/`·`formula/`·`rule/` 재사용.

## 3. PRD 추적성 매트릭스

| PRD Acceptance Criterion | TR | 근거 |
|---|---|---|
| 백엔드는 기존 도메인 계층 직접 import(subprocess 금지) | TR-GUI-001 | PRD 제약 |
| 팩터 목록/상세 조회(생성/수정/삭제 없음) | TR-GUI-004 | PRD §팩터조회 |
| Formula/Rule/Strategy GUI 폼/빌더 생성·수정·삭제 | TR-GUI-005 | PRD §CRUD |
| 저장 전 검증 실시간 표시 | TR-GUI-006 | PRD §CRUD AC2 |
| 활성화/비활성화 토글 | TR-GUI-007 | PRD §CRUD AC3 |
| 템플릿 기반 생성 | TR-GUI-008 | PRD §CRUD AC4 |
| Export/Import(JSON) | TR-GUI-009 | PRD §CRUD AC5 |
| 미존재 id 힌트 포함 오류 | TR-GUI-011 | PRD §CRUD, 공통 원칙 7 |
| 백테스트 실행(종목/기간/데이터소스/전략) | TR-GUI-002, TR-GUI-003 | PRD §백테스트 AC1 |
| 지표 요약/equity curve/거래내역 표시 | TR-GUI-002 (`results` 필드) | PRD §백테스트 AC2-4 |
| 기존 CLI 27개 회귀 없음 | TR-GUI-003 (리팩터링 회귀 테스트) | PRD §CLI호환 |
| localhost 전용, 인증 불필요 | TR-GUI-012 | PRD 제약 |
| AST 순수성(INV-1) 위반 없음 | TR-GUI-001 | PRD 제약, CLAUDE.md |

## 4. 기술 요구사항 (TR-GUI-xxx)

### 4.1 모듈 배치 및 계층 순수성

**TR-GUI-001 — `api/`·`web/` 배치와 소비 방향**
- `src/quant_krx/api/`(FastAPI 백엔드)는 `workspace/`·`factors/`·`data/`·`formula/validation`·`rule/validation`을 **소비만** 한다. `factors/`·`formula/`·`rule/`·`strategy/` 어디에도 `api` import가 없어야 한다(기존 INV-1과 동형).
- 프론트엔드(`web/`)는 저장소 루트에 Python 패키지 트리와 분리 배치.
- 근거: `← PRD 제약(subprocess 금지, 기존 계층 재사용) / CLAUDE.md INV-1`

### 4.2 백테스트 파사드 결함 수정

**TR-GUI-002 — `BacktestReport.results` additive 필드**
- `workspace/backtest.py::BacktestReport`(frozen dataclass)에 `results: dict[str, QuantBacktestResult] = field(default_factory=dict)`를 추가한다. `run_backtest()`가 `run_single_symbol_backtest()`의 전체 반환값을 `results`에 채운다(계산 로직 무변경).
- 기존 소비자(`__main__.py`, `test_backtest.py`, `test_templates.py`)는 `.metrics`/`.per_symbol`만 사용하므로 회귀 없음.
- **구현 완료**(M0): `src/quant_krx/workspace/backtest.py`, 신규 테스트 `tests/unit/workspace/test_backtest.py::test_service_backtest_exposes_full_results_per_symbol`.
- 근거: `← PRD §백테스트 AC2-4`

**TR-GUI-003 — `prepare_backtest_data()` 공유 오케스트레이션**
- `workspace/data_loading.py`에 `prepare_backtest_data(db, defn, symbols, *, data_source, start, end, benchmark, resolve_rule, resolve_formula, on_benchmark_warning) -> tuple[dict[str, FactorInput], pd.DataFrame | None]`을 추가한다. 데이터소스 어댑터 선택 → 필요 시 펀더멘털 증분 수집 → `FactorInput` 조립 → 벤치마크 수집을 단일 경로로 수행한다.
- CLI(`strategy_backtest_cmd`)와 API(`routers/backtests.py`)가 **동일 함수**를 호출한다(drift 방지).
- **구현 완료**(M0): `src/quant_krx/workspace/data_loading.py`, `src/quant_krx/__main__.py` 리팩터링, 기존 `strategy-backtest` CLI 통합 테스트 회귀 통과 + 수동 스모크 확인.
- 근거: `← Decision Driver #2`

### 4.3 API 배선

**TR-GUI-004 — 팩터 조회 라우팅**
- `GET /api/factors`(→ `list_factors(category)`), `GET /api/factors/{id}`(→ `get_factor(id, **params)`). 생성/수정/삭제 엔드포인트를 두지 않는다(PRD Non-Goals).
- 근거: `← PRD §팩터조회`

**TR-GUI-005 — Formula/Rule/Strategy CRUD 라우팅**
- `WorkspaceService`의 `upsert_*`/`get_*`/`list_*`/`delete_*`를 1:1 REST로 매핑한다(§4.5 API 계약 참조). 신규 CRUD 로직을 두지 않는다.
- 근거: `← PRD §CRUD AC1`

**TR-GUI-006 — 저장 전 검증(validate) 라우팅**
- `WorkspaceService`에는 `validate_formula`/`validate_rule` 메서드가 없다(`validate_strategy`만 존재, `service.py:134`). `/api/formulas/validate`·`/api/rules/validate`는 `formula/validation.py::validate_formula`·`rule/validation.py::validate_rule` **순수 함수를 직접** `resolve_formula=svc.get_formula`로 호출한다(신규 검증 로직 아님, 기존 순수 함수 재사용 — `WorkspaceService.validate_strategy`가 내부적으로 이미 호출하는 것과 동일 함수).
- `ValidationResult`는 `(ok: bool, errors: tuple[str, ...])`만 제공하며 경고(warnings) 채널이 없다 — "오류/경고 실시간 표시"는 "오류 표시"로 범위를 좁힌다(코드베이스에 경고 개념 부재).
- 근거: `← PRD §CRUD AC2`

**TR-GUI-007 — 활성화/비활성화 라우팅**
- `POST /api/strategies/{id}/activate`, `/deactivate` → `activate`/`deactivate`. `GET /api/strategies/active` → `list_active()`.
- 근거: `← PRD §CRUD AC3`

**TR-GUI-008 — 템플릿 라우팅**
- `GET /api/templates`, `POST /api/templates/from/{template_id}` → `list_templates`/`create_from_template`.
- 근거: `← PRD §CRUD AC4`

**TR-GUI-009 — Import/Export 라우팅**
- `GET /api/strategies/{id}/export` → `export_strategy(id)`. `POST /api/strategies/import` → `import_strategy(bundle, on_conflict)`.
- 근거: `← PRD §CRUD AC5`

**TR-GUI-010 — 백테스트 라우팅 + 직렬화 계약**
- `POST /api/backtests`: `prepare_backtest_data()`(TR-GUI-003) → `svc.backtest()` → `report.results[symbol]`의 `trades`(`pd.DataFrame`, vectorbt `records_readable`)/`equity_curve`(`pd.Series`, Timestamp 인덱스)를 JSON으로 직렬화한다(NaN→`null`). 스키마는 DESIGN-R01 §5에서 확정(이 GUI가 최초 소비자이므로 자유 정의).
- 핸들러는 **동기 `def`**로 선언한다(FastAPI 스레드풀 실행, pykrx 수집이 수 분 걸릴 수 있어 event loop 블로킹 방지).
- 근거: `← PRD §백테스트 AC1-4 / Decision Driver #1`

**TR-GUI-011 — 오류 계약**
- `api/errors.py`에서 `WorkspaceError`(및 `not_found_hint` 포함 메시지)를 그대로 HTTP 4xx `detail`에 실어 반환한다(메시지 재작성 금지 — CLI와 동일한 한국어 힌트 보존).
- 근거: `← 공통 원칙 7(CLAUDE.md), PRD §CRUD`

### 4.4 동시성·구동 배선

**TR-GUI-012 — 동시성/블로킹/바인딩**
- `Database`(`storage/db.py`)는 스레드 세이프하지 않다 — API는 요청 스코프로 `Database(settings.duckdb_path).connect()`를 열고 응답 후 `close()`한다(FastAPI `Depends`).
- `serve-gui`는 `127.0.0.1`에만 바인딩한다(무인증 전제, `0.0.0.0` 금지).
- `serve-gui`도 다른 CLI 명령과 동일하게 모듈 최상단 `load_dotenv()`(`__main__.py:21`)의 적용을 받는다(pykrx `KRX_ID`/`KRX_PW` 제약, CLAUDE.md).
- 근거: `← PRD 제약(로컬 1인용) / CLAUDE.md PyKrx KRX 로그인 제약`

**TR-GUI-013 — 설정/CLI 구동**
- `config/settings.py`에 `GuiConfig(BaseSettings)`(host="127.0.0.1", port=8765) 추가, `Settings.gui` 필드로 합성(기존 `NotifyConfig` 패턴과 동일).
- `__main__.py`에 `@app.command("serve-gui")` 추가, `fastapi`/`uvicorn` 무거운 import는 함수 내부 lazy import(기존 `strategy-backtest` 관례와 동일).
- 근거: `← 기존 설정 패턴 일관성`

## 5. 비기능 요구사항 (NFR)

| NFR | 요구 | 검증 |
|---|---|---|
| NFR-01 회귀 없음 | 기존 CLI 27개 명령·전체 pytest 스위트가 이번 변경 후에도 통과 | `uv run pytest tests/ -q` |
| NFR-02 오프라인 검증 | API 통합 테스트는 `tmp_path` 격리 DuckDB + `FixtureAdapter`로 네트워크 없이 검증 | CI 오프라인 실행 green |
| NFR-03 로컬 전용 바인딩 | `127.0.0.1` 명시 바인딩, 인증 미구현(전제 위반 없음) | 코드 리뷰 + 통합 테스트 |
| NFR-04 오류 힌트 보존 | HTTP 오류 body에 `not_found_hint` 텍스트가 CLI와 동일하게 포함 | 통합 테스트 1건 |
| NFR-05 동시성 안전 | 동시 요청(백테스트 실행 중 CRUD 쓰기)이 DuckDB 락 충돌로 500을 반환하지 않음 | 통합 테스트 1건 |

## 6. 수용 기준 (PRD AC 승계 + pytest 매핑)

| AC | 요지 | 테스트 |
|---|---|---|
| AC-GUI-01 | 팩터 목록/상세 조회 | `tests/integration/test_api_factors.py` |
| AC-GUI-02 | Formula/Rule/Strategy CRUD 왕복 | `tests/integration/test_api_formulas.py`, `test_api_rules.py`, `test_api_strategies.py` |
| AC-GUI-03 | 저장 전 검증(오류) 실시간 | `test_api_formulas.py::test_validate_*`, `test_api_rules.py::test_validate_*` |
| AC-GUI-04 | 활성화/비활성화 토글 | `test_api_strategies.py::test_activate_deactivate` |
| AC-GUI-05 | 템플릿 생성 | `test_api_templates.py` |
| AC-GUI-06 | Export/Import 왕복 | `test_api_strategies.py::test_export_import_roundtrip` |
| AC-GUI-07 | 백테스트 실행 + 지표/equity_curve/trades 직렬화 | `test_api_backtests.py` |
| AC-GUI-08 | 오류 힌트 보존 | `test_api_*.py::test_not_found_hint_preserved` |
| AC-GUI-09 | 동시성 안전 | `test_api_backtests.py::test_concurrent_backtest_and_crud` |
| AC-GUI-10 | 기존 CLI 회귀 없음 | `uv run pytest tests/ -q` 전체 |

## 7. 리스크·완화

| 리스크 | 완화 |
|---|---|
| 프론트엔드(React) 커버리지 부재 | Vitest로 트리↔JSON 순수 로직 단위 테스트, 수동 스모크 체크리스트로 보완 |
| 장시간 백테스트(pykrx 수집)로 인한 API 블로킹 | 동기 `def` 핸들러(스레드풀 실행), 향후 진짜 비동기 job 큐 필요 시 재설계 |
| DuckDB 동시 쓰기 충돌 | 요청 스코프 커넥션 + 재시도 1회, 통합 테스트로 검증 |
| `run-daily` 등 장시간 작업의 향후 GUI 확장 | 현재 동기 REST 모델은 이 확장에 부적합 — Follow-up으로 명시(§0 ADR) |

## 8. 부록

### 8.1 마일스톤

M0(백엔드 배관, 완료) → M1(본 문서+DESIGN) → M2(백엔드 골격+팩터조회) → M3(CRUD API+최소 프론트) → M4(백테스트 API+시각화) → M5(트리 빌더 고도화) → M6(회귀 마감). 상세는 `.claude/plans/consensus-direct-roadmap-epic-r02-prd-r-kind-moore.md` 참조.

### 8.2 하위(EPIC_R01) 인터페이스 참조표

| 소비 대상 | 시그니처 | 원천 |
|---|---|---|
| `WorkspaceService` | CRUD/validate/activate/backtest/template/export-import 전 메서드 | `workspace/service.py` |
| `validate_formula` | `(formula, resolve_formula) -> ValidationResult` | `formula/validation.py:101` |
| `validate_rule` | `(rule, resolve_formula) -> ValidationResult` | `rule/validation.py:97` |
| `list_factors`/`get_factor` | 팩터 카탈로그 조회 | `factors/registry.py` |
| `BacktestReport` | `metrics, per_symbol, results(신규), benchmark, benchmark_note` | `workspace/backtest.py:24-30` |

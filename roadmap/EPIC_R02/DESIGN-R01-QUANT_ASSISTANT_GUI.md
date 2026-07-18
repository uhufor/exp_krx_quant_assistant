# DESIGN-R01 : Quant Assistant GUI

## 1. 개요

### 1.1 목적

`TRD-R01-QUANT_ASSISTANT_GUI.md`가 확정한 배선 결정을 실제 패키지 구조·타입 시그니처·직렬화 스키마·마일스톤으로 구체화한다.

### 1.2 PRD/TRD와의 관계

`PRD-R01-QUANT_ASSISTANT_GUI.md`(요구사항 원천) → `TRD-R01`(기술 결정/배선, ADR형 옵션 비교) → 본 `DESIGN-R01`(구현 형상: 타입 시그니처·JSON 스키마·알고리즘 없음 명시·ADR). PRD/TRD가 이미 확정한 것(범위, 배선 결정)은 여기서 재논쟁하지 않는다.

### 1.3 자기완결성·오염 가드 선언

본 문서가 참조하는 기존 인터페이스(`WorkspaceService`, `validate_formula`, `validate_rule`, `BacktestReport`)는 EPIC_R01 확정 산출물이며, 본 문서는 이를 **재정의하지 않고 소비만** 한다. 신규 계산/검증 알고리즘은 0건이다(§6에서 명시적으로 확인).

### 1.4 결정론 범위 선결 고지

API 계층은 결정론 요구가 없다(GUI 응답은 사용자 조작에 반응하는 상호작용형이므로 EPIC_R01의 "2회 실행 동일" 결정론 계약 대상이 아니다). 단, 백테스트 응답 직렬화는 **동일 `BacktestReport` 입력 → 동일 JSON 출력**을 보장한다(순수 변환).

## 2. 모듈 구조 및 의존 방향

### 2.1 패키지 트리

```
src/quant_krx/
├── api/                          # 신규 — FastAPI 백엔드
│   ├── __init__.py
│   ├── app.py                    # create_app(settings) -> FastAPI
│   ├── deps.py                   # 요청 스코프 Database/WorkspaceService
│   ├── errors.py                 # WorkspaceError -> HTTP 매핑
│   ├── schemas/
│   │   ├── factor.py
│   │   ├── formula.py
│   │   ├── rule.py
│   │   ├── strategy.py
│   │   └── backtest.py           # equity_curve/trades 직렬화
│   └── routers/
│       ├── factors.py
│       ├── formulas.py
│       ├── rules.py
│       ├── strategies.py
│       ├── templates.py
│       └── backtests.py
├── workspace/
│   ├── backtest.py                # (수정) BacktestReport.results 추가
│   └── data_loading.py            # (수정) prepare_backtest_data() 추가
├── config/settings.py             # (수정) GuiConfig 추가
└── __main__.py                    # (수정) serve-gui 명령 추가

web/                                # 신규 — 저장소 루트, Python 패키지 트리와 분리
├── package.json
├── vite.config.ts
├── src/
│   ├── main.tsx
│   ├── api/client.ts              # 백엔드 REST 클라이언트
│   ├── pages/
│   │   ├── FactorsPage.tsx
│   │   ├── FormulaBuilderPage.tsx
│   │   ├── RuleBuilderPage.tsx
│   │   ├── StrategyBuilderPage.tsx
│   │   └── BacktestPage.tsx
│   ├── components/
│   │   ├── tree/                  # Formula/Rule 재귀 트리 편집 컴포넌트
│   │   └── charts/                # equity curve 등
│   └── tree.ts                    # 트리 ↔ JSON 순수 변환 로직(Vitest 대상)
└── dist/                          # 빌드 산출물(프로덕션 시 FastAPI StaticFiles로 서빙)
```

### 2.2 의존 방향과 소비 원칙(INV-1 동형 적용)

- `api/`는 `workspace/`·`factors/`·`formula/validation`·`rule/validation`·`config/`·`storage/`를 **소비만** 한다.
- `factors/`·`formula/`·`rule/`·`strategy/`(정의 코어)는 `api`를 import하지 않는다 — 기존 순수성 AST 스캔(`tests/unit/factors/test_purity_ast.py`)이 이번 변경으로 영향받지 않음(신규 스캔 불필요, 기존 스캔이 이미 `api/`를 커버 범위 밖 신규 계층으로 무시).
- `web/`은 별도 언어 런타임(TypeScript/Node)이므로 Python import 그래프 밖이다. HTTP 계약(`api/schemas/`)이 유일한 결합점.

## 3. 도메인 타입 시그니처

### 3.1 `api/deps.py` — 요청 스코프 의존성

```python
def get_db(settings: Settings = Depends(get_settings)) -> Iterator[Database]:
    db = Database(settings.duckdb_path)
    db.connect()
    try:
        yield db
    finally:
        db.close()

def get_workspace_service(db: Database = Depends(get_db)) -> WorkspaceService:
    return WorkspaceService(db)
```
- 요청마다 `Database` 신규 생성·해제(TR-GUI-012 동시성 배선). 테스트에서는 `app.dependency_overrides[get_db]`로 `tmp_path` 격리 DB를 주입.

### 3.2 `api/app.py` — 앱 팩토리

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="quant-krx GUI API")
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:*"], ...)
    app.include_router(factors.router, prefix="/api/factors")
    app.include_router(formulas.router, prefix="/api/formulas")
    app.include_router(rules.router, prefix="/api/rules")
    app.include_router(strategies.router, prefix="/api/strategies")
    app.include_router(templates.router, prefix="/api/templates")
    app.include_router(backtests.router, prefix="/api/backtests")
    app.add_exception_handler(WorkspaceError, workspace_error_handler)  # TR-GUI-011
    return app
```

### 3.3 `api/errors.py` — 오류 매핑 (TR-GUI-011)

```python
def workspace_error_handler(request: Request, exc: WorkspaceError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})  # not_found_hint 문자열 그대로 보존

def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})
```
- `WorkspaceError` 메시지(활성 참조 차단·`not_found_hint` 포함)를 재작성하지 않고 그대로 `detail`에 싣는다.

### 3.4 `api/routers/formulas.py` — 대표 라우터 시그니처 (TR-GUI-005/006)

```python
@router.get("", response_model=list[FormulaOut])
def list_formulas(svc: WorkspaceService = Depends(get_workspace_service)) -> list[FormulaOut]: ...

@router.get("/{formula_id}", response_model=FormulaOut)
def get_formula(formula_id: str, svc=Depends(get_workspace_service)) -> FormulaOut: ...

@router.put("/{formula_id}", response_model=FormulaOut, status_code=200)
def upsert_formula(formula_id: str, body: FormulaIn, svc=Depends(get_workspace_service)) -> FormulaOut:
    formula = Formula.from_dict({**body.model_dump(), "id": formula_id})
    svc.upsert_formula(formula, now=datetime.now())
    return FormulaOut.from_domain(formula)

@router.post("/validate", response_model=ValidationResultOut)
def validate_formula_draft(body: FormulaIn, svc=Depends(get_workspace_service)) -> ValidationResultOut:
    formula = Formula.from_dict({**body.model_dump(), "id": body.id or "__draft__"})
    result = validate_formula(formula, resolve_formula=svc.get_formula)  # 순수 함수 직접 재사용(TR-GUI-006)
    return ValidationResultOut(ok=result.ok, errors=list(result.errors))

@router.delete("/{formula_id}", status_code=204)
def delete_formula(formula_id: str, svc=Depends(get_workspace_service)) -> None:
    svc.delete_formula(formula_id)  # 활성 참조 시 WorkspaceError -> 409(errors.py)
```
- `rules.py`/`strategies.py`는 동일 패턴(각각 `validate_rule`/`svc.validate_strategy` 소비). `strategies.py`는 추가로 `activate`/`deactivate`/`export_strategy`/`import_strategy`/템플릿 라우트를 포함한다(TR-GUI-007/008/009).

### 3.5 `api/routers/backtests.py` — 백테스트 (TR-GUI-002/003/010)

```python
@router.post("", response_model=BacktestReportOut)
def run_backtest_endpoint(body: BacktestRequest, db=Depends(get_db), svc=Depends(get_workspace_service)) -> BacktestReportOut:
    defn = svc.get_strategy(body.strategy_id)  # 404 처리는 errors.py NotFoundError
    data, benchmark_df = prepare_backtest_data(  # TR-GUI-003, CLI와 동일 함수
        db, defn, body.symbols,
        data_source=body.data_source, start=body.start, end=body.end, benchmark=body.benchmark,
        resolve_rule=svc.get_rule, resolve_formula=svc.get_formula,
        on_benchmark_warning=lambda bm, e: logger.warning(...),
    )
    report = svc.backtest(body.strategy_id, data=data, start=body.start, end=body.end,
                           fees=body.fees, slippage=body.slippage, benchmark=benchmark_df)
    return BacktestReportOut.from_domain(report)  # §5 직렬화 계약
```
- 동기 `def` 핸들러(FastAPI 스레드풀 실행) — event loop 블로킹 방지(TR-GUI-010).

## 4. 데이터 구조 결정 (옵션 비교·ADR 연계)

**결정 D-GUI-1 — `BacktestReportOut` 직렬화 대상**: `BacktestReport.results`(신규 필드, `QuantBacktestResult` per symbol)를 API 응답의 유일한 소스로 삼는다. `report.per_symbol`(메트릭 전용, CLI 표 렌더링용)은 API에서 별도로 다시 계산하지 않고 `results[symbol].metrics`에서 파생한다(중복 계산 회피).

**결정 D-GUI-2 — 다종목 백테스트 응답 형상**: 대표 종목 하나만 최상위에 두는 CLI 관례(`report.metrics` = 대표 종목)를 API는 따르지 않는다 — GUI는 `per_symbol`(모든 종목 지표) + `results`(모든 종목 trades/equity_curve)를 **동등하게** 반환한다(CLI의 "대표 종목" 단순화는 rich 표 출력 제약이었을 뿐, API에는 해당 제약이 없음).

## 5. 직렬화 규약 (신규 정의 — 이 GUI가 최초 소비자)

### 5.1 `BacktestReportOut` JSON 스키마

```json
{
  "metrics": { "total_return": 0.0, "mdd": 0.0, "sharpe": 0.0, "sortino": 0.0,
               "win_rate": 0.0, "trade_count": 0, "fees_paid": 0.0, "slippage_cost": 0.0,
               "benchmark_return": null, "excess_return": null, "benchmark_note": "" },
  "per_symbol": { "005930": { "...위와 동일 필드..." } },
  "results": {
    "005930": {
      "equity_curve": [ { "date": "2024-01-02", "value": 1000000.0 } ],
      "trades": [ { "entry_date": "2024-02-01", "exit_date": "2024-03-01",
                     "entry_price": 70000.0, "exit_price": 72000.0, "pnl": 2000.0 } ]
    }
  },
  "benchmark": null,
  "benchmark_note": null
}
```
- `pd.Series`(equity_curve, `DatetimeIndex`) → `[{date: ISO8601, value: float}]` 리스트, 인덱스를 명시적 컬럼으로 변환.
- `pd.DataFrame`(trades, vectorbt `records_readable`) → `to_dict("records")` 후 `NaN`은 `None`(JSON `null`)으로 치환(pydantic 기본 NaN 직렬화가 유효하지 않은 JSON을 낼 수 있으므로 명시적 `df.replace({np.nan: None})` 후 변환).
- `Timestamp`는 `date.isoformat()`(시각 정보 불필요, 일봉 데이터).

### 5.2 DDL 변경 없음

이번 GUI 작업은 DuckDB 스키마를 변경하지 않는다(additive 진화 원칙, 신규 테이블 0건) — `BacktestReport.results`는 순수 인메모리 반환값이며 영속화되지 않는다.

## 6. 알고리즘·검증 설계

**신규 계산/검증 알고리즘 없음.** 본 GUI가 도입하는 모든 로직은 (a) 기존 `WorkspaceService`/`validate_formula`/`validate_rule`/`run_backtest` 호출의 **얇은 배선**, (b) `pandas`↔JSON **순수 변환**(§5) 둘 중 하나다. 팩터/공식/규칙 평가, 백테스트 엔진, 수치 규약은 EPIC_R01이 이미 확정했으며 본 계층은 이를 재구현하지 않는다.

## 7. 영속화/CRUD + 호출자 책임 경계

- **CRUD 자체**: `WorkspaceService`(R02/R03 저장 게이트) 소비만 — API 라우터는 신규 저장 로직을 두지 않는다.
- **API가 추가하는 것**: HTTP 요청/응답 변환(pydantic 스키마), 오류 코드 매핑(§3.3), 백테스트 데이터 조립 오케스트레이션 호출(`prepare_backtest_data`).
- **API가 추가하지 않는 것**: 검증 규칙, 활성 참조 보호 판정(파사드 책임 그대로), 백테스트 엔진 로직.

## 8. 마일스톤 (M0..M6)

| 마일스톤 | 내용 | 상태 |
|---|---|---|
| M0 | `BacktestReport.results` additive 필드, `prepare_backtest_data()` 추출, CLI 리팩터링 | **완료** |
| M1 | 본 TRD-R01/DESIGN-R01 작성 | **완료** |
| M2 | `fastapi`/`uvicorn` 의존성, `api/app.py`/`deps.py`, `GuiConfig`, `serve-gui`, `GET /api/factors*` | **완료** |
| M3 | Formula/Rule/Strategy CRUD API 전체 + React 스캐폴드(JSON textarea) | **완료** |
| M4 | `POST /api/backtests` + 직렬화 + 프론트 결과 시각화 | **완료** |
| M5 | 트리 빌더 UI 고도화(Formula→Rule), Vitest 단위 테스트 | **완료** |
| M6 | 회귀 테스트 마감(`uv run pytest tests/ -q`, ruff, CLI 스모크) | **완료** |

## 9. 문서화 체크리스트

- [x] PRD-R01 작성 및 승인(deep-interview, 모호성 15.75%)
- [x] TRD-R01 작성(본 세트)
- [x] DESIGN-R01 작성(본 세트)
- [x] README.md 사용법 섹션에 `serve-gui` 명령 및 로드맵 v1.6 추가
- [x] M6에서 AC-GUI-01~10 전체 테스트 매핑 최종 확인(백엔드 pytest 30건 신규 + 프론트 Vitest 6건)

### 알려진 범위 조정
- Strategy는 트리 구조가 아닌 참조형 정의(rule id 목록)이므로 M5 트리 빌더 대상에서 제외하고
  JSON 폼(`ResourceCrudPage`)을 유지한다(PRD의 "JSON 직접 입력 없이 생성 가능"은 Formula/Rule의
  중첩 표현식에 대한 요구였으며, Strategy는 필드가 평평해 JSON 폼만으로도 동등하게 충족됨).
- 프론트엔드 테스트는 순수 로직(트리 기본값 생성·타입 판별)만 Vitest로 커버하고, React 컴포넌트
  렌더링 테스트·E2E(Playwright)는 범위 밖(ADR-GUI-03 결정 유지). 백엔드 계약은 통합 테스트로,
  프론트-백엔드 연동은 실제 서버 기동 후 curl 기반 수동 스모크로 검증했다.

## 10. ADR

### ADR-GUI-01 — `BacktestReport`에 `results` additive 필드로 trades/equity_curve 노출
- **Decision**: `BacktestReport`에 `results: dict[str, QuantBacktestResult] = field(default_factory=dict)` 추가.
- **Drivers**: PRD AC(equity curve/거래내역 필수), 파사드=로직 원칙 유지, 회귀 0.
- **Alternatives**: API가 `run_single_symbol_backtest` 직접 호출(파사드 우회, 게이트 복제 위험으로 기각).
- **Why chosen**: 이미 계산되지만 버려지던 값을 반환 경로에 추가할 뿐 — 계산 로직 변경 없이 유일하게 파사드 원칙과 회귀 없음을 동시 만족.
- **Consequences**: `BacktestReport` 메모리 사용량 소폭 증가(1인용 로컬이라 무시 가능). 완료(M0).

### ADR-GUI-02 — 데이터 로딩 오케스트레이션을 `workspace/data_loading.py`로 추출
- **Decision**: `prepare_backtest_data()` 신설, CLI/API 공유.
- **Drivers**: drift 방지(CLI와 API가 각자 어댑터 선택·펀더멘털 수집을 재구현하면 서서히 어긋남).
- **Alternatives**: API가 CLI 로직을 복제(기각 — 유지보수 시 두 곳 동시 수정 필요).
- **Why chosen**: 단일 진실 원천, 기존 `strategy-backtest` CLI 테스트로 회귀 검증 가능.
- **Consequences**: `__main__.py::strategy_backtest_cmd` 리팩터링(동작 불변, 완료·검증됨).

### ADR-GUI-03 — 프론트엔드는 FastAPI + React/Vite SPA
- **Decision**: `web/`에 React/Vite SPA, 백엔드는 `StaticFiles`로 프로덕션 빌드 서빙.
- **Drivers**: 사용자 명시적 선택(트리 에디터/차트 생태계 우선).
- **Alternatives**: NiceGUI(순수 Python, 더 나은 pytest 커버리지 여지), HTMX(경량, 트리 상호작용 구현 부담).
- **Why chosen**: 사용자 확정. 잔여 리스크(프론트 테스트 공백)는 Vitest 단위 테스트로 부분 완화(M5).
- **Consequences**: 저장소 최초 Node.js 빌드체인 도입. 전체 E2E 커버리지 없음(수동 스모크로 대체).

### ADR-GUI-04 — 저장 전 검증은 순수 검증기 직접 재사용
- **Decision**: `/api/formulas/validate`·`/api/rules/validate`가 `validate_formula`/`validate_rule`을 직접 호출.
- **Drivers**: `WorkspaceService`에 대응 메서드가 없음(오직 `validate_strategy`만 존재), 신규 검증 로직 금지 원칙.
- **Alternatives**: `WorkspaceService`에 `validate_formula`/`validate_rule` 메서드 추가(파사드 확장 — 검토했으나 API가 이미 리졸버를 보유하므로 불필요한 간접 계층으로 판단, 기각).
- **Why chosen**: 순수 함수를 직접 재사용하는 것이 가장 얇은 경로이며, `WorkspaceService.validate_strategy`가 내부적으로 이미 동일 패턴(순수 함수 직접 호출)을 사용 중이라 일관성 있음.
- **Consequences**: API 라우터가 `workspace/service.py` 외에 `formula/validation.py`·`rule/validation.py`도 직접 import(§2.2 소비 원칙 범위 내, 위반 아님).

## 11. 픽스처 및 테스트 매핑

### 11.1 재사용 픽스처
- `tests/fixtures/sample_ohlcv.csv` — 백테스트 API 통합 테스트(`data_source=fixture` 고정, 결정론 유지).
- `tmp_db`/`test_settings` 패턴(`tests/integration/test_daily_job.py:16-35`) — API 통합 테스트의 격리 DB 기반.

### 11.2 AC → 테스트 모듈 매핑

| AC | 테스트 모듈 |
|---|---|
| AC-GUI-01~09 | `tests/integration/test_api_factors.py`, `test_api_formulas.py`, `test_api_rules.py`, `test_api_strategies.py`, `test_api_templates.py`, `test_api_backtests.py` |
| AC-GUI-10 | 기존 `tests/` 전체(회귀), 특히 `tests/unit/workspace/test_backtest.py`, `tests/integration/`의 `strategy-backtest` 관련 테스트 |

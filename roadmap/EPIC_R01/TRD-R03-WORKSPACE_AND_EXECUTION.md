# TRD-R03 : Workspace & Execution

**대응 PRD**: `PRD-R03-WORKSPACE_AND_EXECUTION.md`
**계층**: R03 (최상위, impure — 전 계층 소비·오케스트레이션) / **의존**: R02(정의·영속·검증), R01(팩터 계산·펀더멘털 데이터)
**Status**: Draft for review
**전제**: 본 문서는 main 브랜치 시점에서 No-Code Strategy Workspace의 실행·오케스트레이션 계층을 **처음 구현한다**고 가정한다. 모든 서술은 PRD-R03 + `README.md`(§4 D1~D5 · §5 공통 불변 원칙 7) + 하위 계층 확정 인터페이스(`DESIGN-R01 §3` · `DESIGN-R02 §3`) 역추적으로만 정당화한다. 이 네 원천 밖의 문서·산출물을 설계 근거로 두지 않는다.

> **문서 규약(§D no-restate)**: PRD-R03이 이미 TR급으로 확정한 항목(FR-08 수치 규약 6종 전문, Built-in Template 5종 정의 표 §8, CLI 명령 확정 목록 §10, Import 충돌 3분기 §9)은 본 문서 §4 TR에서 반복 서술하지 않고 §3 추적성 매트릭스 1행으로 축약한다(`FR-xx ← TR-R03-yy (PRD 확정 인용)`). §4 TR은 **PRD에 없는 기술 결정**(하위 인터페이스 소비 배선, Daily 삽입 지점, 캐시 구현 방식, 실패 격리 배선, 오류 모델, AC→pytest 매핑, NFR)만 담는다.
>
> **인터페이스 인용 규약(§D-2)**: R03가 소비하는 하위 시그니처(`FactorInput`·`compute_factor`·`get_factor`·`get_factor_notes`·`FundamentalProvider` = `DESIGN-R01 §3`; `validate_formula`·`validate_rule`·`validate_definition`·`is_runnable`·`derive_required_data`·`from_dict`/`to_dict`·`ValidationResult`·리졸버 계약 = `DESIGN-R02 §3`)의 확정 원천은 각 하위 DESIGN §3이며, 본 문서는 이를 **재정의하지 않고 링크 인용**한다(요약 1줄까지). baseline 재사용 자산은 `TRD-R01 §8.2` 앵커 표 명칭으로만 인용한다.

---

## 0. RALPLAN-DR 요약 (SHORT)

본 절은 **이 TRD 수준에서 새로 내리는 기술 결정**(PRD가 확정하지 않은 배선·구현 선택)에 한정한다. D1~D5·FR-08 수치 규약·Built-in 5종·CLI 목록은 확정 전제이므로 재논쟁하지 않는다(README §4/§5, PRD-R03 정본 인용).

### Principles (원칙 3)

1. **PRD 역추적 유일 정당화**: 모든 TR은 PRD-R03의 FR/AC/INV 또는 README §4(D1~D5)/§5(공통 원칙 7)로 역추적된다. TR은 요구사항을 창작하지 않고 하위 인터페이스 소비 배선·오케스트레이션 결정만 확정한다.
2. **소비만·역주입 금지(계층 단방향)**: R03는 R01/R02·storage·백테스트 엔진을 **소비만** 하며, 평가·실행·storage 의존을 하위 정의 패키지에 역주입하지 않는다(INV-1). 이는 최상위 제약이다.
3. **결정론·오프라인 검증이 완료 판정 축(신호·Report A까지)**: 모든 AC는 합성 Fixture + 격리 DuckDB + LLM mock + pytest로 네트워크·실데이터 없이 2회 동일 검증 가능해야 한다(INV-3). LLM Report B는 mock 주입 시에만 결정론 범위.

### Decision Drivers (상위 3)

1. **단일 실행 경로 보존(INV-2)**: 모든 전략(Built-in Template 포함)이 동일한 평가→시그널→백테스트→Daily 경로를 통과하도록 배선한다. 전략별 특수 분기·이중 디스패치의 재유입을 구조적으로 차단한다(D3 정합).
2. **결정론·데이터 오염 차단**: 평가 캐시 수명·전환 시드 멱등·수치 규약 강제점이 종목 간·실행 간 오염이나 비결정성의 원천이 되지 않도록 배선한다.
3. **하위 계약 무변조 소비**: R01/R02 확정 인터페이스를 재정의·우회 없이 그대로 소비하며, 신규 검증 로직·신규 백테스트 엔진·신규 다운스트림 경로를 만들지 않는다(재사용 강제).

### Viable Options (TRD 수준의 자유 결정, ≥2 + 무효화 근거)

**결정 축 C1 — 활성 참조 보호(FR-04a) 차단 판정 방식**

| 옵션 | 방식 | 장점 | 단점 |
|---|---|---|---|
| **C1-i. 변경 시점 온디맨드 전이 폐포 계산** ✅채택 | Workspace 파사드가 Rule/Formula/Strategy upsert·delete 진입 시 `list_active()` 각 전략의 전이 참조 폐포를 리졸버로 산출해 대상 id 포함 여부를 판정, 포함 시 차단(전략 id 목록 사유) | 상태 무보유(무동기화) → drift 원천 0 / 결정론 / 신규 테이블 불요(additive 최소) | 변경마다 활성 전략 폐포 재계산 비용(단일 종목·소규모 활성 집합에서 무시 가능) |
| C1-ii. 역참조 인덱스 테이블 유지 | 참조 그래프를 별도 테이블에 색인, 변경 시 조회 | 조회 O(1) | 색인 동기화 유지 필요 → drift/불일치 위험 / 신규 DDL·트리거 로직 / 결정론 부담 |

**무효화 근거**: C1-ii는 driver#2(결정론·오염 차단)를 위협 — 역인덱스는 upsert/delete마다 동기화가 필요해 불일치(dangling 색인)의 원천이 된다. C1-i는 store를 유일 진실 원천으로 두고 매 판정을 재계산해 상태 drift를 원천 제거하며, R02 저장 게이트가 이미 노출한 리졸버(`DESIGN-R02 §3.9`)를 그대로 재사용한다.

**결정 축 C2 — 전환 시드(FR-14a) 배치·멱등 지점**

| 옵션 | 방식 | 장점 | 단점 |
|---|---|---|---|
| **C2-i. Daily 부트스트랩 인라인 멱등 시드** ✅채택 | Daily 실행 집합 조회 직전 `seed_builtin_strategies()`를 호출, 각 Template id 존재 검사로 멱등(존재 시 정의·활성 무변경) | 운영 연속성 자동 보장(별도 조작 불요, D3 "끊김 없이") / 1회성·멱등이 한 지점에 국소화 | Daily 경로에 시드 판정 1회 추가(id 존재 검사 5회) |
| C2-ii. 별도 마이그레이션 CLI 1회 실행 | 운영자가 명시적 명령으로 시드 | Daily 경로 무변경 | 운영자 실행 누락 시 활성 0건 실패(연속성 미보장) / FR-14a "자동 시드" 문구 이탈 |

**무효화 근거**: C2-ii는 FR-14a("자동으로 전략 인스턴스화·활성화")와 D3(전환 시 연속성 보장)를 이탈 — 운영자 개입 의존은 활성 0건 실패(FR-14) 위험을 남긴다. C2-i는 시드를 Daily 부트스트랩에 국소화해 멱등·1회성을 보증하되, 기존 id 존재 시 정의·활성 상태를 일절 변경하지 않아(사용자 결정 비덮어쓰기) 재실행 안전성을 확보한다.

**결정 축 C3 — 평가 캐시(팩터 계산·Formula 메모) 수명 구현**

| 옵션 | 방식 | 장점 | 단점 |
|---|---|---|---|
| **C3-i. (전략, 종목) 평가 컨텍스트 소유 dict** ✅채택 | 평가 진입 시 생성되는 컨텍스트 객체가 캐시 dict를 소유, 컨텍스트 종료 시 폐기 | 캐시 수명이 단일 (전략, 종목)으로 구조적 한정(FR-07) → 종목·전략·실행 간 공유 불가 | 컨텍스트 경계 밖 재사용 없음(의도된 제약) |
| C3-ii. 모듈 수준 LRU/전역 dict | 프로세스 수명 캐시 | 재실행 히트율 높음 | 종목·전략·실행 간 공유 → 데이터 오염(FR-07 금지) / 결정론·격리 붕괴 |

**무효화 근거**: C3-ii는 FR-07("캐시 수명은 단일 (전략, 종목) 평가 컨텍스트로 한정 — 공유 금지")를 정면 위반하고 driver#2를 무너뜨린다. C3-i는 캐시 소유권을 컨텍스트 객체에 두어 GC 경계와 수명 경계를 일치시킨다(캐시 키는 `(factor_id, canonical(params))` — DESIGN-R03 §알고리즘에서 구체화).

### ADR 요약 (본 TRD 수준의 배선 결정 — DESIGN-R03 ADR과 별개)

- **Decision**: 활성 참조 보호는 상태 무보유 온디맨드 전이 폐포 판정(C1-i), 전환 시드는 Daily 부트스트랩 인라인 멱등(C2-i), 평가 캐시는 (전략, 종목) 컨텍스트 소유(C3-i)로 배선한다.
- **Drivers**: 단일 실행 경로 / 결정론·오염 차단 / 하위 계약 무변조 소비.
- **Consequences**: 신규 상태 테이블 없이 R02 리졸버·저장 게이트를 재사용하며(C1), Daily 전략 원천이 활성 선언형 단일로 수렴하고(C2/D3), 캐시가 컨텍스트 경계로 격리된다(C3).
- **Follow-ups**: 캐시 키 canonical화·수치 규약 강제점 모듈 형상·백테스트 어댑터 시그니처는 `DESIGN-R03 §3/§6`에서 확정.

---

## 1. 목적

정의 코어(R01/R02) 위에 얹는 **impure 상위 계층**의 기술 요구사항을 확정한다. 구체적으로:

- 오케스트레이션 파사드(`WorkspaceService`)가 하위 CRUD·검증·평가·백테스트·Template·Import/Export를 **어떻게 조합·배선**하는지 확정한다(로직은 파사드, I/O는 CLI).
- 선언형 평가 엔진(Formula compute·Rule 평가)이 R01 `compute_factor`/`get_factor`·R02 `from_dict`·리졸버를 소비하는 배선과, 수치 규약(FR-08)의 **단일 강제점** 배치를 확정한다.
- 백테스트가 baseline `Portfolio.from_signals`·`BacktestMetrics`를 재사용하는 연결 지점과 시그널 사상 배선을 확정한다.
- Daily 파이프라인에서 코드형 전략 선택 기전을 제거하고 활성 선언형 전략 단일 원천으로 수렴시키는 **삽입 지점**과 전환 시드·universe 해석·부가 데이터 자동 수집·실패 격리 배선을 확정한다.
- 모든 요구사항을 합성 Fixture + 격리 DuckDB + LLM mock + pytest 결정론 검증으로 매핑한다.

본 문서는 하위 시그니처·수치 규약·Built-in 정의·CLI 목록을 **재정의하지 않는다**(PRD/하위 DESIGN 확정 원천). 그것들의 **소비·조합·강제·오케스트레이션 방식**만 확정한다.

## 2. 범위 (In / Out)

### In

- `WorkspaceService` 파사드의 하위 계층 소비·조합 배선(storage 주입, CRUD·검증·평가·백테스트·Template·Import/Export).
- 전이 검증(R02 검증기 조합, 신규 로직 0)·활성화 영속(`strategy_activation`)·활성 참조 보호 게이트(FR-04a, Workspace 책임)의 배선.
- 평가 엔진(evaluate_formula·evaluate_rule) 배선, 파라미터 해석(get_factor 오버라이드), 캐시 수명 한정, 수치 규약 단일 강제점, 데이터 계약(required_data 전이 합집합 파생·미충족 실패).
- 백테스트 어댑터(시그널 사상·baseline 엔진 재사용·지표 재사용)·백테스트 CLI.
- Daily 통합(실행 집합·`settings.strategy.enabled` 제거·전환 시드·universe 해석·부가 데이터 자동 수집·실패 격리·다운스트림 동형).
- Built-in Template 5종 번들·`create_from_template`·사용자 Template(`strategy_templates`)·Import/Export.
- CLI 명령 표면·README 동기화 규약·오류 모델·계층 순수성 INV-1~4.

### Out (확정)

- 팩터 계산·펀더멘털 저장/수집 계약 자체 (→ R01). 본 계층은 소비·오케스트레이션만.
- Formula/Rule/Strategy 정의·직렬화·저장 게이트·검증기 구현 자체 (→ R02). 본 계층은 조합·소비만.
- GUI·웹 프론트엔드 / Portfolio·리밸런싱 집행 / 실시간·주문 집행 / AI 생성·최적화 / 신규 백테스트 지표·리스크 모델(§8 최소 지표 집합만) / 정규화·순위 함수(PRD-R03 §3 Out 유지).
- 신규 백테스트 엔진·신규 지표 산식·신규 다운스트림(신호·리포트·알림) 경로 — 전부 baseline 재사용(FR-11/12/18).

## 3. PRD 추적성 매트릭스 (공백 0)

> **판독 규약**: "TR" 열은 §4의 기술 결정을 가리킨다. **(PRD 확정 인용)** 표시 행은 PRD-R03이 이미 TR급으로 확정한 항목으로, §4에서 반복하지 않고 본 매트릭스로 축약한다(하위 시그니처 원천 = DESIGN-R01/R02 §3). 나머지 행은 §4가 PRD에 없는 기술 결정을 추가한다.

### 3.1 Functional Requirements (FR-01~FR-23)

| FR | 요지 | TR | 근거 |
|---|---|---|---|
| FR-01 | `WorkspaceService` 파사드 — storage 주입, CRUD·검증·평가·백테스트·Template·Import/Export 조합, CLI 얇은 래핑 | TR-R03-002 | PRD §4 |
| FR-02 | `validate_strategy` 전이 검증 — R02 검증기 조합, 신규 로직 0, `is_runnable` 소비 | TR-R03-003 | PRD §4 |
| FR-03 | 활성화 영속(`strategy_activation` PK/active/updated_at), activate/deactivate/is_active/list_active, idempotent | TR-R03-004 | PRD §4 |
| FR-04 | 활성화 전제(존재 + `is_runnable` + 전이 검증 통과), 초안·검증 실패 거부 | TR-R03-005 | PRD §4, D4 |
| FR-04a | 활성 전략 자신 + 전이 참조 Rule/Formula 수정·삭제 거부(차단 사유 전략 id 목록) | TR-R03-006 | PRD §4 |
| FR-05 | `evaluate_formula(formula, data, resolve_formula) -> Series` 재귀·formula_id 메모이제이션 | TR-R03-007 | PRD §5.1 |
| FR-06 | `evaluate_rule(rule, data, resolve_formula) -> Series(bool)` Predicate/Composition, Factor→레지스트리·Formula→evaluate_formula 라우팅 | TR-R03-008 | PRD §5.2 |
| FR-07 | 파라미터 해석(`get_factor(id, **params)` 오버라이드 인스턴스) + 캐시 키 `(factor_id, canonical(params))` + 캐시 수명 (전략,종목) 한정 | TR-R03-009 | PRD §5.3, D1 |
| FR-08 | 수치 규약 6종(reindex 무보간·NaN→False·div0→NaN·교차 shift·스칼라 브로드캐스트·2회 동일) | TR-R03-010 (PRD 확정 인용) | PRD §5.4 |
| FR-09 | 데이터 계약 — required_data 전이 합집합 파생, 미충족 `EvaluationError`(누락 종류+id) | TR-R03-011 | PRD §5.5 |
| FR-10 | 시그널 사상 — entry AND 결합→entries, exit AND→exits, exit 부재→all False, close 정렬+NaN→False 불리언 | TR-R03-012 | PRD §6 |
| FR-11 | 백테스트 계약 — baseline `Portfolio.from_signals`(long-only·전량·`freq="D"`) 투입, 신규 엔진 0, 엔진 기본 의미론 | TR-R03-012 (PRD 확정 인용) | PRD §6 |
| FR-12 | 최소 지표 집합(총수익률·CAGR·MDD·Sharpe·승률·거래횟수·총비용·초과수익률), 산식 원천 = `BacktestMetrics` 재사용 | TR-R03-012 (PRD 확정 인용) | PRD §6 |
| FR-13 | `strategy-backtest <id>` CLI(universe·기간·비용·데이터소스 옵션, runnable 아님→실행 전 거부) | TR-R03-013 | PRD §6 |
| FR-14 | Daily 실행 집합 = `list_active()`(id 정렬), 활성 0건 명확 실패, `settings.strategy.enabled` 제거 | TR-R03-014 | PRD §7, D3 |
| FR-14a | 전환 시드 — Built-in 5종 자동 인스턴스화·활성화, 멱등·1회성(기존 id 무변경) | TR-R03-015 (PRD 확정 인용) | PRD §7, D3 |
| FR-15 | universe 해석 — 실행 대상=`universe.symbols`(빈=watchlist), 수집 대상=watchlist ∪ 활성 universe 합집합 | TR-R03-016 | PRD §7, D5 |
| FR-16 | 부가 데이터 자동 수집 — required_data 합집합 따라 펀더멘털 선행 수집·저장·공급, R01 `FundamentalProvider`·upsert·`fetch-fundamental` 동일 경로 | TR-R03-017 | PRD §7 |
| FR-17 | 실패 격리 — 전략×종목 단위 오류 기록·나머지 완주, run 이벤트 로깅 관례 | TR-R03-018 | PRD §7 |
| FR-18 | 다운스트림 동형 — 백테스트→신호 분류→Report A/B→알림 기존 경로 통과, content-hash outbox 재사용 | TR-R03-019 (PRD 확정 인용) | PRD §7 |
| FR-19 | Built-in Template 5종(코드 상수 번들, D1·D2 표현, 즉시 runnable) | TR-R03-020 (PRD 확정 인용) | PRD §8, D1/D2 |
| FR-20 | `create_from_template(template_id, new_id)` 복제 저장(참조 Rule 함께 upsert), 저장 게이트·검증 통과·즉시 runnable | TR-R03-020 | PRD §8 |
| FR-21 | `save_as_template` (`strategy_templates`), Built-in id 충돌 거부, builtin/user 출처 구분 통합 열거, CRUD | TR-R03-021 | PRD §8 |
| FR-22 | `export_strategy(id)` → 전이 참조 Rule·Formula 포함 결정론 JSON 번들(키 정렬·스키마 버전) | TR-R03-022 | PRD §9 |
| FR-23 | `import_strategy(bundle, on_conflict)` 위상 순서(Formula→Rule→Strategy), 충돌 3분기(동일 멱등/상이 거부/`--overwrite`), FR-04a 우선 | TR-R03-022 (PRD 확정 인용) | PRD §9 |

### 3.2 CLI 표면 (PRD §10)

| PRD 항목 | 요지 | TR | 근거 |
|---|---|---|---|
| §10 | `strategy-*`/`rule-*`/`formula-*` 명령 확정 목록 + 전체 JSON 교체 편집 의미론 + README 동기화 | TR-R03-023 (PRD 확정 인용) | PRD §10 |

### 3.3 Acceptance Criteria (AC-01~AC-09)

| AC | 요지 | §6 승계 | TR |
|---|---|---|---|
| AC-01 | 파사드/CLI 전 명령 왕복(생성→조회→수정→삭제 DB 재조회 일치), 오류 non-zero | AC-R03-01 | TR-R03-002, TR-R03-023 |
| AC-02 | 활성화 idempotent·재조회 보존·초안/검증실패/미존재 거부·활성 참조 수정·삭제 거부(전략 id 포함·비활성화 후 허용) | AC-R03-02 | TR-R03-004, TR-R03-005, TR-R03-006 |
| AC-03 | 평가 — Formula 다단 DAG 위상·Rule 비교/AND/OR/NOT/교차·params 오버라이드(sma5≠sma20+골든크로스)·NaN→False·div0→NaN·스칼라 교차·2회 동일 | AC-R03-03 | TR-R03-007, TR-R03-008, TR-R03-009, TR-R03-010 |
| AC-04 | 데이터 계약 — required_data 미충족 `EvaluationError`(누락 종류+id), ohlcv-only 집합 부가 로딩 0 | AC-R03-04 | TR-R03-011, TR-R03-017 |
| AC-05 | 백테스트 — fixture 최소 지표 산출·CLI 표시·runnable 아님 실행 전 거부 | AC-R03-05 | TR-R03-012, TR-R03-013 |
| AC-06 | Daily — 활성 집합 id 정렬·universe 해석(부분 종목+수집 합집합)·전략×종목 실패 격리 완주·활성 0건 실패·펀더멘털 자동 수집·전환 시드 멱등·신호→리포트→알림 통과 | AC-R03-06 | TR-R03-014~019 |
| AC-07 | Template — Built-in 5종 즉시 검증 통과+fixture 백테스트 완주·생성물 runnable·사용자 Template 저장→재생성 동등 | AC-R03-07 | TR-R03-020, TR-R03-021 |
| AC-08 | Import/Export — 왕복 동일 복원·위상 순서 저장·dangling/순환 거부·충돌 3분기 | AC-R03-08 | TR-R03-022 |
| AC-09 | 순수성·문서 — INV-1 스캔 green·README 동기화·`pytest`/`ruff` 전량 통과 | AC-R03-09 | TR-R03-001, TR-R03-023, TR-R03-026 |

### 3.4 INV / 확정 결정(D1~D5)

| 항목 | 요지 | TR | 근거 |
|---|---|---|---|
| INV-1 (계층 단방향) | workspace는 R01/R02·storage·백테스트 엔진 소비만, 역주입 금지 | TR-R03-001 | PRD §11 |
| INV-2 (단일 실행 경로) | 모든 전략이 동일 평가→시그널→백테스트→Daily, 전략별 특수 분기 금지 | TR-R03-025 | PRD §11 |
| INV-3 (결정론) | 동일 (정의+데이터+주입 시각) → 신호·Report A까지 동일, Report B는 mock 시 결정론 | TR-R03-025 | PRD §11 |
| INV-4 (참조 무결성) | 저장·활성화·Import 시점 차단 + 실행 시점 `EvaluationError` 격리 | TR-R03-006, TR-R03-011, TR-R03-022 | PRD §11 |
| D1 | 파라미터 오버라이드 완전 해석(평가 인스턴스화) | TR-R03-009 | README §4 |
| D2 | 가격은 참조 가능한 팩터(`price.close`) — bollinger_band 템플릿 entry·사용자 전략 동형 노출 | TR-R03-020 | README §4 |
| D3 | 선언형 단일 — 코드형 5종 제거, 전환 시드로 연속성 | TR-R03-014, TR-R03-015 | README §4 |
| D4 | rule 슬롯 roles 단일, runnable=entry≥1(정의 검증) | TR-R03-005 | README §4 |
| D5 | universe 실제 소비(빈=watchlist 전체) | TR-R03-016 | README §4 |
| 공통 원칙 6 | additive 진화(2테이블 추가만) | TR-R03-027 | README §5 |
| 공통 원칙 7 | 오류 한국어+행동 힌트, CLI non-zero | TR-R03-024 | README §5 |

**커버리지**: FR-01~23(FR-04a·FR-14a 포함, 23건) + AC-01~09(9건) + INV-1~4 + D1~D5 전건 매핑 완료. 공백 0.

## 4. 기술 요구사항 (TR-R03-xxx)

> 각 TR은 PRD가 확정하지 않은 기술 결정(하위 인터페이스 소비 배선·오케스트레이션·삽입 지점·오류 모델)만 담는다. 하위 시그니처·수치 규약·Built-in 정의·CLI 목록의 확정 원천은 DESIGN-R01/R02 §3 및 PRD-R03이며 여기서 재정의하지 않는다. 완전한 함수 본문은 두지 않고 시그니처·의사코드·표·서술까지만 확정한다.

### 4.1 모듈 배치 및 계층 순수성

**TR-R03-001 — `workspace/`·`jobs/` 배치와 INV-1 단방향 AST 스캔**
- `workspace/`(파사드·평가 엔진·백테스트 어댑터·Template·Import/Export)와 `jobs/`(Daily 파이프라인 오케스트레이션)를 impure 상위 계층으로 배치한다. 정의 코어(`strategy`/`rule`/`formula`/`factors`)와 storage·백테스트 엔진은 이 계층이 **소비만** 한다.
- INV-1 강제(단방향): (a) R01/R02 순수성 AST 스캔이 **무변경 green**을 유지하고(정의 패키지가 workspace를 import하지 않음), (b) 정의 패키지(`factors`/`formula`/`rule`/`strategy`) 어디에도 `workspace`·`jobs` import가 없음을 별도 스캔으로 강제한다. 역방향(상위→하위 소비)은 허용, 순방향(하위→상위 역주입)은 0건.
- 배선: 평가·실행·백테스트 어댑터·Template·Import/Export 코드는 전부 이 상위 계층 하위에만 존재한다. 하위 계층은 평가·실행 코드를 보유하지 않는다(R01/R02 INV와 정합).
- 근거: `← FR-01 / INV-1 / PRD-R03 §11`

### 4.2 파사드 배선

**TR-R03-002 — `WorkspaceService` 파사드 조합 배선**
- `WorkspaceService`는 storage(`Database`)를 **주입**받아 도메인 CRUD·검증·평가·백테스트·Template·Import/Export를 하나의 사용자 API로 조합한다. 로직은 파사드에, I/O(입력 파싱·표 출력·종료 코드)는 CLI에 둔다(FR-01).
- CRUD 위임 배선: 도메인 CRUD는 R02 저장 게이트(`upsert_*`/`get_*`/`list_*`/`delete_*`, `DESIGN-R02 §7.2`)로 **위임**하며 파사드는 신규 저장 로직을 두지 않는다. 파사드가 추가하는 것은 활성 상태 게이트(TR-R03-006)·전이 검증 조합(TR-R03-003)·평가/백테스트 오케스트레이션뿐이다.
- 검증기 소비: 파사드는 R02 검증기(`validate_definition`/`validate_rule`/`validate_formula`, `DESIGN-R02 §3.4/§3.6/§3.8`)를 리졸버와 함께 조합 호출한다. 저장 게이트가 이미 엄격 검증을 강제하므로(`DESIGN-R02 §7.2`), 파사드의 `validate_strategy`는 **실행 없는 사전 진단**(비발생 검증기 조합, 전 오류 수집) 역할이다.
- 근거: `← FR-01 / FR-02 / PRD-R03 §4`

### 4.3 전이 검증·활성화·활성 참조 보호

**TR-R03-003 — 전이 검증 = R02 검증기 조합(신규 로직 0)**
- `validate_strategy(defn)`는 R02 검증기를 **조합만** 한다: Strategy 구조·rule 슬롯(`validate_definition`) → 참조 Rule 각각(`validate_rule`, factor/formula/params 포함) → 참조 Formula 각각(`validate_formula`, 순환 포함)을 리졸버 주입으로 전이 검증한다. **신규 검증 로직을 만들지 않는다** — 단 하나의 예외도 없다.
- runnable 판정도 R02 `is_runnable`(`DESIGN-R02 §3.8`)을 **소비**한다(자체 판정 금지). dangling 참조는 저장·활성화 전에 거부된다(R02 저장 게이트 + 리졸버).
- 리졸버 소비: 전이 확장은 R02 리졸버 계약(`FormulaResolver`/`RuleResolver`, `DESIGN-R02 §3.9`)을 storage store 기반으로 주입해 수행한다. 파사드는 리졸버를 storage로 감싸 전달할 뿐 검증 알고리즘을 중복 구현하지 않는다.
- 근거: `← FR-02 / INV-1 / PRD-R03 §4`

**TR-R03-004 — 활성화 영속 배선(`strategy_activation`, idempotent)**
- 활성 상태는 `strategy_activation`(`strategy_id` PK, `active`, `updated_at`) 테이블에 영속한다(additive, TR-R03-027). `activate`/`deactivate`/`is_active`/`list_active`(id 오름차순)를 파사드가 제공한다.
- idempotent 배선: 동일 전이 반복은 무효과(재활성=활성 유지, 재비활성=비활성 유지). 미존재 행 = 비활성으로 해석(누락 행 조회 시 False). `updated_at`은 **주입 시각**으로 기록(결정론, INV-3).
- 근거: `← FR-03 / INV-3 / PRD-R03 §4`

**TR-R03-005 — 활성화 전제 조건 게이트(D4)**
- `activate(id)`는 (a) 전략 존재, (b) `is_runnable(defn) == True`(roles + entry≥1, `DESIGN-R02 §3.8`), (c) 전이 검증 통과(TR-R03-003)를 요구한다. 초안(rule=None)·검증 실패 전략의 활성화는 한국어 사유 + non-zero로 거부된다.
- 불변식: **활성화된 전략은 항상 실행 가능**하다(D4). "정의 검증 통과하나 실행 시점 거부"는 R02가 구조적으로 금지하므로, 활성화 게이트는 `is_runnable` 소비만으로 이 불변식을 보증한다.
- 근거: `← FR-04 / D4 / AC-02 / PRD-R03 §4`

**TR-R03-006 — 활성 참조 보호 게이트(FR-04a, Workspace 책임)**
- 활성 전략 자신, 그리고 활성 전략이 **전이적으로 참조**하는 Rule/Formula의 수정(upsert)·삭제는 거부된다 — 해당 전략을 비활성화한 후에만 허용. 거부 메시지에는 차단 사유인 **활성 전략 id 목록**을 포함한다(공통 원칙 7).
- 배선 위치(경계 정합): 저장 계층은 활성 상태를 모르므로(R02 REQ-P4·`DESIGN-R02 §7.3`이 "활성 참조 보호는 R03 위임"으로 명시) 이 게이트는 **Workspace 파사드**의 책임이다. 파사드의 upsert/delete 진입점이 저장 게이트 호출 **전** 활성 참조 보호를 판정한다.
- 판정 방식(C1-i): `list_active()` 각 전략의 전이 참조 폐포(참조 Rule ∪ 참조 Formula, 리졸버로 확장)를 산출해 대상 id 포함 여부를 온디맨드 판정한다. 상태 무보유(색인 테이블 없음) → drift 0.
- Import 우선순위: `--overwrite` Import도 이 게이트를 우선 적용한다(FR-23 "FR-04a가 우선", TR-R03-022).
- 근거: `← FR-04a / INV-4 / AC-02 / PRD-R03 §4`

### 4.4 평가 엔진 배선

**TR-R03-007 — `evaluate_formula` 재귀·메모이제이션 배선**
- `evaluate_formula(formula, data: FactorInput, resolve_formula) -> pd.Series`를 산술 트리 재귀 평가로 배선한다. 리프 — factor 피연산자는 파라미터 적용 인스턴스로 계산(TR-R03-009), 상수는 브로드캐스트(수치 규약 TR-R03-010), formula 참조는 `resolve_formula`로 리졸브 후 **재귀 평가 + `formula_id` 메모이제이션**.
- 입력 계약: `data`는 R01 `FactorInput`(`DESIGN-R01 §3.4`) 형상을 그대로 소비한다(재정의 없음). formula 리프의 재귀는 R02 표현 트리(`Expr`, `DESIGN-R02 §3.3`)를 태그 순회(`.node`/`.kind`)로 평가하며, DAG 비순환은 저장 시점 보장(R02)이나 **방어적 visited 가드**를 유지한다(FR-05).
- 산술 트리 → Series 사상: `BinaryOp`(`+`/`-`/`*`/`/`)·`UnaryOp`(`neg`)를 수치 규약(TR-R03-010) 하에서 원소별 연산한다. div0→NaN 전파는 수치 규약 소관.
- 근거: `← FR-05 / PRD-R03 §5.1`

**TR-R03-008 — `evaluate_rule` Predicate/Composition 라우팅 배선**
- `evaluate_rule(rule, data, resolve_formula) -> pd.Series(bool)`: `Predicate`는 좌/우를 시계열/스칼라로 평가 후 비교(교차 포함), `Composition`은 자식 불리언 시계열의 `AND`(전항 논리곱)/`OR`/`NOT`. R02 Rule 트리(`Node`, `DESIGN-R02 §3.5`)를 태그 순회로 평가한다.
- 피연산자 라우팅: `FactorOperand`는 **팩터 레지스트리 기전**(get_factor→compute_factor, TR-R03-009)으로, `FormulaOperand`는 `evaluate_formula`(TR-R03-007)로 라우팅한다. **Formula를 factor 레지스트리에 병합하지 않는다**(별도 네임스페이스). 사용자에게는 동형 "지표 선택" UX로만 통합 노출(정의·표시 계층 소관, 평가 라우팅은 분리).
- 불리언화 지점: 비교·논리 결과의 NaN→False는 수치 규약(TR-R03-010)에 위임한다(불리언화 직전 단일 지점).
- 근거: `← FR-06 / PRD-R03 §5.2`

**TR-R03-009 — 파라미터 해석 + 캐시 수명 한정(D1, C3-i)**
- `FactorOperand(factor_id, column, params)` 평가는 R01 `get_factor(factor_id, **params)`(`DESIGN-R01 §3.7`)로 **오버라이드 적용 인스턴스**를 생성하고 `compute_factor`(`DESIGN-R01 §3.6`)로 계산한다(빈 params = 기본값). 결측 사유는 `get_factor_notes`(`DESIGN-R01 §3.9`)로 반환 **직후** 판독한다(R01 advisory 계약).
- 캐시 키·수명: 계산 결과 캐시 키 = `(factor_id, canonical(params))` — 동일 팩터·상이 파라미터는 별개 시계열(sma(5)≠sma(20), D1). 캐시(팩터 계산·Formula 메모)의 **수명은 단일 (전략, 종목) 평가 컨텍스트로 한정**(C3-i) — 종목 간·전략 간·실행 간 공유 금지(데이터 오염 차단). 컨텍스트 객체가 캐시 dict를 소유하고 종료 시 폐기한다.
- 근거: `← FR-07 / D1 / AC-03 / PRD-R03 §5.3`

**TR-R03-010 — 수치 규약 단일 강제점 배선(결정론 핵심, PRD 확정 인용)**
- FR-08 수치 규약 6종(공통 인덱스 reindex 정렬만·보간/ffill 금지 / 산술 NaN 전파·불리언화 직전 NaN→False / div0→NaN 무예외 / `crosses_above(l,r)=(l>r)&(l.shift(1)<=r.shift(1))` below 대칭·shift 첫 원소 NaN→False / 스칼라 상수 브로드캐스트 / 2회 동일)의 **규약 전문은 PRD-R03 §5.4가 확정**하므로 본 TR은 재서술하지 않는다.
- 본 TR의 기술 결정: 이 6종을 **단일 강제점(공유 수치 헬퍼)**에 배치해 evaluate_formula·evaluate_rule·백테스트 사상이 모두 동일 함수를 경유하게 한다(규약 drift·우회 차단, DESIGN-R03 §6에서 헬퍼 형상 확정). reindex 기준 인덱스는 대상 종목 close의 `DatetimeIndex`이며, 저빈도→일별 변환은 R01 as-of 정렬(FR-17)이 유일 지점이고 reindex는 정렬만 수행한다(보간 없음).
- 근거: `← FR-08 / INV-3 / AC-03 / PRD-R03 §5.4`

**TR-R03-011 — 데이터 계약(required_data 전이 합집합 파생·미충족 실패)**
- 평가 전에 전략이 전이적으로 참조하는 factor/formula의 `required_data` 합집합(`ohlcv`/`valuation`/`financials`)을 파생하고, `FactorInput`에 해당 프레임이 없으면 **`EvaluationError`로 명확히 실패**한다(누락 데이터 종류 + 요구 id 포함). 조용한 오작동 금지(INV-4).
- 파생 배선: Formula 참조의 required_data 전이 합집합은 R02 `derive_required_data(formula, resolve_formula)`(`DESIGN-R02 §3.4`)를 소비하고, factor 참조는 R01 `FactorMetadata.required_data`(`DESIGN-R01 §3`)를 조회해 합집합한다. 전략 단위 합집합은 factor_refs + rule 전이 factor/formula의 파생을 union한다(신규 파생 로직 없이 하위 계약 조합).
- `EvaluationError` 유형: 누락 프레임 종류(valuation/financials)와 이를 요구한 factor/formula id를 힌트에 포함(공통 원칙 7).
- 근거: `← FR-09 / INV-4 / AC-04 / PRD-R03 §5.5`

### 4.5 백테스트 배선

**TR-R03-012 — 백테스트 어댑터(시그널 사상·baseline 엔진·지표 재사용)**
- 시그널 사상(FR-10): `roles` 슬롯 소비 — entry 역할 각 Rule을 `evaluate_rule`로 평가해 **AND 결합** → `entries`, exit 역할 동일 → `exits`(조건 간 OR는 Rule 내부 논리). exit 부재/빈 리스트 → `exits = all False`(보유 지속). entries/exits는 close 인덱스 정렬 + NaN→False 보장 불리언 Series(TR-R03-010).
- 백테스트 계약(FR-11, PRD 확정 인용): 종목별 `(close, entries, exits, fees, slippage)`를 baseline **`Portfolio.from_signals`**(`TRD-R01 §8.2` 앵커 — long-only·전량 진입/청산·`freq="D"`)에 투입한다. **신규 엔진을 만들지 않는다.** 체결 시점·동시 entry/exit 신호 처리는 엔진 기본 의미론을 따르며 커스텀 규칙을 추가하지 않는다. 벤치마크 지정 시 상대 성과 함께 산출.
- 지표(FR-12, PRD 확정 인용): 최소 지표 집합의 산식 진실 원천은 baseline **`BacktestMetrics`**(`TRD-R01 §8.2` 앵커)이며 재사용·무변경. 벤치마크 산출 불가 시 값 NaN + 사유 문자열.
- 배선 결정(PRD에 없는 것): 어댑터는 R02 `StrategyDefinition`을 소비해 종목별로 위 튜플을 구성하고 baseline 엔진에 위임하는 **얇은 연결 계층**이다(신규 지표·체결 규칙 0). 어댑터 시그니처는 DESIGN-R03 §3에서 확정.
- 근거: `← FR-10 / FR-11 / FR-12 / INV-2 / AC-05 / PRD-R03 §6`

**TR-R03-013 — 백테스트 CLI 배선**
- `strategy-backtest <id>`: 대상 종목(universe 해석, TR-R03-016)·기간·비용(fees/slippage 기본값은 Pydantic Settings, `TRD-R01 §8.2` 앵커)·데이터 소스(fixture 포함)를 옵션으로 받아 지표를 rich 표로 표시한다. runnable 아님·검증 실패면 **실행 전 거부**(한국어 사유 + non-zero, TR-R03-024).
- 근거: `← FR-13 / AC-05 / PRD-R03 §6`

### 4.6 Daily 통합 배선

**TR-R03-014 — Daily 실행 집합 + 코드형 선택 기전 제거(D3)**
- Daily 전략 실행 집합 = `list_active()`(id 정렬 — 순서 결정론). 활성 전략 0건이면 **명확한 오류로 실패**(조용한 no-op 금지). `settings.strategy.enabled` 기반 코드형 전략 선택 기전은 제거되어 전략 원천이 활성 선언형 전략 단일로 수렴한다(D3).
- 삽입 지점(기술 결정): Daily 파이프라인의 전략 조립 단계에서 코드형 5종 조립 표현을 **제거**하고 활성 선언형 전략 집합을 실행 집합으로 사용한다. 다운스트림(신호→리포트→알림)은 무변경(TR-R03-019). 단일 진입점(`DailyJob.run()`) 및 `run_id` 실행 단위 키 관례는 유지한다.
- 근거: `← FR-14 / D3 / AC-06 / PRD-R03 §7`

**TR-R03-015 — 전환 시드 멱등 배선(FR-14a, C2-i, PRD 확정 인용)**
- 최초 전환 시 Built-in Template 5종(§8)을 자동 인스턴스화·활성화하여 baseline 전략 세트가 끊김 없이 운영되게 한다(정의 표는 PRD-R03 §8 확정, TR-R03-020 배선).
- 멱등·1회성(C2-i): 시드는 Daily 부트스트랩(실행 집합 조회 직전)에 인라인 배치하며, 각 Template 전략 id가 **이미 존재하면 정의·활성 상태를 일절 변경하지 않는다**(사용자의 비활성화·수정 결정을 재실행이 덮어쓰지 않음). id 존재 검사가 멱등 판정 지점.
- 근거: `← FR-14a / D3 / AC-06 / PRD-R03 §7`

**TR-R03-016 — universe 해석 배선(D5)**
- 각 전략 실행 대상 = `universe.symbols`(비어 있으면 파이프라인 watchlist 전체, `DESIGN-R02 §3.7` Universe 소비). Daily **데이터 수집 대상 = watchlist ∪ (활성 전략들의 universe 합집합)** — universe 심볼은 watchlist 포함 여부와 무관하게 실행된다. 수집 실패·데이터 부재 종목은 전략×종목 오류로 격리(TR-R03-018).
- 배선 결정: 수집 대상 합집합 산출은 `list_active()` 각 전략 universe를 union하는 단일 지점에 두어, 수집(R01 경로, TR-R03-017)과 실행(전략별 universe 필터)이 동일 종목 집합 계약을 공유하게 한다.
- 근거: `← FR-15 / D5 / AC-06 / PRD-R03 §7`

**TR-R03-017 — 부가 데이터 자동 수집·공급 배선**
- Daily는 활성 전략들의 `required_data` 합집합(TR-R03-011)에 따라 필요한 펀더멘털 데이터(valuation/financials)를 **파이프라인 선행 단계에서 자동 수집·저장**한 뒤 `FactorInput`으로 공급한다. R01 `FundamentalProvider`(`DESIGN-R01 §3.11`)·upsert 단일 강제점·품질 게이트 경로를 재사용하며 `fetch-fundamental` CLI(R01 FR-17a)와 **동일 경로**다. 수집 실패는 전략×종목 단위 격리(TR-R03-018).
- 조건부 로딩: `ohlcv`만 요구하는 전략 집합에서는 펀더멘털 수집·로딩이 **발생하지 않는다**(required_data 합집합에 valuation/financials 부재 → 스킵). AC-04로 검증(부가 로딩 0).
- 근거: `← FR-16 / AC-04 / AC-06 / PRD-R03 §7`

**TR-R03-018 — 실패 격리 배선(전략×종목)**
- 전략×종목 단위 평가·데이터 실패는 해당 단위 오류로 기록되고 나머지 실행은 계속된다(부분 실패 격리). 실행 단계 이벤트는 baseline run 이벤트 로깅 관례(`run_events`, `TRD-R01 §8.2` DuckDB 8테이블)로 남긴다.
- 배선 결정: 평가·백테스트 루프는 전략×종목 단위로 try 경계를 두어 한 단위 실패가 배치 전체를 중단하지 않게 한다. 격리 오류는 `EvaluationError`(TR-R03-011) 및 수집 실패를 포괄하며, 사유·전략 id·종목을 이벤트로 기록.
- 근거: `← FR-17 / AC-06 / PRD-R03 §7`

**TR-R03-019 — 다운스트림 동형 배선(PRD 확정 인용)**
- 백테스트 결과 → 신호 분류(`SignalClassifier`) → Report A(결정론)/Report B(LLM) → 알림의 baseline 파이프라인 경로를 **그대로 통과**한다. 신호·리포트·중복 발송 방지(content-hash `notification_outbox`)는 baseline 인프라(`TRD-R01 §8.2` 앵커)를 재사용하며 **신규 경로를 만들지 않는다**(INV-2).
- 결정론 범위: 신호·Report A까지 결정론(INV-3), LLM Report B는 mock Provider 주입 시에만 결정론.
- 근거: `← FR-18 / INV-2 / INV-3 / AC-06 / PRD-R03 §7`

### 4.7 Template 배선

**TR-R03-020 — Built-in 5종 번들 + `create_from_template`(D1·D2, PRD 확정 인용)**
- Built-in Template 5종(`ma_crossover`/`rsi_breakout`/`bollinger_band`/`macd`/`momentum`)의 **정의 표는 PRD-R03 §8이 확정**하므로 재서술하지 않는다. 전부 D1(파라미터)·D2(`price` 팩터 — 예: `bollinger_band` entry가 `price.close`를 참조)로 표현되며, 코드 상수 번들(Strategy 정의 + 참조 Rule, 즉시 검증 통과 상태)로 제공한다.
- 배선 결정(PRD에 없는 것): 번들은 R02 `StrategyDefinition`/`Rule`/`Formula`의 `from_dict`(`DESIGN-R02 §3`) 형상을 코드 상수로 조립한다(신규 정의 형식 0). `create_from_template(template_id, new_id)`는 번들을 복제해 새 id 사용자 전략으로 저장하며, 참조 Rule이 store에 없으면 함께 upsert한다. 산출물은 일반 저장 게이트·검증(TR-R03-003)을 통과해야 하고 즉시 runnable이다(FR-20).
- 근거: `← FR-19 / FR-20 / D1 / D2 / AC-07 / PRD-R03 §8`

**TR-R03-021 — 사용자 Template 배선(`strategy_templates`)**
- `save_as_template(strategy_id, template_id)`는 전략 + 전이 참조를 Export 번들 형상(TR-R03-022)으로 `strategy_templates` 테이블(additive, TR-R03-027)에 저장한다. 저장 Template로 재생성 시 동등 정의가 복원된다. CRUD(목록·조회·삭제) 제공.
- 충돌·열거 배선: 사용자 Template id는 Built-in Template id와 충돌할 수 없다(거부, 한국어 사유). `strategy-template-list`는 Built-in과 사용자 Template를 **출처(builtin/user) 구분과 함께 통합 열거**한다.
- 근거: `← FR-21 / AC-07 / PRD-R03 §8`

### 4.8 Import/Export 배선

**TR-R03-022 — Import/Export 위상 순서 + 충돌 3분기(PRD 확정 인용)**
- Export(FR-22): `export_strategy(id)` → Strategy + 전이 참조된 모든 Rule·Formula를 하나의 결정론적 JSON 번들로 직렬화(키 정렬·스키마 버전). 결정론은 R02 canonical 직렬화(`to_dict`, `DESIGN-R02 §5.3`)를 소비한다(신규 직렬화 0).
- Import(FR-23): `import_strategy(bundle, on_conflict="reject")` → **Formula → Rule → Strategy 의존 위상 순서**로 검증·저장. 참조 무결성(dangling·순환·컬럼 불일치·params 위반)은 R02 저장 게이트(`DESIGN-R02 §7.2`)로 거부. **충돌 3분기(id 공통: 동일 canonical 멱등 통과 / 상이 거부 / `--overwrite` 대체)의 규약은 PRD-R03 §9가 확정**하므로 재서술하지 않는다.
- FR-04a 우선(배선 결정): `--overwrite`라도 활성 참조 보호(TR-R03-006)가 우선한다 — 활성 전략 전이 참조 대상은 대체 전 비활성화를 요구. 동일성 판정은 R02 canonical eq(`DESIGN-R02 §6.1`) 소비.
- 근거: `← FR-22 / FR-23 / INV-4 / AC-08 / PRD-R03 §9`

### 4.9 CLI·오류 모델·순수성·테스트 배선

**TR-R03-023 — CLI 명령 표면 + README 동기화(PRD 확정 인용)**
- CLI 확정 목록(`strategy-*`/`rule-*`/`formula-*` + R01 3계약)과 편집 의미론(**전체 정의 JSON 교체** — 부분 필드 패치 없음, 왕복 무손실 정합)은 **PRD-R03 §10이 확정**하므로 재나열하지 않는다.
- 배선 결정: CLI는 `WorkspaceService` 파사드를 얇게 감싸며(로직은 파사드, I/O는 CLI) baseline Typer CLI 관례(`TRD-R01 §8.2` 앵커)를 계승한다. 정의 입력은 JSON 파일 경로 또는 stdin. rich 표/패널 출력, 한국어 오류 + non-zero(TR-R03-024). **CLI 변경 시 README 사용법 동기화**를 완료 조건에 포함(AC-09).
- 근거: `← PRD-R03 §10 / AC-01 / AC-09`

**TR-R03-024 — 오류 모델 구체화(전역)**
- 오류 메시지는 **한국어 + 행동 가능 힌트**를 담는다: 미존재 id → 사용 가능 id 목록, 활성 참조 차단 → 차단 전략 id 목록(TR-R03-006), 데이터 미충족 → 누락 데이터 종류 + 요구 id(TR-R03-011), 검증 실패 → R02 `ValidationResult.errors`(`DESIGN-R02 §3.1`) 승계, runnable 아님 → 활성화·백테스트 전제 안내. CLI 실패는 non-zero 종료.
- 결정론 관련: 평가·백테스트·Daily 어디서도 네트워크·현재시각에 의존하지 않는다(시각 주입, INV-3). 이는 오류 재현성의 전제.
- 근거: `← 공통 원칙 7 / INV-3 / README §5`

**TR-R03-025 — 단일 실행 경로(INV-2) + 결정론(INV-3) 배선**
- INV-2: Built-in Template 포함 모든 전략은 동일한 평가→시그널→백테스트→Daily 경로를 통과한다. 전략별 특수 분기·코드형 우회 경로를 두지 않는다(D3 정합). Template 실행 테스트로 검증.
- INV-3: 동일 (정의+데이터+주입 시각) → 평가·백테스트·Daily 산출 동일(신호·Report A까지). run_id·시각 주입 고정 + LLM mock으로 2회 실행 동등 판정.
- 근거: `← INV-2 / INV-3 / AC-06 / AC-09 / PRD-R03 §11`

**TR-R03-026 — 테스트 전략 배선**
- 모든 AC는 합성 Fixture + `tmp_path` 격리 DuckDB + `LLM_MOCK=true`(MockProvider) + pytest로 네트워크·실데이터·실LLM·시각 의존 없이 검증한다. 결정론은 **2회 실행 동일**로 판정(신호·Report A 범위).
- 기대값 하드코딩 금지: 평가 결과(Formula 파생 시계열·Rule 불리언·교차)는 테스트가 §5.4 수치 규약을 pandas로 **독립 재도출**하여 대조한다(골든 상수 금지). Fixture는 R01 OHLCV/펀더멘털 픽스처와 종목 정합.
- 근거: `← 원칙 3 / AC-03 / AC-06 / AC-09 / PRD-R03 §12`

**TR-R03-027 — additive 진화(2테이블 추가)**
- R03는 `strategy_activation`·`strategy_templates` **2테이블만 additive 추가**한다(원칙 6). baseline 8테이블·R01 2테이블·R02 3테이블 DDL은 무변경. 모든 DDL은 `CREATE TABLE IF NOT EXISTS` 멱등. 신규 Template=행 추가, 신규 활성 상태=행 upsert로만 확장.
- 근거: `← 공통 원칙 6 / PRD-R03 §13 / README §5`

## 5. 비기능 요구사항 (NFR)

| NFR | 요구 | 검증 |
|---|---|---|
| **NFR-01 결정론** | 동일 (정의+데이터+주입 시각) → 신호·Report A까지 동일. 평가·백테스트·Daily 네트워크·현재시각 미의존(시각 주입). LLM Report B는 mock 시에만. | 2회 실행 동등(신호·Report A, LLM mock) |
| **NFR-02 오프라인 검증** | 전 AC가 네트워크·실데이터·실LLM 없이 합성 Fixture + 격리 DuckDB + LLM mock으로 검증. | CI 오프라인 실행 green |
| **NFR-03 계층 단방향(INV-1)** | `workspace`/`jobs`는 R01/R02·storage·백테스트 엔진 소비만, 하위 역주입 0. | R01/R02 순수성 스캔 무변경 green + 정의 패키지 workspace import 부재 스캔 |
| **NFR-04 단일 실행 경로(INV-2)** | 모든 전략 동일 경로, 전략별 특수 분기 부재. | 설계 리뷰 + Template 실행 테스트 |
| **NFR-05 캐시 격리** | 평가 캐시 수명이 (전략, 종목) 컨텍스트로 한정, 종목·전략·실행 간 공유 0. | 컨텍스트 경계 밖 캐시 히트 부재 테스트 |
| **NFR-06 재사용 무변조** | 백테스트 엔진·지표·다운스트림·펀더멘털 수집 경로를 baseline·R01에서 재사용하며 신규 구현 0. | 코드 리뷰 + 앵커 경유 확인 |
| **NFR-07 실패 격리** | 전략×종목 단위 실패가 배치 전체를 중단하지 않음. | 부분 실패 후 완주 테스트 |
| **NFR-08 멱등** | 활성화 전이·전환 시드·Import·테이블 생성 재실행이 중복·오류 0. | 재실행 동등 테스트 |

## 6. 수용 기준 (PRD AC 승계 + pytest 매핑)

> PRD AC-01~09를 `AC-R03-xx`로 승계·구체화하고 pytest 검증 방법을 명시한다. 기대값 하드코딩 금지(수치 규약 재도출). 합성 Fixture + 격리 DuckDB + LLM mock.

- **AC-R03-01 (← AC-01)** 파사드/CLI 전 명령 왕복(생성→조회→수정→삭제, DB 재조회 일치), 오류 시 non-zero.
  - *pytest*: CLI runner로 `strategy-create`→`strategy-show`→`strategy-edit`(전체 JSON 교체)→`strategy-delete` 후 DB 재조회 일치; 미존재/무효 입력 non-zero. `rule-*`/`formula-*` 동형.
- **AC-R03-02 (← AC-02)** 활성화 idempotent 전이·재조회 보존 · 초안/검증 실패/미존재 활성화 거부 · 활성 참조 엔티티 수정·삭제 거부(FR-04a — 차단 사유에 전략 id, 비활성화 후 허용).
  - *pytest*: `activate` 2회 후 상태 동일; 초안(rule=None)·검증 실패 전략 `activate` 거부; 활성 전략 참조 Rule/Formula `upsert`/`delete` 거부 메시지에 전략 id 포함; `deactivate` 후 허용.
- **AC-R03-03 (← AC-03)** Formula 파생 시계열·다단 DAG 위상 · Rule 비교/AND/OR/NOT/교차 정확성 · **params 오버라이드(sma(5) vs sma(20) 상이 + 골든크로스 교차 발생)** · NaN→False·div0→NaN·스칼라 교차 · 2회 평가 동일.
  - *pytest*: fixture 입력에 Formula 재귀 평가를 §5.4 규약으로 독립 재도출 대조; 다단 DAG 위상 순서 결과 일치; Rule 각 연산자 정확성; `sma(5)`/`sma(20)` 시계열 상이 + 교차 신호 발생; NaN→False·div0→NaN·스칼라 브로드캐스트 경계; 2회 `assert_series_equal`.
- **AC-R03-04 (← AC-04)** required_data 미충족 → `EvaluationError`(누락 종류 + id 포함) · ohlcv-only 전략 집합에서 부가 로딩 0.
  - *pytest*: valuation/financials 요구 전략에 해당 프레임 부재 시 `EvaluationError`(힌트에 누락 종류·id); ohlcv-only 활성 집합 Daily에서 펀더멘털 수집 호출 0(spy).
- **AC-R03-05 (← AC-05)** fixture로 최소 지표 집합 산출 · CLI 표시 · runnable 아님 → 실행 전 거부.
  - *pytest*: `strategy-backtest`가 fixture로 총수익률·CAGR·MDD·Sharpe·승률·거래횟수·총비용 표 산출(baseline 엔진·지표 경유); 초안 전략 백테스트 실행 전 non-zero 거부.
- **AC-R03-06 (← AC-06)** 활성 집합 실행·id 정렬 · universe 해석(전략별 부분 종목 + 수집 합집합) · 전략×종목 실패 격리 후 완주 · 활성 0건 명확 실패 · 펀더멘털 요구 전략 자동 수집(FR-16 Fixture provider) · 전환 시드 멱등(FR-14a — 최초 생성+활성, 기존 id 무변경) · 신호→리포트→알림 통과.
  - *pytest*: `list_active` id 정렬; 전략별 universe 필터 + 수집 대상 = watchlist ∪ universe 검증; 1개 종목 데이터 부재 시 해당 단위 오류 격리 후 배치 완주; 활성 0건 시 명확 실패; Fixture 펀더멘털 provider 자동 수집 경로; 전환 시드 최초 1회 5종 생성·활성 후 재실행 시 정의·활성 무변경(사용자 비활성화 보존); Report A/B·outbox 통과(LLM mock).
- **AC-R03-07 (← AC-07)** Built-in 5종 전부 즉시 검증 통과 + fixture 백테스트 완주 · 생성물 runnable · 사용자 Template 저장→재생성 동등.
  - *pytest*: Built-in 5종 각 `validate_strategy` 통과·`is_runnable` True·fixture 백테스트 지표 산출; `create_from_template` 산출물 저장 게이트 통과·runnable; `save_as_template`→`create_from_template` 왕복 정의 canonical 동등.
- **AC-R03-08 (← AC-08)** Export→Import 왕복 동일 정의 복원 · 위상 순서 저장 · dangling/순환 거부 · 충돌 3분기(동일 멱등 통과 / 상이 거부 / `--overwrite` 대체).
  - *pytest*: export 번들 canonical 결정론(2회 바이트 동일); import Formula→Rule→Strategy 순서 저장; dangling·순환 번들 거부; 동일 canonical 재import 멱등, 상이 거부, `--overwrite` 대체(단 활성 참조 FR-04a 우선 거부).
- **AC-R03-09 (← AC-09)** INV-1 스캔 green · README 사용법 동기화 · `pytest`·`ruff` 전량 통과.
  - *pytest*: R01/R02 순수성 AST 스캔 무변경 green + 정의 패키지 `workspace`/`jobs` import 부재; CLI 명령 목록과 README 사용법 섹션 대조; `ruff check` 0 위반.

## 7. 리스크·완화 (Open Tensions)

| # | Tension | 영향 | 완화 |
|---|---|---|---|
| OT-1 | **캐시 오염** — 팩터/Formula 캐시가 종목·전략·실행 간 공유되어 잘못된 시계열 재사용 | 비결정·오답 신호 | (전략, 종목) 컨텍스트 소유 캐시(C3-i, TR-R03-009), 캐시 격리 테스트(NFR-05) |
| OT-2 | **결측 사유 소실** — `compute_factor` 반환 후 pandas 연산이 `attrs`를 드롭 | 결측 판독 불가 | R01 계약대로 반환 직후 `get_factor_notes` 판독(TR-R03-009, `DESIGN-R01 §3.9`) |
| OT-3 | **활성 참조 보호 우회** — Import `--overwrite`가 활성 전략 참조를 조용히 대체 | 운영 중 전략 무단 변경 | FR-04a 우선 배선(TR-R03-022), 활성 폐포 온디맨드 판정(C1-i) |
| OT-4 | **전환 시드 덮어쓰기** — 재실행 시드가 사용자 수정·비활성화를 되돌림 | 사용자 결정 손실 | id 존재 멱등 가드(C2-i, TR-R03-015), 재실행 무변경 테스트(AC-06) |
| OT-5 | **이중 실행 경로 재유입** — 코드형 전략 우회 경로가 남아 D3 위반 | 단일 경로 붕괴 | `settings.strategy.enabled` 제거 + INV-2 스캔·Template 실행 테스트(TR-R03-014/025) |
| OT-6 | **수치 규약 drift** — evaluate_formula/rule/백테스트가 각기 다른 NaN·교차 처리 | 비결정·경계 오답 | 단일 강제점 공유 헬퍼(TR-R03-010), 경계 케이스 재도출 테스트(AC-03) |
| OT-7 | **신규 엔진·지표 유입** — 백테스트가 baseline 엔진 대신 커스텀 구현 | 재사용 원칙·정합 붕괴 | `Portfolio.from_signals`/`BacktestMetrics` 앵커 경유 강제(TR-R03-012, NFR-06) |
| OT-8 | **활성 0건 조용한 no-op** — Daily가 활성 전략 없이 조용히 완료 | 운영 공백 미검출 | 활성 0건 명확 실패(TR-R03-014, AC-06) |

## 8. 부록

### 8.1 마일스톤 (논리 단위)

| M | 범위 | 완료 신호 |
|---|---|---|
| M0 | 모듈 골격(`workspace/`·`jobs/`) + INV-1 단방향 AST 스캔 | 스캔 green(AC-R03-09 부분) |
| M1 | `WorkspaceService` 파사드 + CRUD 위임 + 전이 검증 조합 + 활성화·활성 참조 보호 | AC-R03-01/02 부분 |
| M2 | 평가 엔진(evaluate_formula·evaluate_rule) + 파라미터 해석·캐시 + 수치 규약 강제점 + 데이터 계약 | AC-R03-03/04 |
| M3 | 백테스트 어댑터(시그널 사상·baseline 엔진·지표 재사용) + 백테스트 CLI | AC-R03-05 |
| M4 | Daily 통합(실행 집합·`settings.strategy.enabled` 제거·전환 시드·universe 해석·부가 수집·실패 격리·다운스트림 동형) | AC-R03-06 |
| M5 | Template 5종·`create_from_template`·사용자 Template + Import/Export 위상 순서·충돌 3분기 | AC-R03-07/08 |

> 마일스톤은 문서상 논리 단위다(스프린트 분할은 구현 계획 시점 확정).

### 8.2 하위(R01/R02) 인터페이스 참조표 (R03가 소비하는 확정 앵커)

> 시그니처 확정 원천은 하위 DESIGN §3. 본 문서는 아래를 링크 인용하며 재정의하지 않는다(§D-2).

| 인터페이스 | 형태(요약) | R03 소비 지점 | 확정 원천 |
|---|---|---|---|
| `FactorInput` | (ohlcv, valuation, financials) 3프레임, 단일 종목 | 평가 엔진 입력·데이터 계약 | DESIGN-R01 §3.4 |
| `compute_factor(factor, data)` | 유일 인가 디스패치 → DataFrame | 팩터 계산(TR-R03-009) | DESIGN-R01 §3.6 |
| `get_factor(id, **params)` | 오버라이드 인스턴스 생성 | 파라미터 해석(TR-R03-009, D1) | DESIGN-R01 §3.7 |
| `get_factor_notes(result)` | 결측 사유 유일 접근자 | 평가 사유 판독 | DESIGN-R01 §3.9 |
| `FactorMetadata.required_data` | 팩터 요구 데이터 종류 | 데이터 계약 파생(TR-R03-011) | DESIGN-R01 §3 |
| `FundamentalProvider` | 밸류에이션·재무제표 조달, OHLCV Provider와 분리 | Daily 자동 수집(TR-R03-017) | DESIGN-R01 §3.11 |
| `validate_formula` / `validate_rule` / `validate_definition`(+strict) | 검증기 3종(비발생/엄격) | 전이 검증 조합(TR-R03-003) | DESIGN-R02 §3.4/§3.6/§3.8 |
| `is_runnable(defn)` | roles + entry≥1 판정 | 활성화·백테스트 전제(TR-R03-005) | DESIGN-R02 §3.8 |
| `derive_required_data` | Formula 참조 required_data 전이 파생 | 데이터 계약(TR-R03-011) | DESIGN-R02 §3.4 |
| `from_dict`/`to_dict`(Formula/Rule/StrategyDefinition) | 왕복·canonical 직렬화 | Template 번들·Import/Export(TR-R03-020/022) | DESIGN-R02 §3.3/§3.5/§3.7, §5.3 |
| `ValidationResult` | ok + 한국어 오류 튜플 | 오류 모델 승계(TR-R03-024) | DESIGN-R02 §3.1 |
| `FormulaResolver` / `RuleResolver` | id → 리졸브(duck-typed), None=완화 | 전이 검증·참조 보호 폐포(TR-R03-003/006) | DESIGN-R02 §3.9 |

### 8.3 baseline 앵커 소비표 (main 시점 재사용 자산)

> `TRD-R01 §8.2` 앵커 표 명칭으로만 인용한다(재구축 없음, 세부 파일 경로 언급 금지).

| 앵커 명칭 (TRD-R01 §8.2) | R03 소비 지점 |
|---|---|
| `Portfolio.from_signals` (vectorbt) | 백테스트 어댑터가 시그널 투입(TR-R03-012, 신규 엔진 0) |
| `BacktestMetrics` | 최소 지표 집합 산식 원천 재사용(TR-R03-012, 신규 산식 0) |
| 신호 분류기(SignalClassifier) | 백테스트 결과→신호 분류 다운스트림(TR-R03-019) |
| content-hash 기반 `notification_outbox` | 중복 발송 방지 재사용(TR-R03-019) |
| DuckDB 기존 8테이블 | `run_events` 로깅(TR-R03-018) 등 무변경 소비. R03는 `strategy_activation`·`strategy_templates` 2테이블 additive 추가(TR-R03-027) |
| OHLCV `DataProvider` | Daily OHLCV 조달(무변경), 펀더멘털은 R01 `FundamentalProvider` 별도 경로(TR-R03-017) |
| Typer CLI | `strategy-*`/`rule-*`/`formula-*` 명령을 동일 관례로 추가(TR-R03-023) |
| Pydantic Settings | 비용(fees/slippage) 기본값·데이터 소스·LLM mock 로딩 소비(TR-R03-013, NFR-02) |

---

**추적성 요약**: FR-01~23(FR-04a·FR-14a 포함) · AC-01~09 · INV-1~4 · D1~D5 전건이 §3 매트릭스에서 ≥1 TR로 매핑(공백 0). §4는 TR-R03-001~027로 구성되며, PRD 확정 항목(FR-08 수치 규약·Built-in 5종 표·CLI 목록·충돌 3분기)은 §3 매트릭스로 축약해 §4 중복 서술을 두지 않는다(§D-9 준수). 하위 시그니처는 `DESIGN-R01 §3`·`DESIGN-R02 §3` 링크 인용만 하고 재정의하지 않으며(§D-2), baseline 자산은 `TRD-R01 §8.2` 앵커 명칭으로만 인용한다(§D-5).

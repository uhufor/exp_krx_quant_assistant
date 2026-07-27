# TRD-R04 — 백테스트/스크리닝 펀더멘털 증분 수집 + 팩터 기반 순위 스크리닝

**작성일**: 2026-07-26
**Status**: 구현 완료(§1~§5 전항목 구현+테스트 완료, `test_fundamental_sync.py`/`test_factor_ranking.py`/`test_evaluation.py`/`test_definition.py`/`test_service.py`/`ScreeningTreeEditor` 반영)
**전제**: `RESEARCH-R04-FACTOR_DATA_EXPANSION.md`의 후속. "스크리닝에서 DART 재무 팩터로 순위를 매길 수 있나?"(현재 불가) 확인 과정에서 나온 요구사항을 기능으로 정의한다.

**핵심 결정(사용자 확정)**: 별도 배치 잡을 만들지 않는다. **실행 시점(백테스트/스크리닝) 기준으로 DB 커버리지를 먼저 체크하고, 부족한 범위만 DART에서 벌크로 채운 뒤 기존 로직을 그대로 태운다.** 커버리지가 이미 충분하면(부족분 0) DART 호출을 완전히 바이패스한다.

---

## 부록 — 실사용 중 발견한 재호출 버그 2건과 수정 (2026-07-27)

배포 후 실사용(000270 반복 백테스트, 전종목 부채비율 스크리닝 반복 실행)에서 "커버리지가 이미 충분한데도 매번 DART를 다시 부른다"는 문제가 재현되어 원인을 특정하고 수정했다. 000270 기본 5년 백테스트 범위로 재현 시 **수정 전: 2회 연속 실행 = 14콜(회당 7콜, 항상 동일) → 수정 후: 2콜(1회차만, 2회차는 0콜)**.

**버그 1 — 범위 밖 분기를 API 호출 후에야 버림**: `fetch_financials`가 `[start, end]`의 "연도"만 보고 4개 분기를 전부 호출한 뒤 응답의 `disclosure_date`로 사후 필터링했다. 버려진 응답은 저장이 안 되니 `skip_periods`에도 안 남아 **매 실행마다 재호출**됐다(000270의 2021 Q1처럼 실제로는 데이터가 있지만 `start` 이전에 공시된 경우, 2026 Q3/Q4처럼 아직 끝나지도 않은 미래 분기).
- **수정**: `data/dart_fundamental.py::_worth_attempting(bsns_year, reprt_code, start, end)` — API 호출 전에 계산만으로 "이 분기가 `[start, end]` 안에서 공시될 가능성이 있는지" 판정(`period_end > end` 또는 `period_end + DISCLOSURE_GRACE_DAYS(100일) < start`면 즉시 거부). `fetch_financials` 루프에서 `skip_periods` 체크 직후 적용.

**버그 2 — "아직 미공시" 결과는 캐시할 곳이 없어 매번 재확인**: 최신 분기가 실제로 아직 공시되지 않은 경우(013 응답)는 성공 데이터가 아니므로 `financial_statements`에 저장되지 않고, 따라서 다음 실행에서도 또 확인 대상이 된다. 이건 계산으로 미리 걸러낼 수 없는 별개 문제다(버그 1의 "범위 밖" 필터는 날짜 계산상 멀쩡한 후보를 통과시키므로, "범위 안인데 실제로 아직 없는" 이 케이스를 못 잡는다).
- **수정(사용자 확정: 1시간 TTL)**: 신규 `data/dart_missing_period_cache.py::DartMissingPeriodCache` — "(symbol, 분기)를 언제 확인했는데 없더라"를 로컬 parquet 캐시(`~/.cache/quant_krx/dart_missing_periods.parquet`)에 기록. `_fetch_one_period`가 호출 전 캐시를 확인해 TTL(1시간) 이내면 API 호출 없이 즉시 결측 처리하고, TTL이 지나면 재확인한다. 매 조회마다 디스크 I/O를 하지 않도록 메모리에 로드해 실행 중 갱신하고 `adapter.close()` 시점에 한 번만 flush한다(모든 호출부가 이미 `close()`를 호출하므로 별도 배선 불필요).

`fundamental_sync.py`의 `_DISCLOSURE_GRACE_DAYS`(100일) 상수는 `dart_fundamental.py::DISCLOSURE_GRACE_DAYS`로 승격해 두 모듈이 공유한다(중복 정의 제거).

---

## 0. 기술적 전제 — 재무 팩터는 OHLCV 값을 쓰지 않는다

`factors/catalog/financial.py`의 14종 전부 확인 결과, `.compute()`는 `data.ohlcv.index`(날짜 인덱스)만 as-of 병합 기준(`align_financials`)으로 쓰고 **open/high/low/close/volume 값 자체는 참조하지 않는다.** 따라서 스크리닝에서 종목별 실제 OHLCV 이력을 조회할 필요 없이, `pd.DataFrame(index=pd.DatetimeIndex([as_of]))` 같은 인덱스만 있는 더미 프레임 + DB의 financials/valuation만으로 `compute_factor()`를 그대로 재사용해 as-of 시점 값을 계산할 수 있다 — 팩터 계산 로직 중복 없음, 백테스트와 완전히 동일한 산식 보장.

이 전제 덕분에 전종목(2000+) 순위 계산 비용은 **종목당 DART/PyKrx 호출(펀더멘털 동기화) + 가벼운 pandas 계산**뿐이고, 종목당 OHLCV fetch가 추가로 필요 없다.

## 1. 백테스트 — financials 증분 수집(gap-check)

**현황**: `workspace/data_loading.py::fetch_and_upsert_fundamentals`는 valuation은 이미 `_existing_valuation_coverage`/`_gap_ranges`로 날짜 구간 증분 수집을 하지만, financials는 "PK가 날짜 축이 아니므로 매번 전체 재수집"한다(주석 그대로) — 동일 종목·구간으로 반복 백테스트해도 매번 DART를 전부 다시 호출한다.

**변경**: financials도 커버리지 체크 후 부족분만 수집한다.
- `_existing_financials_periods(conn, symbols) -> dict[str, set[tuple[int, int]]]`: `financial_statements`에서 symbol별 `(fiscal_year, fiscal_quarter)` distinct 집합 조회(scope 무관 — CFS든 OFS든 그 분기가 이미 있으면 커버된 것으로 간주).
- `DartFundamentalAdapter.fetch_financials(symbols, start, end, *, skip_periods: Mapping[str, set[tuple[int,int]]] | None = None)`: 내부 `bsns_year × reprt_code` 루프에서 `(symbol, bsns_year, fiscal_quarter)`가 `skip_periods`에 있으면 API 호출 없이 건너뛴다.
- 호출부(`_fetch_fundamentals_for_backtest`)가 커버리지를 조회해 `skip_periods`로 넘긴다.

**바이패스 조건**: 요청 구간의 모든 (bsns_year, reprt_code) 조합이 이미 존재하면 DART 호출 0회.

## 2. DART — 최신 분기 조회 모드(`fetch_latest_financials`)

전종목 순위용으로는 시계열 백필이 필요 없고 "현재 시점 최신 확정값" 하나만 필요하다. 기존 `fetch_financials`(연도 범위 전체 순회)와는 다른, 비용을 낮춘 신규 메서드를 추가한다.

```python
def fetch_latest_financials(
    self, symbols: Sequence[str], as_of: date, *, max_quarters_back: int = 3
) -> pd.DataFrame:
```

- `as_of` 기준 최근 분기부터 역순으로 최대 `max_quarters_back`개 분기 후보를 시도하고, 성공(CFS 또는 OFS 확보)하는 즉시 해당 종목 결과를 채택 — 더 오래된 분기는 시도하지 않는다.
- 종목당 호출 수: 최선 1회(최신 분기 CFS 즉시 성공), 최악 `max_quarters_back × 2`(분기 후보 전부 실패 + 매 분기 CFS/OFS 둘 다 시도) — 실무 평균은 1~2회로 추정(§2 대화 근거: 대다수 종목이 연결재무 보유 + 최신 분기 공시 완료 상태).
- 이미 DB에 있는 (symbol, year, quarter)는 호출 자체를 생략(§1의 `skip_periods`와 동일 메커니즘 재사용).

## 3. 스크리닝 — 전종목 재무/밸류에이션 신선도 체크 + 벌크 동기화

신규 모듈 `screening/fundamental_sync.py`:

```python
def sync_universe_fundamentals(
    db: Database, symbols: list[str], *, as_of: date, needs_valuation: bool, needs_financials: bool
) -> None:
```

- **valuation**: 커버리지 조회 로직(`existing_valuation_coverage`/`date_range_gaps`)은 원래 `workspace/data_loading.py`에 있었으나, `screening/`이 이를 직접 import하면 INV-2(screening은 workspace를 참조하지 않음) 위반이라 구현 시점에 `data/coverage.py`(신규)로 승격했다 — `workspace/data_loading.py`와 `screening/fundamental_sync.py` 양쪽이 이 공유 모듈을 import한다(중복 없음, 격리 유지). 갭이 있는 종목만 `PyKrxFundamentalAdapter.fetch_valuation` 호출.
- **financials**: 신규 로직 — symbol별 `financial_statements` 최신 `(fiscal_year, fiscal_quarter)`와 그 `disclosure_date`를 조회해, "현재 시점 기준 있을 법한 최신 분기"보다 오래됐으면(신선도 미달) 갱신 대상으로 표시. 갱신 대상 종목만 `DartFundamentalAdapter.fetch_latest_financials`로 벌크 조회.
- 갱신 대상이 0종목이면 두 provider 모두 호출하지 않고 즉시 반환(바이패스).
- 개별 종목 실패(전기 corp_code 미해결 등)는 건너뛰고 계속(기존 "종목 단위 격리" 원칙과 동일).

`ScreeningService.run()`은 조건 트리에 `FactorRankPredicate`가 있을 때만(§4) 이 동기화를 호출한다 — 순수 OHLCV 조건(`RankPredicate`/`Predicate`)만 있으면 지금처럼 전혀 관여하지 않는다(회귀 없음).

## 4. 신규 노드 `FactorRankPredicate` — 팩터 기반 횡단면 순위

기존 `RankPredicate`(시장 스냅샷 네이티브 컬럼 `close`/`volume`/`trading_value` 전용, `ranking.py`)는 **변경하지 않는다** — 데이터 경로가 근본적으로 다르므로(PRD-R03 D3 연장) 별도 노드로 분리한다.

### 4.1 정의 (`screening/definition.py`)

```python
@dataclass(frozen=True, eq=False)
class FactorRankPredicate(CanonicalEq):
    """재무제표/밸류에이션 팩터 값 기준 횡단면 순위 — OHLCV 시계열이 불필요한 팩터 전용."""
    factor_id: str
    column: str
    rank_metric: str  # "asc" | "desc"
    top_n: int
    params: Mapping[str, Any] = field(default_factory=dict)
    node: ClassVar[str] = "factor_rank_predicate"
```

`RankPredicate`와 필드 형상은 동일하지만 **클래스와 node 태그가 별개**(`"factor_rank_predicate"`) — 평가 경로가 다르다는 것을 스키마 레벨에서 명시. `Node` 유니온과 `dispatch.py::_NODE_DISPATCH`에 추가.

### 4.2 검증 (`screening/service.py::_collect_validation_errors`)

- `factor_id`가 카탈로그에 존재해야 함(기존과 동일).
- **`factor.metadata.required_data`에 `"ohlcv"`가 포함되면 거부**(명확한 에러: "FactorRankPredicate는 OHLCV가 필요한 팩터를 지원하지 않습니다 — sma/rsi 등은 RankPredicate/Predicate+WindowPredicate를 쓰십시오"). 즉 허용 대상은 `required_data ⊆ {"valuation", "financials"}`인 팩터(밸류에이션 11종 + 재무제표 14종) — 가격·기술 팩터는 원천적으로 이 노드에서 선택 불가하게 만든다(선택 가능해 보이지만 항상 실패하는 UI 금지 원칙과 동일 결).

### 4.3 계산 (신규 `screening/factor_ranking.py`)

```python
def compute_cross_sectional_factor_rank(
    db: Database, symbols: list[str], *, as_of: date, rank_predicate: FactorRankPredicate,
) -> set[str]:
```

- §0 전제대로 `pd.DataFrame(index=pd.DatetimeIndex([pd.Timestamp(as_of)]))` 더미 ohlcv + `data/loader.py::load_factor_input(conn, symbol, end=as_of, ohlcv=dummy)`로 얻은 `valuation`/`financials`를 `FactorInput`에 담아 `compute_factor(factor, factor_input)` 호출(팩터 계산 로직 재구현 없음, 백테스트와 동일 함수).
- 종목별 결과의 마지막(유일) 행 값을 모아 `pandas.Series.rank()`로 순위, `top_n` 이내만 통과 집합에 포함.
- 값이 NaN인 종목(결측 데이터)은 자연 제외(에러 아님).

`apply_factor_rank_predicates(node, ...)`가 트리에서 `FactorRankPredicate` 전부 추출해 동일 `rank_membership` dict(키 타입: `RankPredicate | FactorRankPredicate` — `CanonicalEq.__eq__`가 `type(self) is not type(other)`부터 검사하므로 두 노드 타입이 같은 dict에 섞여도 충돌 없음, 확인 완료)에 병합한다.

### 4.4 평가 경로 연결

- `screening/evaluation.py::_eval_screening_node`에 `FactorRankPredicate` 분기 추가(`RankPredicate` 분기와 동일 패턴 — `ctx.rank_membership`에서 소속 조회).
- `tree_requires_ohlcv`/`estimate_required_lookback`에 `FactorRankPredicate` 분기 추가(둘 다 `RankPredicate`와 동일하게 "OHLCV 불필요/lookback 0").
- `extract_rank_predicates`는 `RankPredicate` 전용으로 유지하고, `FactorRankPredicate` 전용 추출 함수를 별도로 둔다(트리 순회 구조는 동일하되 반환 타입이 다르므로 함수 분리 — 명확성 우선).
- `ScreeningService.run()`: 트리에 `FactorRankPredicate`가 있으면 §3의 동기화 호출 → `apply_factor_rank_predicates` 호출 → 결과를 `rank_membership`에 병합.

## 5. GUI

- `web/src/tree/screeningTypes.ts`에 `ScreeningFactorRankPredicateJSON`(`node: 'factor_rank_predicate'`) 추가, `ScreeningNodeJSON` 유니온에 포함.
- `ScreeningTreeEditor.tsx`: 노드 타입 선택지에 "팩터 순위 조건(재무/밸류에이션)" 추가. 팩터 드롭다운은 `required_data`가 `ohlcv`를 포함하지 않는 팩터만 필터링해서 보여준다(백엔드 검증과 동일 제약을 프런트에서도 선반영 — 선택 가능해 보이지만 저장 시 항상 실패하는 UI 금지).
- 기존 `RankPredicate` 편집기의 `factor_id(참조용, lookback 추정에만 사용)` 필드는 **제거**한다 — 실제로 아무 데도 안 쓰이는(lookback도 0 고정) 오도성 필드였음(이전 대화에서 확인). `column` 드롭다운 라벨을 `거래대금`/`거래량`/`종가`로 사람이 읽기 좋게 바꾼다.

## 6. 범위 밖(v1 제외)

- 밸류에이션 신선도 판정은 기존 `_gap_ranges`(날짜 구간)를 그대로 쓰므로 별도 "최신 1건만" 최적화를 하지 않는다(밸류에이션은 일별 데이터라 financials처럼 분기 단위 최적화가 필요 없음).
- `FactorRankPredicate`의 `params`(팩터 파라미터 오버라이드)는 지원하되, 팩터별 param 검증(ParamSpec 범위 등)은 기존 `get_factor()` 경로를 그대로 통과시켜 재구현하지 않는다.
- 신선도 임계값(§3 "있을 법한 최신 분기") 계산은 분기말 + 공시 유예기간(사업보고서 90일/분반기 45일 근사)을 상수로 둔다 — 종목별 정밀 공시 스케줄 추적은 하지 않는다(과설계 방지).

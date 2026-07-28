from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime

import pandas as pd

from quant_krx.data.base import DataProvider
from quant_krx.data.coverage import (
    date_range_gaps,
    existing_financials_periods,
    existing_valuation_coverage,
)
from quant_krx.data.fundamental_base import FundamentalProvider
from quant_krx.data.loader import load_factor_input
from quant_krx.data.upsert import upsert_fundamental
from quant_krx.data_sources import DATA_SOURCES, OFFLINE_DATA_SOURCES
from quant_krx.factors import FactorInput
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import StrategyDefinition
from quant_krx.workspace.dynamic_universe import (
    DynamicUniversePlan,
    ScreeningResolver,
    build_plan,
)
from quant_krx.workspace.errors import EmptyOhlcvError
from quant_krx.workspace.evaluation import FormulaResolver, RuleResolver, strategy_required_data

# 화이트리스트 원천은 quant_krx.data_sources(의존성 없는 최상위 모듈) — 여기서는 기존 import
# 경로(`from workspace.data_loading import DATA_SOURCES`)를 유지하기 위해 재export만 한다.
__all__ = ["DATA_SOURCES", "OFFLINE_DATA_SOURCES"]


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    result = df.set_index("date") if "date" in df.columns else df
    result.index = pd.to_datetime(result.index)
    result = result.sort_index()
    return result[["open", "high", "low", "close", "volume"]].astype(float)


def fetch_and_upsert_fundamentals(
    db: Database,
    symbols: list[str],
    provider: FundamentalProvider,
    *,
    start: date,
    end: date,
    as_of: date,
    kinds: frozenset[str],
    financials_kwargs: Mapping[str, object] | None = None,
) -> None:
    """required_data에 valuation/financials가 있을 때만 호출한다(AC-04 — ohlcv-only는 호출 0회).

    R01 FundamentalProvider·upsert_fundamental 단일 강제점·품질 게이트 경로를 그대로
    재사용하며(fetch-fundamental CLI와 동일 경로), 신규 수집 로직을 두지 않는다.

    valuation은 symbol별 기존 fundamental_daily 커버리지를 조회해, 요청 구간 중 이미
    확보된 부분은 건너뛰고 경계 바깥(이전/이후)만 증분 수집한다(라이브 provider 호출
    최소화 — PyKrx처럼 재로그인·개인 자격증명이 필요한 provider에서 중요).
    financials는 `financials_kwargs`(예: `{"skip_periods": {...}}`)를 provider 호출에
    그대로 전달한다 — 기본값 None이면 기존과 동일하게 아무 추가 인자 없이 호출되므로
    이 키워드를 모르는 provider(Fixture/PyKrx)는 영향받지 않는다(TRD-R04 §1).
    """
    with db.cursor() as conn:
        if "valuation" in kinds:
            coverage = existing_valuation_coverage(conn, symbols)
            grouped: dict[tuple[date, date], list[str]] = {}
            for symbol in symbols:
                for gap in date_range_gaps(coverage.get(symbol), start, end):
                    grouped.setdefault(gap, []).append(symbol)
            for (gap_start, gap_end), gap_symbols in grouped.items():
                frame = provider.fetch_valuation(gap_symbols, gap_start, gap_end)
                frame = frame.assign(source=provider.source_name, fetched_at=datetime.utcnow())
                upsert_fundamental(conn, "fundamental_daily", frame, as_of=as_of)
        if "financials" in kinds:
            frame = provider.fetch_financials(symbols, start, end, **(financials_kwargs or {}))
            frame = frame.assign(source=provider.source_name, fetched_at=datetime.utcnow())
            upsert_fundamental(conn, "financial_statements", frame, as_of=as_of)


def build_factor_input_from_ohlcv(
    db: Database,
    symbol: str,
    ohlcv_raw: pd.DataFrame,
    *,
    start: date,
    end: date,
) -> FactorInput:
    """이미 조회된 OHLCV(raw, date 컬럼 포함 가능)로 FactorInput을 조립한다(중복 fetch 회피).

    data/는 factors/를 모르므로(INV-1) 두 계층을 모두 아는 상위 호출자(R03)가 조립을 수행한다.
    """
    ohlcv_df = _normalize_ohlcv(ohlcv_raw)
    if ohlcv_df.empty:
        raise EmptyOhlcvError(symbol)
    with db.cursor() as conn:
        bundle = load_factor_input(conn, symbol, start=start, end=end, ohlcv=ohlcv_df)
    return FactorInput(ohlcv=bundle.ohlcv, valuation=bundle.valuation, financials=bundle.financials)


def build_factor_input(
    db: Database,
    symbol: str,
    *,
    ohlcv_provider: DataProvider,
    start: date,
    end: date,
) -> FactorInput:
    """OHLCV를 조회한 뒤 build_factor_input_from_ohlcv로 위임한다."""
    ohlcv_data = ohlcv_provider.fetch_ohlcv(symbol, start, end)
    return build_factor_input_from_ohlcv(db, symbol, ohlcv_data.df, start=start, end=end)


def resolve_backtest_symbols(
    defn: StrategyDefinition, requested: list[str] | None
) -> list[str]:
    """백테스트 대상 종목 해석: 명시 요청 > 전략 universe(CLI/API 공유, drift 방지).

    watchlist(config/watchlist.yaml)는 jobs/daily.py 자동 파이프라인 전용 모니터링
    대상이며, 사용자가 임의 종목을 탐색하는 ad-hoc 백테스트(CLI/GUI)에는 관여하지
    않는다 — universe가 비어 있는데도 watchlist로 조용히 대체되면, 사용자가 명시
    요청한 종목이 아닌 엉뚱한 종목이 실행되고도 에러 없이 넘어가 혼란을 유발한다.

    동적 유니버스(kind="screening")는 종목이 시점마다 정해지므로 여기서 해석하지 않는다 —
    호출부가 `prepare_dynamic_universe`로 계획을 먼저 세워야 한다(P2).
    """
    if requested:
        return requested
    return list(defn.universe.symbols)


def prepare_dynamic_universe(
    defn: StrategyDefinition,
    *,
    start: date,
    end: date,
    resolve: ScreeningResolver,
    on_progress: Callable[[int, int, date], None] | None = None,
) -> DynamicUniversePlan:
    """동적 유니버스 계획 수립 — CLI/API 공유 진입점(P2).

    스크리닝 실행 자체는 주입된 `resolve`가 담당하므로 이 모듈은 screening 패키지를
    import하지 않는다(workspace ↔ screening 형제 관계 유지, EPIC-03 INV-1).
    """
    if not defn.universe.is_dynamic:
        raise ValueError("동적 유니버스 전략에만 사용할 수 있습니다")
    if defn.portfolio is None:
        # 저장 시점 검증이 이미 막지만(validate_definition), 직접 호출 경로 이중 방어.
        raise ValueError("동적 유니버스는 portfolio 정책이 필요합니다")
    return build_plan(
        defn.universe.screening_id,
        start=start, end=end, rebalance=defn.portfolio.rebalance,
        resolve=resolve, on_progress=on_progress,
    )


def _ohlcv_provider_for(data_source: str) -> DataProvider:
    """--data-source 문자열로 OHLCV 어댑터를 선택한다(무거운 provider는 lazy import)."""
    if data_source == "fixture":
        from quant_krx.data.fixture_adapter import FixtureAdapter

        return FixtureAdapter()
    if data_source == "fixture_10y":
        from quant_krx.data.fixture_adapter import FIXTURE_10Y_PATH, FixtureAdapter

        return FixtureAdapter(fixture_path=FIXTURE_10Y_PATH)
    if data_source == "krx_dart":
        from quant_krx.data.pykrx_adapter import PyKrxAdapter

        return PyKrxAdapter()
    raise ValueError(f"알 수 없는 data_source '{data_source}'(허용: {DATA_SOURCES})")


def _fetch_or_warn(
    db: Database,
    symbols: list[str],
    make_provider: Callable[[], FundamentalProvider],
    kinds: frozenset[str],
    *,
    start: date,
    end: date,
    on_warning: Callable[[str, Exception], None] | None,
    label: str,
    financials_kwargs: Mapping[str, object] | None = None,
) -> None:
    """provider 생성·수집 중 실패해도(예: DART_API_KEY 미설정) 다른 kind나 OHLCV 기반
    팩터 계산을 막지 않는다 — 실패분은 NaN으로 자연 degrade한다(기존 결측 처리 원칙과 동일)."""
    if not kinds:
        return
    provider: FundamentalProvider | None = None
    try:
        provider = make_provider()
        fetch_and_upsert_fundamentals(
            db, symbols, provider, start=start, end=end, as_of=date.today(), kinds=kinds,
            financials_kwargs=financials_kwargs,
        )
    except Exception as e:  # noqa: BLE001 — 펀더멘털 수집 실패는 백테스트 자체를 막지 않음
        if on_warning is not None:
            on_warning(label, e)
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()


def _fetch_fundamentals_for_backtest(
    db: Database,
    symbols: list[str],
    required_kinds: frozenset[str],
    *,
    data_source: str,
    start: date,
    end: date,
    on_warning: Callable[[str, Exception], None] | None,
) -> None:
    """valuation은 PyKrx, financials는 DART가 각각 전담한다 — 단일 provider가 둘 다 지원하지
    않으므로(`PyKrxFundamentalAdapter.fetch_financials`/`DartFundamentalAdapter.fetch_valuation`
    모두 `NotImplementedError`) kind별로 분리 수집하며, 한쪽 실패가 다른 kind를 막지 않는다.
    """
    if data_source in OFFLINE_DATA_SOURCES:
        # fixture_10y는 OHLCV만 10년치이고 펀더멘털 픽스처는 2024년 1년치뿐이다 —
        # 밸류에이션·재무 팩터를 쓰는 전략은 그 바깥 구간에서 NaN으로 자연 탈락한다.
        from quant_krx.data.fixture_fundamental import FixtureFundamentalAdapter

        _fetch_or_warn(
            db, symbols, FixtureFundamentalAdapter,
            required_kinds & {"valuation", "financials"},
            start=start, end=end, on_warning=on_warning, label=data_source,
        )
        return

    if "valuation" in required_kinds:
        from quant_krx.data.pykrx_fundamental import PyKrxFundamentalAdapter

        _fetch_or_warn(
            db, symbols, PyKrxFundamentalAdapter, frozenset({"valuation"}),
            start=start, end=end, on_warning=on_warning, label="valuation(pykrx)",
        )

    if "financials" in required_kinds:
        from quant_krx.data.dart_fundamental import DartFundamentalAdapter

        with db.cursor() as conn:
            skip_periods = existing_financials_periods(conn, symbols)

        _fetch_or_warn(
            db, symbols, DartFundamentalAdapter, frozenset({"financials"}),
            start=start, end=end, on_warning=on_warning, label="financials(dart)",
            financials_kwargs={"skip_periods": skip_periods} if skip_periods else None,
        )


def prepare_backtest_data(
    db: Database,
    defn: StrategyDefinition,
    symbols: list[str],
    *,
    data_source: str,
    start: date,
    end: date,
    benchmark: str | None,
    resolve_rule: RuleResolver,
    resolve_formula: FormulaResolver,
    on_benchmark_warning: Callable[[str, Exception], None] | None = None,
    on_symbol_error: Callable[[str, Exception], None] | None = None,
    on_fundamental_warning: Callable[[str, Exception], None] | None = None,
) -> tuple[dict[str, FactorInput], pd.DataFrame | None]:
    """`strategy-backtest` CLI(FR-11/12 경로)와 GUI API가 공유하는 백테스트 입력 조립.

    데이터소스 어댑터 선택 → (필요 시) 펀더멘털 증분 수집 → 종목별 FactorInput 조립 →
    벤치마크 수집까지 단일 경로로 수행한다. 두 소비자가 각자 재구현하면 drift가 생기므로
    이 함수 하나만 CLI/API가 공유한다(신규 계산 로직 없음, 기존 어댑터/헬퍼 조합만 재사용).

    종목별 FactorInput 조립은 jobs/daily.py와 동일한 종목 단위 실패 격리 원칙(FR-17)을
    따른다 — 상장 전/후 구간이라 OHLCV가 없는 종목, 조회 실패 종목 등 하나가 실패해도
    나머지 종목의 배치 전체를 막지 않고 건너뛴다(on_symbol_error로 사유 통지).
    """
    if data_source not in DATA_SOURCES:
        raise ValueError(f"알 수 없는 data_source '{data_source}'(허용: {DATA_SOURCES})")

    ohlcv_provider = _ohlcv_provider_for(data_source)

    required_kinds = strategy_required_data(defn, resolve_rule, resolve_formula)
    if required_kinds & {"valuation", "financials"}:
        _fetch_fundamentals_for_backtest(
            db, symbols, required_kinds,
            data_source=data_source, start=start, end=end,
            on_warning=on_fundamental_warning,
        )

    data: dict[str, FactorInput] = {}
    for sym in symbols:
        try:
            data[sym] = build_factor_input(
                db, sym, ohlcv_provider=ohlcv_provider, start=start, end=end
            )
        except Exception as e:  # noqa: BLE001 — 종목 단위 격리(FR-17), 원인은 on_symbol_error로 통지
            if on_symbol_error is not None:
                on_symbol_error(sym, e)

    benchmark_df: pd.DataFrame | None = None
    if benchmark:
        try:
            benchmark_df = ohlcv_provider.fetch_benchmark(benchmark, start, end).df
        except Exception as e:  # noqa: BLE001 — 벤치마크 실패는 백테스트 자체를 막지 않음(원 동작 유지)
            if on_benchmark_warning is not None:
                on_benchmark_warning(benchmark, e)

    return data, benchmark_df

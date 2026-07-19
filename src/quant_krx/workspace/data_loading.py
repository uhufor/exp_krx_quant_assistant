from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

import pandas as pd

from quant_krx.data.base import DataProvider
from quant_krx.data.fundamental_base import FundamentalProvider
from quant_krx.data.loader import load_factor_input
from quant_krx.data.upsert import upsert_fundamental
from quant_krx.factors import FactorInput
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import StrategyDefinition
from quant_krx.workspace.errors import EmptyOhlcvError
from quant_krx.workspace.evaluation import FormulaResolver, RuleResolver, strategy_required_data

DATA_SOURCES = ("fixture", "fdr", "pykrx")


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    result = df.set_index("date") if "date" in df.columns else df
    result.index = pd.to_datetime(result.index)
    result = result.sort_index()
    return result[["open", "high", "low", "close", "volume"]].astype(float)


def _existing_valuation_coverage(
    conn, symbols: list[str]
) -> dict[str, tuple[date, date]]:
    """symbol별 fundamental_daily 기존 커버리지(min/max date)를 조회한다."""
    if not symbols:
        return {}
    df = conn.execute(
        "SELECT symbol, MIN(date) AS min_date, MAX(date) AS max_date "
        "FROM fundamental_daily WHERE symbol = ANY(?) GROUP BY symbol",
        [symbols],
    ).df()
    return {
        row["symbol"]: (pd.Timestamp(row["min_date"]).date(), pd.Timestamp(row["max_date"]).date())
        for _, row in df.iterrows()
    }


def _gap_ranges(
    existing: tuple[date, date] | None, start: date, end: date
) -> list[tuple[date, date]]:
    """요청 구간[start, end] 중 기존 커버리지 밖(이전/이후)만 반환한다.

    기존 구간 내부(거래 캘린더상 자연스러운 결측 제외)는 재수집하지 않는다 — 이미 있는
    데이터는 건드리지 않고, 경계 바깥의 부족분만 최소로 채운다.
    """
    if existing is None:
        return [(start, end)]
    existing_min, existing_max = existing
    gaps: list[tuple[date, date]] = []
    if start < existing_min:
        gaps.append((start, min(existing_min - timedelta(days=1), end)))
    if end > existing_max:
        gaps.append((max(existing_max + timedelta(days=1), start), end))
    return gaps


def fetch_and_upsert_fundamentals(
    db: Database,
    symbols: list[str],
    provider: FundamentalProvider,
    *,
    start: date,
    end: date,
    as_of: date,
    kinds: frozenset[str],
) -> None:
    """required_data에 valuation/financials가 있을 때만 호출한다(AC-04 — ohlcv-only는 호출 0회).

    R01 FundamentalProvider·upsert_fundamental 단일 강제점·품질 게이트 경로를 그대로
    재사용하며(fetch-fundamental CLI와 동일 경로), 신규 수집 로직을 두지 않는다.

    valuation은 symbol별 기존 fundamental_daily 커버리지를 조회해, 요청 구간 중 이미
    확보된 부분은 건너뛰고 경계 바깥(이전/이후)만 증분 수집한다(라이브 provider 호출
    최소화 — PyKrx처럼 재로그인·개인 자격증명이 필요한 provider에서 중요).
    financials는 PK가 날짜 축이 아니므로(fiscal_year/quarter) 기존 방식(전체 재수집)을
    유지한다.
    """
    with db.cursor() as conn:
        if "valuation" in kinds:
            coverage = _existing_valuation_coverage(conn, symbols)
            grouped: dict[tuple[date, date], list[str]] = {}
            for symbol in symbols:
                for gap in _gap_ranges(coverage.get(symbol), start, end):
                    grouped.setdefault(gap, []).append(symbol)
            for (gap_start, gap_end), gap_symbols in grouped.items():
                frame = provider.fetch_valuation(gap_symbols, gap_start, gap_end)
                frame = frame.assign(source=provider.source_name, fetched_at=datetime.utcnow())
                upsert_fundamental(conn, "fundamental_daily", frame, as_of=as_of)
        if "financials" in kinds:
            frame = provider.fetch_financials(symbols, start, end)
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
    """
    if requested:
        return requested
    return list(defn.universe.symbols)


def _ohlcv_provider_for(data_source: str) -> DataProvider:
    """--data-source 문자열로 OHLCV 어댑터를 선택한다(무거운 provider는 lazy import)."""
    if data_source == "fixture":
        from quant_krx.data.fixture_adapter import FixtureAdapter

        return FixtureAdapter()
    if data_source == "fdr":
        from quant_krx.data.fdr_adapter import FDRAdapter

        return FDRAdapter()
    if data_source == "pykrx":
        from quant_krx.data.pykrx_adapter import PyKrxAdapter

        return PyKrxAdapter()
    raise ValueError(f"알 수 없는 data_source '{data_source}'(허용: {DATA_SOURCES})")


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
        if data_source == "fixture":
            from quant_krx.data.fixture_fundamental import FixtureFundamentalAdapter

            fundamental_provider: FundamentalProvider = FixtureFundamentalAdapter()
        else:
            from quant_krx.data.pykrx_fundamental import PyKrxFundamentalAdapter

            fundamental_provider = PyKrxFundamentalAdapter()
        fetch_and_upsert_fundamentals(
            db, symbols, fundamental_provider,
            start=start, end=end, as_of=date.today(), kinds=required_kinds,
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

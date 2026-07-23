from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from quant_krx.data.base import DataProvider
from quant_krx.factors import list_factors
from quant_krx.screening.definition import (
    Composition,
    FactorOperand,
    FormulaOperand,
    Node,
    Operand,
    Predicate,
    RankPredicate,
    ScreeningCondition,
    WindowPredicate,
)
from quant_krx.screening.errors import ScreeningError
from quant_krx.screening.evaluation import (
    ScreeningEvaluationContext,
    _eval_screening_node,
    default_factor_lookback_resolver,
    estimate_required_lookback,
)
from quant_krx.screening.ranking import apply_rank_predicates
from quant_krx.screening.universe import resolve_scan_universe
from quant_krx.screening.universe_data import fetch_universe_ohlcv_cached
from quant_krx.storage.db import Database

# RankPredicate.column이 가리켜야 하는 시장 스냅샷 네이티브 컬럼(ranking.py의 계약과 동일).
_SNAPSHOT_COLUMNS = frozenset({"close", "volume", "trading_value"})

# lookback 봉수를 달력일로 환산할 때의 여유 배수(주말·휴장일 보정). 정교한 거래일 캘린더
# 계산은 이 스토리 범위 밖 — 넉넉한 달력일 여유로 warm-up 구간을 확보한다.
_CALENDAR_DAY_MARGIN = 1.5


@dataclass(frozen=True)
class ValidationResult:
    """screening 전용 검증 결과 — R02 workspace.ValidationResult와 독립(INV-2)."""

    ok: bool
    errors: tuple[str, ...]


class ScreeningService:
    """스크리닝 조건 CRUD와 실행 오케스트레이션 파사드(EPIC-03).

    저장은 Database 게이트로 위임하고, run()은 유니버스 해석 → 순위 사전 계산 →
    OHLCV 확보 → 종목별 트리 평가를 조합하는 순수 조회/계산이다(실행 이력 미저장).
    """

    def __init__(self, db: Database, provider: DataProvider) -> None:
        self._db = db
        self._provider = provider

    # --- CRUD (Database 저장 게이트 위임) ---

    def upsert_condition(self, cond: ScreeningCondition, *, now: datetime) -> None:
        self._db.upsert_screening_condition(
            cond.id, name=cond.name, body=cond.to_dict(), now=now
        )

    def get_condition(self, id: str) -> ScreeningCondition | None:
        body = self._db.get_screening_condition(id)
        return ScreeningCondition.from_dict(body) if body is not None else None

    def list_conditions(self) -> tuple[ScreeningCondition, ...]:
        return tuple(
            ScreeningCondition.from_dict(body)
            for body in self._db.list_screening_conditions()
        )

    def delete_condition(self, id: str) -> None:
        self._db.delete_screening_condition(id)

    # --- 검증 (screening 전용 자체 검증) ---

    def validate_condition(self, cond: ScreeningCondition) -> ValidationResult:
        """조건 트리의 참조 무결성을 검증한다(팩터 id 존재·RankPredicate 컬럼·미지원 피연산자).

        구조 검증(arity/연산자/스키마 버전)은 from_dict 시점에 이미 강제되므로 여기서는
        실행 가능성에 직결되는 의미 검증만 수행한다.
        """
        known_factor_ids = {f.id for f in list_factors()}
        errors: list[str] = []
        _collect_validation_errors(cond.root, known_factor_ids, errors)
        return ValidationResult(ok=not errors, errors=tuple(errors))

    # --- 유니버스 사전 조회 (실행 전 대상 종목수 표시용, 시계열/순위 계산 없음) ---

    def count_universe(self, condition_id: str) -> int:
        """조건의 스캔 유니버스 크기만 빠르게 계산한다(OHLCV·순위 조회 없음).

        run() 전에 "대상 N종목"을 미리 보여주기 위한 경량 조회다 — list_symbols +
        제외 필터 적용만 수행하므로 전종목 시세 조회보다 훨씬 빠르다.
        """
        cond = self.get_condition(condition_id)
        if cond is None:
            raise ScreeningError(f"스크리닝 조건 '{condition_id}'을(를) 찾을 수 없습니다")
        return len(resolve_scan_universe(self._provider, cond.universe.exclusion_filters))

    # --- 실행 (순수 조회/계산, 이력 미저장) ---

    def run(
        self,
        condition_id: str,
        *,
        as_of: date | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[tuple[str, str]]:
        """on_progress(processed, total)는 OHLCV 확보 단계에서 종목 단위로 호출된다
        (total=유니버스 크기). 순위 사전계산·평가 단계는 진행률 콜백 대상이 아니다 —
        전체 소요시간의 대부분이 OHLCV fetch 단계에 있기 때문이다."""
        cond = self.get_condition(condition_id)
        if cond is None:
            raise ScreeningError(f"스크리닝 조건 '{condition_id}'을(를) 찾을 수 없습니다")

        if as_of is None:
            as_of = date.today()

        universe_symbols = resolve_scan_universe(
            self._provider, cond.universe.exclusion_filters
        )

        rank_membership = apply_rank_predicates(
            cond.root,
            provider=self._provider,
            symbols=universe_symbols,
            as_of=as_of,
            market=cond.universe.market,
        )

        lookback_bars = estimate_required_lookback(
            cond.root, factor_lookback_resolver=default_factor_lookback_resolver
        )
        start = as_of - timedelta(days=int(lookback_bars * _CALENDAR_DAY_MARGIN))
        ohlcv_by_symbol = fetch_universe_ohlcv_cached(
            self._db,
            self._provider,
            universe_symbols,
            start=start,
            end=as_of,
            market=cond.universe.market,
            on_progress=on_progress,
        )

        passed: list[str] = []
        for symbol in universe_symbols:
            raw = ohlcv_by_symbol.get(symbol)
            if raw is None or raw.empty:
                continue
            try:
                ohlcv = _prepare_symbol_ohlcv(raw)
                ctx = ScreeningEvaluationContext(
                    ohlcv=ohlcv,
                    index=ohlcv.index,
                    rank_membership=rank_membership,
                    current_symbol=symbol,
                )
                result = _eval_screening_node(cond.root, ctx)
                if bool(result.iloc[-1]):
                    passed.append(symbol)
            except Exception:  # noqa: BLE001 — 종목 단위 격리(하나 실패해도 나머지 계속)
                continue

        metadata = self._provider.fetch_metadata(passed)
        return [(s, metadata.get(s, {}).get("name", "")) for s in passed]


def _prepare_symbol_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    """DuckDB에서 조회한 종목 OHLCV 행을 평가 컨텍스트가 기대하는 형태로 정규화한다.

    date를 DatetimeIndex로 세우고 open/high/low/close/volume만 float로 남긴다
    (test_evaluation의 픽스처 로딩과 동일 형상).
    """
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def _validate_operand(operand: Operand, known_factor_ids: set[str], errors: list[str]) -> None:
    if isinstance(operand, FactorOperand):
        if operand.factor_id not in known_factor_ids:
            errors.append(f"미지의 팩터 id '{operand.factor_id}'(피연산자 참조)")
    elif isinstance(operand, FormulaOperand):
        errors.append(
            f"FormulaOperand(formula_id={operand.formula_id!r})는 screening에서 아직"
            " 지원되지 않습니다"
        )


def _collect_validation_errors(
    node: Node, known_factor_ids: set[str], errors: list[str]
) -> None:
    if isinstance(node, Predicate):
        _validate_operand(node.left, known_factor_ids, errors)
        _validate_operand(node.right, known_factor_ids, errors)
    elif isinstance(node, Composition):
        for child in node.operands:
            _collect_validation_errors(child, known_factor_ids, errors)
    elif isinstance(node, WindowPredicate):
        _collect_validation_errors(node.inner, known_factor_ids, errors)
    elif isinstance(node, RankPredicate):
        if node.column not in _SNAPSHOT_COLUMNS:
            errors.append(
                f"RankPredicate.column '{node.column}'은 시장 스냅샷 네이티브 컬럼이 아닙니다"
                f"(허용: {sorted(_SNAPSHOT_COLUMNS)})"
            )

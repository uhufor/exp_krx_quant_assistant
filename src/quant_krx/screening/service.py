from __future__ import annotations

import logging
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
    tree_requires_ohlcv,
)
from quant_krx.screening.ranking import apply_rank_predicates
from quant_krx.screening.universe import resolve_scan_universe
from quant_krx.screening.universe_data import fetch_universe_ohlcv_cached
from quant_krx.storage.db import Database

logger = logging.getLogger(__name__)

# RankPredicate.column이 가리켜야 하는 시장 스냅샷 네이티브 컬럼(ranking.py의 계약과 동일).
_SNAPSHOT_COLUMNS = frozenset({"close", "volume", "trading_value"})

# lookback 봉수를 달력일로 환산할 때의 여유 배수(주말·휴장일 보정). provider가
# list_trading_days를 지원하지 않을 때만 쓰는 폴백 추정치 — 지원하는 provider(PyKrx)는
# _compute_lookback_start가 실제 거래일 캘린더를 역산해 이 배수보다 정밀하게 계산한다.
_CALENDAR_DAY_MARGIN = 1.5

# _compute_lookback_start가 거래일 부족(공휴일 군집 등)으로 재시도할 최대 횟수 —
# 매 시도마다 조회 구간을 2배로 넓힌다.
_MAX_LOOKBACK_EXPANSION_ATTEMPTS = 3

# 빈 DataFrame(순수 RankPredicate 조건 평가용) — OHLCV 확보 자체가 불필요한 트리에서
# ScreeningEvaluationContext.ohlcv 자리를 채우는 더미 값(RankPredicate 평가는 이를
# 참조하지 않는다, tree_requires_ohlcv 참고).
_EMPTY_OHLCV = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


def _compute_lookback_start(provider: DataProvider, as_of: date, lookback_bars: int) -> date:
    """lookback_bars개의 실제 거래일을 확보할 수 있는 달력 시작일을 계산한다.

    provider가 list_trading_days를 지원하면(PyKrx) 실제 거래일 캘린더를 역산해 정확한
    시작일을 구한다 — 고정 배수(_CALENDAR_DAY_MARGIN) 추정은 설/추석 등 공휴일 군집
    구간에서 거래일 수를 과소평가해 warm-up 부족(팩터 NaN → 조용한 탈락)을 유발할 수
    있기 때문이다. 조회 구간에 거래일이 부족하면 구간을 2배씩 넓혀 재시도하고, 그래도
    부족하면(available data 자체가 짧은 경우) 마지막 후보 시작일로 폴백한다 — 명확한
    실패보다 최대한 확보한 이력으로 계속 진행하는 편이 더 안전하다. list_trading_days를
    지원하지 않는 provider(FDR/Fixture)는 기존 배수 추정으로 폴백한다.
    """
    if lookback_bars <= 0:
        return as_of
    if not hasattr(provider, "list_trading_days"):
        return as_of - timedelta(days=int(lookback_bars * _CALENDAR_DAY_MARGIN))

    margin = _CALENDAR_DAY_MARGIN
    candidate_start = as_of
    for _ in range(_MAX_LOOKBACK_EXPANSION_ATTEMPTS):
        candidate_start = as_of - timedelta(days=int(lookback_bars * margin))
        trading_days = provider.list_trading_days(candidate_start, as_of)
        if len(trading_days) >= lookback_bars + 1:
            return sorted(trading_days)[-(lookback_bars + 1)]
        margin *= 2
    return candidate_start


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
    ) -> list[tuple[str, str, str]]:
        """반환은 (symbol, name, market) 튜플 목록 — market은 provider.fetch_metadata가
        채운 "KOSPI"/"KOSDAQ"/미상 시 빈 문자열이다. on_progress(processed, total)는
        OHLCV 확보 단계에서 종목 단위로 호출된다(total=유니버스 크기). 순위 사전계산·평가
        단계는 진행률 콜백 대상이 아니다 — 전체 소요시간의 대부분이 OHLCV fetch 단계에
        있기 때문이다."""
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

        # 조건 트리가 RankPredicate로만 구성되면(예: "거래대금 Top100 AND 거래량 Top100")
        # OHLCV 확보 자체가 불필요하다 — 생략하면 순위 조건이 무관한 OHLCV 결측/일시 조회
        # 실패에 영향받지 않고(정확성), 대량 fetch도 피한다(성능). tree_requires_ohlcv 참고.
        requires_ohlcv = tree_requires_ohlcv(cond.root)
        ohlcv_by_symbol: dict[str, pd.DataFrame] = {}
        if requires_ohlcv:
            lookback_bars = estimate_required_lookback(
                cond.root, factor_lookback_resolver=default_factor_lookback_resolver
            )
            start = _compute_lookback_start(self._provider, as_of, lookback_bars)
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
        eval_attempts = 0
        eval_errors = 0
        last_error: Exception | None = None
        static_index = pd.DatetimeIndex([pd.Timestamp(as_of)])
        for symbol in universe_symbols:
            if requires_ohlcv:
                raw = ohlcv_by_symbol.get(symbol)
                if raw is None or raw.empty:
                    continue
                ohlcv = _prepare_symbol_ohlcv(raw)
                index = ohlcv.index
            else:
                ohlcv = _EMPTY_OHLCV
                index = static_index

            eval_attempts += 1
            try:
                ctx = ScreeningEvaluationContext(
                    ohlcv=ohlcv,
                    index=index,
                    rank_membership=rank_membership,
                    current_symbol=symbol,
                )
                result = _eval_screening_node(cond.root, ctx)
                if bool(result.iloc[-1]):
                    passed.append(symbol)
            except Exception as e:  # noqa: BLE001 — 종목 단위 격리(하나 실패해도 나머지 계속)
                eval_errors += 1
                last_error = e
                logger.warning("종목 %s 스크리닝 평가 실패, 건너뜀: %s", symbol, e)

        # 모든 평가 시도가 동일하게 실패했다면 종목별 데이터 이슈가 아니라 조건 정의/코드
        # 오류일 가능성이 높다 — "정상적으로 0종목 통과"와 구분되도록 명시적으로 실패시킨다.
        if eval_attempts > 0 and eval_errors == eval_attempts:
            raise ScreeningError(
                f"스크리닝 평가 중 시도한 {eval_attempts}개 종목이 모두 실패했습니다"
                f"(조건 정의 오류 가능성) — 마지막 오류: {last_error}"
            ) from last_error

        metadata = self._provider.fetch_metadata(passed)
        return [
            (s, metadata.get(s, {}).get("name", ""), metadata.get(s, {}).get("market", ""))
            for s in passed
        ]


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
        if node.factor_id not in known_factor_ids:
            errors.append(f"미지의 팩터 id '{node.factor_id}'(RankPredicate 참조)")

"""동적(스크리닝) 유니버스 실행 계획(P2).

동적 유니버스에는 닭-달걀 문제가 있다. 백테스트를 돌리려면 대상 종목의 OHLCV를 **미리**
수집해야 하는데, 대상 종목은 리밸런싱 시점마다 스크리닝으로 정해진다. 그렇다고 엔진이
거래일 인덱스를 확정한 뒤에 종목을 정하면, 그때는 이미 데이터 수집이 끝난 뒤다.

그래서 실행 계층이 먼저 **계획**을 세운다:

1. 백테스트 구간을 리밸런싱 주기로 잘라 달력 기준 앵커 날짜를 만든다(월간이면 각 월 1일).
2. 앵커마다 스크리닝을 실행해 통과 종목을 구한다(결과는 DB 캐시로 재사용).
3. 전 앵커의 합집합이 OHLCV 수집 대상이 된다.
4. 엔진이 **실제 거래일** 기준 리밸런싱일 d로 유니버스를 물으면, d 이하 가장 최근 앵커의
   결과를 돌려준다(backward 매칭).

4번이 중요하다. 앵커(달력)와 엔진의 리밸런싱일(실제 거래일)은 며칠 어긋날 수 있는데,
backward 매칭이 없으면 엔진이 계획에 없는 날짜로 스크리닝을 다시 돌려 수집하지 않은 종목이
튀어나온다 — 그 종목은 가격 데이터가 없어 조용히 탈락하므로 "왜 안 담겼는지 알 수 없는"
결과가 된다. 매칭해 두면 수집 대상과 실제 후보가 항상 일치한다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import pandas as pd

from quant_krx.workspace.errors import EvaluationError

logger = logging.getLogger(__name__)

# 리밸런싱 주기 -> pandas 기간 문자열. workspace/portfolio.py::_PERIOD_FREQ와 짝을 이룬다
# (그쪽은 실제 거래일 인덱스를 쪼개고, 이쪽은 달력에서 앵커를 만든다).
_ANCHOR_FREQ = {"weekly": "W-MON", "monthly": "MS", "quarterly": "QS"}

ScreeningResolver = Callable[[str, date], list[str]]


def anchor_dates(start: date, end: date, rebalance: str) -> list[date]:
    """구간을 리밸런싱 주기로 자른 달력 앵커 날짜. 시작일은 항상 포함된다."""
    freq = _ANCHOR_FREQ.get(rebalance)
    if freq is None:
        raise EvaluationError(
            f"미지의 rebalance '{rebalance}'(허용: {sorted(_ANCHOR_FREQ)})"
        )
    stamps = pd.date_range(start=start, end=end, freq=freq)
    dates = [ts.date() for ts in stamps]
    if not dates or dates[0] != start:
        dates.insert(0, start)  # 첫 구간이 비지 않도록 시작일을 앵커로 포함
    return dates


@dataclass(frozen=True)
class DynamicUniversePlan:
    """앵커별 스크리닝 결과와 그 조회 인터페이스."""

    screening_id: str
    by_anchor: dict[date, tuple[str, ...]]

    @property
    def symbols(self) -> list[str]:
        """전 앵커 통과 종목의 합집합 — OHLCV 수집 대상."""
        union: set[str] = set()
        for symbols in self.by_anchor.values():
            union |= set(symbols)
        return sorted(union)

    def eligible_at(self, screening_id: str, as_of: date) -> list[str]:
        """as_of 이하 가장 최근 앵커의 통과 종목(backward 매칭).

        엔진이 주입받는 리졸버 형상(screening_id, as_of)을 그대로 만족한다.
        """
        if screening_id != self.screening_id:
            raise EvaluationError(
                f"계획에 없는 스크리닝 '{screening_id}'을(를) 조회했습니다"
                f"(계획: '{self.screening_id}')"
            )
        candidates = [anchor for anchor in self.by_anchor if anchor <= as_of]
        if not candidates:
            # as_of가 첫 앵커보다 이르면 아직 유니버스가 정해지지 않은 구간이다.
            return []
        return list(self.by_anchor[max(candidates)])


def build_plan(
    screening_id: str,
    *,
    start: date,
    end: date,
    rebalance: str,
    resolve: ScreeningResolver,
    on_progress: Callable[[int, int, date], None] | None = None,
) -> DynamicUniversePlan:
    """앵커마다 스크리닝을 실행해 계획을 만든다.

    한 앵커에서 스크리닝이 실패해도 전체를 중단하지 않는다 — 그 시점은 빈 유니버스가 되고
    (해당 구간은 현금 보유) 나머지 구간은 정상 실행된다. 전 구간이 실패하면 합집합이 비어
    호출부가 "대상 종목 없음"으로 명확히 실패한다.
    """
    anchors = anchor_dates(start, end, rebalance)
    by_anchor: dict[date, tuple[str, ...]] = {}
    for i, anchor in enumerate(anchors, start=1):
        try:
            by_anchor[anchor] = tuple(resolve(screening_id, anchor))
        except Exception as e:  # noqa: BLE001 — 시점 단위 격리(위 docstring)
            logger.warning("%s 시점 스크리닝 실패, 해당 구간은 빈 유니버스로 처리: %s", anchor, e)
            by_anchor[anchor] = ()
        if on_progress is not None:
            on_progress(i, len(anchors), anchor)
    return DynamicUniversePlan(screening_id=screening_id, by_anchor=by_anchor)

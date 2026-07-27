"""포트폴리오 백테스트의 목표 비중 계산(P1).

vectorbt의 `from_signals`로는 "최대 N종목 동시 보유"를 표현할 수 없다 — 신호는 종목마다
독립적이고 자본 제약을 모르기 때문이다. 그래서 신호를 **목표 비중 행렬**로 먼저 변환한 뒤
`from_orders(size_type='targetpercent', cash_sharing=True)`에 넘긴다. 이 모듈은 그 변환만
담당하는 순수 계산이며(pandas 외 의존 없음), vectorbt를 import하지 않는다.

확정된 정책(사용자 결정):
- **거래는 리밸런싱 시점에만** 일어난다. 사이의 진입·청산 신호는 "보유 의도" 상태로만 누적되고,
  실제 매매는 각 주기의 첫 거래일에 한 번에 반영된다.
- **후보가 max_positions보다 많으면 ranking 값으로 줄을 세운다.** ranking 미지정 시에는
  종목코드 오름차순으로 결정론만 보장한다(임의 기준을 몰래 끼워넣지 않는다 — D5).
- **균등 분배.** 선택된 종목 수 k로 1/k씩 배분한다(1/max_positions 고정이 아니다 — 후보가
  N보다 적을 때 자본을 놀리지 않는다).
"""

from __future__ import annotations

import pandas as pd

from quant_krx.strategy.definition import PortfolioPolicy
from quant_krx.workspace.errors import EvaluationError

# 리밸런싱 주기 -> pandas 기간 변환 규칙. 각 기간의 첫 거래일이 리밸런싱일이 된다.
_PERIOD_FREQ = {"weekly": "W", "monthly": "M", "quarterly": "Q"}


def holding_intent(entries: pd.DataFrame, exits: pd.DataFrame) -> pd.DataFrame:
    """진입·청산 신호를 "보유하고 싶은 상태"의 시계열로 바꾼다.

    entry=True면 보유 시작, exit=True면 보유 종료, 아무 신호도 없는 날은 직전 상태를 유지한다.
    같은 날 진입과 청산이 동시에 발생하면 **청산이 이긴다** — 두 조건을 동시에 만족하는
    모호한 상태에서 포지션을 잡는 것보다 잡지 않는 쪽이 보수적이기 때문이다.
    """
    # 1.0=보유 시작, 0.0=보유 종료, NaN=신호 없음(직전 상태 유지). object dtype 대신 float를
    # 쓰는 이유는 pandas의 object 다운캐스팅 경고를 피하면서 ffill 의미를 그대로 살리기 위함.
    state = pd.DataFrame(float("nan"), index=entries.index, columns=entries.columns)
    state = state.mask(entries.fillna(False).astype(bool), 1.0)
    state = state.mask(exits.fillna(False).astype(bool), 0.0)  # 동시 발생 시 청산 우선(위 주석)
    return state.ffill().fillna(0.0).astype(bool)


def rebalance_dates(index: pd.DatetimeIndex, rebalance: str) -> pd.DatetimeIndex:
    """각 주기 구간의 첫 거래일 목록.

    달력일이 아니라 실제 데이터 인덱스에서 고르므로 휴장일에 리밸런싱이 잡히지 않는다.
    데이터 첫날은 항상 포함된다 — 그렇지 않으면 첫 구간 내내 포지션이 비어 있게 된다.
    """
    freq = _PERIOD_FREQ.get(rebalance)
    if freq is None:
        raise EvaluationError(
            f"미지의 rebalance '{rebalance}'(허용: {sorted(_PERIOD_FREQ)})"
        )
    if len(index) == 0:
        return pd.DatetimeIndex([])
    periods = index.to_period(freq)
    first_of_period = ~pd.Series(periods, index=index).duplicated()
    return index[first_of_period.to_numpy()]


def _select_symbols(
    candidates: list[str], scores: pd.Series | None, policy: PortfolioPolicy
) -> list[str]:
    """후보 중 max_positions개를 고른다. 동점·결측은 종목코드 오름차순으로 결정론 확보."""
    if scores is None:
        ordered = sorted(candidates)
    else:
        # 점수가 NaN인 종목은 순위를 매길 수 없으므로 후보에서 제외한다 — 임의 값으로
        # 채워 넣으면 데이터가 없는 종목이 상위에 올라올 수 있다.
        scored = [(symbol, scores.get(symbol)) for symbol in candidates]
        valid = [(s, v) for s, v in scored if v is not None and pd.notna(v)]
        ordered = [
            symbol
            for symbol, _ in sorted(
                valid, key=lambda kv: (-kv[1] if policy.ranking.descending else kv[1], kv[0])
            )
        ]
    return ordered[: policy.max_positions]


def build_target_weights(
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    policy: PortfolioPolicy,
    *,
    ranking_scores: pd.DataFrame | None = None,
    tradable: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """목표 비중 행렬을 만든다.

    리밸런싱일에만 값이 채워지고 나머지 날은 NaN이다(NaN = 주문 없음 = 기존 포지션 유지).
    미선택 종목에는 0을 넣어 명시적으로 청산시킨다 — NaN으로 두면 이전 비중이 유지된다.

    `tradable`은 해당 시점에 실제 가격 데이터가 있는지 여부다(상장 전/데이터 결손 구간
    제외용). 지정하면 그 구간의 종목은 후보에서 빠진다.
    """
    index = entries.index
    intent = holding_intent(entries, exits)
    if tradable is not None:
        intent = intent & tradable.reindex(index=index, columns=intent.columns).fillna(False)

    weights = pd.DataFrame(float("nan"), index=index, columns=entries.columns)
    for date in rebalance_dates(index, policy.rebalance):
        candidates = [symbol for symbol in intent.columns if bool(intent.at[date, symbol])]
        scores = (
            ranking_scores.loc[date]
            if ranking_scores is not None and date in ranking_scores.index
            else None
        )
        selected = _select_symbols(candidates, scores, policy)
        weights.loc[date] = 0.0  # 미선택 종목은 명시적 청산
        if selected:
            weights.loc[date, selected] = 1.0 / len(selected)  # 균등 분배(선택 수 기준)
    return weights

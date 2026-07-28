"""검증 폴드 분할(P4) — 순수 날짜 계산, 백테스트·저장 계층 미참조.

전 구간 성과 하나만 보면 "그 숫자가 미래에도 재현될지"를 알 수 없다. 구간을 학습(IS)과
검증(OOS)으로 나눠 **파라미터를 고른 구간과 성과를 측정한 구간을 분리**하는 것이 목적이다.

분할은 거래일이 아니라 **달력 기준**이다(P2 동적 유니버스 앵커와 같은 관례) — 거래일
기준으로 나누면 종목마다 다른 결손일 때문에 폴드 경계가 종목별로 달라진다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

VALIDATION_MODES = ("holdout", "walkforward")

# 폴드 하나가 이보다 짧으면 지표가 의미를 갖지 못한다(거래가 몇 건 나오지 않음).
MIN_SEGMENT_DAYS = 30


class FoldSpecError(ValueError):
    """폴드 분할이 불가능한 설정(구간이 너무 짧거나 파라미터가 범위를 벗어남)."""


@dataclass(frozen=True)
class Fold:
    """학습 구간과 그 직후의 검증 구간 한 쌍. train_end < test_start가 항상 성립한다."""

    index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Fold:
        return cls(
            index=int(d["index"]),
            train_start=date.fromisoformat(d["train_start"]),
            train_end=date.fromisoformat(d["train_end"]),
            test_start=date.fromisoformat(d["test_start"]),
            test_end=date.fromisoformat(d["test_end"]),
        )


def build_folds(
    start: date,
    end: date,
    *,
    mode: str = "walkforward",
    n_folds: int = 3,
    test_ratio: float = 0.3,
    anchored: bool = True,
) -> tuple[Fold, ...]:
    """[start, end]를 학습/검증 폴드로 나눈다.

    전체 구간의 뒤쪽 `test_ratio`를 검증에 쓰고, 그 검증 구간을 다시 `n_folds`로 쪼갠다.
    각 폴드의 학습 구간은 자기 검증 구간 직전까지다.

    - `anchored=True`(확장창): 학습 시작은 항상 `start` — 데이터를 버리지 않는다.
    - `anchored=False`(롤링창): 학습 길이를 고정해 뒤로 밀며, 오래된 국면을 잊는다.
    - `mode="holdout"`은 `n_folds=1`의 특수형이다(단일 분할).

    경계는 반닫힘이 아니라 **닫힌 구간**이며 하루도 겹치지 않는다
    (`train_end = test_start - 1일`) — 겹치면 학습 구간의 정보가 검증에 새어 들어간다.
    """
    if mode not in VALIDATION_MODES:
        raise FoldSpecError(f"미지의 mode '{mode}'(허용: {list(VALIDATION_MODES)})")
    if mode == "holdout":
        n_folds = 1
    if n_folds < 1:
        raise FoldSpecError(f"n_folds는 1 이상이어야 합니다(입력: {n_folds})")
    if not 0.0 < test_ratio < 1.0:
        raise FoldSpecError(f"test_ratio는 0과 1 사이여야 합니다(입력: {test_ratio})")
    if end <= start:
        raise FoldSpecError(f"end({end})는 start({start})보다 뒤여야 합니다")

    total_days = (end - start).days + 1
    train_days = int(total_days * (1.0 - test_ratio))
    test_days = (total_days - train_days) // n_folds

    if train_days < MIN_SEGMENT_DAYS:
        raise FoldSpecError(
            f"학습 구간이 {train_days}일로 너무 짧습니다(최소 {MIN_SEGMENT_DAYS}일)"
            f" — 전체 기간을 늘리거나 test_ratio를 낮추십시오"
        )
    if test_days < MIN_SEGMENT_DAYS:
        raise FoldSpecError(
            f"폴드당 검증 구간이 {test_days}일로 너무 짧습니다(최소 {MIN_SEGMENT_DAYS}일)"
            f" — 폴드 수를 줄이거나 전체 기간을 늘리십시오"
        )

    folds: list[Fold] = []
    for i in range(n_folds):
        test_start = start + timedelta(days=train_days + i * test_days)
        # 마지막 폴드는 나눗셈 나머지를 흡수해 end까지 덮는다(구간이 잘려 버려지지 않게).
        test_end = end if i == n_folds - 1 else test_start + timedelta(days=test_days - 1)
        train_end = test_start - timedelta(days=1)
        train_start = start if anchored else max(start, train_end - timedelta(days=train_days - 1))
        folds.append(
            Fold(
                index=i,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
    return tuple(folds)

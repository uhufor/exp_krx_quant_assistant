from __future__ import annotations

from datetime import date, timedelta

import pytest

from quant_krx.workspace.walkforward import Fold, FoldSpecError, build_folds

START = date(2020, 1, 1)
END = date(2024, 12, 31)


def test_no_overlap_between_train_and_test():
    """학습 구간이 검증 구간과 하루라도 겹치면 정보가 새어 들어가 검증이 무의미해진다."""
    for fold in build_folds(START, END, n_folds=3):
        assert fold.train_end < fold.test_start
        assert fold.test_start - fold.train_end == timedelta(days=1)


def test_folds_cover_the_tail_without_gaps():
    folds = build_folds(START, END, n_folds=3)
    assert folds[-1].test_end == END
    for prev, nxt in zip(folds, folds[1:], strict=False):
        assert nxt.test_start - prev.test_end == timedelta(days=1)


def test_anchored_keeps_train_start_fixed():
    folds = build_folds(START, END, n_folds=3, anchored=True)
    assert {f.train_start for f in folds} == {START}


def test_rolling_moves_train_window_forward():
    """롤링창은 학습 길이를 유지한 채 뒤로 민다 — 오래된 국면을 잊는 설정."""
    folds = build_folds(START, END, n_folds=3, anchored=False)
    starts = [f.train_start for f in folds]
    assert starts == sorted(starts)
    assert len(set(starts)) == 3
    lengths = {(f.train_end - f.train_start).days for f in folds}
    assert len(lengths) == 1  # 길이 고정


def test_holdout_is_single_fold():
    folds = build_folds(START, END, mode="holdout", n_folds=5)
    assert len(folds) == 1
    assert folds[0].test_end == END


def test_test_ratio_controls_split_point():
    small = build_folds(START, END, mode="holdout", test_ratio=0.2)[0]
    large = build_folds(START, END, mode="holdout", test_ratio=0.5)[0]
    assert small.test_start > large.test_start


def test_rejects_unknown_mode():
    with pytest.raises(FoldSpecError, match="미지의 mode"):
        build_folds(START, END, mode="cv")


@pytest.mark.parametrize("ratio", [0.0, 1.0, -0.1, 1.5])
def test_rejects_out_of_range_test_ratio(ratio):
    with pytest.raises(FoldSpecError, match="test_ratio"):
        build_folds(START, END, test_ratio=ratio)


def test_rejects_reversed_range():
    with pytest.raises(FoldSpecError, match="뒤여야"):
        build_folds(END, START)


def test_rejects_too_short_train_segment():
    """학습 구간이 며칠뿐이면 거래가 몇 건 나오지 않아 지표가 의미를 잃는다."""
    with pytest.raises(FoldSpecError, match="학습 구간"):
        build_folds(date(2024, 1, 1), date(2024, 2, 1), mode="holdout", test_ratio=0.5)


def test_rejects_too_many_folds_for_range():
    with pytest.raises(FoldSpecError, match="검증 구간"):
        build_folds(date(2024, 1, 1), date(2024, 12, 31), n_folds=20)


def test_fold_roundtrips_through_dict():
    fold = build_folds(START, END, n_folds=2)[1]
    assert Fold.from_dict(fold.to_dict()) == fold

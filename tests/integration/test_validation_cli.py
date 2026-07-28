from __future__ import annotations

import json
import re
from datetime import datetime

from typer.testing import CliRunner

from quant_krx.__main__ import app
from quant_krx.rule.definition import ConstantOperand, FactorOperand, Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.service import WorkspaceService

runner = CliRunner(env={"COLUMNS": "220"})
NOW = datetime(2026, 1, 1)

# fixture는 2024-12-18까지의 252거래일 — 폴드가 성립하도록 넉넉히 잡는다.
START = "2024-01-02"
END = "2024-12-18"


def _seed(tmp_path, monkeypatch, strategy_id: str = "val_test") -> None:
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    db = Database(path=db_path)
    db.connect()
    svc = WorkspaceService(db)
    svc.upsert_rule(
        Rule(
            id="entry_rule", name="entry", version="1",
            root=Predicate(
                FactorOperand("sma", "sma", {"window": 5}), ">",
                FactorOperand("sma", "sma", {"window": 20}),
            ),
        ),
        now=NOW,
    )
    # 임계값 스윕 대상 — 단일 Predicate + 우변 상수 형상이라야 오버레이가 걸린다.
    svc.upsert_rule(
        Rule(
            id="threshold_rule", name="threshold", version="1",
            root=Predicate(FactorOperand("rsi", "rsi", {}), "<", ConstantOperand(70.0)),
        ),
        now=NOW,
    )
    svc.upsert_strategy(
        StrategyDefinition(
            id=strategy_id, name=strategy_id, version="1",
            factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
            universe=Universe(symbols=("005930",)),
            rule=RuleBinding(entry=("entry_rule",)),
        ),
        now=NOW,
    )
    svc.upsert_strategy(
        StrategyDefinition(
            id="thr_test", name="thr_test", version="1",
            factor_refs=(FactorRef("rsi"),),
            universe=Universe(symbols=("005930",)),
            rule=RuleBinding(entry=("threshold_rule",)),
        ),
        now=NOW,
    )
    db.close()


def _run(*extra: str, strategy_id: str = "val_test"):
    return runner.invoke(
        app,
        [
            "validation-run", strategy_id,
            "--data-source", "fixture", "--start", START, "--end", END,
            *extra,
        ],
    )


def _validation_id_from(stdout: str) -> str:
    match = re.search(r"validation_id=(\S+?)[,)\s]", stdout + " ")
    assert match, f"stdout에서 validation_id를 찾지 못했습니다: {stdout}"
    return match.group(1)


# --- 실행 ---


def test_holdout_run_prints_summary(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    result = _run("--mode", "holdout")

    assert result.exit_code == 0, result.stdout
    assert "검증 요약" in result.stdout
    assert "성과 저하율" in result.stdout
    assert "폴드별 결과" in result.stdout


def test_walkforward_run_shows_each_fold(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    result = _run("--folds", "2", "--test-ratio", "0.4")

    assert result.exit_code == 0, result.stdout
    assert "2/2 성공" in result.stdout


def test_run_is_persisted_and_listable(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    run_result = _run("--mode", "holdout")
    validation_id = _validation_id_from(run_result.stdout)

    listed = runner.invoke(app, ["validation-list"])
    assert listed.exit_code == 0
    assert validation_id in listed.stdout


def test_show_reproduces_the_same_summary(monkeypatch, tmp_path):
    """저장/복원을 거쳐도 실행 직후와 같은 표가 나와야 한다(직렬화 계약 확인)."""
    _seed(tmp_path, monkeypatch)
    run_result = _run("--mode", "holdout")
    validation_id = _validation_id_from(run_result.stdout)

    shown = runner.invoke(app, ["validation-show", validation_id])
    assert shown.exit_code == 0, shown.stdout
    assert "검증 요약" in shown.stdout
    assert "OOS 합성 수익률" in shown.stdout


def test_show_rejects_unknown_id(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    result = runner.invoke(app, ["validation-show", "nope"])
    assert result.exit_code == 1
    assert "찾을 수 없습니다" in result.stdout


def test_list_is_empty_before_any_run(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    result = runner.invoke(app, ["validation-list"])
    assert result.exit_code == 0
    assert "저장된 검증 이력이 없습니다" in result.stdout


# --- 파라미터 그리드 ---


def test_grid_from_spec_file_selects_parameters(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps({"mode": "holdout", "grid": {"factor.sma@5.window": [3, 5]}}),
        encoding="utf-8",
    )

    result = _run("--spec", str(spec))

    assert result.exit_code == 0, result.stdout
    assert "factor.sma@5.window=" in result.stdout


def test_cli_option_overrides_spec_file(monkeypatch, tmp_path):
    """그리드는 스펙 파일에 두고 폴드 수만 바꿔가며 돌리는 흐름을 지원한다."""
    _seed(tmp_path, monkeypatch)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"mode": "walkforward", "n_folds": 3}), encoding="utf-8")

    result = _run("--spec", str(spec), "--mode", "holdout")

    assert result.exit_code == 0, result.stdout
    assert "1/1 성공" in result.stdout


def test_unknown_spec_field_is_rejected(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"purge_days": 5}), encoding="utf-8")

    result = _run("--spec", str(spec))

    assert result.exit_code == 1
    assert "미지의 스펙 필드" in result.stdout


def test_unknown_objective_is_rejected(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    result = _run("--objective", "omega")
    assert result.exit_code == 1
    assert "미지의 objective" in result.stdout


def test_impossible_fold_split_fails_with_reason(monkeypatch, tmp_path):
    """폴드가 성립하지 않으면 Traceback이 아니라 이유를 보여준다."""
    _seed(tmp_path, monkeypatch)
    result = _run("--folds", "30")

    assert result.exit_code == 1
    assert "검증 구간" in result.stdout
    assert "Traceback" not in result.stdout


def test_unknown_strategy_is_rejected(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    result = _run(strategy_id="nope")
    assert result.exit_code == 1
    assert "찾을 수 없습니다" in result.stdout


def test_unknown_data_source_is_rejected(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    result = runner.invoke(
        app, ["validation-run", "val_test", "--data-source", "yahoo"]
    )
    assert result.exit_code == 1
    assert "알 수 없는 --data-source" in result.stdout


def test_validation_does_not_pollute_backtest_history(monkeypatch, tmp_path):
    """검증 내부 실행이 backtest_runs에 쌓이면 사용자가 의도적으로 돌린 이력이 파묻힌다."""
    _seed(tmp_path, monkeypatch)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps({"mode": "holdout", "grid": {"factor.sma@5.window": [3, 5]}}),
        encoding="utf-8",
    )
    assert _run("--spec", str(spec)).exit_code == 0

    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    try:
        assert db.list_backtest_runs() == []
        assert len(db.list_validation_runs()) == 1
    finally:
        db.close()


def test_rule_threshold_sweep_runs_end_to_end(monkeypatch, tmp_path):
    """룰 임계값 스윕이 저장된 룰을 건드리지 않고 실제로 반영되어야 한다."""
    _seed(tmp_path, monkeypatch)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps({"mode": "holdout", "grid": {"rule.threshold_rule.threshold": [30, 50, 70]}}),
        encoding="utf-8",
    )

    result = _run("--spec", str(spec), strategy_id="thr_test")

    assert result.exit_code == 0, result.stdout
    assert "rule.threshold_rule.threshold=" in result.stdout

    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    try:
        stored = db.get_rule("threshold_rule")
        assert stored.root.right.value == 70.0  # 저장된 정의는 그대로
    finally:
        db.close()


def test_grid_typo_reports_reason_not_all_folds_failed(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"grid": {"rule.no_such.threshold": [1, 2]}}), encoding="utf-8")

    result = _run("--spec", str(spec), "--mode", "holdout")

    assert result.exit_code == 1
    assert "파라미터 그리드 오류" in result.stdout
    assert "모든 폴드" not in result.stdout


def test_composite_rule_threshold_fails_fast(monkeypatch, tmp_path):
    """AND/OR 결합 룰은 임계값을 특정할 수 없다 — 폴드를 다 돌기 전에 이유를 알려야 한다."""
    _seed(tmp_path, monkeypatch)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"grid": {"rule.entry_rule.threshold": [1, 2]}}), encoding="utf-8")

    result = _run("--spec", str(spec), "--mode", "holdout")

    assert result.exit_code == 1
    assert "파라미터 그리드 오류" in result.stdout
    assert "상수 피연산자가 없습니다" in result.stdout


def test_accepts_fixture_10y_data_source(monkeypatch, tmp_path):
    """10년치 실데이터 픽스처로 워크포워드가 끝까지 도는지 — 롤링창은 긴 구간이라야 의미가 있다."""
    _seed(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "validation-run", "val_test", "--data-source", "fixture_10y",
            "--start", "2015-01-02", "--end", "2024-12-30",
            "--folds", "3", "--rolling",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "3/3 성공" in result.stdout
    assert "롤링창" in result.stdout


def test_rolling_and_anchored_differ_on_long_history(monkeypatch, tmp_path):
    """확장창은 학습 시작이 고정, 롤링창은 뒤로 밀린다 — 10년 구간에서 실제로 갈려야 한다."""
    _seed(tmp_path, monkeypatch)
    period = ["--start", "2015-01-02", "--end", "2024-12-30", "--folds", "3"]
    base = ["validation-run", "val_test", "--data-source", "fixture_10y", *period]

    anchored = runner.invoke(app, [*base, "--anchored"])
    rolling = runner.invoke(app, [*base, "--rolling"])
    assert anchored.exit_code == 0 and rolling.exit_code == 0

    # 확장창은 모든 폴드의 학습 시작이 2015-01-02, 롤링창은 폴드마다 다르다.
    assert anchored.stdout.count("2015-01-02~") == 3
    assert rolling.stdout.count("2015-01-02~") == 1


def test_list_distinguishes_anchored_from_rolling(monkeypatch, tmp_path):
    """두 방식을 대조 실행하는 것이 표준 사용법이므로 목록에서 구분되어야 한다."""
    _seed(tmp_path, monkeypatch)
    _run("--folds", "2", "--test-ratio", "0.4", "--anchored")
    _run("--folds", "2", "--test-ratio", "0.4", "--rolling")

    listed = runner.invoke(app, ["validation-list"])
    assert listed.exit_code == 0
    assert "walkforward(확장)" in listed.stdout
    assert "walkforward(롤링)" in listed.stdout


def test_list_omits_window_label_for_holdout(monkeypatch, tmp_path):
    """단일 분할은 폴드가 하나뿐이라 확장/롤링 구분이 의미가 없다."""
    _seed(tmp_path, monkeypatch)
    _run("--mode", "holdout")

    listed = runner.invoke(app, ["validation-list"])
    assert "holdout·" in listed.stdout
    assert "확장" not in listed.stdout

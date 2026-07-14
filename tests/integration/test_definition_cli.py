from __future__ import annotations

import json

from typer.testing import CliRunner

from quant_krx.__main__ import app

runner = CliRunner()

_FORMULA_JSON = json.dumps({
    "id": "cli_formula", "name": "cli_formula", "version": "1",
    "expression": {"kind": "constant", "value": 1},
    "output_column": "value", "metadata": {}, "schema_version": 1,
})

_RULE_JSON = json.dumps({
    "id": "cli_rule", "name": "cli_rule", "version": "1",
    "root": {
        "node": "predicate",
        "left": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {}},
        "operator": ">",
        "right": {"kind": "constant", "value": 0},
    },
    "metadata": {}, "schema_version": 1,
})


def _strategy_json(rule_id: str = "cli_rule", strategy_id: str = "cli_strategy") -> str:
    return json.dumps({
        "id": strategy_id, "name": strategy_id, "version": "1",
        "factor_refs": [{"factor_id": "sma", "params": {}}],
        "universe": {"symbols": []},
        "rule": {"roles": {"entry": [rule_id], "exit": []}},
        "metadata": {}, "schema_version": 1,
    })


def test_formula_crud_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    formula_path = tmp_path / "formula.json"
    formula_path.write_text(_FORMULA_JSON)

    r = runner.invoke(app, ["formula-create", str(formula_path)])
    assert r.exit_code == 0

    r = runner.invoke(app, ["formula-show", "cli_formula"])
    assert r.exit_code == 0
    assert "cli_formula" in r.stdout

    r = runner.invoke(app, ["list-formulas"])
    assert r.exit_code == 0
    assert "cli_formula" in r.stdout

    r = runner.invoke(app, ["formula-delete", "cli_formula"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["formula-show", "cli_formula"])
    assert r.exit_code != 0


def test_formula_show_missing_id_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    r = runner.invoke(app, ["formula-show", "no_such"])
    assert r.exit_code != 0


def test_formula_create_invalid_json_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not valid json")
    r = runner.invoke(app, ["formula-create", str(bad_path)])
    assert r.exit_code != 0


def test_rule_crud_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    rule_path = tmp_path / "rule.json"
    rule_path.write_text(_RULE_JSON)

    r = runner.invoke(app, ["rule-create", str(rule_path)])
    assert r.exit_code == 0

    r = runner.invoke(app, ["rule-show", "cli_rule"])
    assert r.exit_code == 0
    assert "cli_rule" in r.stdout

    r = runner.invoke(app, ["list-rules"])
    assert r.exit_code == 0
    assert "cli_rule" in r.stdout

    r = runner.invoke(app, ["rule-delete", "cli_rule"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["rule-show", "cli_rule"])
    assert r.exit_code != 0


def test_strategy_crud_and_lifecycle_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    rule_path = tmp_path / "rule.json"
    rule_path.write_text(_RULE_JSON)
    runner.invoke(app, ["rule-create", str(rule_path)])

    strategy_path = tmp_path / "strategy.json"
    strategy_path.write_text(_strategy_json())

    r = runner.invoke(app, ["strategy-create", "cli_strategy", str(strategy_path)])
    assert r.exit_code == 0

    r = runner.invoke(app, ["strategy-show", "cli_strategy"])
    assert r.exit_code == 0
    assert "cli_strategy" in r.stdout

    r = runner.invoke(app, ["strategy-list"])
    assert r.exit_code == 0
    assert "cli_strategy" in r.stdout

    r = runner.invoke(app, ["strategy-validate", "cli_strategy"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["strategy-activate", "cli_strategy"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["strategy-list"])
    assert "ON" in r.stdout

    r = runner.invoke(app, ["strategy-deactivate", "cli_strategy"])
    assert r.exit_code == 0

    edited_path = tmp_path / "strategy_edited.json"
    edited_path.write_text(_strategy_json())
    r = runner.invoke(app, ["strategy-edit", "cli_strategy", str(edited_path)])
    assert r.exit_code == 0

    r = runner.invoke(app, ["strategy-delete", "cli_strategy"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["strategy-show", "cli_strategy"])
    assert r.exit_code != 0


def test_strategy_create_from_template(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    r = runner.invoke(app, ["strategy-create", "my_ma", "--template", "ma_crossover"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["strategy-template-list"])
    assert r.exit_code == 0
    assert "ma_crossover" in r.stdout
    assert "builtin" in r.stdout


def test_strategy_export_import_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    runner.invoke(app, ["strategy-create", "my_ma", "--template", "ma_crossover"])

    export_path = tmp_path / "bundle.json"
    r = runner.invoke(app, ["strategy-export", "my_ma", "--output", str(export_path)])
    assert r.exit_code == 0
    assert export_path.exists()

    r = runner.invoke(app, ["strategy-import", str(export_path)])
    assert r.exit_code == 0  # 동일 내용 → 멱등 통과


def test_strategy_validate_missing_strategy_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    r = runner.invoke(app, ["strategy-validate", "no_such"])
    assert r.exit_code != 0


def test_strategy_activate_draft_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    draft_json = json.dumps({
        "id": "draft_strategy", "name": "draft", "version": "1",
        "factor_refs": [{"factor_id": "sma", "params": {}}],
        "universe": {"symbols": []}, "rule": None, "metadata": {}, "schema_version": 1,
    })
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(draft_json)
    runner.invoke(app, ["strategy-create", "draft_strategy", str(draft_path)])

    r = runner.invoke(app, ["strategy-activate", "draft_strategy"])
    assert r.exit_code != 0

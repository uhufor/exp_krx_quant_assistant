from __future__ import annotations

import json

import pandas as pd
from typer.testing import CliRunner

from quant_krx.__main__ import app
from quant_krx.data.fixture_adapter import FIXTURE_PATH

runner = CliRunner()

_AS_OF = "2024-12-18"  # 픽스처 마지막 거래일

# MACD 골든크로스(최근 60봉 내) AND 52주고점 근접(종가 <= 60봉 롤링 최고가, 항상 참에
# 가까운 근접 프록시) AND 거래대금 Top-3 조합 — fixture 5종목 규모에 맞춰 top_n=3으로 축소.
_SCREEN_JSON = json.dumps(
    {
        "id": "cli_screen",
        "name": "MACD골든크로스+52주고점근접+거래대금Top3",
        "version": "1",
        "universe": {"market": "KRX", "exclusion_filters": []},
        "root": {
            "node": "composition",
            "op": "AND",
            "operands": [
                {
                    "node": "window_predicate",
                    "inner": {
                        "node": "predicate",
                        "left": {
                            "kind": "factor", "factor_id": "macd", "column": "macd", "params": {},
                        },
                        "operator": "crosses_above",
                        "right": {
                            "kind": "factor", "factor_id": "macd", "column": "signal", "params": {},
                        },
                    },
                    "n_bars": 60,
                    "include_current_bar": True,
                },
                {
                    "node": "predicate",
                    "left": {
                        "kind": "factor", "factor_id": "price", "column": "close", "params": {},
                    },
                    "operator": "<=",
                    "right": {
                        "kind": "factor",
                        "factor_id": "rolling_high",
                        "column": "rolling_high",
                        "params": {"window": 60},
                    },
                },
                {
                    "node": "rank_predicate",
                    "factor_id": "trading_value",
                    "column": "trading_value",
                    "rank_metric": "desc",
                    "top_n": 3,
                    "params": {},
                },
            ],
        },
        "metadata": {},
        "schema_version": 1,
    },
    ensure_ascii=False,
)


def _expected_top3_by_trading_value() -> list[str]:
    """픽스처 마지막 거래일 거래대금 Top-3 종목 — RankPredicate가 AND의 유일한 제약이 되는
    조합(window_macd/near_high는 픽스처 전 종목에서 참)이므로 최종 통과 종목과 일치해야 한다."""
    df = pd.read_csv(FIXTURE_PATH, dtype={"symbol": str}, parse_dates=["date"])
    df["symbol"] = df["symbol"].str.zfill(6)
    snap = df[df["date"] == pd.Timestamp(_AS_OF)][["symbol", "close", "volume"]].copy()
    snap["trading_value"] = snap["close"] * snap["volume"]
    return sorted(snap.sort_values("trading_value", ascending=False).head(3)["symbol"])


def test_screen_full_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    screen_path = tmp_path / "screen.json"
    screen_path.write_text(_SCREEN_JSON)

    r = runner.invoke(app, ["screen-create", str(screen_path)])
    assert r.exit_code == 0, r.stdout

    r = runner.invoke(app, ["screen-show", "cli_screen"])
    assert r.exit_code == 0, r.stdout
    assert "cli_screen" in r.stdout

    r = runner.invoke(app, ["screen-list"])
    assert r.exit_code == 0, r.stdout
    assert "cli_screen" in r.stdout

    r = runner.invoke(app, ["screen-validate", "cli_screen"])
    assert r.exit_code == 0, r.stdout
    assert "검증 통과" in r.stdout

    r = runner.invoke(
        app,
        ["screen-run", "cli_screen", "--as-of", _AS_OF, "--data-source", "fixture"],
    )
    assert r.exit_code == 0, r.stdout
    expected = _expected_top3_by_trading_value()
    assert len(expected) == 3
    for symbol in expected:
        assert symbol in r.stdout
    assert "통과 종목 3건" in r.stdout


def test_screen_edit_replaces_definition(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    screen_path = tmp_path / "screen.json"
    screen_path.write_text(_SCREEN_JSON)
    r = runner.invoke(app, ["screen-create", str(screen_path)])
    assert r.exit_code == 0, r.stdout

    edited = json.loads(_SCREEN_JSON)
    edited["name"] = "이름 변경"
    edited_path = tmp_path / "screen_edited.json"
    edited_path.write_text(json.dumps(edited, ensure_ascii=False))

    r = runner.invoke(app, ["screen-edit", "cli_screen", str(edited_path)])
    assert r.exit_code == 0, r.stdout

    r = runner.invoke(app, ["screen-show", "cli_screen"])
    assert r.exit_code == 0, r.stdout
    assert "이름 변경" in r.stdout


def test_screen_delete_then_show_misses(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    screen_path = tmp_path / "screen.json"
    screen_path.write_text(_SCREEN_JSON)
    r = runner.invoke(app, ["screen-create", str(screen_path)])
    assert r.exit_code == 0, r.stdout

    r = runner.invoke(app, ["screen-delete", "cli_screen"])
    assert r.exit_code == 0, r.stdout

    r = runner.invoke(app, ["screen-show", "cli_screen"])
    assert r.exit_code != 0


def test_screen_create_invalid_json_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not valid json")
    r = runner.invoke(app, ["screen-create", str(bad_path)])
    assert r.exit_code != 0


def test_screen_show_missing_id_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    r = runner.invoke(app, ["screen-show", "no_such"])
    assert r.exit_code != 0

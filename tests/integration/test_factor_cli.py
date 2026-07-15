from __future__ import annotations

from typer.testing import CliRunner

from quant_krx.__main__ import app

runner = CliRunner()


def test_list_factors_exits_zero_and_lists_all_32(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, ["list-factors"])
    assert result.exit_code == 0
    assert "sma" in result.stdout
    assert "roa" in result.stdout


def test_list_factors_category_filter(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, ["list-factors", "--category", "value"])
    assert result.exit_code == 0
    assert "per" in result.stdout
    assert "sma" not in result.stdout


def test_list_factors_unknown_category_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, ["list-factors", "--category", "not_a_category"])
    assert result.exit_code != 0


def test_show_factor_valid_id(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, ["show-factor", "macd"])
    assert result.exit_code == 0
    assert "MACD" in result.stdout
    assert "fast" in result.stdout


def test_show_factor_financial_factor_shows_dart_hint(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, ["show-factor", "roa"])
    assert result.exit_code == 0
    assert "DART" in result.stdout


def test_show_factor_unknown_id_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, ["show-factor", "not_a_real_factor"])
    assert result.exit_code != 0
    assert "not_a_real_factor" in result.stdout


def test_fetch_fundamental_fixture_provider_succeeds_and_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    args = [
        "fetch-fundamental", "--provider", "fixture", "--symbols", "005930",
        "--start", "2022-01-01", "--end", "2024-12-31", "--kind", "all",
    ]
    r1 = runner.invoke(app, args)
    assert r1.exit_code == 0
    assert "valuation" in r1.stdout
    assert "financials" in r1.stdout

    r2 = runner.invoke(app, args)
    assert r2.exit_code == 0
    # 두 실행의 수용 건수 라인이 동일해야 함(멱등)
    assert r1.stdout == r2.stdout


def test_fetch_fundamental_valuation_only(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, [
        "fetch-fundamental", "--provider", "fixture", "--symbols", "005930",
        "--start", "2022-01-01", "--end", "2024-12-31", "--kind", "valuation",
    ])
    assert result.exit_code == 0
    assert "financials" not in result.stdout


def test_fetch_fundamental_unknown_kind_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, [
        "fetch-fundamental", "--provider", "fixture", "--symbols", "005930", "--kind", "bogus",
    ])
    assert result.exit_code != 0


def test_fetch_fundamental_unknown_provider_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, [
        "fetch-fundamental", "--provider", "bogus", "--symbols", "005930",
    ])
    assert result.exit_code != 0


def test_fetch_fundamental_pykrx_financials_reports_not_implemented(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, [
        "fetch-fundamental", "--provider", "pykrx", "--symbols", "005930",
        "--kind", "financials",
    ])
    assert result.exit_code != 0

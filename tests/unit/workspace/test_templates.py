from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from quant_krx.factors import FactorInput
from quant_krx.storage.db import Database
from quant_krx.workspace.errors import WorkspaceError
from quant_krx.workspace.service import WorkspaceService
from quant_krx.workspace.templates import BUILTIN_TEMPLATES

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sample_ohlcv.csv"
NOW = datetime(2026, 1, 1, 0, 0, 0)


@pytest.fixture(scope="module")
def ohlcv() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE_PATH, dtype={"symbol": str}, parse_dates=["date"])
    df = df[df["symbol"] == "005930"].sort_values("date").set_index("date")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


@pytest.fixture
def svc(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield WorkspaceService(db)
    db.close()


@pytest.mark.parametrize("template_id", list(BUILTIN_TEMPLATES.keys()))
def test_builtin_template_is_immediately_valid_and_runnable(svc, template_id) -> None:
    bundle = BUILTIN_TEMPLATES[template_id]
    for formula in bundle.formulas:
        svc.upsert_formula(formula, now=NOW)
    for rule in bundle.rules:
        svc.upsert_rule(rule, now=NOW)
    svc.upsert_strategy(bundle.strategy, now=NOW)

    assert svc.validate_strategy(bundle.strategy).ok
    assert svc.is_runnable(bundle.strategy.id)


@pytest.mark.parametrize("template_id", list(BUILTIN_TEMPLATES.keys()))
def test_builtin_template_backtests_to_completion(svc, ohlcv, template_id) -> None:
    new_id = f"{template_id}_copy"
    defn = svc.create_from_template(template_id, new_id, now=NOW)
    data = {"005930": FactorInput(ohlcv=ohlcv)}
    report = svc.backtest(defn.id, data=data, fees=0.003, slippage=0.001)
    assert "005930" in report.per_symbol


def test_create_from_template_produces_runnable_strategy(svc) -> None:
    defn = svc.create_from_template("ma_crossover", "my_ma", now=NOW)
    assert defn.id == "my_ma"
    assert svc.is_runnable("my_ma")
    assert svc.get_rule("ma_crossover_entry") is not None


def test_create_from_template_unknown_template_rejected(svc) -> None:
    with pytest.raises(WorkspaceError):
        svc.create_from_template("no_such_template", "x", now=NOW)


def test_list_templates_includes_builtin_and_user(svc) -> None:
    svc.create_from_template("rsi_breakout", "my_rsi", now=NOW)
    svc.save_as_template("my_rsi", "my_rsi_template", now=NOW)

    infos = svc.list_templates()
    origins = {info.template_id: info.origin for info in infos}
    assert origins["ma_crossover"] == "builtin"
    assert origins["my_rsi_template"] == "user"


def test_save_as_template_rejects_builtin_id_collision(svc) -> None:
    svc.create_from_template("macd", "my_macd", now=NOW)
    with pytest.raises(WorkspaceError):
        svc.save_as_template("my_macd", "macd", now=NOW)


def test_save_as_template_then_create_from_template_roundtrip_equivalent(svc) -> None:
    original = svc.create_from_template("bollinger_band", "orig_bb", now=NOW)
    svc.save_as_template("orig_bb", "bb_template", now=NOW)

    restored = svc.create_from_template("bb_template", "restored_bb", now=NOW)

    assert restored.factor_refs == original.factor_refs
    assert restored.universe == original.universe
    assert restored.rule == original.rule


def test_get_and_delete_template(svc) -> None:
    svc.create_from_template("momentum", "my_mom", now=NOW)
    svc.save_as_template("my_mom", "mom_template", now=NOW)

    bundle = svc.get_template("mom_template")
    assert bundle is not None
    assert bundle.strategy.id == "my_mom"

    svc.delete_template("mom_template")
    assert svc.get_template("mom_template") is None


def test_delete_builtin_template_rejected(svc) -> None:
    with pytest.raises(WorkspaceError):
        svc.delete_template("ma_crossover")

from __future__ import annotations

from pathlib import Path

from tests.unit.factors.test_purity_ast import (
    DYNAMIC_IMPORT_MARKER,
    SRC_DIR,
    _imported_modules,
)

SRC_ROOT = SRC_DIR / "quant_krx"
FORMULA_ROOT = SRC_ROOT / "formula"
RULE_ROOT = SRC_ROOT / "rule"
STRATEGY_ROOT = SRC_ROOT / "strategy"

# INV-1: 세 도메인 패키지는 백테스트·평가/실행·storage를 런타임 import하지 않는다.
FORBIDDEN_LAYERS = (
    "vectorbt",
    "quant_krx.workspace",
    "quant_krx.jobs",
    "quant_krx.quant",
    "quant_krx.storage",
)

# INV-2: formula/rule/strategy는 서로를 import하지 않는다.
_PACKAGE_FORBIDDEN = {
    "formula": ("quant_krx.rule", "quant_krx.strategy"),
    "rule": ("quant_krx.formula", "quant_krx.strategy"),
    "strategy": ("quant_krx.formula", "quant_krx.rule"),
}


def _violations(root: Path, forbidden: tuple[str, ...]) -> list[str]:
    violations = []
    for py_file in sorted(root.rglob("*.py")):
        for mod in _imported_modules(py_file):
            is_forbidden = mod == DYNAMIC_IMPORT_MARKER or any(
                mod == f or mod.startswith(f + ".") for f in forbidden
            )
            if is_forbidden:
                violations.append(f"{py_file.relative_to(root.parents[1])}: import {mod}")
    return violations


def test_formula_package_does_not_import_execution_or_storage_layers():
    violations = _violations(FORMULA_ROOT, FORBIDDEN_LAYERS)
    assert violations == [], f"INV-1 위반(formula/ 순수성): {violations}"


def test_rule_package_does_not_import_execution_or_storage_layers():
    violations = _violations(RULE_ROOT, FORBIDDEN_LAYERS)
    assert violations == [], f"INV-1 위반(rule/ 순수성): {violations}"


def test_strategy_package_does_not_import_execution_or_storage_layers():
    violations = _violations(STRATEGY_ROOT, FORBIDDEN_LAYERS)
    assert violations == [], f"INV-1 위반(strategy/ 순수성): {violations}"


def test_formula_package_does_not_import_sibling_definition_packages():
    violations = _violations(FORMULA_ROOT, _PACKAGE_FORBIDDEN["formula"])
    assert violations == [], f"INV-2 위반(formula가 rule/strategy를 참조함): {violations}"


def test_rule_package_does_not_import_sibling_definition_packages():
    violations = _violations(RULE_ROOT, _PACKAGE_FORBIDDEN["rule"])
    assert violations == [], f"INV-2 위반(rule이 formula/strategy를 참조함): {violations}"


def test_strategy_package_does_not_import_sibling_definition_packages():
    violations = _violations(STRATEGY_ROOT, _PACKAGE_FORBIDDEN["strategy"])
    assert violations == [], f"INV-2 위반(strategy가 formula/rule을 참조함): {violations}"

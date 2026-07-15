from __future__ import annotations

from pathlib import Path

from tests.unit.factors.test_purity_ast import DYNAMIC_IMPORT_MARKER, SRC_DIR, _imported_modules

SRC_ROOT = SRC_DIR / "quant_krx"
FACTORS_ROOT = SRC_ROOT / "factors"
FORMULA_ROOT = SRC_ROOT / "formula"
RULE_ROOT = SRC_ROOT / "rule"
STRATEGY_ROOT = SRC_ROOT / "strategy"

# INV-1(R03): 정의 패키지(R01/R02)는 상위 impure 계층을 역주입 참조하지 않는다.
_UPWARD_FORBIDDEN = ("quant_krx.workspace", "quant_krx.jobs")

_DEFINITION_ROOTS = {
    "factors": FACTORS_ROOT,
    "formula": FORMULA_ROOT,
    "rule": RULE_ROOT,
    "strategy": STRATEGY_ROOT,
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


def test_definition_packages_do_not_import_workspace_or_jobs():
    for name, root in _DEFINITION_ROOTS.items():
        violations = _violations(root, _UPWARD_FORBIDDEN)
        assert violations == [], f"INV-1 위반({name}/가 workspace·jobs 역주입): {violations}"

from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[3] / "src"
SRC_ROOT = SRC_DIR / "quant_krx"
FACTORS_ROOT = SRC_ROOT / "factors"
DATA_ROOT = SRC_ROOT / "data"

FACTORS_FORBIDDEN = (
    "vectorbt",
    "quant_krx.jobs",
    "quant_krx.quant",
    "quant_krx.storage",
    "quant_krx.data",
)
DATA_FORBIDDEN = ("quant_krx.factors",)

DYNAMIC_IMPORT_MARKER = "<dynamic-import>"


def _current_package_parts(py_file: Path, src_dir: Path = SRC_DIR) -> list[str]:
    """py_file이 속한 패키지의 dotted 경로 부분(상대 import 해석의 기준점)."""
    rel_parts = list(py_file.relative_to(src_dir).with_suffix("").parts)
    if rel_parts[-1] == "__init__":
        return rel_parts[:-1]
    return rel_parts[:-1]


def _resolve_relative(current_package: list[str], level: int, module: str | None) -> str:
    """PEP 328 상대 import 해석: level=1은 현재 패키지, level=2는 그 상위, ..."""
    trim = level - 1
    base = current_package[: len(current_package) - trim] if trim <= len(current_package) else []
    parts = base + ([module] if module else [])
    return ".".join(parts)


def _imported_modules(py_file: Path, src_dir: Path = SRC_DIR) -> list[str]:
    """py_file의 런타임 import 대상 모듈명(절대 경로로 정규화) 목록.

    TYPE_CHECKING 블록 내부는 제외(런타임 미로딩). 상대 import(from . import x)는
    파일의 실제 패키지 위치 기준으로 절대 dotted 경로로 정규화한다(단순 문자열 접두사
    비교만으로는 상대 import를 놓치는 회피 경로를 막기 위함). importlib.import_module /
    __import__ 동적 import 호출은 인자를 정적으로 알 수 없으므로 fail-closed로
    DYNAMIC_IMPORT_MARKER를 기록해 항상 위반으로 취급한다.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    current_package = _current_package_parts(py_file, src_dir)
    modules: list[str] = []

    def _is_type_checking_guard(node: ast.If) -> bool:
        test = node.test
        if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
            return True
        return isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"

    class Visitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            if _is_type_checking_guard(node):
                return  # TYPE_CHECKING 블록 내부는 순회하지 않음(런타임 미로딩 예외)
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                modules.append(alias.name)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.level and node.level > 0:
                modules.append(_resolve_relative(current_package, node.level, node.module))
            elif node.module:
                modules.append(node.module)

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            is_dynamic = (
                (isinstance(func, ast.Attribute) and func.attr == "import_module")
                or (isinstance(func, ast.Name) and func.id == "__import__")
            )
            if is_dynamic:
                modules.append(DYNAMIC_IMPORT_MARKER)
            self.generic_visit(node)

    Visitor().visit(tree)
    return modules


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


def test_factors_package_does_not_import_execution_or_storage_layers():
    violations = _violations(FACTORS_ROOT, FACTORS_FORBIDDEN)
    assert violations == [], f"INV-1 위반(factors/ 순수성): {violations}"


def test_data_package_does_not_import_factors_package():
    violations = _violations(DATA_ROOT, DATA_FORBIDDEN)
    assert violations == [], f"data/가 factors/를 역참조함(단방향 위반): {violations}"


def test_scanner_catches_relative_import_evasion(tmp_path):
    """`from ..data import x` 같은 상대 import가 절대 경로 접두사 비교를 우회하지 못함을 증명."""
    pkg = tmp_path / "quant_krx" / "factors"
    pkg.mkdir(parents=True)
    evasive = pkg / "evasive.py"
    evasive.write_text("from ..data import upsert\n")
    modules = _imported_modules(evasive, src_dir=tmp_path)
    assert "quant_krx.data" in modules


def test_scanner_catches_dynamic_import_evasion(tmp_path):
    """importlib.import_module/__import__ 동적 import를 fail-closed로 위반 취급함을 증명."""
    pkg = tmp_path / "quant_krx" / "factors"
    pkg.mkdir(parents=True)
    evasive = pkg / "evasive.py"
    evasive.write_text(
        "import importlib\n"
        "def sneaky():\n"
        "    return importlib.import_module('quant_krx.storage.db')\n"
    )
    modules = _imported_modules(evasive, src_dir=tmp_path)
    assert DYNAMIC_IMPORT_MARKER in modules

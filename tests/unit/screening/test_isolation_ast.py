from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[3] / "src"
SCREENING_ROOT = SRC_DIR / "quant_krx" / "screening"

# screening/는 rule/formula/strategy 및 workspace 실행·평가 계층을 import하지 않는
# 완전 독립 스키마여야 한다(INV-2). 이 목록은 이 스토리의 핵심 성공 기준.
SCREENING_FORBIDDEN = (
    "quant_krx.rule",
    "quant_krx.formula",
    "quant_krx.strategy",
    "quant_krx.workspace.evaluation",
    "quant_krx.workspace.service",
)

DYNAMIC_IMPORT_MARKER = "<dynamic-import>"


def _current_package_parts(py_file: Path, src_dir: Path = SRC_DIR) -> list[str]:
    """py_file이 속한 패키지의 dotted 경로 부분(상대 import 해석의 기준점)."""
    rel_parts = list(py_file.relative_to(src_dir).with_suffix("").parts)
    return rel_parts[:-1]


def _resolve_relative(current_package: list[str], level: int, module: str | None) -> str:
    """PEP 328 상대 import 해석: level=1은 현재 패키지, level=2는 그 상위, ..."""
    trim = level - 1
    base = current_package[: len(current_package) - trim] if trim <= len(current_package) else []
    parts = base + ([module] if module else [])
    return ".".join(parts)


def _imported_modules(py_file: Path, src_dir: Path = SRC_DIR) -> list[str]:
    """py_file의 런타임 import 대상 모듈명(절대 경로로 정규화) 목록.

    TYPE_CHECKING 블록 내부는 제외(런타임 미로딩). 상대 import는 파일의 실제 패키지 위치
    기준으로 절대 dotted 경로로 정규화한다. importlib.import_module / __import__ 동적 import는
    인자를 정적으로 알 수 없으므로 fail-closed로 DYNAMIC_IMPORT_MARKER를 기록한다.
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
            is_dynamic = (isinstance(func, ast.Attribute) and func.attr == "import_module") or (
                isinstance(func, ast.Name) and func.id == "__import__"
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


def test_screening_package_is_import_isolated():
    """screening/가 rule·formula·strategy·workspace 실행 계층을 import하지 않음을 증명(INV-2)."""
    violations = _violations(SCREENING_ROOT, SCREENING_FORBIDDEN)
    assert violations == [], f"screening 격리 위반: {violations}"


def test_screening_root_has_python_files():
    """스캔 대상이 실제로 존재함을 보장(빈 디렉터리로 인한 위양성 통과 방지)."""
    py_files = list(SCREENING_ROOT.rglob("*.py"))
    assert py_files, "screening/ 아래에 .py 파일이 없습니다"


def test_scanner_catches_relative_import_evasion(tmp_path):
    """`from ..rule import x` 같은 상대 import가 절대 경로 접두사 비교를 우회하지 못함을 증명."""
    pkg = tmp_path / "quant_krx" / "screening"
    pkg.mkdir(parents=True)
    evasive = pkg / "evasive.py"
    evasive.write_text("from ..rule import definition\n")
    modules = _imported_modules(evasive, src_dir=tmp_path)
    assert "quant_krx.rule" in modules

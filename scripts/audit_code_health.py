#!/usr/bin/env python3
"""Static code-health audit for the reusable Skill implementation.

The audit intentionally distinguishes hard safety/correctness smells from
legacy maintainability debt. Hard findings fail ``--strict``; large modules,
long functions, broad exception handlers and legacy registry drift are reported
as warnings so they can be reduced without turning the first audit into noise.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

HARD_FUNCTION_LINES = 250
LARGE_MODULE_BYTES = 100_000


class Visitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.imported_modules: set[str] = set()
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []

    def issue(self, bucket: list[dict[str, Any]], code: str, node: ast.AST, message: str) -> None:
        bucket.append({"code": code, "path": str(self.path), "line": getattr(node, "lineno", None), "message": message})

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imported_modules.add(alias.asname or alias.name.split(".", 1)[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Imported symbols are local bindings; assigning them is not process-wide
        # monkey patching, so only module imports matter for the attribute rule.
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.issue(self.errors, "bare_except", node, "bare except hides cancellation/system-exit and unrelated defects")
        elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
            self.issue(self.warnings, "broad_exception", node, "broad Exception handler should document why narrower errors are unsafe")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            self.issue(self.errors, "dynamic_code_execution", node, f"{node.func.id} is forbidden in reusable Skill code")
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "os" and node.func.attr == "system":
                self.issue(self.errors, "os_system", node, "use subprocess with an argv list instead of os.system")
            if node.func.value.id == "subprocess":
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        self.issue(self.errors, "subprocess_shell_true", node, "shell=True is forbidden for Skill subprocesses")
        self.generic_visit(node)

    def _assignment_target(self, target: ast.AST, node: ast.AST) -> None:
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id in self.imported_modules:
            self.issue(
                self.errors,
                "imported_module_monkey_patch",
                node,
                f"assignment to imported module attribute {target.value.id}.{target.attr} creates process-global behavior drift",
            )
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._assignment_target(item, node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._assignment_target(target, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._assignment_target(node.target, node)
        self.generic_visit(node)

    def _function_length(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        end = getattr(node, "end_lineno", None)
        if isinstance(end, int) and end - node.lineno + 1 > HARD_FUNCTION_LINES:
            self.issue(self.warnings, "long_function", node, f"function {node.name} spans {end - node.lineno + 1} lines")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_length(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function_length(node)
        self.generic_visit(node)


def audit_file(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        return ([{"code": "unparseable_python", "path": str(path), "line": None, "message": str(exc)}], [])
    visitor = Visitor(path)
    visitor.visit(tree)
    if path.stat().st_size > LARGE_MODULE_BYTES:
        visitor.warnings.append({
            "code": "large_module",
            "path": str(path),
            "line": None,
            "message": f"module is {path.stat().st_size} bytes; consider splitting rendering/domain concerns",
        })
    return visitor.errors, visitor.warnings


def registry_observations(root: Path) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    try:
        import build_results_facts
        import export_ai_bundle
        import merge_graph
        import required_fields
        import validate_graph
    except ImportError as exc:
        return [{"code": "registry_import_failed", "path": str(root), "message": str(exc)}]
    canonical = set(required_fields.ARRAY_KINDS)
    registries = {
        "build_results_facts.ARRAYS": set(build_results_facts.ARRAYS),
        "export_ai_bundle.GROUPS": set(export_ai_bundle.GROUPS),
        "merge_graph.ARRAYS": set(merge_graph.ARRAYS),
        "validate_graph.ARRAYS": set(validate_graph.ARRAYS),
    }
    for name, values in registries.items():
        if values != canonical:
            observations.append({
                "code": "array_registry_drift",
                "path": name,
                "message": f"missing={sorted(canonical - values)} extra={sorted(values - canonical)}",
            })
    return observations


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    files = [path for path in root.rglob("*.py") if path.is_file() and "__pycache__" not in path.parts]
    for path in sorted(files):
        file_errors, file_warnings = audit_file(path)
        errors.extend(file_errors)
        warnings.extend(file_warnings)
    registry = registry_observations(root)
    warnings.extend(registry)
    counts: dict[str, int] = {}
    for item in [*errors, *warnings]:
        counts[item["code"]] = counts.get(item["code"], 0) + 1
    return {
        "valid": not errors,
        "files_scanned": len(files),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "counts": counts,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--strict", action="store_true", help="exit non-zero when hard findings exist")
    args = parser.parse_args()
    report = run(args.root)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json:
        from io_utils import atomic_write_text
        atomic_write_text(args.json, text + "\n")
    print(text)
    return 1 if args.strict and not report["valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Static checker for FastAPI + SQLAlchemy coding rules.

Catches defects that recur in LLM-generated backend code before the code is
shipped. Uses only the standard library (`ast`), no dependencies. See the
rule descriptions in fastapi_guard.md.

Usage:
    python3 fastapi_guard.py [TARGET_DIR]      # default: current directory
Exit code 1 if any error is found, 0 if only warnings or clean.
"""
from __future__ import annotations

import ast
import builtins
import sys
from dataclasses import dataclass
from pathlib import Path

HTTP_METHODS = {"post", "get", "put", "delete", "patch", "request"}
HTTP_LIBS = {"requests", "httpx"}
BUILTINS = set(dir(builtins)) | {"__name__", "__file__"}


@dataclass
class Finding:
    path: str
    line: int
    rule: int
    level: str  # "error" | "warn"
    msg: str


def analyze_file(path: Path, tree: ast.AST, findings: list[Finding], state: dict) -> None:
    rel = str(path)

    # Collect names defined/imported in this file (heuristic for rule 2)
    defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import,)):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                defined.add(a.asname or a.name)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)

    for node in ast.walk(tree):
        # Rule 1 — collect declarative_base() call sites (must be exactly one project-wide)
        if isinstance(node, ast.Call) and _callee_name(node.func) == "declarative_base":
            state["declarative_base"].append((rel, node.lineno))

        # Rule 3 — track whether create_all exists
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create_all":
            state["create_all"] = True

        if isinstance(node, ast.Call):
            # Rule 4 — forbid Model(**obj.__dict__) unpacking
            for kw in node.keywords:
                if kw.arg is None and isinstance(kw.value, ast.Attribute) and kw.value.attr == "__dict__":
                    findings.append(Finding(rel, node.lineno, 4, "error",
                        "ORM->schema: do not use **obj.__dict__. Use model_validate(obj) with from_attributes."))

            # Rule 5 — CORS: forbid allow_credentials=True together with allow_origins=["*"]
            kws = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            if _is_true(kws.get("allow_credentials")) and _has_wildcard(kws.get("allow_origins")):
                findings.append(Finding(rel, node.lineno, 5, "error",
                    'Do not combine allow_credentials=True with allow_origins=["*"]. List explicit origins.'))

            # Rule 7 — requests/httpx calls must pass timeout
            if (isinstance(node.func, ast.Attribute) and node.func.attr in HTTP_METHODS
                    and _callee_root(node.func.value) in HTTP_LIBS):
                if not any(kw.arg == "timeout" for kw in node.keywords):
                    findings.append(Finding(rel, node.lineno, 7, "error",
                        f"External HTTP call missing timeout= ({_callee_root(node.func.value)}.{node.func.attr})."))

            # Rule 6 — datetime.now() without timezone (naive) warning
            if (isinstance(node.func, ast.Attribute) and node.func.attr == "now"
                    and _callee_root(node.func.value) == "datetime"
                    and not node.args and not node.keywords):
                findings.append(Finding(rel, node.lineno, 6, "warn",
                    "datetime.now() used without a timezone. Specify tz (e.g. ZoneInfo)."))

            # Rule 2 — call to a capitalized name that is not imported/defined (possible NameError)
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name[:1].isupper() and name not in defined and name not in BUILTINS:
                    findings.append(Finding(rel, node.lineno, 2, "error",
                        f"'{name}' is called but not imported/defined (possible NameError)."))


def _callee_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _callee_root(node: ast.AST | None) -> str | None:
    """Return the top-level name of a call chain, e.g. `requests`, `datetime`."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _callee_root(node.value)
    return None


def _is_true(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _has_wildcard(node: ast.AST | None) -> bool:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(isinstance(e, ast.Constant) and e.value == "*" for e in node.elts)
    return isinstance(node, ast.Constant) and node.value == "*"


def main(argv: list[str]) -> int:
    target = Path(argv[1] if len(argv) > 1 else ".").resolve()
    files = [p for p in target.rglob("*.py")
             if not any(part in {"node_modules", "venv", ".venv", "__pycache__", ".git"} for part in p.parts)]
    if not files:
        print(f"[harness] no .py files under {target}")
        return 0

    findings: list[Finding] = []
    state: dict = {"declarative_base": [], "create_all": False}
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError as e:
            findings.append(Finding(str(f), e.lineno or 0, 0, "error", f"syntax error: {e.msg}"))
            continue
        analyze_file(f.relative_to(target), tree, findings, state)

    # Rule 1 — declarative_base must be called exactly once
    bases = state["declarative_base"]
    if len(bases) > 1:
        for rel, line in bases:
            findings.append(Finding(rel, line, 1, "error",
                f"declarative_base() called {len(bases)} times. Call it once (database.py) and import it elsewhere."))
    # Rule 3 — models exist but no create_all / migration
    if bases and not state["create_all"]:
        findings.append(Finding("(project)", 0, 3, "warn",
            "declarative_base() present but no Base.metadata.create_all call (add it if there are no migrations)."))

    findings.sort(key=lambda x: (x.path, x.line, x.rule))
    errors = sum(1 for f in findings if f.level == "error")
    warns = sum(1 for f in findings if f.level == "warn")

    for f in findings:
        icon = "x" if f.level == "error" else "!"
        print(f"{icon} {f.path}:{f.line}  [rule {f.rule}] {f.msg}")

    print(f"\n[harness] {len(files)} file(s) checked - {errors} error(s), {warns} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

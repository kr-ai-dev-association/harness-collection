#!/usr/bin/env python3
"""
FastAPI + SQLAlchemy 코딩 규칙 정적 검사기.

LLM이 생성한 백엔드 코드에서 반복적으로 나오던 결함을 출력 전에 잡는다.
표준 라이브러리 `ast`만 사용한다(무의존). 규칙 설명은 README.md 참고.

사용:
    python3 fastapi_guard.py [TARGET_DIR]      # 기본값: 현재 디렉터리
오류(error) 발견 시 종료 코드 1, 경고만 있거나 깨끗하면 0.
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

    # 파일 내 정의/임포트된 이름 수집 (규칙 2 휴리스틱용)
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
        # 규칙 1 — declarative_base() 호출 위치 집계 (프로젝트 전역에서 1번만)
        if isinstance(node, ast.Call) and _callee_name(node.func) == "declarative_base":
            state["declarative_base"].append((rel, node.lineno))

        # 규칙 3 — create_all 존재 여부 집계
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create_all":
            state["create_all"] = True

        if isinstance(node, ast.Call):
            # 규칙 4 — Model(**obj.__dict__) 언패킹 금지
            for kw in node.keywords:
                if kw.arg is None and isinstance(kw.value, ast.Attribute) and kw.value.attr == "__dict__":
                    findings.append(Finding(rel, node.lineno, 4, "error",
                        "ORM→스키마 변환에 **obj.__dict__ 사용 금지. model_validate(obj) + from_attributes 사용."))

            # 규칙 5 — CORS: allow_credentials=True 이면서 allow_origins=["*"] 금지
            kws = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            if _is_true(kws.get("allow_credentials")) and _has_wildcard(kws.get("allow_origins")):
                findings.append(Finding(rel, node.lineno, 5, "error",
                    'allow_credentials=True 와 allow_origins=["*"] 조합 금지. 명시적 오리진을 나열하라.'))

            # 규칙 7 — requests/httpx 호출에 timeout 필수
            if (isinstance(node.func, ast.Attribute) and node.func.attr in HTTP_METHODS
                    and _callee_root(node.func.value) in HTTP_LIBS):
                if not any(kw.arg == "timeout" for kw in node.keywords):
                    findings.append(Finding(rel, node.lineno, 7, "error",
                        f"외부 HTTP 호출에 timeout= 누락 ({_callee_root(node.func.value)}.{node.func.attr})."))

            # 규칙 6 — datetime.now() 타임존 미지정(naive) 경고
            if (isinstance(node.func, ast.Attribute) and node.func.attr == "now"
                    and _callee_root(node.func.value) == "datetime"
                    and not node.args and not node.keywords):
                findings.append(Finding(rel, node.lineno, 6, "warn",
                    "datetime.now() 가 타임존 없이 사용됨. ZoneInfo 등으로 tz를 명시하라."))

            # 규칙 2 — 대문자로 시작하는 미정의/미임포트 이름 호출 (NameError 후보)
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name[:1].isupper() and name not in defined and name not in BUILTINS:
                    findings.append(Finding(rel, node.lineno, 2, "error",
                        f"'{name}' 를 호출하는데 import/정의가 없음 (NameError 후보)."))


def _callee_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _callee_root(node: ast.AST | None) -> str | None:
    """`requests`, `datetime` 처럼 호출 체인의 최상위 이름을 반환."""
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
            findings.append(Finding(str(f), e.lineno or 0, 0, "error", f"구문 오류: {e.msg}"))
            continue
        analyze_file(f.relative_to(target), tree, findings, state)

    # 규칙 1 — declarative_base 는 정확히 1번
    bases = state["declarative_base"]
    if len(bases) > 1:
        for rel, line in bases:
            findings.append(Finding(rel, line, 1, "error",
                f"declarative_base() 가 {len(bases)}번 호출됨. 단 한 곳(database.py)에서만 호출하고 나머지는 import 하라."))
    # 규칙 3 — 모델이 있는데 create_all/마이그레이션이 없음
    if bases and not state["create_all"]:
        findings.append(Finding("(project)", 0, 3, "warn",
            "declarative_base() 는 있으나 Base.metadata.create_all 호출이 없음(마이그레이션이 없다면 추가)."))

    findings.sort(key=lambda x: (x.path, x.line, x.rule))
    errors = sum(1 for f in findings if f.level == "error")
    warns = sum(1 for f in findings if f.level == "warn")

    for f in findings:
        icon = "✘" if f.level == "error" else "▲"
        print(f"{icon} {f.path}:{f.line}  [규칙 {f.rule}] {f.msg}")

    print(f"\n[harness] 검사 파일 {len(files)}개 — 오류 {errors}, 경고 {warns}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

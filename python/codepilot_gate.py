#!/usr/bin/env python3
"""codepilot_gate.py — codepilot PostToolUse hook adapter for the harness guards.

Wire-up (no core changes needed — uses codepilot's built-in hook system):
  stdin  : HookInput JSON line  {event, cwd, toolName, toolInput?, toolOutput?}
  stdout : HookOutput JSON      {continue, systemMessage?, additionalContext?}

Behavior: after the model writes a file (create_file/update_file), run the two
guards over the workspace. If any *error* (version-correctness defect) is found,
inject the findings + fix instructions back to the model via `additionalContext`
(ToolExecutor attaches it to the tool result → the model sees it and self-fixes,
the same loop that took a planted 5-error file to 0 in the eval).

Design: stdlib only · single file · graceful (never breaks the tool pipeline).
Guards are looked up next to this file: springboot_guard.py, db2_guard.py.
"""
import json
import os
import subprocess
import sys


def read_input():
    try:
        line = sys.stdin.readline()
        return json.loads(line) if line.strip() else {}
    except Exception:
        return {}


def run_guards(target):
    here = os.path.dirname(os.path.abspath(__file__))
    findings = []
    for guard in ("springboot_guard.py", "db2_guard.py"):
        gp = os.path.join(here, guard)
        if not os.path.isfile(gp):
            continue
        try:
            r = subprocess.run([sys.executable or "python3", gp, "--json", target],
                               capture_output=True, text=True, timeout=25)
            findings += json.loads(r.stdout or "[]")
        except Exception:
            pass  # graceful — a broken guard must not break the pipeline
    return findings


def main():
    inp = read_input()
    cwd = inp.get("cwd") or os.getcwd()

    # scan the just-written file when the hook payload carries its path;
    # fall back to the whole workspace (guards exclude build dirs; pom gates versions).
    target = cwd
    ti = inp.get("toolInput") or {}
    for key in ("filePath", "file_path", "path", "target", "file"):
        p = ti.get(key)
        if isinstance(p, str) and p:
            cand = p if os.path.isabs(p) else os.path.join(cwd, p)
            if os.path.exists(cand):
                target = cand
                break

    findings = run_guards(target)
    errors = [f for f in findings if f.get("severity") == "error"]
    warns = [f for f in findings if f.get("severity") == "warn"]

    extra = {}
    if errors:
        lines = ["STATIC GATE FINDINGS — the code just written has version-correctness "
                 "defects that will NOT compile/run on this project. Fix them now, "
                 "exactly as instructed:"]
        for e in errors[:15]:
            try:
                rel = os.path.relpath(e["file"], cwd)
            except Exception:
                rel = e.get("file", "?")
            lines.append(f"- {rel}:{e.get('line', '?')} [{e.get('rule')}] {e.get('why')}")
            lines.append(f"  fix: {e.get('fix')}")
        extra = {
            "additionalContext": "\n".join(lines),
            "systemMessage": f"🛡 [Harness] {len(errors)} error(s) — fix instructions sent to the model",
        }
    elif warns:
        extra = {"systemMessage": f"🛡 [Harness] {len(warns)} warn(s) (quality — see guard output)"}

    print(json.dumps({"continue": True, **extra}, ensure_ascii=False))


if __name__ == "__main__":
    main()

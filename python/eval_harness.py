#!/usr/bin/env python3
"""eval_harness.py — orchestration harness for bulk LLM-agent evaluation.

Runs a batch of queries through an agent CLI and *defensively* collects the output and
generated files. It guards, in code, against the 3 traps repeatedly hit when evaluating /
regression-testing a 122B on-prem LLM:

  1. a query hangs forever        → force the timeout by SIGKILL-ing the whole process group
                                     (killing bun alone left the child core holding the pipe).
  2. endpoint/token blip          → retry on a <10s empty response (endpoint drop / token expiry).
  3. the model silently changes   → --verify-model probes tok/s; if it is faster than expected
     (account-global setting)       it warns (from a contamination incident: slow local 122B → fast cloud).

Design: standard library only · single file · no build/install.
Usage:
  python3 eval_harness.py --queries <dir|files> \
      --cli 'bun cli.ts -p {q} --json --yes' --out /tmp/eval [--workers 2] [--timeout 900]
Query format: markdown table `| N | query | detect-point |` (col0 = number).
Generated files are snapshotted under out/<name>/.snap/<N>/.
"""
import argparse, subprocess, json, os, time, glob, shutil, signal, sys
from concurrent.futures import ThreadPoolExecutor


def extract_queries(path):
    out = []
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if s.startswith("|"):
            c = [x.strip() for x in s.strip("|").split("|")]
            if len(c) >= 2 and c[0].isdigit():
                out.append((c[0], c[1], c[2] if len(c) >= 3 else ""))
    return out


def run_cli(cli_tpl, query, cwd, timeout):
    """Launch the CLI in its own process group; on timeout kill the whole group + children (trap 1)."""
    cmd = [query if a == "{q}" else a for a in cli_tpl]
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True,
                            start_new_session=True)
    timed = False
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed, out = True, ""
        for kill in (lambda: os.killpg(os.getpgid(proc.pid), signal.SIGKILL),
                     lambda: subprocess.run(["pkill", "-9", "-P", str(proc.pid)], timeout=5),
                     proc.kill):
            try:
                kill()
            except Exception:
                pass
        try:
            out, _ = proc.communicate(timeout=10)
        except Exception:
            out = ""
    return out or "", timed


def parse_ndjson(out, timed):
    """NDJSON from the agent CLI: type=result/text/tool/error."""
    text, tools, errors = "", [], (["TIMEOUT"] if timed else [])
    for ln in out.splitlines():
        try:
            o = json.loads(ln)
        except Exception:
            continue
        t = o.get("type")
        if t == "result":
            text = o.get("text", "")
            if o.get("error"):
                errors.append(str(o["error"]))
        elif t == "error":
            errors.append(str(o.get("error", "")))
        elif t == "tool":
            tools.append(o.get("tool", ""))
    return text, tools, errors


def changed_files(ws, t0):
    ch = []
    for p in glob.glob(f"{ws}/**/*", recursive=True):
        if not os.path.isfile(p) or "/.snap/" in p:
            continue
        if any(x in p for x in ("/target/", "/node_modules/", "/build/", "/.git/")):
            continue
        if os.path.getmtime(p) >= t0 - 1:
            ch.append(p)
    return ch


def snapshot(ws, num, changed):
    d = os.path.join(ws, ".snap", str(num))
    os.makedirs(d, exist_ok=True)
    for p in changed:
        try:
            if os.path.getsize(p) <= 80_000:
                shutil.copy2(p, os.path.join(d, os.path.relpath(p, ws).replace("/", "__")))
        except Exception:
            pass


def run_one(cli_tpl, ws, query, num, timeout):
    t0 = time.time()
    text, tools, errors, timed = "", [], [], False
    for attempt in range(3):                                   # trap 2: retry on empty response
        out, timed = run_cli(cli_tpl, query, ws, timeout)
        text, tools, errors = parse_ndjson(out, timed)
        secs = round(time.time() - t0)
        if not (not timed and not text and not tools and secs < 10) or attempt == 2:
            break
        time.sleep(8)
    ch = changed_files(ws, t0)
    snapshot(ws, num, ch)
    return {"text": text, "tools": tools, "errors": errors,
            "changed": sorted(os.path.relpath(p, ws) for p in ch),
            "secs": round(time.time() - t0)}


def verify_model(cli_tpl, timeout, min_tps, max_tps):
    """trap 3: detect a model swap via probe tok/s. Warn if out of range."""
    ws = os.path.join("/tmp", f"eval_probe_{os.getpid()}")
    shutil.rmtree(ws, ignore_errors=True)
    os.makedirs(ws)
    t0 = time.time()
    out, _ = run_cli(cli_tpl, "List 10 REST API best practices, one line each.", ws, timeout)
    text, _, _ = parse_ndjson(out, False)
    secs = max(round(time.time() - t0), 1)
    if not text:                       # empty response = not a (fast) model swap → token expiry/endpoint/sidecar
        print("[verify-model] empty response — suspect token expiry / endpoint drop / sidecar not up "
              "(not a model swap). Re-login / check endpoint and retry.", flush=True)
        return False
    tps = (len(text) // 3) // secs
    ok = min_tps <= tps <= max_tps
    verdict = "OK" if ok else ("OUT OF RANGE — fast = suspected model swap" if tps > max_tps
                               else "OUT OF RANGE — slow/abnormal")
    print(f"[verify-model] ~{tps} tok/s ({verdict})", flush=True)
    return ok


def seed_ws(ws, seed):
    """An empty ws makes the agent misjudge the stack (defaults to Node/Python), so seed a project skeleton."""
    for item in os.listdir(seed):
        s, d = os.path.join(seed, item), os.path.join(ws, item)
        shutil.copytree(s, d) if os.path.isdir(s) else shutil.copy2(s, d)


def process_file(f, cli_tpl, base, timeout, seed=None):
    name = os.path.splitext(os.path.basename(f))[0]
    ws = os.path.join(base, name)
    shutil.rmtree(ws, ignore_errors=True)
    os.makedirs(ws)
    if seed:
        seed_ws(ws, seed)
    lines = [f"\n---\n\n# {name}\n"]
    for num, query, detect in extract_queries(f):
        print(f"[{name} #{num}] {query[:44]}", flush=True)
        r = run_one(cli_tpl, ws, query, num, timeout)
        s = r["text"].replace("\n", " ").strip()[:500]
        lines += [f"\n## #{num} · {query}", f"- detect: {detect}",
                  f"- tools: {', '.join(r['tools']) or 'none'} · {r['secs']}s",
                  f"- error: {' / '.join(r['errors']) or 'none'}",
                  f"- created/changed: {', '.join(r['changed']) or 'none'}",
                  f"- response: {s or '(none)'}"]
    open(os.path.join(base, f"{name}.result.md"), "w", encoding="utf-8").write("\n".join(lines))
    print(f"=== DONE {name} ===", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", nargs="+", required=True, help="query .md files/dirs")
    ap.add_argument("--cli", required=True, help="CLI template ({q}=query). e.g. 'bun cli.ts -p {q} --json --yes'")
    ap.add_argument("--out", default="/tmp/eval", help="output directory")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--verify-model", action="store_true", help="probe tok/s to confirm the model before starting")
    ap.add_argument("--tps-range", default="3:20", help="expected tok/s range min:max (for verify)")
    ap.add_argument("--seed", help="project skeleton dir to copy into each workspace (prevents stack misjudgement)")
    a = ap.parse_args()
    if a.seed and not os.path.isdir(a.seed):
        sys.exit(f"--seed dir not found: {a.seed}")

    cli_tpl = a.cli.split()
    files = []
    for q in a.queries:
        files += sorted(glob.glob(os.path.join(q, "*.md"))) if os.path.isdir(q) else [q]
    if not files:
        sys.exit("no query files")
    os.makedirs(a.out, exist_ok=True)

    if a.verify_model:
        lo, hi = (int(x) for x in a.tps_range.split(":"))
        if not verify_model(cli_tpl, a.timeout, lo, hi):
            sys.exit("model verification failed — not the expected model (contamination guard). "
                     "Adjust --tps-range or check the model.")

    print(f"eval {len(files)} file(s) · {a.workers} workers · timeout {a.timeout}s", flush=True)
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(lambda f: process_file(f, cli_tpl, a.out, a.timeout, a.seed), files))
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()

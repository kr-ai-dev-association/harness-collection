# eval_harness

Orchestration harness that runs a batch of queries through an LLM-agent CLI and defensively collects the output and generated files. Code: `eval_harness.py`.

## Usage
```bash
python3 eval_harness.py \
    --queries <dir|files...> \
    --cli 'bun cli.ts -p {q} --json --yes' \   # {q} = replaced by the query
    --out /tmp/eval [--workers 2] [--timeout 900] [--verify-model] \
    [--seed <project-skeleton-dir>]
```
Query format: markdown table `| N | query | detect-point |` (col0 = number).
Output: `out/<name>.result.md` + per-query snapshots of generated files in `out/<name>/.snap/<N>/`.

`--seed`: copies a skeleton (pom.xml, Application, etc.) into each workspace. **An empty workspace makes the agent misjudge the stack** (for a "build X" query it defaults to Node/Python instead of Spring), so a seed is required to evaluate a specific stack. Seed files are excluded from snapshots; only files the agent newly creates are collected.

## Requirements
Python 3. Assumes the agent CLI emits `--json` NDJSON (`{"type":"result"|"text"|"tool"|"error"}`). No external packages.

## Defenses (the traps it wraps — 3 hit in practice)
| trap | defense |
|---|---|
| a query hangs forever (killing bun leaves the child core holding the pipe) | `start_new_session` + on timeout **SIGKILL the whole process group** + pkill children |
| endpoint/token blip → empty response | retry up to **3 times** on a `<10s` empty response |
| the model silently changes (account-global setting) | `--verify-model`: probe **tok/s**; empty = token/endpoint issue, fast = suspected model swap; abort if out of `--tps-range` |

## Checklist (for the user)
- [ ] Use `--verify-model` first to confirm the expected model (a slow 122B is ~2-13 tok/s)
- [ ] `--timeout` should match your longest query (default 900s); over it the process group is killed
- [ ] `error: TIMEOUT` / `(none)` in results are re-run candidates — may be an infra issue
- [ ] Generated code is kept per-query in `.snap/<N>/` → scan it with a static guard (db2_guard etc.)

## Origin (evidence)
Captured from a real qwen3.5-122b eval pipeline:
- A 900s subprocess timeout only killed **bun, leaving the child core holding stdout**, so a query hung up to 12406s (3.4h) → solved with a process-group SIGKILL.
- Endpoint drops / token expiry produced mass **1~17s empty responses** → retry guard.
- The model silently switched from **qwen→a cloud model** via the account-global admin setting, contaminating half the eval → tok/s probe detects it up front.

## Caveats (honestly)
- The NDJSON `type` field assumes the **banya CLI format**. For a different agent, adjust `parse_ndjson`.
- `--verify-model` is a one-shot tok/s heuristic (not an exact model-ID check). Effective when the speed gap is large (local vLLM vs cloud). It also flags an empty response separately (token/endpoint/sidecar), which is not a model swap.
- File-change detection is mtime-based — parallel workers use per-worker workspaces (`out/<name>/`) for isolation.

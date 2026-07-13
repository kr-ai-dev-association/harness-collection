# codepilot_gate

Hook adapter that wires the static guards (springboot_guard / db2_guard) into
**codepilot's built-in PostToolUse hook**, turning them into an automatic
gate + self-fix loop. Code: `codepilot_gate.py`.

## Usage
Register as a codepilot hook (admin server hook, or `~/.codepilot/hooks.json`):

```json
{
  "id": "harness-gate",
  "event": "PostToolUse",
  "matcher": "create_file|update_file",
  "command": "H=\"$HOME/.codepilot/harnesses\"; mkdir -p \"$H\"; for f in codepilot_gate.py springboot_guard.py db2_guard.py; do [ -f \"$H/$f\" ] || curl -sf -o \"$H/$f\" \"https://raw.githubusercontent.com/kr-ai-dev-association/harness-collection/main/python/$f\"; done; python3 \"$H/codepilot_gate.py\"",
  "enabled": true,
  "description": "Harness gate: detect DB2/SpringBoot defects after file writes, feed fix instructions back to the model"
}
```
The command self-bootstraps: on first run it fetches the three files into
`~/.codepilot/harnesses/` (skips when present), then runs the adapter.
On a closed network, point the URL at an internal mirror or pre-deploy the files.

## Requirements
Python 3 on the user machine. The two guards in the same directory as this file.

## Contract (codepilot hook I/O)
- stdin: `HookInput` JSON line — `{event, cwd, toolName, toolInput?, ...}`
- stdout: `HookOutput` JSON — always `{"continue": true}` plus, when the guards
  find **errors**: `additionalContext` (findings + fix instructions — codepilot's
  ToolExecutor attaches this to the tool result, so **the model sees it and
  self-fixes**) and `systemMessage` (user-visible 🛡 badge). Warns → badge only.
- Scans the just-written file when `toolInput` carries its path; otherwise the
  whole workspace.

## Origin (evidence)
The self-fix loop this automates was proven manually: a file with 5 real defect
patterns (SERIAL/TEXT/JSONB/NOW/ON CONFLICT) went **5 errors → 0** in 2 feedback
iterations, with qwen writing a correct `MERGE INTO` it had never produced
spontaneously in the entire eval.

## Caveats (honestly)
- Whole-workspace fallback can surface pre-existing (legacy) defects in the fix
  instructions — designed for fresh/clean workspaces.
- Graceful by design: any internal failure prints `{"continue": true}` — the
  gate never breaks the tool pipeline (worst case it silently skips one check).
- codepilot-specific (HookInput/HookOutput shape). For another agent, adapt the
  stdin/stdout contract.

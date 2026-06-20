# e2e-harness

A very simple Playwright e2e runner. A single Node script with no dependencies and no build.

1. Installs Playwright if the target project doesn't have it (`@playwright/test` + browsers).
2. Finds `*.spec.ts` / `*.spec.js` in the directory (excluding `node_modules`).
3. Runs them and shows **Playwright's result/error output as-is**.
   It also tees the output to `<APP>/e2e-harness.log`, so if a runner backgrounds the
   command and hides its stdout, you can still read the result from that log file.

## Requirements
- Node.js ≥ 18
- The target project must have a `playwright.config.*`.

## Usage
```bash
# From the target app directory
/path/to/nodejs/e2e-llm-harness/e2e-harness

# Or specify the target with --cwd; anything after `--` is forwarded to playwright
/path/to/nodejs/e2e-llm-harness/e2e-harness --cwd ./my-app -- --workers 1
```

The exit code mirrors Playwright's exit code (1 on failure).

import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { dedupe } from "./util.js";
import type { RunResult, RunSummary, TestOutcome, TestResult, TestStatus } from "./types.js";

export interface RunOptions {
  /** Project root where Playwright is installed/configured. */
  cwd: string;
  /** Specific spec files/filters to run. Empty = whatever the config selects. */
  specs?: string[];
  /** Extra args appended to `playwright test`. */
  extraArgs?: string[];
  workers?: number;
  /** Command to invoke Playwright. Default ["npx", "playwright"]. */
  command?: string[];
  env?: Record<string, string>;
  /** Hard timeout for the whole run (ms). */
  timeoutMs?: number;
  /** Stream stdout/stderr chunks as they arrive. */
  onOutput?: (chunk: string) => void;
}

/**
 * Run Playwright tests and parse the JSON report into a structured result.
 * Shells out to the target project's own Playwright via `npx`, so the harness
 * works with any project regardless of Playwright version.
 */
export async function runTests(opts: RunOptions): Promise<RunResult> {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "e2e-harness-"));
  const jsonPath = path.join(tmpDir, "results.json");

  const command = opts.command ?? ["npx", "playwright"];
  const bin = command[0]!;
  const args = [
    ...command.slice(1),
    "test",
    ...(opts.specs ?? []),
    "--reporter=json",
    ...(opts.workers ? [`--workers=${opts.workers}`] : []),
    ...(opts.extraArgs ?? []),
  ];

  const { code, stdout, stderr } = await spawnCapture(bin, args, {
    cwd: opts.cwd,
    env: { ...process.env, ...opts.env, PLAYWRIGHT_JSON_OUTPUT_NAME: jsonPath },
    timeoutMs: opts.timeoutMs,
    onOutput: opts.onOutput,
  });

  let raw: PlaywrightReport;
  try {
    raw = JSON.parse(await fs.readFile(jsonPath, "utf8")) as PlaywrightReport;
  } catch {
    // Some setups stream the JSON report to stdout instead of a file.
    try {
      raw = JSON.parse(stdout) as PlaywrightReport;
    } catch {
      throw new Error(
        `Could not read Playwright JSON report at ${jsonPath} (exit ${code}).\n` +
          `stderr:\n${stderr.slice(0, 1000)}`,
      );
    }
  }

  const tests = flatten(raw);
  return {
    summary: summarize(tests),
    tests,
    rawJsonPath: jsonPath,
    exitCode: code,
    stdout,
    stderr,
  };
}

function flatten(report: PlaywrightReport): TestResult[] {
  const out: TestResult[] = [];

  const visit = (suite: PwSuite, titles: string[], fileHint?: string): void => {
    const file = suite.file ?? fileHint;
    // Skip the synthetic top-level suite title (the file path) to keep titles clean.
    const isFileTitle = !!suite.title && suite.title === suite.file;
    const chain = suite.title && !isFileTitle ? [...titles, suite.title] : titles;

    for (const spec of suite.specs ?? []) {
      for (const test of spec.tests ?? []) {
        const results = test.results ?? [];
        const last = results[results.length - 1];
        const errors: string[] = [];
        for (const r of results) {
          if (r.error?.message) errors.push(stringifyError(r.error));
          for (const e of r.errors ?? []) if (e?.message) errors.push(stringifyError(e));
        }
        out.push({
          title: [...chain, spec.title].filter(Boolean).join(" › "),
          file: spec.file ?? file ?? "unknown",
          line: spec.line,
          status: (last?.status ?? "skipped") as TestStatus,
          outcome: test.status as TestOutcome | undefined,
          durationMs: last?.duration ?? 0,
          errors: dedupe(errors),
          retries: last?.retry ?? 0,
        });
      }
    }
    for (const child of suite.suites ?? []) visit(child, chain, file);
  };

  for (const suite of report.suites ?? []) visit(suite, []);
  return out;
}

function summarize(tests: TestResult[]): RunSummary {
  const s: RunSummary = { total: tests.length, passed: 0, failed: 0, skipped: 0, flaky: 0, durationMs: 0 };
  for (const t of tests) {
    s.durationMs += t.durationMs;
    if (t.outcome === "flaky") s.flaky++;
    if (t.status === "passed") s.passed++;
    else if (t.status === "skipped") s.skipped++;
    else s.failed++; // failed | timedOut | interrupted
  }
  return s;
}

function stringifyError(err: { message?: string; stack?: string }): string {
  return (err.stack || err.message || "").trim();
}

interface SpawnOpts {
  cwd: string;
  env: NodeJS.ProcessEnv;
  timeoutMs?: number;
  onOutput?: (chunk: string) => void;
}

function spawnCapture(
  cmd: string,
  args: string[],
  o: SpawnOpts,
): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, {
      cwd: o.cwd,
      env: o.env,
      shell: process.platform === "win32",
    });
    let stdout = "";
    let stderr = "";
    let timer: NodeJS.Timeout | undefined;
    if (o.timeoutMs) {
      timer = setTimeout(() => {
        child.kill("SIGKILL");
        reject(new Error(`Playwright run timed out after ${o.timeoutMs}ms`));
      }, o.timeoutMs);
    }
    child.stdout.on("data", (d: Buffer) => {
      const s = d.toString();
      stdout += s;
      o.onOutput?.(s);
    });
    child.stderr.on("data", (d: Buffer) => {
      const s = d.toString();
      stderr += s;
      o.onOutput?.(s);
    });
    child.on("error", (err) => {
      if (timer) clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code) => {
      if (timer) clearTimeout(timer);
      resolve({ code: code ?? -1, stdout, stderr });
    });
  });
}

// --- Minimal shape of the Playwright JSON report we rely on ---
interface PlaywrightReport {
  suites?: PwSuite[];
}
interface PwSuite {
  title?: string;
  file?: string;
  specs?: PwSpec[];
  suites?: PwSuite[];
}
interface PwSpec {
  title: string;
  file?: string;
  line?: number;
  tests?: PwTest[];
}
interface PwTest {
  status?: string;
  results?: PwResult[];
}
interface PwResult {
  status?: string;
  duration?: number;
  retry?: number;
  error?: PwError;
  errors?: PwError[];
}
interface PwError {
  message?: string;
  stack?: string;
}

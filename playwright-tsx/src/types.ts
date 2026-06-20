/** Final per-attempt status as reported by Playwright. */
export type TestStatus = "passed" | "failed" | "timedOut" | "skipped" | "interrupted";

/** Overall outcome across retries, as reported by Playwright. */
export type TestOutcome = "expected" | "unexpected" | "flaky" | "skipped";

export interface TestResult {
  /** Full title including describe blocks. */
  title: string;
  file: string;
  line?: number;
  /** Status of the last attempt. */
  status: TestStatus;
  /** Outcome across all attempts (flaky = failed then passed on retry). */
  outcome?: TestOutcome;
  durationMs: number;
  /** Error messages/stacks collected across attempts. */
  errors: string[];
  /** Retry count of the last attempt (0 = first try). */
  retries: number;
}

export interface RunSummary {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  flaky: number;
  durationMs: number;
}

export interface RunResult {
  summary: RunSummary;
  tests: TestResult[];
  /** Path to the raw Playwright JSON report. */
  rawJsonPath?: string;
  exitCode: number;
  stdout: string;
  stderr: string;
}

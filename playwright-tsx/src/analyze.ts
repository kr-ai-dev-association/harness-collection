import type { LLMClient } from "./llm/types.js";
import type { RunResult, TestResult } from "./types.js";

export interface AnalyzeOptions {
  /** Max characters of error text to include per test (keeps the prompt bounded). */
  maxErrorChars?: number;
  /** Extra context to help the model distinguish app-bug vs test-bug. */
  appContext?: string;
  temperature?: number;
  maxTokens?: number;
  signal?: AbortSignal;
}

const SYSTEM = `You are a senior test engineer triaging Playwright e2e results.
Produce a concise Markdown report with:
1. A one-line overall verdict plus pass/fail/flaky counts.
2. For each FAILING or FLAKY test, a bullet containing:
   - the test title,
   - a root-cause category from [app-bug | test-bug | selector | timing/flaky | environment | unknown],
   - a short explanation grounded in the actual error message,
   - a concrete suggested fix.
3. A short "Recommended next actions" list.
Be specific. Do not invent details that the errors do not support. Keep it tight.`;

/**
 * Feed run results to the LLM and get back a Markdown triage report.
 * Only failing/flaky tests are sent in detail to keep the prompt small.
 */
export async function analyzeResults(
  llm: LLMClient,
  run: RunResult,
  opts: AnalyzeOptions = {},
): Promise<string> {
  const maxErr = opts.maxErrorChars ?? 1500;
  const failing = run.tests.filter(
    (t) => (t.status !== "passed" && t.status !== "skipped") || t.outcome === "flaky",
  );

  const payload = {
    summary: run.summary,
    exitCode: run.exitCode,
    failing: failing.map((t) => compact(t, maxErr)),
  };

  const user = [
    opts.appContext ? `App context:\n${opts.appContext}\n` : "",
    "Playwright run results (JSON):",
    "```json",
    JSON.stringify(payload, null, 2),
    "```",
  ]
    .filter(Boolean)
    .join("\n");

  return llm.complete(
    [
      { role: "system", content: SYSTEM },
      { role: "user", content: user },
    ],
    {
      temperature: opts.temperature ?? 0.2,
      maxTokens: opts.maxTokens ?? 1500,
      signal: opts.signal,
    },
  );
}

function compact(t: TestResult, maxErr: number) {
  return {
    title: t.title,
    file: t.file,
    line: t.line,
    status: t.status,
    outcome: t.outcome,
    durationMs: t.durationMs,
    errors: t.errors.map((e) => e.slice(0, maxErr)),
  };
}

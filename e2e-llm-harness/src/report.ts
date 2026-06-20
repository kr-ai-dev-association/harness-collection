import type { RunResult } from "./types.js";

/** One-line summary, e.g. "4/5 passed, 1 failed (72.3s)". */
export function formatSummaryLine(run: RunResult): string {
  const s = run.summary;
  return (
    `${s.passed}/${s.total} passed` +
    (s.failed ? `, ${s.failed} failed` : "") +
    (s.flaky ? `, ${s.flaky} flaky` : "") +
    (s.skipped ? `, ${s.skipped} skipped` : "") +
    ` (${(s.durationMs / 1000).toFixed(1)}s)`
  );
}

/** Full Markdown report combining run stats, per-test list, and optional LLM analysis. */
export function formatReport(run: RunResult, analysis?: string): string {
  const lines: string[] = ["# E2E Run Report", ""];
  lines.push(`**Result:** ${formatSummaryLine(run)}  `);
  lines.push(`**Exit code:** ${run.exitCode}`, "");
  lines.push("## Tests", "");
  for (const t of run.tests) {
    const icon =
      t.status === "passed"
        ? t.outcome === "flaky"
          ? "⚠️"
          : "✓"
        : t.status === "skipped"
          ? "•"
          : "✘";
    lines.push(`- ${icon} \`${t.status}\` ${t.title} — ${(t.durationMs / 1000).toFixed(1)}s`);
  }
  if (analysis && analysis.trim()) {
    lines.push("", "## LLM Analysis", "", analysis.trim());
  }
  return lines.join("\n");
}

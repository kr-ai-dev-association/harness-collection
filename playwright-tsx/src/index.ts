export { E2EHarness } from "./harness.js";
export type { HarnessConfig, PipelineResult } from "./harness.js";

export { discoverSpecs } from "./discover.js";
export type { DiscoverOptions } from "./discover.js";

export { runTests } from "./run.js";
export type { RunOptions } from "./run.js";

export { generateSpec } from "./generate.js";
export type { GenerateSpecOptions } from "./generate.js";

export { analyzeResults } from "./analyze.js";
export type { AnalyzeOptions } from "./analyze.js";

export { formatReport, formatSummaryLine } from "./report.js";

export type {
  RunResult,
  RunSummary,
  TestResult,
  TestStatus,
  TestOutcome,
} from "./types.js";

export {
  OpenAICompatibleClient,
} from "./llm/index.js";
export type {
  LLMClient,
  LLMMessage,
  LLMCompleteOptions,
  LLMRole,
  OpenAICompatibleConfig,
} from "./llm/index.js";

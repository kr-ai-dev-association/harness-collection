import { promises as fs } from "node:fs";
import path from "node:path";
import type { LLMClient } from "./llm/types.js";
import { discoverSpecs, type DiscoverOptions } from "./discover.js";
import { runTests, type RunOptions } from "./run.js";
import { generateSpec, type GenerateSpecOptions } from "./generate.js";
import { analyzeResults, type AnalyzeOptions } from "./analyze.js";
import { formatReport } from "./report.js";
import type { RunResult } from "./types.js";

export interface HarnessConfig {
  /** Project root that contains the Playwright setup. */
  cwd: string;
  /** Any LLMClient. Required only for generate()/analyze(). */
  llm?: LLMClient;
  /** Base URL passed to generated tests. */
  baseURL?: string;
  /** Shared app context fed into generation and analysis. */
  appContext?: string;
}

export interface PipelineResult {
  discovered: string[];
  run: RunResult;
  analysis?: string;
  report: string;
}

/**
 * Orchestrates the full loop: discover → run → analyze. Each step is also
 * available standalone. Generation/analysis require an LLMClient; discovery and
 * running do not.
 */
export class E2EHarness {
  constructor(private readonly cfg: HarnessConfig) {}

  /** Find spec files under the project. */
  discover(opts?: Partial<DiscoverOptions>): Promise<string[]> {
    return discoverSpecs({ cwd: this.cfg.cwd, ...opts });
  }

  /** Run Playwright tests and parse the results. */
  run(opts?: Partial<RunOptions>): Promise<RunResult> {
    return runTests({ cwd: this.cfg.cwd, ...opts });
  }

  /** Generate a Playwright spec from a natural-language scenario. */
  generate(opts: GenerateSpecOptions): Promise<string> {
    return generateSpec(this.requireLLM(), {
      baseURL: this.cfg.baseURL,
      appContext: this.cfg.appContext,
      ...opts,
    });
  }

  /** Generate a spec and write it to disk (relative to cwd). Returns the abs path. */
  async generateToFile(filePath: string, opts: GenerateSpecOptions): Promise<string> {
    const code = await this.generate(opts);
    const abs = path.resolve(this.cfg.cwd, filePath);
    await fs.mkdir(path.dirname(abs), { recursive: true });
    await fs.writeFile(abs, code.endsWith("\n") ? code : code + "\n", "utf8");
    return abs;
  }

  /** Triage run results into a Markdown report via the LLM. */
  analyze(run: RunResult, opts?: AnalyzeOptions): Promise<string> {
    return analyzeResults(this.requireLLM(), run, { appContext: this.cfg.appContext, ...opts });
  }

  /** discover → run → (analyze if an LLM is configured) → formatted report. */
  async pipeline(opts?: {
    specs?: string[];
    run?: Partial<RunOptions>;
    analyze?: AnalyzeOptions;
  }): Promise<PipelineResult> {
    const discovered = opts?.specs ?? (await this.discover());
    const run = await this.run({ specs: discovered, ...opts?.run });
    let analysis: string | undefined;
    if (this.cfg.llm) analysis = await this.analyze(run, opts?.analyze);
    return { discovered, run, analysis, report: formatReport(run, analysis) };
  }

  private requireLLM(): LLMClient {
    if (!this.cfg.llm) {
      throw new Error("This operation requires an LLMClient. Provide one in HarnessConfig.llm.");
    }
    return this.cfg.llm;
  }
}

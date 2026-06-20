#!/usr/bin/env node
import { promises as fs } from "node:fs";
import path from "node:path";
import { E2EHarness } from "./harness.js";
import { OpenAICompatibleClient } from "./llm/openai-compatible.js";
import type { LLMClient } from "./llm/types.js";
import { formatReport, formatSummaryLine } from "./report.js";

const USAGE = `e2e-harness — LLM-agnostic Playwright harness

Usage:
  e2e-harness discover [--cwd .] [--root e2e]
  e2e-harness run [--cwd .] [--workers 1] [spec ...]
  e2e-harness generate "<scenario>" --out e2e/foo.spec.ts [--base-url URL] [--example FILE] [--context FILE]
  e2e-harness analyze [--cwd .] [--workers 1] [spec ...]      # run, then LLM triage
  e2e-harness pipeline [--cwd .] [--out report.md]            # discover + run + analyze

LLM config via env (OpenAI-compatible; implement LLMClient for other providers):
  LLM_BASE_URL   e.g. https://host/v1
  LLM_MODEL      e.g. qwen3.5-122b   (must match GET {LLM_BASE_URL}/models)
  LLM_API_KEY    optional bearer token
  LLM_NO_THINK   set to 1 to disable "thinking" on Qwen/vLLM models
  LLM_TIMEOUT_MS default 60000
`;

interface Args {
  positionals: string[];
  flags: Record<string, string | boolean>;
}

function parseArgs(argv: string[]): Args {
  const positionals: string[] = [];
  const flags: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]!;
    if (a.startsWith("--")) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next === undefined || next.startsWith("--")) flags[key] = true;
      else {
        flags[key] = next;
        i++;
      }
    } else positionals.push(a);
  }
  return { positionals, flags };
}

function str(flags: Args["flags"], key: string): string | undefined {
  const v = flags[key];
  return typeof v === "string" ? v : undefined;
}

function llmFromEnv(): LLMClient | undefined {
  const baseURL = process.env.LLM_BASE_URL;
  const model = process.env.LLM_MODEL;
  if (!baseURL || !model) return undefined;
  return new OpenAICompatibleClient({
    baseURL,
    model,
    apiKey: process.env.LLM_API_KEY,
    extraBody: process.env.LLM_NO_THINK
      ? { chat_template_kwargs: { enable_thinking: false } }
      : undefined,
    timeoutMs: process.env.LLM_TIMEOUT_MS ? Number(process.env.LLM_TIMEOUT_MS) : 60_000,
  });
}

function requireLLM(): LLMClient {
  const llm = llmFromEnv();
  if (!llm) {
    console.error("Error: this command needs an LLM. Set LLM_BASE_URL and LLM_MODEL (see --help).");
    process.exit(2);
  }
  return llm;
}

async function main(): Promise<void> {
  const { positionals, flags } = parseArgs(process.argv.slice(2));
  const command = positionals[0];

  if (!command || flags.help || flags.h) {
    console.log(USAGE);
    return;
  }

  const cwd = path.resolve(str(flags, "cwd") ?? process.cwd());
  const workers = flags.workers ? Number(str(flags, "workers")) : undefined;
  const roots = flags.root ? [str(flags, "root")!] : undefined;

  switch (command) {
    case "discover": {
      const harness = new E2EHarness({ cwd });
      const specs = await harness.discover(roots ? { roots } : undefined);
      if (specs.length === 0) console.log("(no spec files found)");
      else specs.forEach((s) => console.log(s));
      break;
    }

    case "run": {
      const harness = new E2EHarness({ cwd });
      const specs = positionals.slice(1);
      const run = await harness.run({ specs, workers, onOutput: (c) => process.stderr.write(c) });
      const report = formatReport(run);
      console.log("\n" + report);
      await writeOut(cwd, str(flags, "out"), report);
      process.exitCode = run.summary.failed > 0 ? 1 : 0;
      break;
    }

    case "generate": {
      const scenario = positionals[1];
      const out = str(flags, "out");
      if (!scenario || !out) {
        console.error('Error: generate needs a scenario and --out. e.g. generate "login works" --out e2e/login.spec.ts');
        process.exit(2);
      }
      const harness = new E2EHarness({
        cwd,
        llm: requireLLM(),
        baseURL: str(flags, "base-url"),
        appContext: await readMaybe(cwd, str(flags, "context")),
      });
      const abs = await harness.generateToFile(out, {
        scenario,
        exampleSpec: await readMaybe(cwd, str(flags, "example")),
        language: out.endsWith(".js") ? "javascript" : "typescript",
      });
      console.log(`Wrote ${path.relative(cwd, abs)}`);
      break;
    }

    case "analyze": {
      const harness = new E2EHarness({ cwd, llm: requireLLM() });
      const specs = positionals.slice(1);
      const run = await harness.run({ specs, workers, onOutput: (c) => process.stderr.write(c) });
      const analysis = await harness.analyze(run);
      const report = formatReport(run, analysis);
      console.log("\n" + report);
      await writeOut(cwd, str(flags, "out"), report);
      process.exitCode = run.summary.failed > 0 ? 1 : 0;
      break;
    }

    case "pipeline": {
      const harness = new E2EHarness({ cwd, llm: llmFromEnv() });
      const result = await harness.pipeline({
        run: { workers, onOutput: (c) => process.stderr.write(c) },
      });
      console.log("\n" + result.report);
      await writeOut(cwd, str(flags, "out"), result.report);
      process.exitCode = result.run.summary.failed > 0 ? 1 : 0;
      break;
    }

    default:
      console.error(`Unknown command: ${command}\n`);
      console.log(USAGE);
      process.exit(2);
  }
}

async function readMaybe(cwd: string, file?: string): Promise<string | undefined> {
  if (!file) return undefined;
  return fs.readFile(path.resolve(cwd, file), "utf8");
}

/** Persist the report to a file so results survive backgrounded/stream-less runners. */
async function writeOut(cwd: string, out: string | undefined, content: string): Promise<void> {
  if (!out) return;
  const abs = path.resolve(cwd, out);
  await fs.writeFile(abs, content.endsWith("\n") ? content : content + "\n", "utf8");
  console.error(`\nReport written to ${out}`);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});

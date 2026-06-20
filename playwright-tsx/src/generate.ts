import type { LLMClient } from "./llm/types.js";
import { stripCodeFences } from "./util.js";

export interface GenerateSpecOptions {
  /** Natural-language scenario(s) the test should cover. */
  scenario: string;
  baseURL?: string;
  /** Free-form app context: routes, key selectors / data-testids, auth flow, etc. */
  appContext?: string;
  /** An existing spec whose conventions/style the new test should follow. */
  exampleSpec?: string;
  language?: "typescript" | "javascript";
  temperature?: number;
  maxTokens?: number;
  signal?: AbortSignal;
}

const SYSTEM = `You are a senior QA automation engineer who writes end-to-end UI tests with @playwright/test.
Rules:
- Output ONLY the complete test file source. No prose, no explanations, no Markdown code fences.
- Import from '@playwright/test': import { test, expect } from '@playwright/test'.
- Prefer role/label/test-id locators (getByRole, getByLabel, getByTestId); use CSS only when necessary.
- Use web-first assertions (await expect(locator).toBeVisible(), toContainText, ...) instead of fixed sleeps.
- Keep tests deterministic and independent; use test.describe / test.beforeEach where it helps.
- Never invent selectors or behavior that contradicts the provided app context.`;

/**
 * Ask the LLM to produce a Playwright spec for the given scenario.
 * Returns the raw test-file source (code fences stripped).
 */
export async function generateSpec(llm: LLMClient, opts: GenerateSpecOptions): Promise<string> {
  const lang = opts.language ?? "typescript";
  const parts: string[] = [`Target language: ${lang}.`];
  if (opts.baseURL) parts.push(`Base URL: ${opts.baseURL}`);
  if (opts.appContext) parts.push(`App context:\n${opts.appContext}`);
  if (opts.exampleSpec) {
    parts.push(`Follow the conventions of this existing test:\n\n${opts.exampleSpec}`);
  }
  parts.push(`Scenario(s) to cover:\n${opts.scenario}`);
  parts.push("Write the full test file now.");

  const text = await llm.complete(
    [
      { role: "system", content: SYSTEM },
      { role: "user", content: parts.join("\n\n") },
    ],
    {
      temperature: opts.temperature ?? 0.2,
      maxTokens: opts.maxTokens ?? 2048,
      signal: opts.signal,
    },
  );
  return stripCodeFences(text);
}

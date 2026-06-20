import type { LLMClient, LLMCompleteOptions, LLMMessage } from "./types.js";

export interface OpenAICompatibleConfig {
  /** Base URL up to and including `/v1`, e.g. "https://host/v1" or "http://localhost:8002/v1". */
  baseURL: string;
  /** Exact model id from `GET {baseURL}/models`, e.g. "qwen3.5-122b". */
  model: string;
  /** Bearer token. Omit if the server requires no auth. */
  apiKey?: string;
  /**
   * Extra fields merged into the request body. For Qwen/vLLM "thinking" models,
   * pass `{ chat_template_kwargs: { enable_thinking: false } }` to disable reasoning.
   */
  extraBody?: Record<string, unknown>;
  /** Extra HTTP headers. */
  headers?: Record<string, string>;
  /** Per-request timeout in ms. Default 60000. */
  timeoutMs?: number;
  defaultTemperature?: number;
  defaultMaxTokens?: number;
  /** Display name for reports. Defaults to `openai-compatible:{model}`. */
  name?: string;
}

/**
 * LLMClient for any OpenAI-compatible `/chat/completions` endpoint
 * (OpenAI, vLLM, Together, Ollama's OpenAI shim, the internal Qwen server, ...).
 */
export class OpenAICompatibleClient implements LLMClient {
  readonly name: string;
  private readonly cfg: OpenAICompatibleConfig;

  constructor(cfg: OpenAICompatibleConfig) {
    if (!cfg.baseURL) throw new Error("OpenAICompatibleClient: baseURL is required");
    if (!cfg.model) throw new Error("OpenAICompatibleClient: model is required");
    this.cfg = cfg;
    this.name = cfg.name ?? `openai-compatible:${cfg.model}`;
  }

  async complete(messages: LLMMessage[], options?: LLMCompleteOptions): Promise<string> {
    const url = `${this.cfg.baseURL.replace(/\/$/, "")}/chat/completions`;
    const maxTokens = options?.maxTokens ?? this.cfg.defaultMaxTokens;
    const body: Record<string, unknown> = {
      model: this.cfg.model,
      messages,
      temperature: options?.temperature ?? this.cfg.defaultTemperature ?? 0.1,
      ...(maxTokens ? { max_tokens: maxTokens } : {}),
      ...this.cfg.extraBody,
    };

    const signal = options?.signal ?? AbortSignal.timeout(this.cfg.timeoutMs ?? 60_000);

    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(this.cfg.apiKey ? { Authorization: `Bearer ${this.cfg.apiKey}` } : {}),
          ...this.cfg.headers,
        },
        body: JSON.stringify(body),
        signal,
      });
    } catch (err) {
      throw new Error(`LLM request to ${url} failed: ${(err as Error).message}`);
    }

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`LLM HTTP ${res.status} from ${url}: ${text.slice(0, 500)}`);
    }

    const data = (await res.json()) as ChatCompletionResponse;
    const choice = data?.choices?.[0];
    const content = choice?.message?.content;

    if (typeof content !== "string" || content.trim() === "") {
      const hasReasoning = typeof choice?.message?.reasoning === "string" && choice.message.reasoning.length > 0;
      const hint = hasReasoning
        ? " The response only filled a `reasoning` field — this is a thinking model. " +
          "Disable thinking via extraBody, e.g. { chat_template_kwargs: { enable_thinking: false } }."
        : "";
      throw new Error(
        `LLM returned empty content (finish_reason=${choice?.finish_reason ?? "unknown"}).${hint}`,
      );
    }

    return content;
  }
}

interface ChatCompletionResponse {
  choices?: Array<{
    finish_reason?: string;
    message?: { content?: string | null; reasoning?: string | null };
  }>;
}

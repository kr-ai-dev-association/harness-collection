export type LLMRole = "system" | "user" | "assistant";

export interface LLMMessage {
  role: LLMRole;
  content: string;
}

export interface LLMCompleteOptions {
  /** Sampling temperature. Lower = more deterministic. */
  temperature?: number;
  /** Maximum number of tokens to generate. */
  maxTokens?: number;
  /** Abort signal for cancellation / timeout. */
  signal?: AbortSignal;
}

/**
 * Provider-agnostic LLM contract. Implement this for any model — OpenAI,
 * Anthropic, Qwen/vLLM, a local model, or a mock for tests. The harness only
 * ever calls `complete`, so plugging in a new provider is a single method.
 */
export interface LLMClient {
  /** Return the assistant's text completion for the given messages. */
  complete(messages: LLMMessage[], options?: LLMCompleteOptions): Promise<string>;
  /** Optional human-readable identifier, surfaced in reports/logs. */
  readonly name?: string;
}

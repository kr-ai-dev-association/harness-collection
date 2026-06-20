# llm_client

Standard usage and caveats for calling an OpenAI-compatible LLM inference server (internal Qwen/vLLM, etc.). Code: `llm_client.py` (standard library only, no dependencies).

## Endpoint / Model

| Item | Value |
|------|-------|
| Base URL | `https://agentgo-qwen.changshininc.com/v1` (example) |
| Chat | `POST {base_url}/chat/completions` |
| Models | `GET {base_url}/models` |
| Model ID | `qwen3.5-122b` |
| Server | vLLM (OpenAI-compatible), max_model_len 131072 |
| Auth | none currently |

> Always use the exact model ID from `/v1/models`. A short name like `qwen` returns `404 The model 'qwen' does not exist`.

```bash
curl -s {base_url}/models | jq '.data[].id'   # => "qwen3.5-122b"
```

## Disable thinking — required

`qwen3.5-122b` is a reasoning model: a plain call leaves `message.content` `null` (reasoning goes to `message.reasoning`) and is very slow (can exceed 120s). For extraction/classification and other tasks that don't need reasoning, turn thinking off — `llm_client.chat(...)` with `disable_thinking=True` (default) adds `chat_template_kwargs.enable_thinking=false` to the request. With it off, content typically returns in 4-6s.

## Usage

```python
from llm_client import chat, with_today, extract_json

content = chat(
    [
        {"role": "system", "content": "Extract schedule info and return valid JSON only."},
        {"role": "user", "content": with_today("Set up a 2pm meeting with Samsung Securities today")},
    ],
    base_url="https://host/v1",
    model="qwen3.5-122b",
)
data = extract_json(content)   # defensive parse against code fences/noise
```

Manual check: `python3 llm_client.py <base_url> <model>`

## Caveats

1. **Relative dates/times** — the model doesn't know "now". When handling `today/tomorrow/next week`, inject the current date via `with_today()` (otherwise it converts to an arbitrary past date).
2. **Timeout** — even with thinking off, a 122B model takes 4-6s. Use at least 30s for `timeout` (default). Use more if thinking is on.
3. **Empty content** — if thinking is on or `max_tokens` is too small (output truncated), `content` is empty. `chat()` raises `RuntimeError` in that case (with a thinking hint if `reasoning` is present). `finish_reason=length` means out of tokens.
4. **Structured output (JSON)** — even when told "JSON only", code fences/prose may be added. Parse defensively with `extract_json()`, or enforce a schema with the server's `response_format` (json_object/json_schema) or guided decoding. A regex fallback covers too little to be a safety net.
5. **Network reachability** — the inference server is intranet/VPN-only. From external networks or CI, DNS may fail (NXDOMAIN) or the connection may be refused. `chat()` raises a `RuntimeError` with a hint on connection failure.
6. **max_tokens** — 512 is enough for short structured responses. Use small values only together with thinking off.
7. **temperature** — keep it low (~0.1) for deterministic results like extraction/classification.

## Checklist
- [ ] Verified the model ID via `/v1/models` (`qwen3.5-122b`)
- [ ] `disable_thinking=True` for tasks that don't need reasoning
- [ ] Injected the current time via `with_today()` for relative dates
- [ ] `timeout` >= 30s
- [ ] Handled empty content / `finish_reason=length`
- [ ] Parsed JSON defensively (e.g. `extract_json()`)
- [ ] Endpoint reachable from the target environment

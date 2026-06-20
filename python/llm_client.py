#!/usr/bin/env python3
"""
Helper to call an OpenAI-compatible LLM endpoint (internal Qwen/vLLM, etc.).

Uses only the standard library (urllib), no dependencies. See rules/caveats in
llm_client.md. Key points:
  - Thinking (reasoning) models: turn it off with disable_thinking=True (default).
  - timeout defaults to 30s; raises a clear error if content is empty.
  - For relative dates, inject the current time into the prompt via with_today().
  - For structured output, parse defensively with extract_json().
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any


def chat(
    messages: list[dict[str, str]],
    *,
    base_url: str,
    model: str,
    api_key: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 512,
    disable_thinking: bool = True,
    timeout: float = 30,
    extra_body: dict[str, Any] | None = None,
) -> str:
    """Call `{base_url}/chat/completions` and return the assistant content string.

    base_url example: "https://host/v1". model must be the exact id from /v1/models.
    """
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if disable_thinking:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    if extra_body:
        body.update(extra_body)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"LLM HTTP {e.code} from {req.full_url}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM connection failed {req.full_url}: {e.reason} (check intranet/VPN)") from e

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if not content or not str(content).strip():
        hint = ""
        if message.get("reasoning"):
            hint = " - only the reasoning field was filled (thinking model). Set disable_thinking=True."
        raise RuntimeError(
            f"LLM returned empty content (finish_reason={choice.get('finish_reason')}){hint}"
        )
    return content


def with_today(user_message: str, tz_label: str = "") -> str:
    """Build a user content with the current date injected, for relative-date parsing."""
    today = datetime.now().strftime("%Y-%m-%d (%A)")
    suffix = f" {tz_label}" if tz_label else ""
    return f"Today is {today}{suffix}.\nUser message: {user_message}"


def extract_json(content: str) -> Any:
    """Strip code fences/noise and parse the span from the first '{' to the last '}'."""
    s = content.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if "```" in s:
            s = s.rsplit("```", 1)[0]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in content")
    return json.loads(s[start : end + 1])


if __name__ == "__main__":
    # Quick manual check: python3 llm_client.py <base_url> <model>
    import sys

    if len(sys.argv) < 3:
        print("usage: python3 llm_client.py <base_url> <model>")
        raise SystemExit(2)
    base_url, model = sys.argv[1], sys.argv[2]
    out = chat(
        [
            {"role": "system", "content": "Answer in a single word."},
            {"role": "user", "content": with_today("What day of the week is it today?")},
        ],
        base_url=base_url,
        model=model,
    )
    print(out)

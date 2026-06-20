#!/usr/bin/env python3
"""
OpenAI 호환 LLM 엔드포인트(사내 Qwen/vLLM 등) 호출 헬퍼.

표준 라이브러리(urllib)만 사용한다(무의존). 규칙/주의사항은 llm_client.md 참고.
핵심:
  - thinking(추론) 모델은 disable_thinking=True 로 끈다(기본값).
  - timeout 기본 30초, content 비면 명확한 예외.
  - 상대 날짜는 with_today()로 현재 시각을 프롬프트에 주입.
  - 구조화 출력은 extract_json()으로 방어적 파싱.
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
    """`{base_url}/chat/completions` 를 호출하고 assistant content 문자열을 반환.

    base_url 예: "https://host/v1". model 은 /v1/models 로 확인한 정확한 ID.
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
        raise RuntimeError(f"LLM 연결 실패 {req.full_url}: {e.reason} (사내망/VPN 확인)") from e

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if not content or not str(content).strip():
        hint = ""
        if message.get("reasoning"):
            hint = " — reasoning 필드만 채워짐(추론 모델). disable_thinking=True 필요."
        raise RuntimeError(
            f"LLM 빈 content (finish_reason={choice.get('finish_reason')}){hint}"
        )
    return content


def with_today(user_message: str, tz_label: str = "") -> str:
    """상대 날짜 해석을 위해 현재 날짜를 프롬프트에 주입한 user content 를 만든다."""
    today = datetime.now().strftime("%Y-%m-%d (%A)")
    suffix = f" {tz_label}" if tz_label else ""
    return f"오늘 날짜는 {today}{suffix} 입니다.\n사용자 메시지: {user_message}"


def extract_json(content: str) -> Any:
    """코드펜스/잡음을 제거하고 첫 '{' ~ 마지막 '}' 구간을 JSON 으로 파싱."""
    s = content.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if "```" in s:
            s = s.rsplit("```", 1)[0]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("content 안에서 JSON object 를 찾지 못함")
    return json.loads(s[start : end + 1])


if __name__ == "__main__":
    # 간단한 수동 점검: python3 llm_client.py <base_url> <model>
    import sys

    if len(sys.argv) < 3:
        print("usage: python3 llm_client.py <base_url> <model>")
        raise SystemExit(2)
    base_url, model = sys.argv[1], sys.argv[2]
    out = chat(
        [
            {"role": "system", "content": "한 단어로만 답하라."},
            {"role": "user", "content": with_today("오늘 무슨 요일이야?")},
        ],
        base_url=base_url,
        model=model,
    )
    print(out)

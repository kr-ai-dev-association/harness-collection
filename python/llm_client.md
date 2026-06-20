# llm_client

OpenAI 호환 LLM 추론 서버(사내 Qwen/vLLM 등)를 연동하는 표준 사용법과 주의사항. 코드: `llm_client.py` (표준 라이브러리만, 무의존).

## 엔드포인트 / 모델

| 항목 | 값 |
|------|-----|
| Base URL | `https://agentgo-qwen.changshininc.com/v1` (예시) |
| Chat | `POST {base_url}/chat/completions` |
| 모델 목록 | `GET {base_url}/models` |
| 모델 ID | `qwen3.5-122b` |
| 서버 | vLLM (OpenAI 호환), max_model_len 131072 |
| 인증 | 현재 없음 |

> 모델 ID는 반드시 `/v1/models`로 확인한 정확한 값을 쓸 것. `qwen` 같은 축약명은 `404 The model 'qwen' does not exist` 를 반환한다.

```bash
curl -s {base_url}/models | jq '.data[].id'   # => "qwen3.5-122b"
```

## thinking(추론) 비활성화 — 필수

`qwen3.5-122b`는 추론 모델이라 기본 호출 시 `message.content`가 `null`(사고는 `message.reasoning`)이 되고 응답이 매우 느리다(120초 초과 가능). 추출·분류 등 사고가 불필요한 작업은 thinking을 끈다 — `llm_client.chat(...)`의 `disable_thinking=True`(기본값)가 요청에 `chat_template_kwargs.enable_thinking=false`를 넣는다. 끄면 보통 4~6초에 `content`를 반환한다.

## 사용

```python
from llm_client import chat, with_today, extract_json

content = chat(
    [
        {"role": "system", "content": "일정 정보를 추출해 유효한 JSON만 반환."},
        {"role": "user", "content": with_today("오늘 오후 2시 삼성증권 미팅 잡아줘")},
    ],
    base_url="https://host/v1",
    model="qwen3.5-122b",
)
data = extract_json(content)   # 코드펜스/잡음 방어 파싱
```

수동 점검: `python3 llm_client.py <base_url> <model>`

## 주의사항

1. **상대 날짜·시간** — 모델은 "지금"을 모른다. `오늘/내일/다음주` 를 다루면 `with_today()`로 현재 날짜를 주입하라(미주입 시 임의 과거 날짜로 변환).
2. **타임아웃** — 122B는 thinking을 꺼도 4~6초 걸린다. `timeout`은 최소 30초(기본값). thinking을 켜는 작업이면 더 길게.
3. **빈 content** — thinking이 켜져 있거나 `max_tokens`가 작아 잘리면 `content`가 빈다. `chat()`은 이때 `RuntimeError`를 던진다(`reasoning`이 있으면 thinking 힌트 포함). `finish_reason=length`는 토큰 부족.
4. **구조화 출력(JSON)** — "JSON만 반환"을 지시해도 코드펜스/설명이 붙을 수 있다. `extract_json()`으로 방어 파싱하거나, 서버의 `response_format`(json_object/json_schema)·guided decoding으로 스키마를 강제하라. 정규식 폴백은 적용 범위가 좁아 안전망이 되기 어렵다.
5. **네트워크 도달성** — 추론 서버는 사내망/VPN 전용. 외부망·CI에서는 DNS 실패(NXDOMAIN)/연결 거부 가능. `chat()`은 연결 실패 시 안내 메시지를 포함한 `RuntimeError`를 던진다.
6. **max_tokens** — 짧은 구조화 응답은 512면 충분. 작은 값은 반드시 thinking off와 함께.
7. **temperature** — 추출·분류 등 결정적 결과는 0.1 내외로 낮게.

## 체크리스트
- [ ] 모델 ID를 `/v1/models`로 확인 (`qwen3.5-122b`)
- [ ] 사고 불필요 작업에 `disable_thinking=True`
- [ ] 상대 날짜 시 `with_today()`로 현재 시각 주입
- [ ] `timeout` ≥ 30초
- [ ] 빈 content / `finish_reason=length` 처리
- [ ] JSON은 `extract_json()` 등으로 방어적 파싱
- [ ] 대상 환경에서 엔드포인트 접근 가능

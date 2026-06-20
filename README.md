# harness-collection

LLM 개발 작업에 쓰는 작은 하니스 모음. **언어별 디렉터리**로 나누고, 각 코드 파일/디렉터리와 **같은 이름의 `.md`** 문서를 둔다.

```
nodejs/
  e2e-llm-harness/      # Playwright e2e 러너 (단일 스크립트 e2e-harness)
  e2e-llm-harness.md    # ↑ 문서
python/
  fastapi_guard.py      # FastAPI+SQLAlchemy 정적 규칙 검사기
  fastapi_guard.md      # ↑ 문서
  llm_client.py         # OpenAI 호환 LLM 호출 헬퍼 (thinking off)
  llm_client.md         # ↑ 문서
```

## 목록

| 언어 | 하니스 | 용도 |
|------|--------|------|
| nodejs | [e2e-llm-harness](nodejs/e2e-llm-harness.md) | Playwright 설치·spec 탐색·실행, 출력 그대로 |
| python | [fastapi_guard](python/fastapi_guard.md) | LLM 생성 백엔드 코드의 반복 결함 정적 검사 |
| python | [llm_client](python/llm_client.md) | 사내 OpenAI 호환 LLM 호출(추론 비활성화·방어 파싱) |

각 하니스는 의존성·빌드가 없는 단일 파일을 지향한다.

# harness-collection

LLM 개발 작업에 쓰는 작은 하니스 모음. **언어별 디렉터리**로 나누고, 각 코드 파일/디렉터리와 **같은 이름의 `.md`** 문서를 둔다.

## 가져오기 & 실행

각 하니스는 의존성·빌드가 없으므로 **받아서 바로 실행**한다. 별도 설치 과정은 없다.

```bash
# 1) 전체 클론
git clone https://github.com/kr-ai-dev-association/harness-collection
cd harness-collection

# 2) 필요한 하니스의 .md(스킬 문서)를 읽고, 같은 이름의 코드를 실행
#    python — 검사기:
python python/fastapi_guard.py <TARGET_DIR>
#    python — LLM 호출 헬퍼: 코드에서 import
#      from llm_client import chat, with_today, extract_json   (sys.path 에 python/ 추가)
#    nodejs — Playwright 러너:
nodejs/e2e-llm-harness/e2e-harness --cwd <APP_DIR>
```

단일 파일 하니스는 클론 없이 **raw 다운로드**만으로도 쓸 수 있다.

```bash
curl -O https://raw.githubusercontent.com/kr-ai-dev-association/harness-collection/main/python/fastapi_guard.py
python fastapi_guard.py <TARGET_DIR>
```

> 실행 전 해당 `.md`의 **요구 사항**(예: e2e는 Node ≥18·`playwright.config.*`, fastapi_guard는 Python, llm_client는 도달 가능한 엔드포인트)을 먼저 확인한다.

## 하위 `.md`는 스킬(skill) 문서다

각 하니스의 `.md`는 **LLM/에이전트가 읽고 곧바로 실행에 옮기는 스킬 문서**로 쓰도록 설계되었다. 그래서:

- **최소 토큰**으로 단순화되어 있다 — 배경 설명·예시를 늘어놓지 않고, 무엇을 어떻게 호출하는지만 담는다.
- 문서는 로직을 글로 풀어 쓰지 않고 **옆의 실제 코드 파일을 호출하도록** 안내한다(예: `fastapi_guard.md` → `python fastapi_guard.py`, `llm_client.md` → `from llm_client import chat`). 즉 **문서는 얇게, 동작은 코드로**.
- 코드 파일과 `.md` 파일명이 1:1로 일치하므로, 에이전트가 스킬 문서만 보고 바로 대응 코드를 찾아 실행할 수 있다.

이 규칙 덕분에 새 하니스를 추가할 때도 "코드 + 동명의 얇은 스킬 md" 한 쌍만 만들면 된다.

대부분의 하니스는 **단일 코드 파일**(예: `fastapi_guard.py`)이지만, **복잡한 하니스는 디렉터리**가 될 수 있다. 이때는 디렉터리와 같은 이름의 `.md`를 그 옆에 둔다(예: `nodejs/e2e-llm-harness/` ↔ `nodejs/e2e-llm-harness.md`). 어느 경우든 "코드(파일 또는 디렉터리) ↔ 동명의 스킬 md" 매칭은 동일하다.

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

각 하니스는 의존성·빌드가 없는 단일 파일을 지향하되, 복잡하면 디렉터리로 둘 수 있다.

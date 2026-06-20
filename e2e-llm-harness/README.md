# e2e-llm-harness

LLM에 무관한(provider-agnostic) **Playwright e2e 하니스**. 어떤 LLM이든 인터페이스 하나(`LLMClient`)만 구현하면, e2e 테스트 스크립트를 **생성 → 탐색 → 실행 → 분석**까지 한 번에 돌릴 수 있습니다.

- **generate** — 자연어 시나리오로 Playwright 스펙 생성
- **discover** — 프로젝트에서 e2e 스펙 자동 탐색
- **run** — Playwright 실행 후 JSON 리포트를 구조화 결과로 파싱
- **analyze** — 실패/플래키 테스트를 LLM이 원인 분류 + 수정안까지 리포트

LLM은 `LLMClient` 인터페이스 뒤로 추상화되어 있고, **OpenAI 호환 어댑터**가 기본 포함됩니다(OpenAI, vLLM, 사내 Qwen 서버, Ollama OpenAI shim 등). 다른 제공자는 메서드 하나만 구현하면 됩니다.

---

## 요구 사항

- Node.js **≥ 18** (전역 `fetch` 사용)
- 대상 프로젝트에 **Playwright**가 설치/설정되어 있어야 함 (`@playwright/test`, `playwright.config.*`)
  - 하니스는 대상 프로젝트의 `npx playwright`를 호출하므로 Playwright 버전에 구애받지 않습니다.

## 설치

### A. 저장소에서 직접 빌드

```bash
git clone <this-repo>
cd e2e-llm-harness         # 하니스 디렉터리
npm install
npm run build              # dist/ 생성
```

빌드 후 CLI 실행:

```bash
node dist/cli.js --help
# 또는 전역 링크
npm link
e2e-harness --help
```

### B. 빌드 없이 바로 실행 (개발용)

```bash
npm install
npm run dev -- --help          # tsx로 src/cli.ts 직접 실행
# 예: npm run dev -- discover --cwd ../my-app
```

### C. 의존성으로 사용

```bash
npm install e2e-llm-harness @playwright/test
```

```ts
import { E2EHarness, OpenAICompatibleClient } from "e2e-llm-harness";
```

---

## LLM 설정 (환경 변수)

`generate` / `analyze` / `pipeline`(분석 포함)은 LLM이 필요합니다. 기본 OpenAI 호환 어댑터는 아래 환경 변수로 설정합니다. (`discover`, `run`은 LLM이 필요 없습니다.)

| 변수 | 설명 | 예시 |
|------|------|------|
| `LLM_BASE_URL` | `/v1`까지 포함한 base URL | `https://host/v1` |
| `LLM_MODEL` | `GET {LLM_BASE_URL}/models`로 확인한 정확한 모델 ID | `qwen3.5-122b` |
| `LLM_API_KEY` | (선택) Bearer 토큰. 없으면 생략 | `sk-...` |
| `LLM_NO_THINK` | (선택) `1`이면 Qwen/vLLM 추론 모델의 thinking 비활성화 | `1` |
| `LLM_TIMEOUT_MS` | (선택) 요청 타임아웃. 기본 60000 | `60000` |

`.env.example`을 참고하세요. (셸에서 `export` 하거나 `LLM_BASE_URL=... node dist/cli.js ...` 형태로 전달)

> **thinking 모델 주의:** Qwen3 계열 등 추론 모델은 `content`가 비고 응답이 매우 느릴 수 있습니다. `LLM_NO_THINK=1`을 설정하면 어댑터가 `chat_template_kwargs.enable_thinking=false`를 보내 빠르게 본문을 받습니다.

---

## 실행 방법 (CLI)

아래 예시는 빌드본(`node dist/cli.js`) 기준입니다. 개발 중에는 `npm run dev --` 로 대체할 수 있습니다.

### 1) 스펙 탐색

```bash
node dist/cli.js discover --cwd ../my-app
# e2e/login.spec.ts
# e2e/checkout.spec.ts
```

기본 탐색 위치는 `e2e/`, `tests/`, `test/` 이며, 없으면 프로젝트 전체를 스캔합니다. `--root` 로 직접 지정할 수 있습니다.

### 2) 스펙 생성 (LLM)

```bash
export LLM_BASE_URL=https://host/v1 LLM_MODEL=qwen3.5-122b LLM_NO_THINK=1
node dist/cli.js generate "로그인 후 대시보드가 보인다" \
  --out e2e/login.spec.ts \
  --base-url http://localhost:5173 \
  --example e2e/existing.spec.ts \
  --context app-notes.md \
  --cwd ../my-app
# Wrote e2e/login.spec.ts
```

- `--out` 생성 파일 경로 (확장자가 `.js`면 JavaScript로 생성)
- `--example` 스타일을 따라갈 기존 스펙 파일(선택)
- `--context` 라우트/셀렉터/인증 흐름 등 앱 컨텍스트 파일(선택)

### 3) 실행

```bash
node dist/cli.js run --cwd ../my-app --workers 1
# (테스트별 진행 로그) ...
# 4/5 passed, 1 failed (72.3s)

# 특정 스펙만:
node dist/cli.js run e2e/login.spec.ts --cwd ../my-app
```

### 4) 실행 + LLM 분석

```bash
node dist/cli.js analyze --cwd ../my-app --workers 1
# # E2E Run Report
# **Result:** 4/5 passed, 1 failed (72.3s)
# ## Tests ...
# ## LLM Analysis
# - "패턴 4 ..." — [app-bug] 백엔드가 400 반환 ... 수정안: ...
```

### 5) 전체 파이프라인 (탐색 → 실행 → 분석 → 리포트)

```bash
node dist/cli.js pipeline --cwd ../my-app --out report.md
```

`LLM_*` 환경 변수가 없으면 분석 단계는 건너뛰고 실행 리포트만 출력합니다. 실패가 있으면 종료 코드 `1`을 반환하므로 CI에서 활용할 수 있습니다.

---

## 프로그램 API

```ts
import { E2EHarness, OpenAICompatibleClient } from "e2e-llm-harness";

const llm = new OpenAICompatibleClient({
  baseURL: "https://host/v1",
  model: "qwen3.5-122b",
  extraBody: { chat_template_kwargs: { enable_thinking: false } }, // thinking off
});

const harness = new E2EHarness({
  cwd: "/path/to/my-app",
  llm,
  baseURL: "http://localhost:5173",
  appContext: "라우트: /login, /dashboard. 입력: getByLabel('이메일') ...",
});

// 개별 단계
const specs = await harness.discover();
await harness.generateToFile("e2e/login.spec.ts", { scenario: "로그인 후 대시보드" });
const run = await harness.run({ specs, workers: 1 });
const analysis = await harness.analyze(run);

// 한 번에: 탐색 → 실행 → 분석 → 리포트
const { run: r, report } = await harness.pipeline();
console.log(report);
```

### 다른 LLM 붙이기 (어떤 모델이든)

`LLMClient`는 메서드가 하나뿐이라 어떤 SDK든 감쌀 수 있습니다.

```ts
import Anthropic from "@anthropic-ai/sdk";
import type { LLMClient, LLMMessage } from "e2e-llm-harness";

class AnthropicClient implements LLMClient {
  name = "anthropic:claude";
  private client = new Anthropic();
  async complete(messages: LLMMessage[]): Promise<string> {
    const system = messages.filter((m) => m.role === "system").map((m) => m.content).join("\n");
    const res = await this.client.messages.create({
      model: "claude-opus-4-8",
      max_tokens: 2048,
      system,
      messages: messages
        .filter((m) => m.role !== "system")
        .map((m) => ({ role: m.role as "user" | "assistant", content: m.content })),
    });
    return res.content.filter((b) => b.type === "text").map((b: any) => b.text).join("");
  }
}

const harness = new E2EHarness({ cwd, llm: new AnthropicClient() });
```

---

## 동작 방식 (요약)

| 단계 | 모듈 | 비고 |
|------|------|------|
| 탐색 | `discover.ts` | 파일시스템 워크 + 파일명 패턴 매칭 (의존성 0) |
| 생성 | `generate.ts` | 시나리오/예시/컨텍스트로 프롬프트 구성, 코드펜스 방어 파싱 |
| 실행 | `run.ts` | `npx playwright test --reporter=json` 호출 후 JSON 파싱 |
| 분석 | `analyze.ts` | 실패/플래키만 추려 LLM에 전달, Markdown 리포트 반환 |
| 리포트 | `report.ts` | 실행 통계 + 테스트 목록 + LLM 분석 결합 |

## npm 스크립트

```bash
npm run build       # tsc로 dist/ 빌드
npm run typecheck   # 타입 체크만
npm run dev -- ...  # tsx로 src/cli.ts 직접 실행
```

## 라이선스

MIT

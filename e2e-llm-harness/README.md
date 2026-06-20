# e2e-harness

아주 단순한 Playwright e2e 러너. 의존성·빌드 없는 단일 Node 스크립트.

1. 대상 프로젝트에 Playwright가 없으면 설치한다 (`@playwright/test` + 브라우저).
2. 디렉터리에서 `*.spec.ts` / `*.spec.js` 를 찾는다 (`node_modules` 제외).
3. 실행하고 **Playwright가 출력하는 result/error를 그대로** 보여준다.

## 요구 사항
- Node.js ≥ 18
- 대상 프로젝트에 `playwright.config.*` 가 있어야 한다.

## 사용
```bash
# 대상 앱 디렉터리에서
/path/to/e2e-llm-harness/e2e-harness

# 또는 --cwd 로 대상 지정, `--` 뒤는 playwright 로 그대로 전달
/path/to/e2e-llm-harness/e2e-harness --cwd ./my-app -- --workers 1
```

종료 코드는 Playwright의 종료 코드를 그대로 따른다(실패 시 1).

---
name: e2e-harness
description: Playwright e2e 테스트를 찾아 실행하는 최소 러너. Playwright 미설치 시 자동 설치하고, 디렉터리 내 spec 파일을 찾아 돌린 뒤 결과/에러를 그대로 출력.
---

# e2e-harness

소스/상세: https://github.com/kr-ai-dev-association/harness-collection (`e2e-llm-harness/`)

## 사용
```bash
# 대상 앱 디렉터리에서 실행 (또는 --cwd 로 지정)
/path/to/e2e-llm-harness/e2e-harness
/path/to/e2e-llm-harness/e2e-harness --cwd <APP> -- --workers 1
```
- 하는 일: Playwright 없으면 설치 → `*.spec.ts/js` 찾기 → 실행 → Playwright 출력 그대로.
- **출력은 `<APP>/e2e-harness.log` 에도 저장된다.** 러너가 명령을 백그라운드로 돌려 화면 출력이 안 보이면 이 파일을 읽어라.
- `--` 뒤 인자는 `playwright test` 로 전달된다. 종료 코드는 Playwright를 그대로 따른다(실패 시 1).

---
name: e2e-llm-harness
description: Playwright e2e 테스트를 생성·탐색·실행·분석하는 LLM 무관 하니스. e2e 테스트를 만들거나 돌리거나 실패 원인을 분석할 때 사용.
---

# e2e-llm-harness

소스/상세: https://github.com/kr-ai-dev-association/harness-collection (`e2e-llm-harness/`)

## 사용 (`--cwd`는 대상 프로젝트 루트)
`e2e-harness` 래퍼를 호출하면 **첫 실행 때만 자동으로 install/build 하고, 이후엔 건너뛴다.** 별도 설치 단계 불필요.
```bash
HARNESS=/path/to/e2e-llm-harness/e2e-harness
$HARNESS discover --cwd <APP>                                          # 스펙 탐색
$HARNESS run --cwd <APP> --workers 1 [spec...] --out result.md         # 실행
$HARNESS analyze --cwd <APP> --workers 1 [spec...] --out result.md     # 실행+LLM 분석
$HARNESS pipeline --cwd <APP> --out result.md                         # 탐색→실행→분석
$HARNESS generate "<시나리오>" --out e2e/x.spec.ts --cwd <APP>         # 스펙 생성
```
- 리포트는 stdout + `--out` 파일에 저장된다. **러너가 명령을 백그라운드로 돌리면 stdout이 안 보일 수 있으니 항상 `--out`을 주고 그 파일을 읽어라.**
- 실패가 있으면 종료 코드 1. `generate`/`analyze`/`pipeline`은 아래 LLM 설정 필요.

## LLM 설정 (env)
```bash
export LLM_BASE_URL=https://host/v1   # /v1 포함
export LLM_MODEL=<id>                  # /v1/models 로 확인한 정확한 ID
export LLM_NO_THINK=1                  # 추론 모델이면 필수
# export LLM_API_KEY=...              # 필요 시
```

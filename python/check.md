# check

LLM이 생성한 **FastAPI + SQLAlchemy** 코드에서 반복적으로 나오던 결함을, 코드 내보내기 전에 잡는 정적 검사기. 표준 라이브러리 `ast`만 사용하며 의존성·빌드가 없다. 코드: `check.py`.

## 사용
```bash
python check.py [TARGET_DIR]   # 기본값: 현재 디렉터리
```
- 대상 디렉터리의 모든 `*.py`를 검사한다(`venv`, `__pycache__`, `node_modules` 등 제외).
- **오류(✘)가 있으면 종료 코드 1**, 경고(▲)만 있거나 깨끗하면 0 → CI에 그대로 쓸 수 있다.

출력 예:
```
✘ main.py:42  [규칙 2] 'Schedule' 를 호출하는데 import/정의가 없음 (NameError 후보).
✘ main.py:88  [규칙 7] 외부 HTTP 호출에 timeout= 누락 (requests.post).
▲ main.py:51  [규칙 6] datetime.now() 가 타임존 없이 사용됨. ZoneInfo 등으로 tz를 명시하라.

[harness] 검사 파일 3개 — 오류 2, 경고 1
```

## 검사 규칙

| # | 수준 | 내용 |
|---|------|------|
| 1 | error | `declarative_base()`는 **프로젝트 전체에서 1번만** 호출. 여러 번이면 메타데이터가 갈라져 테이블이 연결되지 않는다. 한 곳(`database.py`)에서만 만들고 나머지는 import. |
| 2 | error | 대문자로 시작하는 식별자를 **호출**하는데 import/정의가 없으면 `NameError` 후보. (예: `Schedule(...)` 인데 import 누락) |
| 3 | warn | `declarative_base()`가 있는데 `Base.metadata.create_all` 호출이 없음 → 마이그레이션이 없다면 추가(개발/SQLite). |
| 4 | error | ORM→Pydantic 변환에 `Model(**obj.__dict__)` 금지. `_sa_instance_state`가 새어 든다. `model_validate(obj)` + `from_attributes=True` 사용. |
| 5 | error | CORS에서 `allow_credentials=True`와 `allow_origins=["*"]` 조합 금지. 명시적 오리진을 나열. |
| 6 | warn | `datetime.now()`를 타임존 없이(naive) 사용. "오늘/내일" 해석 시 `ZoneInfo("Asia/Seoul")` 등 tz 명시. |
| 7 | error | 외부 HTTP 호출(`requests`/`httpx`의 `post/get/...`)에 `timeout=` 누락. |

## 한계
- 규칙 2는 모듈 전역의 정의/임포트만 보는 **휴리스틱**이라 드물게 오탐/누락이 있을 수 있다. 정밀 검사는 `pyflakes`/`ruff`로 보완하라.
- AST 정적 분석이므로 동적으로 생성되는 심볼·런타임 동작은 대상이 아니다.

## 출처
이 규칙들은 동일 프로젝트에서 LLM 코드 생성 시 실제로 발생했던 결함을 정리한 것이다.

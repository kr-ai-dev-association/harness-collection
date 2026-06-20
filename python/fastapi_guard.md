# fastapi_guard

Static checker that catches defects recurring in LLM-generated **FastAPI + SQLAlchemy** code before the code is shipped. Uses only the standard library (`ast`), no dependencies, no build. Code: `fastapi_guard.py`.

## Usage
```bash
python3 fastapi_guard.py [TARGET_DIR]   # default: current directory
```
- Checks every `*.py` under the target dir (excluding `venv`, `__pycache__`, `node_modules`, etc.).
- **Exit code 1 if there are errors (x)**, 0 if only warnings (!) or clean — usable directly in CI.

Example output:
```
x main.py:42  [rule 2] 'Schedule' is called but not imported/defined (possible NameError).
x main.py:88  [rule 7] External HTTP call missing timeout= (requests.post).
! main.py:51  [rule 6] datetime.now() used without a timezone. Specify tz (e.g. ZoneInfo).

[harness] 3 file(s) checked - 2 error(s), 1 warning(s)
```

## Rules

| # | Level | Rule |
|---|-------|------|
| 1 | error | `declarative_base()` must be called **once project-wide**. Calling it multiple times splits the metadata so tables aren't linked. Create it in one place (`database.py`) and import it elsewhere. |
| 2 | error | Calling a capitalized identifier that is not imported/defined is a `NameError` candidate (e.g. `Schedule(...)` without the import). |
| 3 | warn | `declarative_base()` is present but there is no `Base.metadata.create_all` call — add it if there are no migrations (dev/SQLite). |
| 4 | error | Do not use `Model(**obj.__dict__)` for ORM->Pydantic conversion; `_sa_instance_state` leaks in. Use `model_validate(obj)` with `from_attributes=True`. |
| 5 | error | In CORS, do not combine `allow_credentials=True` with `allow_origins=["*"]`. List explicit origins. |
| 6 | warn | `datetime.now()` used without a timezone (naive). When interpreting "today/tomorrow", specify tz such as `ZoneInfo("Asia/Seoul")`. |
| 7 | error | External HTTP calls (`requests`/`httpx` `post/get/...`) missing `timeout=`. |

## Limitations
- Rule 2 only looks at module-level definitions/imports, so it is a **heuristic** with rare false positives/negatives. Complement with `pyflakes`/`ruff` for precise checks.
- Being static AST analysis, it does not cover dynamically created symbols or runtime behavior.

## Origin
These rules summarize defects that actually occurred during LLM code generation in the same project.

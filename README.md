# harness-collection

A small collection of harnesses for LLM development work. Organized into **per-language directories**, with a **`.md` of the same name** next to each code file/directory.

## Get & Run

Each harness has no dependencies and no build step, so you **fetch it and run it directly**. There is no separate install step.

```bash
# 1) Clone the whole repo
git clone https://github.com/kr-ai-dev-association/harness-collection
cd harness-collection

# 2) Read the harness's .md (skill doc), then run the same-named code
#    python — checker:
python3 python/fastapi_guard.py <TARGET_DIR>
#    python — LLM call helper: import from code
#      from llm_client import chat, with_today, extract_json   (add python/ to sys.path)
#    nodejs — Playwright runner:
nodejs/e2e-llm-harness/e2e-harness --cwd <APP_DIR>
```

Single-file harnesses can be used with a **raw download** alone, without cloning.

```bash
curl -O https://raw.githubusercontent.com/kr-ai-dev-association/harness-collection/main/python/fastapi_guard.py
python3 fastapi_guard.py <TARGET_DIR>
```

> Before running, check the **Requirements** in that `.md` (e.g. e2e needs Node ≥18 and `playwright.config.*`, fastapi_guard needs Python, llm_client needs a reachable endpoint).
> Examples use `python3`. On environments that only have `python`, run with `python` instead.

## The sub-`.md` files are skill docs

Each harness's `.md` is designed as a **skill doc that an LLM/agent reads and acts on immediately**. Therefore:

- It is simplified for **minimum tokens** — no long background or examples, only what to call and how.
- The doc does not spell out logic in prose; it **points to the actual code file next to it** (e.g. `fastapi_guard.md` → `python3 fastapi_guard.py`, `llm_client.md` → `from llm_client import chat`). In short: **thin docs, behavior in code**.
- Code file and `.md` filenames match 1:1, so an agent can find and run the corresponding code from the skill doc alone.

Thanks to this rule, adding a new harness only takes one pair: "code + a thin same-named skill md".

Most harnesses are a **single code file** (e.g. `fastapi_guard.py`); its `.md` sits next to it with the same name. A **complex harness is a directory**, and its same-named `.md` lives **inside that directory** so the doc travels with the harness when the directory is copied/installed (e.g. `nodejs/e2e-llm-harness/e2e-llm-harness.md`). Either way the doc stays with the code unit it documents.

```
nodejs/
  e2e-llm-harness/        # directory harness
    e2e-harness           # the script (Playwright e2e runner)
    e2e-llm-harness.md    # ^ doc — inside the dir, so it installs with the harness
python/
  fastapi_guard.py        # FastAPI+SQLAlchemy static rule checker
  fastapi_guard.md        # ^ doc
  llm_client.py           # OpenAI-compatible LLM call helper (thinking off)
  llm_client.md           # ^ doc
```

## Catalog

| Language | Harness | Purpose |
|----------|---------|---------|
| nodejs | [e2e-llm-harness](nodejs/e2e-llm-harness/e2e-llm-harness.md) | Install Playwright, discover specs, run, output as-is |
| python | [fastapi_guard](python/fastapi_guard.md) | Static check for recurring defects in LLM-generated backend code |
| python | [llm_client](python/llm_client.md) | Call an OpenAI-compatible LLM (thinking disabled, defensive parsing) |

Each harness aims to be a single dependency-free, build-free file, or a directory when it gets complex.

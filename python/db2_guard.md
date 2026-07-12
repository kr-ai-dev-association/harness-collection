# db2_guard

Static checker that catches PostgreSQL/MySQL dialect leaking into DB2 projects before the code ships. Uses only the standard library, no dependencies, no build. Code: `db2_guard.py`.

## Usage
```bash
python3 db2_guard.py <paths ...>      # dirs/files (defaults to CWD)
python3 db2_guard.py --json <paths>   # machine-readable (JSON)
```
**Exit code 1 if there are errors** — wire it straight into CI. Standard library only, no install/build.

## Requirements
Python 3. No external packages.

## Rules
A 122B on-prem LLM probabilistically defaults to the PG/MySQL syntax it saw more often in training, even in DB2 projects. Left = banned (leak), right = the DB2 answer:

| rule | banned (leak) | DB2 answer | level |
|---|---|---|---|
| DB2_SERIAL | `SERIAL` / `BIGSERIAL` | `GENERATED ALWAYS AS IDENTITY` | error |
| DB2_TIMESTAMPTZ | `TIMESTAMP WITH TIME ZONE` / `TIMESTAMPTZ` | `TIMESTAMP` | error |
| DB2_NOW | `NOW()` | `CURRENT TIMESTAMP` | error |
| DB2_AUTOINC | `AUTO_INCREMENT` | `GENERATED ALWAYS AS IDENTITY` | error |
| DB2_UPSERT | `ON CONFLICT` / `ON DUPLICATE KEY` / `INSERT IGNORE` / `REPLACE INTO` | `MERGE INTO … WHEN MATCHED/NOT MATCHED` | error |
| DB2_TEXT_TYPE | `col TEXT` (PG/MySQL column type) | `CLOB` (long text) / `VARCHAR(n)` | error |
| DB2_JSONB | `col JSONB` / `…::jsonb` | `CLOB` + JSON functions (`JSON_VALUE`/`JSON_TABLE`) | error |
| DB2_DRIVER | `org.postgresql` / `com.mysql` driver | `com.ibm.db2.jcc.DB2Driver` | error |
| DB2_JDBC_URL | `jdbc:postgresql:` / `jdbc:mysql:` | `jdbc:db2://host:50000/DB` | error |
| DB2_DIALECT | `org.hibernate.dialect.PostgreSQLDialect` etc. | `org.hibernate.dialect.DB2Dialect` | error |
| DB2_LIMIT | `LIMIT n` | `FETCH FIRST n ROWS ONLY` | warn |

**Known DB2 incompatibilities (factual completeness — see Origin):**

| rule | banned (leak) | DB2 answer | level |
|---|---|---|---|
| DB2_ILIKE | `ILIKE` (PG) | `UPPER(col) LIKE UPPER(?)` | error |
| DB2_PG_CAST | `x::type` (PG cast) | `CAST(x AS type)` | error |
| DB2_GETDATE | `GETDATE()` (T-SQL) | `CURRENT TIMESTAMP` | error |
| DB2_TSQL_LEN | `LEN(...)` (T-SQL) | `LENGTH(...)` | error |
| DB2_TOP | `SELECT TOP n` (T-SQL) | `... FETCH FIRST n ROWS ONLY` | error |
| DB2_ISNULL | `ISNULL(x, y)` (T-SQL/MySQL) | `COALESCE(x, y)` | error |
| DB2_BACKTICK | `` `col` `` (MySQL) | `"col"` or unquoted | error |
| DB2_ENUM | `ENUM('a','b')` (MySQL) | `VARCHAR + CHECK (col IN ...)` | error |
| DB2_UNSIGNED | `INT UNSIGNED` (MySQL) | wider signed type (`BIGINT`) | error |
| DB2_NEXTVAL | `nextval('s')` (PG) | `NEXT VALUE FOR s` | error |
| DB2_LASTID | `LAST_INSERT_ID()` / `@@IDENTITY` | `IDENTITY_VAL_LOCAL()` | error |
| DB2_MYSQL_DATEFN | `CURDATE`/`CURTIME`/`DATE_ADD`/`DATE_SUB` | `CURRENT DATE` · `col + n DAYS` | error |
| DB2_RETURNING | `INSERT … RETURNING` (PG) | `SELECT … FROM FINAL TABLE (INSERT …)` | error |

## Origin (evidence)
Only defects observed to recur in the qwen3.5-122b eval (springboot 27 + db2 17 files):
- Dialect leaks — `NOW()` 33 · `SERIAL` 11 · `TIMESTAMPTZ` 2 · `AUTO_INCREMENT` 1 (sb-05/06/11, db2-01~15).
- UPSERT — db2-04/05 emit only PG `ON CONFLICT`, DB2 `MERGE` **0 times** (a comment even said "using the PostgreSQL ON CONFLICT clause").
- **TEXT type 7 hits / 4 files** (db2-07/11/14/15) · **jsonb 5 hits / 2 files** (db2-01/15, incl. `::jsonb` casts) — promoted on the db2-11~17 rescan.
- By contrast the same advanced files' SQL PL procedures had **0** PL/SQL (`DBMS_OUTPUT`/`%TYPE`) or T-SQL leaks — generated correctly with DB2 `BEGIN…END`·`LISTAGG`·OLAP → no procedure-syntax rule (no speculation, principle 5).

**Two tiers of evidence:**
- **Observed** (DB2_SERIAL…DB2_JSONB): defects seen recurring in the qwen eval — principle 5, no speculation.
- **Known-incompatibility** (DB2_ILIKE…DB2_RETURNING, 13 rules): not from observed recurrence but from the *factual* DB2 incompatibility surface — DB2 genuinely rejects these PG/MySQL/T-SQL constructs regardless. A limited on-prem model will eventually emit an unseen-but-breaking one, so completeness on this *factual* surface (not speculative quality lints — those stay observation-gated) maximizes DB2 reliability. Verified **0 false positives** on a valid-DB2 fixture (GENERATED IDENTITY / CURRENT TIMESTAMP / FETCH FIRST / MERGE / LENGTH / COALESCE / NEXT VALUE FOR / CAST all pass clean).

## Checklist (for the agent)
- [ ] In a DB2 project, never use the "banned" column syntax above
- [ ] Default timestamp = `CURRENT TIMESTAMP` (`NOW()` ❌)
- [ ] PK auto-numbering = `GENERATED ALWAYS AS IDENTITY` (`SERIAL`/`AUTO_INCREMENT` ❌)
- [ ] UPSERT = `MERGE INTO` (`ON CONFLICT`/`ON DUPLICATE KEY` ❌)
- [ ] Driver/URL/Dialect are the DB2 ones (`jdbc:db2://…:50000`, `DB2Driver`, `DB2Dialect`)
- [ ] Before shipping, run `python3 db2_guard.py <src>` and confirm 0 errors

## Caveats (honestly)
- **Regex heuristic** (the Python stdlib has no SQL/Java parser, so regex instead of `ast`). For SQL files, `--` comments are stripped before matching (code only); patterns inside string literals can still match. `DB2_NOW` excludes `.now()` (Java `LocalDateTime.now()`) via negative-lookbehind; `DB2_TEXT_TYPE` only matches TEXT followed by `,`/`)`, excluding `CONTEXT` and prose strings (e.g. `'…the TEXT type…'`).
- `DB2_LIMIT` is warn — DB2 11.1+ compat mode allows some `LIMIT`; the standard is `FETCH FIRST`.
- No SQL PL (procedure-syntax) rule — not observed in the eval (qwen writes DB2 procedures correctly). LOB/JSON is partly covered by `DB2_JSONB` (+`TEXT`). Add rules with level + evidence when you hit a new trap.

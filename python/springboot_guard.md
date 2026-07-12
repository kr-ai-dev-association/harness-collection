# springboot_guard

Static checker for Spring Boot code: (1) recurring quality/security anti-patterns (**warn**) and (2) version-drift compile defects (**error**). Code: `springboot_guard.py`.

## Usage
```bash
python3 springboot_guard.py <paths ...>      # dirs/files (defaults to CWD)
python3 springboot_guard.py --json <paths>   # machine-readable (JSON)
```
- **warn** (11 quality/security rules): code still runs. A reactive guard can gate on the warn count.
- **error** (3 drift rules): SB3/Java16+ idioms mixed into SB2.x/Java11 → **compile failure** → exit 1 (CI block).
  If `pom.xml`/`build.gradle` shows **SB3.x, the drift rules auto-disable** (avoids false positives on SB3 projects).
Standard library only.

## Requirements
Python 3. No external packages.

## Rules
A 122B on-prem LLM generates SB code that is *mechanically* fine most of the time but repeats the anti-patterns below. Left = banned, right = the correct way:

| rule | anti-pattern (banned) | correct way | level |
|---|---|---|---|
| SB_SYSOUT | `System.out.println` / `System.err.println` | SLF4J logger (`log.info(...)`) | warn |
| SB_PRINTSTACK | `e.printStackTrace()` | `log.error("msg", e)` | warn |
| SB_FIELD_INJECT | `@Autowired private Xxx x;` (field injection) | constructor injection (`private final Xxx x;`) | warn |
| SB_PLAINTEXT_SECRET | `password: db2password` (plaintext) | `password: ${DB_PASSWORD}` | warn |
| SB_DDL_AUTO | `ddl-auto: update`/`create` | prod `validate`/`none` + Flyway/Liquibase | warn |
| SB_SHOW_SQL | `show-sql: true` | prod `false` (control via log level) | warn |
| SB_NO_VALID | `@RequestBody Xxx` (no validation) | `@Valid @RequestBody Xxx` + DTO constraints | warn |
| SB_ERR_LEAK | `return "…" + e.getMessage()` (exception exposed) | generalized error response; detail in server logs only | warn |
| SB_STAR_IMPORT | `import x.y.*;` (wildcard) | explicit imports | warn |
| SB_BROAD_CATCH | `catch (Exception e)` / `catch (Throwable t)` | catch specific exceptions or `@ControllerAdvice` | warn |
| SB_UNBOUNDED_FINDALL | `repo.findAll()` (no-arg, loads all) | `findAll(Pageable)` → return `Page<T>` | warn |

**Version drift (SB 2.x / Java 11 baseline — auto-disabled if pom says SB3.x):**

| rule | drift (compile failure) | correct way (SB2.5.2) | level |
|---|---|---|---|
| SB_JAKARTA_IMPORT | `import jakarta.*` | `import javax.*` (persistence/validation/servlet) | error |
| SB_SB3_SECURITY | `SecurityFilterChain` bean / `authorizeHttpRequests` / `requestMatchers` | `WebSecurityConfigurerAdapter` + `authorizeRequests().antMatchers()` | error |
| SB_JAVA_RECORD | `public record X(...)` (Java16+) | regular class + constructor/getters (or Lombok) | error |

## Origin (evidence)
Observed to recur in the qwen3.5-122b eval (27 SB files + generation queries):
- `System.out.println` 12 files · field injection 8 · plaintext password 9 (`db2password` etc.) · `printStackTrace` 2.
- `ddl-auto: update` 3 · `show-sql: true` 3 · **`@Valid` 0 files** (even the sb-07 validation demo) · `e.getMessage()` in response 5 · wildcard import 9.
- `catch (Exception/Throwable)` broad catch in 6 classes; no-arg `findAll()` (no paging) in 3 classes (MemberService·TokenController·TransactionService).
- **Version drift (correctness, error)**: after seeding an SB2.5.2 skeleton and generating fresh code, qwen mixes SB3/Java16+ idioms — `jakarta.*` imports **11 classes** (persistence 16·servlet 12·validation 5) · SB3 security DSL (SecurityConfig) · `record` (MemberResponse). These **fail to compile** on SB2.x/Java11. (The first 27-file audit missed this axis and concluded "0 compile defects"; a version-explicit skeleton surfaced it — the value of re-auditing.)
- The other classic security mistakes are **absent** — `new Random()` (uses SecureRandom) · `RestTemplate` · MD5/SHA-1 · hardcoded secrets · CORS(*) · ECB · EAGER = 0. Not encoded (no speculation, principle 5).

## Checklist (for the agent)
- [ ] Logging via SLF4J (`System.out.println`/`printStackTrace` ❌)
- [ ] Constructor injection (`@Autowired` field injection ❌)
- [ ] Passwords/secrets as `${ENV}` refs (plaintext hardcode ❌)
- [ ] prod config: `ddl-auto: validate/none`, `show-sql: false`
- [ ] `@RequestBody` needs `@Valid` + DTO constraint annotations
- [ ] **SB2.5.2/Java11**: `javax.*` (jakarta ❌) · `WebSecurityConfigurerAdapter` (SecurityFilterChain ❌) · no `record`
- [ ] Before shipping, run `python3 springboot_guard.py <src>` — confirm 0 errors (drift), review warns

## Caveats (honestly)
- **Regex heuristic** (no Java `ast`). `SB_PLAINTEXT_SECRET` excludes `${...}` refs via negative-lookahead but may catch placeholder passwords in example/test config — use judgement.
- `SB_FIELD_INJECT` only matches a field declaration after `@Autowired` (ends with `;`, no parens) — constructor/setter injection excluded; rare public field injection may be missed.
- **Drift rules (error) assume SB 2.x / Java 11.** The guard reads the spring-boot version from `pom.xml`/`build.gradle` and **auto-disables them for SB3.x** (where jakarta/record are correct). With no pom found it assumes the qwen target SB2.x and keeps checking → scanning SB3 code without a pom in the path can false-positive (include the pom in the path).
- Quality rules (warn) mean the code runs (quality, not a bug). Drift rules (error) mean it does not compile.

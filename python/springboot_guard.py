#!/usr/bin/env python3
"""springboot_guard.py — static checker for Spring Boot anti-patterns + version drift (harness).

Why: a 122B on-prem LLM (qwen3.5-122b) generates Spring Boot code that is
   *mechanically* fine most of the time, but it (1) repeats production quality/security
   anti-patterns and (2) mixes in SB3/Java16+ idioms that break compilation on an
   SB2.x/Java11 project. This guard catches both deterministically.
Origin (observed, 27 SB files + generation queries): System.out.println 12 ·
   @Autowired field injection 8 · plaintext password 9 · printStackTrace 2 ·
   broad catch 6 · findAll() 3 · jakarta.* import 11.

Rules: 11 quality/security (warn) + 7 SB3-API drift (error, fire only when the build file
   says SB2.x) + 6 Java-feature drift (error, fire only when the project's Java major is
   below the feature's requirement). Version gates are read from pom.xml/build.gradle.

Design: standard library only · no build · single file.
Usage:  python3 springboot_guard.py <paths ...>  |  python3 springboot_guard.py --json <paths>
Return: exit 1 if any error (version drift). Quality anti-patterns are warn (exit 0).
"""
import os
import re
import sys
import json
import glob

JAVA = (".java",)
CFG = (".yml", ".yaml", ".properties")

# (id, severity, applicable extensions, regex [applied to whole file text], why, fix)
RULES = [
    ("SB_SYSOUT", "warn", JAVA,
     r"System\.(?:out|err)\.print",
     "logging via System.out/err (not production-grade)",
     "SLF4J: private static final Logger log = LoggerFactory.getLogger(X.class); log.info(...)"),

    ("SB_PRINTSTACK", "warn", JAVA,
     r"\.printStackTrace\s*\(",
     "e.printStackTrace() — leaks the exception to stderr (swallowed)",
     "log.error(\"message\", e) or propagate appropriately"),

    ("SB_FIELD_INJECT", "warn", JAVA,
     r"@Autowired\s+(?:private|protected|public|final|\s)*[\w.<>\[\]]+\s+\w+\s*;",
     "@Autowired field injection (fragile for testing/immutability/circular deps)",
     "constructor injection: private final Xxx x; + constructor param (@Autowired optional)"),

    ("SB_PLAINTEXT_SECRET", "warn", CFG,
     r"(?im)^\s*[\w.-]*password[\w.-]*\s*[:=]\s*(?!\$\{)(?![\"']?\s*(?:#|$))[\"']?[^\s#$]",
     "plaintext password hardcoded in config",
     "reference an env var / secret: password: ${DB_PASSWORD}"),

    # CONFIRMED(sb-13/14 observed): schema auto-change in production config.
    ("SB_DDL_AUTO", "warn", CFG,
     r"(?im)ddl-auto\s*[:=]\s*(update|create|create-drop)",
     "spring.jpa.hibernate.ddl-auto is update/create (auto schema change in prod)",
     "prod: `validate`/`none` + Flyway/Liquibase migration"),

    # CONFIRMED(sb-13/14 observed): show-sql true = prod perf hit + query log exposure.
    ("SB_SHOW_SQL", "warn", CFG,
     r"(?im)show-sql\s*[:=]\s*true",
     "show-sql: true (prod performance hit, query log exposure)",
     "prod: false; control via log level (org.hibernate.SQL) if needed"),

    # CONFIRMED(sb-07/10 observed): @RequestBody with @Valid 0 times = missing input validation.
    # Heuristic: @RequestBody right after '(' or ',' (= no @Valid annotation before it).
    ("SB_NO_VALID", "warn", JAVA,
     r"[(,]\s*@RequestBody\s+[A-Z]",
     "@RequestBody without @Valid (request body input validation missing)",
     "@Valid @RequestBody Xxx + constraint annotations on the DTO (@NotNull/@Size etc.)"),

    # CONFIRMED(sb-10/18 observed): returning exception message in the response = info leak.
    ("SB_ERR_LEAK", "warn", JAVA,
     r"(?:return|\.body\()[^;]{0,80}getMessage\s*\(\s*\)",
     "exception detail (getMessage()) exposed in the client response (info leak)",
     "return a generalized error response; keep detail in server logs (log.error) only"),

    # CONFIRMED(9 files observed): wildcard package import (static excluded).
    ("SB_STAR_IMPORT", "warn", JAVA,
     r"import\s+(?!static\b)[\w.]+\.\*;",
     "wildcard import (namespace pollution, name-collision risk)",
     "explicit imports (IDE auto-organize / checkstyle AvoidStarImport)"),

    # CONFIRMED(6 classes observed: SettlementService/Controller·LoggingFilter·QuartzConfig·
    # RedisCacheEvictListener·LocalDateTimeTypeHandler): broad catch (Exception/Throwable).
    # Regex matches exactly Exception/Throwable — IOException/RuntimeException etc. are not matched.
    ("SB_BROAD_CATCH", "warn", JAVA,
     r"catch\s*\(\s*(?:final\s+)?(?:Exception|Throwable)\s+\w+\s*\)",
     "broad catch (Exception/Throwable) — swallows unchecked exceptions, hides the cause",
     "catch specific exceptions, or handle centrally via @ControllerAdvice/@ExceptionHandler"),

    # CONFIRMED(generation queries, 3 classes: MemberService·TokenController·TransactionService):
    # a service/controller returns no-arg findAll() → loads/returns everything, no paging (OOM/perf).
    # Only empty parens match → findAll(Pageable)/findAll(Sort) (the correct form) are not matched.
    ("SB_UNBOUNDED_FINDALL", "warn", JAVA,
     r"\.findAll\s*\(\s*\)",
     "no-arg findAll() — loads/returns everything without paging (large data OOM/perf)",
     "findAll(Pageable) for paging (controllers return Page<T>/Slice<T>)"),
]

# ── version-drift rules = correctness ERROR (same nature as a DB2 dialect leak) ─────
# qwen mixes SB3/Java16+ idioms (seen more in training) into an SB2.x/Java11 project →
# compile failure. Two independent gates applied in scan():
#   · SB gate   — DRIFT_RULES fire only when the build file says Spring Boot 2.x
#   · Java gate — JAVA_RULES fire only when the project's Java major < the feature's need
# Evidence tiers: rules marked CONFIRMED were observed in the qwen eval; the rest cover the
# *factual* SB2.x/Java11 incompatibility surface (the API/feature genuinely does not exist
# there — completeness, not speculation).
DRIFT_RULES = [
    # CONFIRMED(11 classes observed): jakarta.persistence/servlet/validation imports.
    ("SB_JAKARTA_IMPORT", "error", JAVA,
     r"import\s+jakarta\.",
     "jakarta.* import (SB3; SB2.x uses javax.*) — class not present, compile failure",
     "use javax.* (jakarta.persistence→javax.persistence · jakarta.servlet→javax.servlet etc.)"),

    # CONFIRMED(SecurityConfig observed): SB3 security DSL.
    ("SB_SB3_SECURITY", "error", JAVA,
     r"authorizeHttpRequests|\.requestMatchers\s*\(|\bSecurityFilterChain\s+\w+\s*\(",
     "SB3 security DSL (SecurityFilterChain bean/authorizeHttpRequests/requestMatchers) — unsupported on SB2.5.x",
     "SB2.5.x: extends WebSecurityConfigurerAdapter + http.authorizeRequests().antMatchers(...)"),

    ("SB_ENABLE_METHOD_SEC", "error", JAVA,
     r"@EnableMethodSecurity\b",
     "@EnableMethodSecurity (Spring Security 5.6+/SB3) — not on SB2.5.x (ships Security 5.5)",
     "@EnableGlobalMethodSecurity(prePostEnabled = true)"),

    ("SB_RESTCLIENT", "error", JAVA,
     r"import\s+org\.springframework\.web\.client\.RestClient\b|\bRestClient\s*\.\s*(?:builder|create)\s*\(",
     "RestClient (Spring 6.1/SB3.2) — not on SB2.x",
     "RestTemplate (with explicit timeouts) or WebClient"),

    ("SB_PROBLEM_DETAIL", "error", JAVA,
     r"\bProblemDetail\b",
     "ProblemDetail (Spring 6/SB3) — not on SB2.x",
     "custom error DTO + @ExceptionHandler/@RestControllerAdvice"),

    ("SB_HTTP_EXCHANGE", "error", JAVA,
     r"@(?:Http|Get|Post|Put|Delete|Patch)Exchange\b",
     "@HttpExchange declarative HTTP client (Spring 6/SB3) — not on SB2.x",
     "RestTemplate/WebClient (or OpenFeign)"),

    ("SB_AUTOCONFIGURATION", "error", JAVA,
     r"@AutoConfiguration\b",
     "@AutoConfiguration (SB2.7+) — not on SB2.5.x",
     "@Configuration + META-INF/spring.factories registration"),
]

# (id, severity, exts, pattern, why, fix, needs_java) — fire only when project Java < needs_java
JAVA_RULES = [
    # CONFIRMED(MemberResponse observed): Java16+ record.
    ("SB_JAVA_RECORD", "error", JAVA,
     r"\bpublic\s+record\s+\w+\s*\(",
     "record type (Java 16+) — compile failure on this project's Java",
     "regular class + constructor/getters (or Lombok @Getter)", 16),

    ("SB_SWITCH_ARROW", "error", JAVA,
     r"\b(?:case\s+[^:;\n]*?|default\s*)->",
     "switch arrow labels (Java 14+) — compile failure on this project's Java",
     "classic switch: 'case X:' + break", 14),

    ("SB_TEXT_BLOCK", "error", JAVA,
     r'"""',
     'text block """ (Java 15+) — compile failure on this project\'s Java',
     "concatenated string literals", 15),

    ("SB_STREAM_TOLIST", "error", JAVA,
     r"(?<!Collectors)\.toList\s*\(\s*\)",
     "Stream.toList() (Java 16+) — compile failure on this project's Java",
     ".collect(Collectors.toList())", 16),

    ("SB_INSTANCEOF_PATTERN", "error", JAVA,
     r"\binstanceof\s+[A-Z][\w.]*(?:<[^>]*>)?\s+[a-z]\w*",
     "pattern-matching instanceof (Java 16+) — compile failure on this project's Java",
     "instanceof check + explicit cast", 16),

    ("SB_SEALED", "error", JAVA,
     r"\b(?:sealed|non-sealed)\s+(?:class|interface)\b|\bpermits\s+[A-Z]",
     "sealed class/interface (Java 17+) — compile failure on this project's Java",
     "regular class hierarchy (document the allowed subtypes)", 17),
]

COMPILED = [(rid, sev, exts, re.compile(pat), why, fix)
            for rid, sev, exts, pat, why, fix in RULES]
COMPILED_DRIFT = [(rid, sev, exts, re.compile(pat), why, fix)
                  for rid, sev, exts, pat, why, fix in DRIFT_RULES]
COMPILED_JAVA = [((rid, sev, exts, re.compile(pat), why, fix), need)
                 for rid, sev, exts, pat, why, fix, need in JAVA_RULES]


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for f in glob.glob(f"{p}/**/*", recursive=True):
                if os.path.isfile(f) and "/target/" not in f and "/build/" not in f \
                        and "/.git/" not in f and "/.snap/" not in f:
                    yield f


def sb_is_v2(paths):
    """Decide whether to apply drift rules based on the Spring Boot version in pom.xml/build.gradle.
    Returns False (disable drift rules → avoid false positives on SB3 projects) if SB3.x is stated.
    If not found, assume the qwen target SB2.x and return True (keep drift checks on)."""
    for f in iter_files(paths):
        if os.path.basename(f) in ("pom.xml", "build.gradle", "build.gradle.kts"):
            try:
                t = open(f, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for pat in (r"spring-boot-starter-parent</artifactId>\s*<version>\s*([23])\.",
                        r"<spring-boot\.version>\s*([23])\.",
                        r"org\.springframework\.boot['\"]?\s+version\s+['\"]([23])\.",
                        r"spring-boot-gradle-plugin:([23])\."):
                m = re.search(pat, t)
                if m:
                    return m.group(1) == "2"
    return True


def java_major(paths, default):
    """Project Java major version from pom.xml/build.gradle (gates JAVA_RULES).
    Not found → `default` (11 for SB2 projects — the qwen target; 17 for SB3, its minimum)."""
    for f in iter_files(paths):
        if os.path.basename(f) in ("pom.xml", "build.gradle", "build.gradle.kts"):
            try:
                t = open(f, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for pat in (r"<java\.version>\s*(?:1\.)?(\d+)",
                        r"<maven\.compiler\.(?:source|target|release)>\s*(?:1\.)?(\d+)",
                        r"sourceCompatibility\s*=?\s*['\"]?(?:1\.)?(\d+)",
                        r"JavaVersion\.VERSION_(?:1_)?(\d+)",
                        r"JavaLanguageVersion\.of\(\s*(\d+)"):
                m = re.search(pat, t)
                if m:
                    return int(m.group(1))
    return default


def scan(paths):
    out = []
    v2 = sb_is_v2(paths)
    jmaj = java_major(paths, 11 if v2 else 17)
    rules = COMPILED + (COMPILED_DRIFT if v2 else []) \
        + [r for r, need in COMPILED_JAVA if jmaj < need]
    for f in iter_files(paths):
        if not f.endswith(JAVA + CFG):
            continue
        try:
            text = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for rid, sev, exts, rx, why, fix in rules:
            if not f.endswith(exts):
                continue
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                code = text[m.start():m.start() + 120].splitlines()[0].strip()
                out.append({"rule": rid, "severity": sev, "file": f, "line": line,
                            "code": code[:100], "why": why, "fix": fix})
    return out


def main(argv):
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")] or ["."]
    findings = scan(paths)
    if as_json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    else:
        for x in findings:
            tag = "x" if x["severity"] == "error" else "!"
            print(f"{tag} {x['file']}:{x['line']}  [{x['rule']}] {x['why']}")
            print(f"    > {x['code']}")
            print(f"    -> {x['fix']}")
        errs = [x for x in findings if x["severity"] == "error"]
        warns = [x for x in findings if x["severity"] == "warn"]
        print(f"\n{len(errs)} error, {len(warns)} warn "
              f"({len({x['file'] for x in findings})} files)")
        if not findings:
            print("[harness] no Spring Boot anti-patterns")
    return 1 if any(x["severity"] == "error" for x in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

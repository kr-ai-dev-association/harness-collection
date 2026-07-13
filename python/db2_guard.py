#!/usr/bin/env python3
"""db2_guard.py — static checker for DB2 dialect leaks (harness).

Why: a 122B on-prem LLM (qwen3.5-122b) probabilistically defaults to the
   PostgreSQL/MySQL syntax it saw more often in training, even in DB2 projects.
   This harness deterministically detects those defects and prescribes the fix.
Origin (observed): codepilot eval snapshots sb-05/06/11 — SERIAL /
   TIMESTAMP WITH TIME ZONE / NOW() / org.postgresql driver / jdbc:postgresql URL.
   (Control: the correct CURRENT TIMESTAMP / FETCH FIRST appeared 0 times.)

Design: standard library only · no build · single file · only proven defects.
Usage:  python3 db2_guard.py <paths ...>     (dirs/files; defaults to CWD)
        python3 db2_guard.py --json <paths>  (machine-readable output)
Return: exit 1 if any error (for a reactive guard), else 0.
"""
import os
import re
import sys
import json
import glob

# ── rule: (id, severity, applicable extensions, regex, one-line why, DB2 fix) ──
# status CONFIRMED = a recurring defect observed in eval snapshots. (no speculative rules)
SQL_LIKE = (".sql", ".xml")  # DDL/DML + MyBatis mappers
CFG = (".properties", ".yml", ".yaml")
DEP = ("pom.xml", "build.gradle", "build.gradle.kts")

RULES = [
    # id, severity, exts, pattern, why, fix
    ("DB2_SERIAL", "error", SQL_LIKE,
     r"\b(BIG|SMALL)?SERIAL\b",
     "PostgreSQL SERIAL column type (not in DB2)",
     "GENERATED ALWAYS AS IDENTITY (e.g. id BIGINT GENERATED ALWAYS AS IDENTITY)"),

    ("DB2_TIMESTAMPTZ", "error", SQL_LIKE + (".java",),
     r"TIMESTAMP\s+WITH\s+TIME\s+ZONE|\bTIMESTAMPTZ\b",
     "PostgreSQL 'TIMESTAMP WITH TIME ZONE' (unsupported in DB2)",
     "TIMESTAMP (normalize to UTC at the app layer if a timezone is needed)"),

    ("DB2_NOW", "error", SQL_LIKE,
     r"(?<![.\w])NOW\s*\(\s*\)",
     "MySQL/PG NOW() function (not in DB2)",
     "CURRENT TIMESTAMP"),

    ("DB2_AUTOINC", "error", SQL_LIKE,
     r"\bAUTO_?INCREMENT\b",
     "MySQL AUTO_INCREMENT (not in DB2)",
     "GENERATED ALWAYS AS IDENTITY"),

    ("DB2_DRIVER", "error", DEP + CFG,
     r"org\.postgresql|com\.mysql|mysql-connector|oracle\.jdbc",
     "other-DB JDBC driver in a DB2 project",
     "com.ibm.db2.jcc.DB2Driver (dependency: com.ibm.db2 : jcc)"),

    ("DB2_JDBC_URL", "error", CFG + (".xml",),
     r"jdbc:(postgresql|mysql|oracle|h2|sqlserver):",
     "other-DB JDBC URL in a DB2 project",
     "jdbc:db2://<host>:50000/<DB> (default port 50000)"),

    ("DB2_DIALECT", "error", CFG + (".java",),
     r"org\.hibernate\.dialect\.(PostgreSQL|MySQL|Oracle|H2|SQLServer)\w*Dialect",
     "Hibernate dialect is for another DB",
     "org.hibernate.dialect.DB2Dialect"),

    # severity=warn: DB2 11.1+ compat mode allows some LIMIT, but the standard is FETCH FIRST.
    ("DB2_LIMIT", "warn", SQL_LIKE,
     r"\bLIMIT\s+\d+",
     "MySQL/PG LIMIT (non-standard in DB2; depends on compat mode)",
     "FETCH FIRST n ROWS ONLY (offset: OFFSET m ROWS FETCH NEXT n ROWS ONLY)"),

    # CONFIRMED(db2-04/05 observed): for UPSERT qwen only emits PG ON CONFLICT and
    # never DB2 MERGE (MERGE INTO 0 times). MySQL ON DUPLICATE is the same defect class.
    ("DB2_UPSERT", "error", SQL_LIKE,
     r"ON\s+CONFLICT|ON\s+DUPLICATE\s+KEY|INSERT\s+IGNORE|REPLACE\s+INTO",
     "PG ON CONFLICT / MySQL ON DUPLICATE·INSERT IGNORE·REPLACE INTO (not in DB2)",
     "MERGE INTO tgt USING (source) s ON (key) "
     "WHEN MATCHED THEN UPDATE SET ... WHEN NOT MATCHED THEN INSERT (...)"),

    # CONFIRMED(db2-11/14 observed): PG/MySQL TEXT used as a column / RETURNS TABLE type.
    # DB2 has no TEXT data type, so CREATE fails with SQL0104N (= correctness error).
    # Regex: only when TEXT is immediately followed by ',' or ')' → excludes 'TEXT' inside
    #   strings/comments (e.g. '…the PostgreSQL TEXT type…') and CONTEXT/FULLTEXT (0 false pos).
    ("DB2_TEXT_TYPE", "error", SQL_LIKE,
     r"\bTEXT\b(?=\s*[,)])",
     "PostgreSQL/MySQL TEXT column type (not in DB2 → SQL0104N)",
     "CLOB (long text) or VARCHAR(n)"),

    # CONFIRMED(db2-15 observed): PG jsonb type / `::jsonb` cast used for JSON storage.
    # DB2 has no jsonb type (JSON is handled via CLOB/BLOB + JSON functions).
    ("DB2_JSONB", "error", SQL_LIKE,
     r"\bjsonb\b",
     "PostgreSQL jsonb type/cast (not in DB2)",
     "CLOB + DB2 JSON functions (JSON_VALUE / JSON_TABLE / SYSTOOLS.JSON2BSON)"),

    # ── Known DB2 incompatibilities (factual, for version-correctness completeness) ──
    # DB2 factually rejects these PG/MySQL/T-SQL constructs whether or not qwen was
    # observed emitting them. Since the model has limits and will eventually emit an
    # unseen-but-breaking one, completeness on the *known-incompatible* surface (not
    # speculative quality lints) directly serves "make qwen run on DB2 as reliably as
    # possible". Each regex is verified against a valid-DB2 fixture (0 false positives).
    ("DB2_ILIKE", "error", SQL_LIKE,
     r"\bILIKE\b",
     "PostgreSQL ILIKE (not in DB2)",
     "UPPER(col) LIKE UPPER(?) for case-insensitive match"),

    ("DB2_PG_CAST", "error", SQL_LIKE,
     r"::\s*[A-Za-z]",
     "PostgreSQL '::' cast operator (not in DB2)",
     "CAST(x AS type)"),

    ("DB2_GETDATE", "error", SQL_LIKE,
     r"\bGETDATE\s*\(",
     "T-SQL GETDATE() (not in DB2)",
     "CURRENT TIMESTAMP"),

    ("DB2_TSQL_LEN", "error", SQL_LIKE,
     r"\bLEN\s*\(",
     "T-SQL LEN() (not in DB2; DB2 uses LENGTH)",
     "LENGTH(x)"),

    ("DB2_TOP", "error", SQL_LIKE,
     r"\bSELECT\s+TOP\s+\d",
     "T-SQL SELECT TOP n (not in DB2)",
     "SELECT ... FETCH FIRST n ROWS ONLY"),

    ("DB2_ISNULL", "error", SQL_LIKE,
     r"\bISNULL\s*\(",
     "T-SQL/MySQL ISNULL() function (not in DB2)",
     "COALESCE(x, y)"),

    ("DB2_BACKTICK", "error", SQL_LIKE,
     r"`",
     "MySQL backtick identifier quoting (not in DB2)",
     'double-quote "col" or leave unquoted'),

    ("DB2_ENUM", "error", SQL_LIKE,
     r"\bENUM\s*\(",
     "MySQL ENUM column type (not in DB2)",
     "VARCHAR(n) + CHECK (col IN (...)) constraint"),

    ("DB2_UNSIGNED", "error", SQL_LIKE,
     r"\bUNSIGNED\b",
     "MySQL UNSIGNED modifier (not in DB2)",
     "use a wider signed type (e.g. BIGINT)"),

    ("DB2_NEXTVAL", "error", SQL_LIKE,
     r"\bnextval\s*\(",
     "PostgreSQL nextval() sequence call (not in DB2)",
     "NEXT VALUE FOR seq_name"),

    ("DB2_LASTID", "error", SQL_LIKE,
     r"\bLAST_INSERT_ID\s*\(|@@IDENTITY\b",
     "MySQL LAST_INSERT_ID() / T-SQL @@IDENTITY (not in DB2)",
     "IDENTITY_VAL_LOCAL()"),

    ("DB2_MYSQL_DATEFN", "error", SQL_LIKE,
     r"\b(CURDATE|CURTIME|DATE_ADD|DATE_SUB)\s*\(",
     "MySQL date function (CURDATE/CURTIME/DATE_ADD/DATE_SUB) (not in DB2)",
     "CURRENT DATE / CURRENT TIME · col + n DAYS / col - n DAYS"),

    ("DB2_RETURNING", "error", SQL_LIKE,
     r"\bRETURNING\b",
     "PostgreSQL RETURNING clause (not in DB2)",
     "SELECT ... FROM FINAL TABLE (INSERT ...)"),
]

# Promoted: UPSERT(→MERGE, db2-04/05) · TEXT type(→CLOB/VARCHAR, db2-11/14) ·
#   jsonb(→CLOB+JSON funcs, db2-15) — all confirmed recurring on the db2-11~17 rescan.
# Control (not observed, so no rule): db2-11~17 procedures were generated correctly with
#   DB2 BEGIN…END·LISTAGG·OLAP, no PL/SQL (DBMS_OUTPUT/%TYPE 0) or T-SQL (0) leak → no speculation.
# Held (weak evidence, ≤1 occurrence): IFNULL→COALESCE, backtick identifiers. Promote if re-observed.

COMPILED = [(rid, sev, exts, re.compile(pat, re.I), why, fix)
            for rid, sev, exts, pat, why, fix in RULES]


def applies(path, exts):
    base = os.path.basename(path)
    return base in exts or path.endswith(exts)


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for f in glob.glob(f"{p}/**/*", recursive=True):
                # exclude build output / VCS
                if os.path.isfile(f) and "/target/" not in f and "/build/" not in f \
                        and "/.git/" not in f and "/node_modules/" not in f:
                    yield f


def scan(paths):
    findings = []
    for f in iter_files(paths):
        try:
            text = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        lines = text.splitlines()
        is_sql = f.endswith(SQL_LIKE)  # strip SQL '--' comments before matching (check code only)
        for rid, sev, exts, rx, why, fix in COMPILED:
            if not applies(f, exts):
                continue
            for i, line in enumerate(lines, 1):
                probe = line.split("--", 1)[0] if is_sql else line
                if rx.search(probe):
                    findings.append({
                        "rule": rid, "severity": sev, "file": f, "line": i,
                        "code": line.strip()[:100], "why": why, "fix": fix,
                    })
    return findings


def main(argv):
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")] or ["."]
    findings = scan(paths)

    if as_json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    else:
        errors = [x for x in findings if x["severity"] == "error"]
        warns = [x for x in findings if x["severity"] == "warn"]
        for x in findings:
            tag = "x" if x["severity"] == "error" else "!"
            rel = x["file"]
            print(f"{tag} {rel}:{x['line']}  [{x['rule']}] {x['why']}")
            print(f"    > {x['code']}")
            print(f"    -> DB2: {x['fix']}")
        print(f"\n{len(errors)} error, {len(warns)} warn "
              f"({len({x['file'] for x in findings})} files)")
        if not findings:
            print("[harness] no DB2 dialect leaks")

    return 1 if any(x["severity"] == "error" for x in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

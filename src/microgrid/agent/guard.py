"""Read-only SQL validator — the *belt* of a belt-and-braces design.

``validate()`` is a pure function (no I/O, no database) so it is trivially
unit-testable. It rejects anything that is not a single SELECT/WITH query.
The *braces* live in :mod:`microgrid.agent.tools`: every query additionally
runs inside a ``READ ONLY`` transaction with a statement timeout, so even a
query that slips past this validator cannot write.

Approach: strip comments, string literals and quoted identifiers, then scan
the remaining bare words. This is deliberately conservative — a column that
happened to be named ``update`` would be rejected (none of our tables has
one), while ``SELECT 'please DROP TABLE x'`` passes because the keyword sits
inside a string literal, where it is inert.
"""

from __future__ import annotations

import re

__all__ = ["GuardError", "validate", "FORBIDDEN_KEYWORDS"]


class GuardError(ValueError):
    """Raised when a statement is not a single read-only query."""


_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_QUOTED_IDENT = re.compile(r'"(?:[^"]|"")*"')
_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_0-9]*\$")
_WORD = re.compile(r"[A-Za-z_]+")

# Anything that can write, alter state, or smuggle a write. ``INTO`` blocks
# ``SELECT INTO`` (which creates a table); ``DO``/``CALL`` block procedural
# execution; transaction control is blocked because tools.py owns the
# transaction. PostgreSQL data-modifying CTEs (``WITH d AS (DELETE ...)``)
# are caught by their inner keyword.
FORBIDDEN_KEYWORDS = frozenset({
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT",
    "DROP", "ALTER", "CREATE", "TRUNCATE", "RENAME",
    "GRANT", "REVOKE", "SECURITY",
    "COPY", "CALL", "DO", "EXECUTE", "PREPARE", "DEALLOCATE",
    "SET", "RESET", "VACUUM", "ANALYZE", "COMMENT", "REINDEX", "CLUSTER",
    "LOCK", "LISTEN", "NOTIFY", "REFRESH", "IMPORT",
    "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT",
    "INTO", "DECLARE", "FETCH", "MOVE", "CLOSE",
})


def _strip_literals(sql: str) -> str:
    """Remove comments, string literals and quoted identifiers.

    Order matters: block comments may contain quotes, and ``--`` may appear
    inside strings; stripping comments first then strings handles the common
    cases, and anything pathological still ends up *more* likely to trip the
    keyword scan, never less (leftover fragments only add words).
    """
    s = _BLOCK_COMMENT.sub(" ", sql)
    s = _LINE_COMMENT.sub(" ", s)
    s = _STRING_LITERAL.sub(" ", s)
    s = _QUOTED_IDENT.sub(" ", s)
    return s


def validate(sql: str) -> str:
    """Return the trimmed statement, or raise :class:`GuardError`.

    Rules: non-empty; no dollar-quoted strings (used for function bodies —
    nothing a SELECT needs); exactly one statement; first keyword SELECT or
    WITH; no forbidden keyword anywhere at statement level.
    """
    if not sql or not sql.strip():
        raise GuardError("empty SQL statement")

    if _DOLLAR_QUOTE.search(sql):
        raise GuardError("dollar-quoted strings ($$...$$) are not allowed")

    stripped = _strip_literals(sql)

    # A single optional trailing semicolon is fine; any other semicolon
    # means a second statement is being smuggled in.
    if ";" in stripped.rstrip().rstrip(";"):
        raise GuardError("multiple SQL statements are not allowed")

    words = _WORD.findall(stripped)
    if not words:
        raise GuardError("no SQL keywords found")

    first = words[0].upper()
    if first not in ("SELECT", "WITH"):
        raise GuardError(
            f"only SELECT/WITH queries are allowed (statement starts with '{first}')"
        )

    bad = sorted({w.upper() for w in words} & FORBIDDEN_KEYWORDS)
    if bad:
        raise GuardError(f"forbidden keyword(s) for read-only access: {', '.join(bad)}")

    return sql.strip().rstrip(";").strip()

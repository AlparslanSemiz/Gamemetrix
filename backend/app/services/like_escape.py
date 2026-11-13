"""Escaping user input for SQL LIKE / ILIKE patterns."""

LIKE_ESCAPE_CHAR = "\\"


def escape_like(value: str) -> str:
    """Escape LIKE wildcards so user input matches literally (use with ilike(..., escape=LIKE_ESCAPE_CHAR))."""
    return (
        value.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace("%", f"{LIKE_ESCAPE_CHAR}%")
        .replace("_", f"{LIKE_ESCAPE_CHAR}_")
    )

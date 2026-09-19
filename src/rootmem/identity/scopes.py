"""Identity scopes (ADR 0034). Pure."""

from __future__ import annotations

from typing import Literal

Scope = Literal["read", "readwrite"]

# Tools that only look. Access tracking triggered by recall/search is not a
# user write. A tool NOT listed here is a write: new tools default to denied
# for read-scoped identities until someone classifies them deliberately.
READ_TOOLS: frozenset[str] = frozenset(
    {"recall", "search", "related", "find_skill", "get_skill", "verify_audit"}
)


def scope_allows(scope: Scope, tool_name: str) -> bool:
    if scope == "readwrite":
        return True
    return tool_name in READ_TOOLS

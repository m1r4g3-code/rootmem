"""SKILL.md format validation and rendering (ADR 0018), against the published
agentskills.io standard (December 2025). Pure functions, zero I/O — the
"SKILL.md format work" every prior phase's docs named as forward-looking
scope since Phase 0, made concrete here.

Full derivation: docs/math-spec/phase3-math-spec.md.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillFormatError(Exception):
    """Raised when a draft's `name`/`description` doesn't satisfy
    agentskills.io's own published constraints. A draft failing validation
    is never persisted (NFR10) — the caller (`consolidation.distill`) treats
    this exactly like `DistillationError`: log a degraded outcome, skip this
    cluster/session for the current pass."""


class SkillDraft(BaseModel):
    """A `ProceduralDistillationProvider`'s raw output, before validation."""

    name: str
    description: str
    body_markdown: str


def validate_skill_name(name: str, *, max_length: int) -> None:
    if not _NAME_PATTERN.fullmatch(name):
        raise SkillFormatError(
            f"skill name {name!r} must be lowercase letters/digits, hyphen-separated"
        )
    if len(name) > max_length:
        raise SkillFormatError(f"skill name {name!r} exceeds max length {max_length}")


def validate_skill_description(description: str, *, max_length: int) -> None:
    if not description.strip():
        raise SkillFormatError("skill description must not be blank")
    if len(description) > max_length:
        raise SkillFormatError(f"skill description exceeds max length {max_length}")


def render_skill_markdown(draft: SkillDraft) -> str:
    """Render literal SKILL.md-conformant markdown text: YAML frontmatter
    (`name`, `description` — the spec's only two required fields) plus the
    draft's body. Callers must validate `draft` first (`validate_skill_name`/
    `validate_skill_description`) — this function does not re-validate."""
    return (
        f"---\nname: {draft.name}\ndescription: {draft.description}\n---\n\n{draft.body_markdown}\n"
    )

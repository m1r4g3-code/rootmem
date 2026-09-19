from __future__ import annotations

import pytest

from rootmem.consolidation.skill_format import (
    SkillDraft,
    SkillFormatError,
    render_skill_markdown,
    validate_skill_description,
    validate_skill_name,
)


class TestValidateSkillName:
    def test_lowercase_hyphenated_name_is_valid(self) -> None:
        validate_skill_name("fix-missing-config-default", max_length=64)

    def test_single_word_name_is_valid(self) -> None:
        validate_skill_name("retry", max_length=64)

    def test_uppercase_is_rejected(self) -> None:
        with pytest.raises(SkillFormatError):
            validate_skill_name("Fix-Missing-Default", max_length=64)

    def test_underscore_is_rejected(self) -> None:
        with pytest.raises(SkillFormatError):
            validate_skill_name("fix_missing_default", max_length=64)

    def test_leading_hyphen_is_rejected(self) -> None:
        with pytest.raises(SkillFormatError):
            validate_skill_name("-fix-missing-default", max_length=64)

    def test_double_hyphen_is_rejected(self) -> None:
        with pytest.raises(SkillFormatError):
            validate_skill_name("fix--missing-default", max_length=64)

    def test_too_long_name_is_rejected(self) -> None:
        with pytest.raises(SkillFormatError):
            validate_skill_name("a" * 65, max_length=64)

    def test_exactly_max_length_is_valid(self) -> None:
        validate_skill_name("a" * 64, max_length=64)


class TestValidateSkillDescription:
    def test_nonblank_description_within_limit_is_valid(self) -> None:
        validate_skill_description(
            "Use this when a config loader is missing a default.", max_length=1024
        )

    def test_blank_description_is_rejected(self) -> None:
        with pytest.raises(SkillFormatError):
            validate_skill_description("   ", max_length=1024)

    def test_too_long_description_is_rejected(self) -> None:
        with pytest.raises(SkillFormatError):
            validate_skill_description("a" * 1025, max_length=1024)

    def test_exactly_max_length_is_valid(self) -> None:
        validate_skill_description("a" * 1024, max_length=1024)


class TestRenderSkillMarkdown:
    def test_renders_frontmatter_and_body(self) -> None:
        draft = SkillDraft(
            name="fix-missing-config-default",
            description="Use this when a test fails with a KeyError from a missing config default.",
            body_markdown=(
                "## Steps\n\n1. Find the missing default.\n2. Add it.\n3. Re-run the tests."
            ),
        )
        rendered = render_skill_markdown(draft)
        assert rendered.startswith("---\n")
        assert "name: fix-missing-config-default\n" in rendered
        assert (
            "description: Use this when a test fails with a KeyError from a "
            "missing config default.\n" in rendered
        )
        assert rendered.count("---") == 2
        assert "## Steps" in rendered

    def test_body_appears_after_the_closing_frontmatter_delimiter(self) -> None:
        draft = SkillDraft(name="a-skill", description="d", body_markdown="body content")
        rendered = render_skill_markdown(draft)
        _, _, after = rendered.partition("---\n\n")
        assert after.strip() == "body content"

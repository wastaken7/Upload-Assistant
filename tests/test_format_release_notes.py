from scripts.format_release_notes import format_release_notes

URL = "https://github.com/example/Project/pull"


def _line(title: str, number: int, author: str = "alice") -> str:
    return f"* {title} by @{author} in {URL}/{number}"


def test_groups_and_sorts_pull_requests() -> None:
    notes = "\n".join(
        [
            "## What's Changed",
            _line("fix(webui): keep tabs open", 1),
            _line("feat(tracker): add Example tracker", 2),
            _line("chore(deps): bump widget", 3, "dependabot[bot]"),
            _line("fix: handle Empty folders", 4),
            _line("feat: add banner", 5),
            _line("docs: explain setup", 6),
            _line("fix: avoid crash", 7),
            _line("Update readme", 8),
            "",
            "## New Contributors",
            f"* @bob made their first contribution in {URL}/2",
            "",
            "**Full Changelog**: https://github.com/example/Project/compare/v1.0...v1.1",
        ]
    )

    assert format_release_notes(notes) == "\n".join(
        [
            "## Feature",
            _line("feat: add banner", 5),
            _line("feat(tracker): add Example tracker", 2),
            "## Fix",
            _line("fix: avoid crash", 7),
            _line("fix: handle Empty folders", 4),
            _line("fix(webui): keep tabs open", 1),
            "## Maintenance",
            _line("chore(deps): bump widget", 3, "dependabot[bot]"),
            _line("docs: explain setup", 6),
            _line("Update readme", 8),
            "",
            "## New Contributors",
            f"* @bob made their first contribution in {URL}/2",
            "",
            "**Full Changelog**: https://github.com/example/Project/compare/v1.0...v1.1",
            "",
        ]
    )


def test_omits_empty_sections_and_ignores_case() -> None:
    notes = "## What's Changed\n" + _line("fix: Zebra stripes", 1) + "\n" + _line("fix: apple core", 2)

    assert format_release_notes(notes) == "## Fix\n" + _line("fix: apple core", 2) + "\n" + _line("fix: Zebra stripes", 1) + "\n"


def test_skips_blank_lines_before_change_list() -> None:
    notes = "## What's Changed\n\n" + _line("feat: add banner", 1)

    assert format_release_notes(notes) == "## Feature\n" + _line("feat: add banner", 1) + "\n"


def test_keeps_heading_without_pull_requests() -> None:
    notes = "## What's Changed\n\n**Full Changelog**: https://github.com/example/Project/compare/v1.0...v1.1"

    assert format_release_notes(notes) == notes + "\n"


def test_leaves_notes_without_change_list_untouched() -> None:
    notes = "**Full Changelog**: https://github.com/example/Project/compare/v1.0...v1.1"

    assert format_release_notes(notes) == notes + "\n"

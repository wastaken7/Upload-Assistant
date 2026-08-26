# ruff: noqa: S101

import asyncio

from src.get_desc import DescriptionBuilder
from src.meta import Meta

HEADER = "[center]Screenshots have been adapted for SDR viewing, for reference only.[/center]"
IMPORTED = f"[center]Imported body text[/center]\n{HEADER}"


def _builder(default_header=HEADER, tracker_header=None):
    tracker_config = {} if tracker_header is None else {"tonemapped_header": tracker_header}
    return DescriptionBuilder("TEST", {"DEFAULT": {"tonemapped_header": default_header}, "TRACKERS": {"TEST": tracker_config}})


def _render(meta, builder=None, **sections):
    """Render through the real generator with everything but the description off."""
    builder = builder or _builder()
    off = {
        "audio_spectrogram": False,
        "bluray": False,
        "book": False,
        "custom_header": False,
        "custom_signature": False,
        "game": False,
        "languages": False,
        "logo": False,
        "mediainfo": False,
        "menu_screenshots": False,
        "nfo": False,
        "screenshots": False,
        "tv_info": False,
        "ua_signature": False,
        "user_description": False,
        "music": False,
        "dynamic_hdr_plot": False,
    }
    off.update(sections)
    return asyncio.run(builder.general_description_generator(meta, **off))


def _count(text):
    return text.count("adapted for SDR viewing")


# --- the bug this fixes ----------------------------------------------------


def test_an_imported_header_is_not_rendered_twice():
    """The reported bug: imported copy + UA's own copy both rendered."""
    meta = Meta(description=IMPORTED, tonemapped=True)

    assert _count(_render(meta)) == 1


# --- the regression that gating prevents -----------------------------------


def test_an_imported_header_survives_when_this_run_adds_none():
    """meta.tonemapped is False, so nothing re-adds it, so stripping would delete."""
    meta = Meta(description=IMPORTED, tonemapped=False)

    assert _count(_render(meta)) == 1


def test_an_imported_header_survives_when_the_section_is_disabled():
    meta = Meta(description=IMPORTED, tonemapped=True)

    assert _count(_render(meta, tonemapped_header=False)) == 1


def test_the_imported_body_text_is_never_lost():
    for tonemapped in (True, False):
        rendered = _render(Meta(description=IMPORTED, tonemapped=tonemapped))
        assert "Imported body text" in rendered


# --- the helper ------------------------------------------------------------


def test_the_helper_removes_every_copy_when_replacing():
    builder = _builder()

    assert HEADER not in builder._strip_tonemapped_header(HEADER * 3, Meta(), replacing=True)


def test_whitespace_drift_from_a_tracker_render_is_tolerated():
    builder = _builder()
    reparsed = "[center]Screenshots  have been\nadapted for SDR viewing,   for reference only.[/center]"

    assert builder._strip_tonemapped_header(reparsed, Meta(), replacing=True) == ""


def test_similar_text_is_preserved():
    builder = _builder()
    near_miss = "[center]Screenshots have been adapted for SDR viewing, for comparison.[/center]"

    assert builder._strip_tonemapped_header(near_miss, Meta(), replacing=True) == near_miss


def test_both_the_tracker_header_and_the_default_are_stripped():
    # The description was imported from ANOTHER tracker, so it carries that
    builder = _builder(tracker_header="[b]Tonemapped[/b]")
    text = f"[b]Tonemapped[/b] kept: {HEADER}"

    assert builder._strip_tonemapped_header(text, Meta(), replacing=True).strip() == "kept:"


def test_a_header_is_matched_regardless_of_case():
    builder = _builder(tracker_header="[b]Tonemapped[/b]")
    text = "before [B]TONEMAPPED[/B] after"

    assert "TONEMAPPED" not in builder._strip_tonemapped_header(text, Meta(), replacing=True)


def test_an_unset_header_does_not_strip_an_unrelated_notice():
    builder = _builder(default_header="")
    text = f"body {HEADER}"

    assert builder._strip_tonemapped_header(text, Meta(), replacing=True) == text


def test_the_legacy_header_is_stripped_when_nothing_is_configured():
    # Descriptions produced before a config change carry this exact spelling, so it
    legacy = "[center][code] Screenshots have been tonemapped for reference [/code][/center]"
    builder = _builder(default_header="")
    text = f"body {legacy} tail"

    out = builder._strip_tonemapped_header(text, Meta(), replacing=True)
    assert legacy not in out
    assert "body" in out and "tail" in out


def test_duplicates_collapse_to_one_when_nothing_is_re_added():
    # The case gating on `replacing` alone missed: the duplicate usually arrives on
    builder = _builder()
    text = f"intro {HEADER} middle {HEADER} tail"

    out = builder._strip_tonemapped_header(text, Meta(), replacing=False)
    assert out.count(HEADER) == 1
    assert "intro" in out and "middle" in out and "tail" in out


def test_a_lone_header_is_never_removed():
    # It still describes screenshots that are displayed, so removing the only copy
    builder = _builder()
    text = f"intro {HEADER} tail"

    assert builder._strip_tonemapped_header(text, Meta(), replacing=False) == text


def test_mixed_spellings_collapse_together():
    # The imported copy uses the source tracker's spelling, ours uses the DEFAULT;
    builder = _builder(tracker_header="[b]Tonemapped[/b]")
    out = builder._strip_tonemapped_header(f"x [b]Tonemapped[/b] y {HEADER} z", Meta(), replacing=False)
    total = out.count(HEADER) + out.count("[b]Tonemapped[/b]")
    assert total == 1, out


def test_a_longer_spelling_wins_over_a_shorter_one_it_contains():
    # Without longest-first ordering, whichever spelling the alternation tries first
    long_header = f"{HEADER} [i]see notes[/i]"
    builder = _builder(tracker_header=long_header)
    text = f"x {long_header} y {long_header} z"

    out = builder._strip_tonemapped_header(text, Meta(), replacing=False)

    assert out.count(long_header) == 1, out
    assert out.count("[i]see notes[/i]") == 1, out


def test_an_imported_header_survives_a_whitespace_only_configured_header():
    """Blank is not a header, so nothing meaningful is re-added and the import stays."""
    builder = _builder(tracker_header="   ")
    meta = Meta(description=IMPORTED, tonemapped=True)

    assert _count(_render(meta, builder=builder)) == 1


def test_only_spans_present_in_the_original_text_are_removed():
    """Never delete more than what matched before any edit."""
    builder = _builder(tracker_header="[b]X [/b]")
    text = f"[b]X {HEADER}[/b]"

    out = builder._strip_tonemapped_header(text, Meta(), replacing=True)

    assert out == "[b]X [/b]", out


def test_a_tag_override_spelling_is_stripped():
    """The release group's own override is a candidate, like the tracker's and DEFAULT's."""
    builder = DescriptionBuilder(
        "TEST",
        {
            "DEFAULT": {"tonemapped_header": HEADER, "tag_overrides": {"-GRP": {"tonemapped_header": "[b]Group tonemap note[/b]"}}},
            "TRACKERS": {"TEST": {}},
        },
    )
    meta = Meta(tag="-GRP")
    text = "body [b]Group tonemap note[/b] tail [b]Group tonemap note[/b]"

    out = builder._strip_tonemapped_header(text, meta, replacing=False)

    assert out.count("[b]Group tonemap note[/b]") == 1, out


def test_a_bare_word_header_is_not_stripped_from_prose():
    """A header with no markup cannot be told apart from ordinary prose."""
    builder = _builder(tracker_header="SDR")
    text = "Screenshots were converted from HDR to SDR before capture."

    assert builder._strip_tonemapped_header(text, Meta(), replacing=True) == text


def test_removing_a_header_leaves_every_other_byte_alone():
    """Exact equality, so any whitespace rewriting elsewhere in the text is caught."""
    builder = _builder()
    body = "[code]\nSource: UHD Blu-ray\n\nEncoder: x265\n[/code]"
    # leading and trailing whitespace included: both edges must survive verbatim
    text = f"\n {body}\n\n{HEADER}\n{HEADER}\n\ntail\n"

    out = builder._strip_tonemapped_header(text, Meta(), replacing=False)

    assert out == f"\n {body}\n\n{HEADER}\n\n\ntail\n", repr(out)


def test_whitespace_between_tokens_may_also_be_absent():
    """The tolerance is zero-or-more, not one-or-more."""
    builder = _builder(tracker_header="[b]X [/b]")
    text = "a [b]X[/b] b [b]X[/b] c"

    out = builder._strip_tonemapped_header(text, Meta(), replacing=True)

    assert out == "a  b  c", repr(out)


def test_equal_length_spellings_resolve_deterministically():
    """Equal-length spellings need their own tie-break so the order is always the same."""
    builder = DescriptionBuilder(
        "TEST",
        {
            "DEFAULT": {"tonemapped_header": "[b]a[/b] [i]"},
            "TRACKERS": {"TEST": {"tonemapped_header": "[b]a[/b][i]["}},
        },
    )
    text = "[b]a[/b][i][ tail [b]a[/b][i][ x"

    assert builder._strip_tonemapped_header(text, Meta(), replacing=True) == "[ tail [ x"


def test_candidates_are_ordered_longest_first_then_lexicographically():
    """Ordering is deterministic, and the legacy spelling is pinned literally."""
    builder = _builder(tracker_header="[b]Tonemapped[/b]")

    assert builder._tonemapped_header_candidates(Meta()) == (
        "[center]Screenshots have been adapted for SDR viewing, for reference only.[/center]",
        "[center][code] Screenshots have been tonemapped for reference [/code][/center]",
        "[b]Tonemapped[/b]",
    )


def test_a_header_run_into_preceding_text_is_left_alone():
    """The left anchor alone: punctuation before the header means it is not a header."""
    builder = _builder()
    text = f"body.{HEADER} {HEADER}"

    out = builder._strip_tonemapped_header(text, Meta(), replacing=True)

    assert out == f"body.{HEADER} ", repr(out)


def test_a_header_run_into_following_text_is_left_alone():
    """The right anchor alone: the header is a prefix of a longer word, not a header."""
    builder = _builder()
    text = f"{HEADER}-guide {HEADER}"

    out = builder._strip_tonemapped_header(text, Meta(), replacing=True)

    assert out == f"{HEADER}-guide ", repr(out)


def test_a_configured_header_with_a_newline_still_matches_a_spaced_copy():
    """Tokens split on any whitespace, not only spaces."""
    builder = _builder(tracker_header="[b]Tonemapped\n\tfor reference[/b]")
    text = "body [b]Tonemapped for reference[/b] tail [b]Tonemapped for reference[/b]"

    out = builder._strip_tonemapped_header(text, Meta(), replacing=True)

    assert out == "body  tail ", repr(out)


def test_text_is_returned_untouched_when_the_config_is_unreadable():
    """A config error must degrade to leaving the description alone, never blanking it."""
    builder = DescriptionBuilder("TEST", {"TRACKERS": {"TEST": {}}})  # no DEFAULT key
    text = f"body {HEADER} tail"

    assert builder._strip_tonemapped_header(text, Meta(), replacing=True) == text

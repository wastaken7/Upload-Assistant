# ruff: noqa: S101
"""Slot recommendations in the dupe check flow. Titles and groups are fictional."""

from datetime import date
from typing import Any

import pytest

from src.meta import Meta
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.registry import evaluate_slots, slot_rules_enabled
from src.uphelper import UploadHelper

NAME = "Fictional Film 2021 1080p AMZN WEB-DL DDP 5.1 H.264-NOGRPA"


def make_meta(**overrides: Any) -> Meta:
    values: dict[str, Any] = {
        "category": "MOVIE",
        "name": NAME,
        "type": "WEBDL",
        "resolution": "1080p",
        "video_encode": "H.264",
        "service": "AMZN",
        "tag": "-NOGRPA",
        "source_size": 6 * 1024**3,
    }
    values.update(overrides)
    return Meta(**values)


def decision(verdict: Verdict) -> SlotDecision:
    return SlotDecision(verdict=verdict, reason="test reason", tracker="AITHER", rules_date=date(2026, 10, 15))


class Tracker:
    async def get_name(self, meta: Meta) -> dict[str, str]:
        return {"name": meta.name}


def make_helper(monkeypatch: pytest.MonkeyPatch, messages: list[str], prompts: list[tuple[str, bool]]) -> UploadHelper:
    helper = UploadHelper({"DEFAULT": {}})
    helper.tracker_class_map = {"AITHER": lambda **_kwargs: Tracker(), "NOSLOTS": lambda **_kwargs: Tracker()}

    def ask_yes_no(question: str, default: bool = False) -> bool:
        prompts.append((question, default))
        return default

    monkeypatch.setattr("src.uphelper.cli_ui.ask_yes_no", ask_yes_no)
    monkeypatch.setattr("src.uphelper.logger.info", lambda message, **_kwargs: messages.append(str(message)))
    return helper


def test_slot_rules_enabled_by_default() -> None:
    assert slot_rules_enabled({"DEFAULT": {}})
    assert slot_rules_enabled({})
    assert not slot_rules_enabled({"DEFAULT": {"slot_rules": False}})


@pytest.mark.asyncio
async def test_evaluate_slots_uses_unfiltered_results() -> None:
    dupes = [{"name": "Fictional Film 2021 1080p NF WEB-DL DDP 5.1 H.264-NOGRPB", "size": 5 * 1024**3}]
    result = await evaluate_slots(dupes, make_meta(), "AITHER", {"DEFAULT": {}})
    assert result is not None
    assert result.verdict is Verdict.BLOCK
    assert result.conflicts[0]["name"] == dupes[0]["name"]


@pytest.mark.asyncio
async def test_evaluate_slots_returns_none_when_not_applicable() -> None:
    dupes = [{"name": "Fictional Film 2021 1080p NF WEB-DL DDP 5.1 H.264-NOGRPB"}]
    assert await evaluate_slots(dupes, make_meta(), "AITHER", {"DEFAULT": {"slot_rules": False}}) is None
    assert await evaluate_slots(dupes, make_meta(), "NOSLOTS", {"DEFAULT": {}}) is None
    assert await evaluate_slots(dupes, make_meta(category="GAME"), "AITHER", {"DEFAULT": {}}) is None
    assert await evaluate_slots(dupes, make_meta(is_disc="BDMV", type="DISC"), "AITHER", {"DEFAULT": {}}) is None


@pytest.mark.asyncio
async def test_evaluate_slots_ignores_other_seasons() -> None:
    meta = make_meta(category="TV", name="Fictional Show S02 1080p AMZN WEB-DL DDP 5.1 H.264-NOGRPA", season="S02", episode="", tv_pack=1)
    dupes = [{"name": "Fictional Show S01 1080p NF WEB-DL DDP 5.1 H.264-NOGRPB"}]
    result = await evaluate_slots(dupes, meta, "AITHER", {"DEFAULT": {}})
    assert result is not None
    assert result.verdict is Verdict.ALLOW


@pytest.mark.asyncio
async def test_unattended_allow_uploads_despite_basic_dupes(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []
    prompts: list[tuple[str, bool]] = []
    helper = make_helper(monkeypatch, messages, prompts)
    is_dupe, _meta = await helper.dupe_check(["other release"], make_meta(unattended=True), "AITHER", decision(Verdict.ALLOW))
    assert is_dupe is False
    assert prompts == []
    assert any("Rules as of 2026-10-15" in message for message in messages)


@pytest.mark.asyncio
async def test_unattended_block_skips_even_without_basic_dupes(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []
    prompts: list[tuple[str, bool]] = []
    helper = make_helper(monkeypatch, messages, prompts)
    is_dupe, _meta = await helper.dupe_check([], make_meta(unattended=True), "AITHER", decision(Verdict.BLOCK))
    assert is_dupe is True
    assert prompts == []


@pytest.mark.asyncio
async def test_unattended_review_keeps_basic_result(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []
    prompts: list[tuple[str, bool]] = []
    helper = make_helper(monkeypatch, messages, prompts)
    is_dupe, _meta = await helper.dupe_check(["other release"], make_meta(unattended=True), "AITHER", decision(Verdict.REVIEW))
    assert is_dupe is True
    is_dupe, _meta = await helper.dupe_check([], make_meta(unattended=True), "AITHER", decision(Verdict.REVIEW))
    assert is_dupe is False


@pytest.mark.asyncio
async def test_skip_dupe_check_still_uploads_on_block(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = make_helper(monkeypatch, [], [])
    is_dupe, _meta = await helper.dupe_check([], make_meta(unattended=True, dupe=True), "AITHER", decision(Verdict.BLOCK))
    assert is_dupe is False


@pytest.mark.asyncio
async def test_interactive_prompt_default_follows_recommendation(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts: list[tuple[str, bool]] = []
    helper = make_helper(monkeypatch, [], prompts)
    await helper.dupe_check(["other release"], make_meta(), "AITHER", decision(Verdict.ALLOW))
    await helper.dupe_check(["other release"], make_meta(), "AITHER", decision(Verdict.BLOCK))
    await helper.dupe_check([], make_meta(), "AITHER", decision(Verdict.BLOCK))
    assert prompts == [("Upload to AITHER anyway?", True), ("Upload to AITHER anyway?", False), ("Upload to AITHER anyway?", False)]


@pytest.mark.asyncio
async def test_unsupported_tracker_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []
    helper = make_helper(monkeypatch, messages, [])
    is_dupe, _meta = await helper.dupe_check(["other release"], make_meta(unattended=True), "NOSLOTS", None)
    assert is_dupe is True
    assert "[dim]NOSLOTS: slot rules are not implemented for this tracker; using the basic dupe check.[/dim]" in messages


@pytest.mark.asyncio
async def test_no_notice_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []
    helper = make_helper(monkeypatch, messages, [])
    helper.config = {"DEFAULT": {"slot_rules": False}}
    await helper.dupe_check(["other release"], make_meta(unattended=True), "NOSLOTS", None)
    assert not any("slot rules" in message for message in messages)


def test_describe_size_compares_with_the_upload() -> None:
    from src.uphelper import _describe_size

    upload = 10 * 1024**3
    assert _describe_size(3.5 * 1024**3, upload) == "3.5 GB · 65% smaller than yours"
    assert _describe_size(12 * 1024**3, upload) == "12.0 GB · 20% larger than yours"
    assert _describe_size(10 * 1024**3, upload) == "10.0 GB · about the same size as yours"
    assert _describe_size(None, upload) == ""
    assert _describe_size(500 * 1024**2, None) == "500 MB"


@pytest.mark.asyncio
async def test_exact_episode_wins_over_season_pack_review() -> None:
    name = "Fictional Show S01E02 1080p AMZN WEB-DL DDP 5.1 H.264-NOGRPA"
    meta = make_meta(category="TV", name=name, season="S01", episode="E02", tv_pack=0)
    dupes = [{"name": "Fictional Show S01 1080p NF WEB-DL DDP 5.1 H.264-NOGRPB"}, {"name": name}]
    result = await evaluate_slots(dupes, meta, "AITHER", {"DEFAULT": {}})
    assert result is not None
    assert result.verdict is Verdict.BLOCK
    meta_pack_only = make_meta(category="TV", name=name, season="S01", episode="E02", tv_pack=0)
    result = await evaluate_slots(dupes[:1], meta_pack_only, "AITHER", {"DEFAULT": {}})
    assert result is not None
    assert result.verdict is Verdict.REVIEW


@pytest.mark.asyncio
async def test_interactive_review_with_conflicts_asks_even_without_basic_dupes(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts: list[tuple[str, bool]] = []
    helper = make_helper(monkeypatch, [], prompts)
    review = decision(Verdict.REVIEW)
    review.conflicts = [{"name": "Fictional Film 2021 1080p BluRay x264-NOGRPB"}]
    is_dupe, _meta = await helper.dupe_check([], make_meta(), "AITHER", review)
    assert prompts == [("Upload to AITHER anyway?", False)]
    assert is_dupe is True
    is_dupe, _meta = await helper.dupe_check([], make_meta(unattended=True), "AITHER", review)
    assert is_dupe is False


@pytest.mark.asyncio
async def test_episode_holding_the_slot_blocks_even_with_a_season_pack() -> None:
    name = "Fictional Show S01E02 1080p AMZN WEB-DL DDP 5.1 H.264-NOGRPA"
    meta = make_meta(category="TV", name=name, season="S01", episode="E02", tv_pack=0)
    dupes = [{"name": "Fictional Show S01 1080p NF WEB-DL DDP 5.1 H.264-NOGRPB"}, {"name": "Fictional Show S01E02 1080p NF WEB-DL DDP 5.1 H.264-NOGRPC"}]
    result = await evaluate_slots(dupes, meta, "AITHER", {"DEFAULT": {}})
    assert result is not None
    assert result.verdict is Verdict.BLOCK

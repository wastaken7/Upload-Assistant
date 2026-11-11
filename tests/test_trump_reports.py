# ruff: noqa: S101
"""Trump reports: one review during the dupe check, one report per tracker after the upload."""

import asyncio
from datetime import date
from typing import Any, ClassVar

import pytest

from src import trump_reports
from src.dupe_checking import DupeChecker
from src.meta import Meta
from src.slot_rules.base import SlotRules
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import ReleaseProfile
from src.trackers.UNIT3D.aither import Aither
from src.trackers.UNIT3D.lst import LST
from src.trackers.UNIT3D.ulcx import ULCX
from src.trump_reports import ReviewOutcome, TrumpCandidate, TrumpPlan, TrumpSupport
from src.uphelper import UploadHelper

CONFIG: dict[str, Any] = {"DEFAULT": {}, "TRACKERS": {"AITHER": {"api_key": "fake-key"}, "LST": {"api_key": "fake-key"}, "ULCX": {"api_key": "fake-key"}}}
OLD_FILES = ["Fictional.Feature.2020.1080p.WEB-DL.H.264-OLDGRP.mkv", "Fictional.Feature.2020.1080p.WEB-DL.H.264-OLDGRP.srt"]
OLD = {"name": "Fictional Feature 2020 1080p WEB-DL H.264-OLDGRP", "id": 11, "link": "https://example.invalid/torrents/11", "size": 100, "files": OLD_FILES}


def answers(monkeypatch: pytest.MonkeyPatch, yes_no: list[bool] | None = None, strings: list[str] | None = None) -> list[str]:
    """Answer prompts in order and record each question."""
    asked: list[str] = []
    yes_no_answers = list(yes_no or [])
    string_answers = list(strings or [])

    def ask_yes_no(question: str, default: bool = False) -> bool:
        asked.append(question)
        return yes_no_answers.pop(0) if yes_no_answers else default

    def ask_string(question: str, default: str = "") -> str:
        asked.append(question)
        return string_answers.pop(0) if string_answers else default

    monkeypatch.setattr("src.trump_reports.cli_ui.ask_yes_no", ask_yes_no)
    monkeypatch.setattr("src.trump_reports.cli_ui.ask_string", ask_string)
    monkeypatch.setattr("src.uphelper.cli_ui.ask_yes_no", ask_yes_no)
    return asked


class SearchableTracker:
    """Stub of a tracker that lists existing reports and needs comparisons."""

    trump_support = TrumpSupport(searchable=True, comparison=True)

    def __init__(self, reports: list[dict[str, Any]] | None = None) -> None:
        self.reports = reports
        self.searched: list[str] = []

    async def find_trump_reports(self, _meta: Meta, reported_id: str) -> list[dict[str, Any]] | None:
        self.searched.append(reported_id)
        return self.reports

    async def get_name(self, meta: Meta) -> dict[str, str]:
        return {"name": meta.name}


def candidate(reason: str = trump_reports.TRUMPABLE, **entry: Any) -> TrumpCandidate:
    return TrumpCandidate({**OLD, **entry}, reason)


def review(meta: Meta, tracker: Any, candidates: list[TrumpCandidate], name: str = "AITHER") -> ReviewOutcome:
    return asyncio.run(trump_reports.review(meta, name, tracker, candidates, lambda entry: str(entry.get("name"))))


# --- candidates -------------------------------------------------------------


def exact_meta(**fields: Any) -> Meta:
    """An upload whose files are exactly those of ``OLD``."""
    return Meta(filename_match=f"{OLD['name']} = {OLD['link']}", file_count_match=2, filelist=[f"/data/{name}" for name in OLD_FILES], **fields)


def test_candidates_keep_the_strongest_reason_once_per_torrent() -> None:
    other = {"name": "Fictional Feature 2020 1080p WEB-DL H.264-SECOND", "id": 12, "trump_target": True}
    slot = SlotDecision(Verdict.ALLOW, "Replaces", "AITHER", date(2026, 1, 1), why="DV/HDR takes priority.", conflicts=[{**OLD, "trump_target": True}, other], trump=True)

    found = trump_reports.find_candidates(Meta(), "AITHER", [{**OLD, "trump_target": True}, other], slot)

    assert [(item.torrent_id, item.reason) for item in found] == [("11", trump_reports.TRUMPABLE), ("12", trump_reports.TRUMPABLE)]


def test_an_exact_match_is_the_only_candidate() -> None:
    """Uploading the same files again can only trump that torrent, not another one."""
    other = {"name": "Fictional Feature 2020 1080p WEB-DL H.264-SECOND", "id": 12, "trump_target": True}

    found = trump_reports.find_candidates(exact_meta(), "AITHER", [{**OLD, "trump_target": True}, other], None)

    assert [(item.torrent_id, item.reason) for item in found] == [("11", trump_reports.EXACT_MATCH)]


@pytest.mark.parametrize(
    "files",
    [
        ["Fictional.Feature.2020.1080p.WEB-DL.H.264-OLDGRP.mkv", "Fictional.Feature.2020.1080p.WEB-DL.H.264-OLDGRP.eng.srt"],
        ["Fictional.Feature.2020.1080p.WEB-DL.H.264-OLDGRP.mkv"],
        [],
    ],
)
def test_an_exact_match_needs_the_same_complete_file_list(files: list[str]) -> None:
    """A shared video file is not enough: different extra files are a different release."""
    found = trump_reports.find_candidates(exact_meta(), "AITHER", [{**OLD, "files": files, "trump_target": True}], None)

    assert [(item.torrent_id, item.reason) for item in found] == [("11", trump_reports.TRUMPABLE)]


def test_an_exact_match_accepts_a_comma_separated_file_list() -> None:
    (found,) = trump_reports.find_candidates(exact_meta(), "AITHER", [{**OLD, "files": [", ".join(reversed(OLD_FILES))]}], None)

    assert found.reason == trump_reports.EXACT_MATCH


def test_candidates_need_a_torrent_id() -> None:
    assert trump_reports.find_candidates(Meta(), "AITHER", [{"name": "No id", "trump_target": True}], None) == []


def test_slot_rules_candidates_carry_the_rule() -> None:
    slot = SlotDecision(
        Verdict.ALLOW, "Replaces", "LST", date(2026, 1, 1), why="DV/HDR takes priority.", conflicts=[OLD], rules_url="https://example.invalid/rules", trump=True
    )

    (found,) = trump_reports.find_candidates(Meta(), "LST", [], slot)

    assert (found.reason, found.detail, found.rules_url) == (trump_reports.SLOT_RULES, "DV/HDR takes priority.", "https://example.invalid/rules")


@pytest.mark.parametrize(
    "decision",
    [
        SlotDecision(Verdict.ALLOW, "Room left", "LST", date(2026, 1, 1), conflicts=[OLD]),
        SlotDecision(Verdict.REVIEW, "Maybe", "LST", date(2026, 1, 1), conflicts=[OLD], trump=True),
        SlotDecision(Verdict.ALLOW, "Free", "LST", date(2026, 1, 1), trump=True),
    ],
)
def test_only_an_allowed_slot_trump_offers_a_report(decision: SlotDecision) -> None:
    assert trump_reports.find_candidates(Meta(), "LST", [], decision) == []


def test_season_pack_prefers_the_episode_from_its_own_group() -> None:
    meta = Meta(tv_pack=True, tag="-MINE")
    meta["AITHER_matched_episode_ids"] = [{"id": 1, "name": "Fictional Show S01E01-OTHER"}, {"id": 2, "name": "Fictional Show S01E02-MINE"}]

    (found,) = trump_reports.find_candidates(meta, "AITHER", [], None)

    assert (found.torrent_id, found.reason) == ("2", trump_reports.SEASON_PACK)


def test_slot_rules_mark_a_replacing_release_as_a_trump() -> None:
    upload = ReleaseProfile(name="Fictional Feature 2020 1080p WEB-DL H.264 REPACK-GRP", group="GRP", repack=1)
    existing = ReleaseProfile(name="Fictional Feature 2020 1080p WEB-DL H.264-GRP", group="GRP", entry=OLD)

    decision = SlotRules().by_slot(upload, [existing], lambda _profile: ("1080p",), "1080p", trump=lambda _new, _old: (Verdict.ALLOW, "Better."))

    assert decision.verdict is Verdict.ALLOW
    assert decision.trump is True
    assert trump_reports.slot_trumps(decision)


def test_filter_marks_trumpable_releases_in_the_upload_resolution() -> None:
    meta = Meta(name="Fictional Feature 2020 1080p WEB-DL H.264-NEWGRP", category="MOVIE", resolution="1080p", type="WEBDL", source="WEB", tag="-NEWGRP")
    same_res = {"name": "Fictional Feature 2020 1080p WEB-DL H.264-OLDGRP", "id": 1, "res": "1080p", "trumpable": True, "files": []}
    not_trumpable = {"name": "Fictional Feature 2020 1080p WEB-DL H.264-THIRD", "id": 2, "res": "1080p", "trumpable": False, "files": []}

    result = asyncio.run(DupeChecker(CONFIG).filter_dupes([same_res, not_trumpable], meta, "AITHER"))

    assert {entry["id"]: bool(entry.get("trump_target")) for entry in result} == {1: True, 2: False}


def test_filter_does_not_mark_trumpable_releases_in_another_resolution() -> None:
    """The resolution check keeps a site-marked 2160p release out of a 1080p trump."""
    meta = Meta(name="Fictional Feature 2020 1080p WEB-DL HDR H.265-NEWGRP", category="MOVIE", resolution="1080p", type="WEBDL", source="WEB", tag="-NEWGRP", hdr="HDR")
    # The name also says 1080p so the basic resolution filter keeps it; only ``res`` differs.
    other_res = {"name": "Fictional Feature 2020 1080p WEB-DL HDR H.265-OLDGRP", "id": 3, "res": "2160p", "trumpable": True, "files": []}

    result = asyncio.run(DupeChecker(CONFIG).filter_dupes([other_res], meta, "AITHER"))

    assert [(entry["id"], bool(entry.get("trump_target"))) for entry in result] == [(3, False)]


def season_pack_dupes(tracker: str, config: dict[str, Any] | None = None, **episode_fields: Any) -> tuple[list[Any], Meta]:
    """Filter one same-season episode and one existing season pack for a season pack upload."""
    meta = Meta(
        name="Fictional Show S01 1080p WEB-DL H.264-NEWGRP", category="TV", tv_pack=1, season="S01", episode="", resolution="1080p", type="WEBDL", source="WEB", tag="-NEWGRP"
    )
    episode = {
        "name": "Fictional Show S01E02 1080p WEB-DL H.264-OLDGRP",
        "id": 21,
        "link": "https://example.invalid/torrents/21",
        "res": "1080p",
        "type": "WEB-DL",
        "files": [],
        **episode_fields,
    }
    pack = {"name": "Fictional Show S01 1080p WEB-DL H.264-OTHER", "id": 22, "link": "https://example.invalid/torrents/22", "res": "1080p", "type": "WEB-DL", "files": []}
    result = asyncio.run(DupeChecker(config or CONFIG).filter_dupes([episode, pack], meta, tracker))
    return list(result), meta


def test_season_pack_trump_targets_are_episodes_only() -> None:
    """An existing season pack stays a dupe; it is never listed as an episode to trump."""
    result, meta = season_pack_dupes("AITHER")

    assert [entry["id"] for entry in meta["AITHER_matched_episode_ids"]] == [21]
    assert {entry["id"] for entry in result} == {21, 22}


def test_season_pack_internal_episodes_follow_the_trackers_own_settings() -> None:
    config = {"DEFAULT": {}, "TRACKERS": {"AITHER": {"internal": False}, "LST": {"internal": True, "internal_groups": ["newgrp"]}}}

    _result, meta = season_pack_dupes("LST", config, name="Fictional Show S01E02 1080p WEB-DL H.264-NEWGRP", internal=1)

    assert [entry["id"] for entry in meta["LST_matched_episode_ids"]] == [21]


# --- review -----------------------------------------------------------------


def test_review_stores_a_plan_when_the_comparison_is_in_the_description(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch, yes_no=[True], strings=["d"])
    tracker = SearchableTracker(reports=[])
    meta = Meta(name="Fictional Feature 2020 1080p WEB-DL H.264-NEWGRP")

    assert review(meta, tracker, [candidate()]) is ReviewOutcome.PLANNED

    assert tracker.searched == ["11"]
    assert asked[0] == "Are you trumping this release on AITHER?"
    plan = trump_reports.get_plan(meta, "AITHER")
    assert plan is not None
    assert (plan.reported_id, plan.reason, plan.comparison) == ("11", trump_reports.TRUMPABLE, "description")


def test_review_asks_which_release_when_there_are_several(monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch, strings=["2", "d"])
    meta = Meta()

    outcome = review(meta, SearchableTracker(reports=[]), [candidate(), candidate(trump_reports.SLOT_RULES, id=12, name="Second")])

    assert outcome is ReviewOutcome.PLANNED
    assert meta.trump_plans["AITHER"]["reported_id"] == "12"


@pytest.mark.parametrize("answer", ["\u00b2", "0", "3", "x"])
def test_review_ignores_an_answer_that_is_not_a_listed_number(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    answers(monkeypatch, strings=[answer])
    meta = Meta()

    assert review(meta, SearchableTracker(reports=[]), [candidate(), candidate(trump_reports.SLOT_RULES, id=12, name="Second")]) is ReviewOutcome.DECLINED
    assert meta.trump_plans == {}


def test_review_collects_comparison_links(monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch, yes_no=[True], strings=["L", "https://img.invalid/a, https://img.invalid/b", "https://img.invalid/c"])
    meta = Meta()

    assert review(meta, SearchableTracker(reports=[]), [candidate()]) is ReviewOutcome.PLANNED

    plan = trump_reports.get_plan(meta, "AITHER")
    assert plan is not None
    assert plan.reported_screenshots == ["https://img.invalid/a", "https://img.invalid/b"]
    assert plan.trumping_screenshots == ["https://img.invalid/c"]


@pytest.mark.parametrize("strings", [[""], ["L", ""], ["L", "https://img.invalid/a", ""]])
def test_review_without_a_comparison_sends_no_report(monkeypatch: pytest.MonkeyPatch, strings: list[str]) -> None:
    answers(monkeypatch, yes_no=[True], strings=strings)
    meta = Meta()

    assert review(meta, SearchableTracker(reports=[]), [candidate()]) is ReviewOutcome.DECLINED
    assert meta.trump_plans == {}


@pytest.mark.parametrize(
    "reports",
    [
        None,
        [{"id": 3, "title": "Older report", "trumping_torrent": [{"name": "Other upload"}]}],
        [{"id": 4, "title": "Broken [/markup] title", "solved": True, "trumping_torrent": [{"name": "Name with [/b] tag"}]}],
    ],
)
def test_review_existing_or_unknown_reports_can_skip_the_upload(monkeypatch: pytest.MonkeyPatch, reports: list[dict[str, Any]] | None) -> None:
    asked = answers(monkeypatch, yes_no=[True, False])
    meta = Meta()

    assert review(meta, SearchableTracker(reports=reports), [candidate()]) is ReviewOutcome.SKIP_UPLOAD
    assert len(asked) == 2
    assert meta.trump_plans == {}


def test_review_skips_the_comparison_for_tv_packs(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch, yes_no=[True])
    meta = Meta(tv_pack=True)

    assert review(meta, SearchableTracker(reports=[]), [candidate(trump_reports.SEASON_PACK)]) is ReviewOutcome.PLANNED
    assert asked == ["Are you trumping this release on AITHER?"]


def test_review_asks_lst_for_a_note(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch, yes_no=[True], strings=["Older encode has broken audio"])
    meta = Meta()

    assert review(meta, LST(CONFIG), [candidate()], name="LST") is ReviewOutcome.PLANNED

    assert len(asked) == 2
    assert meta.trump_plans["LST"]["note"] == "Older encode has broken audio"


def test_declining_the_trump_stores_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch, yes_no=[False])
    tracker = SearchableTracker(reports=[])
    meta = Meta()

    assert review(meta, tracker, [candidate()]) is ReviewOutcome.DECLINED
    assert tracker.searched == []
    assert meta.trump_plans == {}


# --- dupe review integration -------------------------------------------------


def dupe_check(meta: Meta, dupes: list[Any], tracker: Any, slot: SlotDecision | None = None) -> tuple[bool, Meta]:
    helper = UploadHelper({"DEFAULT": {}})
    helper.tracker_class_map = {"AITHER": lambda **_kwargs: tracker}
    return asyncio.run(helper.dupe_check(dupes, meta, "AITHER", slot))


def test_accepted_trump_uploads_with_a_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch, yes_no=[True], strings=["d"])

    is_dupe, meta = dupe_check(Meta(name="New"), [{**OLD, "trump_target": True}], SearchableTracker(reports=[]))

    assert is_dupe is False
    assert "AITHER" in meta.trump_plans


def test_declined_trump_falls_back_to_the_dupe_question(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch, yes_no=[False, True])

    is_dupe, meta = dupe_check(Meta(name="New"), [{**OLD, "trump_target": True}], SearchableTracker(reports=[]))

    assert asked == ["Are you trumping this release on AITHER?", "Upload to AITHER anyway?"]
    assert is_dupe is False
    assert meta.trump_plans == {}


def test_declined_exact_trump_is_not_uploaded(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch, yes_no=[False])
    meta = exact_meta(name="New")

    is_dupe, meta = dupe_check(meta, [OLD], SearchableTracker(reports=[]))

    assert asked == ["Are you trumping this release on AITHER?"]
    assert is_dupe is True


def test_exact_dupe_cannot_be_approved_by_trumping_another_release(monkeypatch: pytest.MonkeyPatch) -> None:
    """With an exact dupe on the site, the only trump offered is that dupe."""
    asked = answers(monkeypatch, yes_no=[True], strings=["d"])
    other = {"name": "Fictional Feature 2020 1080p WEB-DL H.264-SECOND", "id": 12, "trump_target": True}

    is_dupe, meta = dupe_check(exact_meta(name="New"), [OLD, other], SearchableTracker(reports=[]))

    assert asked[0] == "Are you trumping this release on AITHER?"
    assert is_dupe is False
    assert (meta.trump_plans["AITHER"]["reported_id"], meta.trump_plans["AITHER"]["reason"]) == ("11", trump_reports.EXACT_MATCH)


def test_declined_season_pack_trump_keeps_an_existing_season_pack_as_a_dupe(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch, yes_no=[False, False])
    dupes, meta = season_pack_dupes("AITHER")
    meta.name = "New"

    is_dupe, meta = dupe_check(meta, dupes, SearchableTracker(reports=[]))

    assert asked == ["Are you trumping this release on AITHER?", "Upload to AITHER anyway?"]
    assert is_dupe is True


def test_slot_trump_is_offered_without_basic_dupes(monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch, yes_no=[True], strings=["d"])
    slot = SlotDecision(Verdict.ALLOW, "Replaces", "AITHER", date(2026, 1, 1), conflicts=[OLD], trump=True)

    is_dupe, meta = dupe_check(Meta(name="New"), [], SearchableTracker(reports=[]), slot)

    assert is_dupe is False
    assert meta.trump_plans["AITHER"]["reason"] == trump_reports.SLOT_RULES


def test_unattended_runs_never_plan_a_trump(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch)
    slot = SlotDecision(Verdict.ALLOW, "Replaces", "AITHER", date(2026, 1, 1), conflicts=[OLD], trump=True)

    is_dupe, meta = dupe_check(Meta(name="New", unattended=True), [{**OLD, "trump_target": True}], SearchableTracker(reports=[]), slot)

    assert asked == []
    assert is_dupe is False
    assert meta.trump_plans == {}


def test_a_new_review_drops_an_older_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch)
    meta = Meta(name="New", trump_plans={"AITHER": TrumpPlan("AITHER", "9", "Stale", trump_reports.TRUMPABLE).to_dict()})

    _is_dupe, meta = dupe_check(meta, [], SearchableTracker(reports=[]))

    assert meta.trump_plans == {}


# --- submission ---------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.body = body or {}

    def json(self) -> dict[str, Any]:
        return self.body


class FakeClient:
    posts: ClassVar[list[tuple[str, dict[str, Any], dict[str, str]]]] = []
    status_code = 201
    body: ClassVar[dict[str, Any]] = {}

    def __init__(self, **_kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
        FakeClient.posts.append((url, json, headers))
        return FakeResponse(FakeClient.status_code, FakeClient.body)


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> type[FakeClient]:
    FakeClient.posts = []
    FakeClient.status_code = 201
    FakeClient.body = {}
    monkeypatch.setattr("src.trump_reports.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("src.api_key_expiry.observe_tracker_response", lambda *_args, **_kwargs: None)
    return FakeClient


def submitted(meta: Meta) -> dict[str, bool]:
    return asyncio.run(trump_reports.submit_reports(meta, CONFIG, {"AITHER": Aither, "LST": LST}))


def planned_meta(**overrides: Any) -> Meta:
    aither = TrumpPlan(
        "AITHER",
        "11",
        OLD["name"],
        trump_reports.SLOT_RULES,
        detail="DV/HDR takes priority.",
        reported_screenshots=["https://img.invalid/a"],
        trumping_screenshots=["https://img.invalid/b"],
    )
    lst = TrumpPlan("LST", "21", OLD["name"], trump_reports.TRUMPABLE, note="Broken audio")
    fields: dict[str, Any] = {
        "ua_name": "Upload Assistant",
        "trump_plans": {"AITHER": aither.to_dict(), "LST": lst.to_dict()},
        "tracker_status": {"AITHER": {"upload": True, "torrent_id": 501}, "LST": {"upload": True, "torrent_id": 601}},
    }
    return Meta({**fields, **overrides})


def test_reports_go_to_each_tracker_with_its_own_payload(fake_http: type[FakeClient]) -> None:
    assert submitted(planned_meta()) == {"AITHER": True, "LST": True}

    (aither_url, aither_payload, headers), (lst_url, lst_payload, _) = fake_http.posts
    assert aither_url == "https://aither.cc/api/trumping-reports/create"
    assert aither_payload == {
        "reported_torrent_id": "11",
        "trumping_torrent_id": 501,
        "message": "Upload Assistant slot trump: DV/HDR takes priority.",
        "screenshots_reported_torrent": "https://img.invalid/a",
        "screenshots_trumping_torrent": "https://img.invalid/b",
    }
    assert headers["Authorization"] == "Bearer fake-key"
    assert lst_url == "https://lst.gg/api/reports/torrents/21/trump"
    assert lst_payload == {"message": "Upload Assistant trumpable release trump - Broken audio: https://lst.gg/torrents/601"}


def test_only_finished_uploads_send_a_report(fake_http: type[FakeClient]) -> None:
    meta = planned_meta(tracker_status={"AITHER": {"upload": False}, "LST": {"upload": True}})

    assert submitted(meta) == {"LST": False}
    assert fake_http.posts == []


def test_debug_runs_print_the_report_without_sending(fake_http: type[FakeClient]) -> None:
    meta = planned_meta(debug=True, tracker_status={"AITHER": {"upload": True}, "LST": {"upload": False}})

    assert submitted(meta) == {"AITHER": True}
    assert fake_http.posts == []


def test_a_refused_report_is_an_error(fake_http: type[FakeClient]) -> None:
    fake_http.status_code = 422

    assert submitted(planned_meta()) == {"AITHER": False, "LST": False}


def test_a_refused_report_shows_the_sites_message(fake_http: type[FakeClient], monkeypatch: pytest.MonkeyPatch) -> None:
    fake_http.status_code = 422
    fake_http.body = {"message": "You already have an open report [on] this torrent."}
    logged: list[str] = []
    monkeypatch.setattr("src.trump_reports.logger.info", lambda message, *_args, **_kwargs: logged.append(str(message)))
    plan = TrumpPlan("ULCX", "31", OLD["name"], trump_reports.TRUMPABLE)
    meta = Meta({"trump_plans": {"ULCX": plan.to_dict()}, "tracker_status": {"ULCX": {"upload": True, "torrent_id": 701}}})

    assert asyncio.run(trump_reports.submit_reports(meta, CONFIG, {"ULCX": ULCX})) == {"ULCX": False}
    assert any("You already have an open report \[on] this torrent." in line for line in logged)


def test_lst_refuses_a_non_numeric_torrent_id(fake_http: type[FakeClient]) -> None:
    meta = planned_meta()
    meta.trump_plans["LST"]["reported_id"] = "None"

    assert submitted(meta)["LST"] is False
    assert [url for url, _payload, _headers in fake_http.posts] == ["https://aither.cc/api/trumping-reports/create"]


@pytest.mark.parametrize(
    ("reason", "category"),
    [(trump_reports.SEASON_PACK, "season_pack_trump"), (trump_reports.SLOT_RULES, "trump_quality"), (trump_reports.TRUMPABLE, "trump_quality")],
)
def test_ulcx_reports_the_trumped_torrent_with_a_link_to_the_upload(fake_http: type[FakeClient], reason: str, category: str) -> None:
    plan = TrumpPlan("ULCX", "31", OLD["name"], reason, note="Better encode")
    meta = Meta({"ua_name": "Upload Assistant", "trump_plans": {"ULCX": plan.to_dict()}, "tracker_status": {"ULCX": {"upload": True, "torrent_id": 701}}})

    assert asyncio.run(trump_reports.submit_reports(meta, CONFIG, {"ULCX": ULCX})) == {"ULCX": True}

    ((url, payload, headers),) = fake_http.posts
    assert url == "https://upload.cx/api/torrents/31/reports"
    assert payload["category"] == category
    assert payload["link"] == "https://upload.cx/torrents/701"
    assert payload["message"].endswith(" - Better encode")
    assert headers["Authorization"] == "Bearer fake-key"


def test_ulcx_refuses_a_non_numeric_torrent_id(fake_http: type[FakeClient]) -> None:
    plan = TrumpPlan("ULCX", "None", OLD["name"], trump_reports.TRUMPABLE)
    meta = Meta({"trump_plans": {"ULCX": plan.to_dict()}, "tracker_status": {"ULCX": {"upload": True, "torrent_id": 701}}})

    assert asyncio.run(trump_reports.submit_reports(meta, CONFIG, {"ULCX": ULCX})) == {"ULCX": False}
    assert fake_http.posts == []


# --- manager to submission ------------------------------------------------------


def test_a_plan_made_in_the_tracker_check_is_submitted_after_the_upload(monkeypatch: pytest.MonkeyPatch, fake_http: type[FakeClient]) -> None:
    """The plan made on the per-tracker copy of meta reaches the shared meta and the report."""
    from src import trackerstatus

    class Setup:
        def __init__(self, config: dict[str, Any]) -> None:
            del config

        def filter_unsupported_trackers(self, meta: Meta) -> Meta:
            return meta

        async def check_banned_group(self, *_args: Any) -> bool:
            return False

        async def get_torrent_claims(self, *_args: Any) -> bool:
            return False

    class Router:
        def __init__(self, *_args: Any) -> None:
            pass

        async def apply(self, meta: Meta) -> Meta:
            return meta

    class Filter:
        def __init__(self, _config: dict[str, Any]) -> None:
            pass

        async def filter_dupes(self, dupes: list[Any], *_args: Any) -> list[Any]:
            return dupes

    class Helper:
        def __init__(self, _config: dict[str, Any]) -> None:
            pass

        async def dupe_check(self, _dupes: list[Any], local_meta: Meta, tracker: str, _slot: Any) -> tuple[bool, Meta]:
            local_meta.trump_plans[tracker] = TrumpPlan(tracker, "11", OLD["name"], trump_reports.TRUMPABLE, comparison="description").to_dict()
            return False, local_meta

    class Tracker(Aither):
        async def search_existing(self, _meta: Meta) -> list[Any]:
            return [{**OLD, "trump_target": True}]

    async def no_slots(*_args: Any) -> None:
        return None

    monkeypatch.setattr(trackerstatus, "TrackerSetup", Setup)
    monkeypatch.setattr(trackerstatus, "AvistaZNetworkRouter", Router)
    monkeypatch.setattr(trackerstatus, "DupeChecker", Filter)
    monkeypatch.setattr(trackerstatus, "UploadHelper", Helper)
    monkeypatch.setattr(trackerstatus, "evaluate_slots", no_slots)
    monkeypatch.setattr(trackerstatus, "tracker_class_map", {"AITHER": Tracker})
    meta = Meta(name="New", ua_name="Upload Assistant", trackers=["AITHER"], tracker_status={}, unattended=True, imdb_id=1)

    assert asyncio.run(trackerstatus.TrackerStatusManager(CONFIG).process_all_trackers(meta)) == 1
    assert meta.trump_plans["AITHER"]["reported_id"] == "11"

    meta.tracker_status["AITHER"]["torrent_id"] = 501  # what a finished upload records
    assert asyncio.run(trump_reports.submit_reports(meta, CONFIG, {"AITHER": Aither})) == {"AITHER": True}
    ((url, payload, _headers),) = fake_http.posts
    assert url == "https://aither.cc/api/trumping-reports/create"
    assert payload["reported_torrent_id"] == "11"
    assert payload["trumping_torrent_id"] == 501

# ruff: noqa: S101
"""Trump reports: one review during the dupe check, one report per tracker after the upload."""

import asyncio
from datetime import date
from typing import Any

import pytest

from src import trump_reports
from src.dupe_checking import DupeChecker
from src.meta import Meta
from src.slot_rules.base import SlotRules
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import ReleaseProfile
from src.trackers.UNIT3D.aither import Aither
from src.trackers.UNIT3D.lst import LST
from src.trump_reports import ReviewOutcome, TrumpCandidate, TrumpPlan, TrumpSupport
from src.uphelper import UploadHelper

CONFIG: dict[str, Any] = {"DEFAULT": {}, "TRACKERS": {"AITHER": {"api_key": "fake-key"}, "LST": {"api_key": "fake-key"}}}
OLD = {"name": "Fictional Feature 2020 1080p WEB-DL H.264-OLDGRP", "id": 11, "link": "https://example.invalid/torrents/11", "size": 100}


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


def test_candidates_keep_the_strongest_reason_once_per_torrent() -> None:
    meta = Meta(filename_match=f"{OLD['name']} = {OLD['link']}", file_count_match=1)
    other = {"name": "Fictional Feature 2020 1080p WEB-DL H.264-SECOND", "id": 12, "trump_target": True}
    slot = SlotDecision(Verdict.ALLOW, "Replaces", "AITHER", date(2026, 1, 1), why="DV/HDR takes priority.", conflicts=[{**OLD, "trump_target": True}, other], trump=True)

    found = trump_reports.find_candidates(meta, "AITHER", [{**OLD, "trump_target": True}, other], slot)

    assert [(item.torrent_id, item.reason) for item in found] == [("11", trump_reports.EXACT_MATCH), ("12", trump_reports.TRUMPABLE)]


def test_candidates_need_a_torrent_id() -> None:
    assert trump_reports.find_candidates(Meta(), "AITHER", [{"name": "No id", "trump_target": True}], None) == []


def test_slot_rules_candidates_carry_the_rule() -> None:
    slot = SlotDecision(Verdict.ALLOW, "Replaces", "LST", date(2026, 1, 1), why="DV/HDR takes priority.", conflicts=[OLD], rules_url="https://example.invalid/rules", trump=True)

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


@pytest.mark.parametrize("reports", [None, [{"id": 3, "title": "Older report", "trumping_torrent": [{"name": "Other upload"}]}]])
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
    meta = Meta(name="New", filename_match=f"{OLD['name']} = {OLD['link']}", file_count_match=1)

    is_dupe, meta = dupe_check(meta, [OLD], SearchableTracker(reports=[]))

    assert asked == ["Are you trumping this release on AITHER?"]
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
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return {}


class FakeClient:
    posts: list[tuple[str, dict[str, Any], dict[str, str]]] = []
    status_code = 201

    def __init__(self, **_kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
        FakeClient.posts.append((url, json, headers))
        return FakeResponse(FakeClient.status_code)


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> type[FakeClient]:
    FakeClient.posts = []
    FakeClient.status_code = 201
    monkeypatch.setattr("src.trump_reports.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("src.api_key_expiry.observe_tracker_response", lambda *_args, **_kwargs: None)
    return FakeClient


def submitted(meta: Meta) -> dict[str, bool]:
    return asyncio.run(trump_reports.submit_reports(meta, CONFIG, {"AITHER": Aither, "LST": LST}))


def planned_meta(**overrides: Any) -> Meta:
    aither = TrumpPlan("AITHER", "11", OLD["name"], trump_reports.SLOT_RULES, detail="DV/HDR takes priority.", reported_screenshots=["https://img.invalid/a"], trumping_screenshots=["https://img.invalid/b"])
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


def test_lst_refuses_a_non_numeric_torrent_id(fake_http: type[FakeClient]) -> None:
    meta = planned_meta()
    meta.trump_plans["LST"]["reported_id"] = "None"

    assert submitted(meta)["LST"] is False
    assert [url for url, _payload, _headers in fake_http.posts] == ["https://aither.cc/api/trumping-reports/create"]

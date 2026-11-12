# ruff: noqa: S101

import asyncio
import time
from datetime import datetime

import pytest

from src import trackerhandle
from src.args import Args
from src.configvalidator import validate_config
from src.meta import Meta
from src.upload_schedule import UploadPacer, configured_upload_interval, format_duration, parse_duration, resolve_upload_at, wait_before_upload

NOW = datetime(2026, 3, 10, 20, 0, 0)
BASE = NOW.timestamp()


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0), ("", 0), (0, 0), (45, 45), ("90", 90), ("90s", 90), ("45m", 2700), ("2h", 7200), ("1d", 86400), ("1h30m", 5400), (" 1H 30M ", 5400)],
)
def test_parse_duration(value, expected):
    assert parse_duration(value) == expected


@pytest.mark.parametrize("value", ["abc", "10x", "m30", "-5", "1.5h", True])
def test_parse_duration_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_duration(value)


def _wall(value: datetime) -> datetime:
    assert value.tzinfo is not None
    return value.replace(tzinfo=None)


def test_time_of_day_later_today():
    assert _wall(resolve_upload_at("23:30", NOW)) == datetime(2026, 3, 10, 23, 30)


def test_time_of_day_already_passed_means_tomorrow():
    assert _wall(resolve_upload_at("7:05", NOW)) == datetime(2026, 3, 11, 7, 5)
    assert _wall(resolve_upload_at("20:00", NOW)) == datetime(2026, 3, 11, 20, 0)


def test_full_date_in_the_future():
    assert _wall(resolve_upload_at("2026-03-12 01:15", NOW)) == datetime(2026, 3, 12, 1, 15)
    assert _wall(resolve_upload_at("2026-03-12T01:15:30", NOW)) == datetime(2026, 3, 12, 1, 15, 30)


@pytest.fixture
def new_york_time(monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("changing the local timezone needs time.tzset")
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_repeated_dst_hour_uses_the_second_occurrence(new_york_time):
    # 01:45 EDT on the night clocks go back: the second 01:30 (EST) is 45 minutes away.
    now = datetime(2026, 11, 1, 1, 45).astimezone()

    target = resolve_upload_at("01:30", now)

    assert target.timestamp() - now.timestamp() == 45 * 60


@pytest.mark.parametrize("value", ["2026-03-09 23:00", "2026-03-12", "24:00", "12:60", "tomorrow", "2026-02-30 10:00"])
def test_upload_at_rejects_past_or_invalid_values(value):
    with pytest.raises(ValueError):
        resolve_upload_at(value, NOW)


@pytest.mark.parametrize(("seconds", "expected"), [(5, "0m 05s"), (65, "1m 05s"), (3725, "1h 02m"), (90061, "1d 1h")])
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


def test_args_parse_scheduling_options(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--upload-interval", "1h30m", "--upload-at", "2099-01-02 03:04"], Meta())

    assert meta.upload_interval == 5400
    assert _wall(datetime.fromisoformat(meta.upload_at)) == datetime(2099, 1, 2, 3, 4)


@pytest.mark.parametrize("option", [["--upload-at", "25:00"], ["--upload-at", "2000-01-01 10:00"], ["--upload-interval", "soon"]])
def test_args_reject_invalid_scheduling_options(tmp_path, option):
    with pytest.raises(SystemExit):
        Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), *option], Meta())


def test_configured_upload_interval_prefers_the_command_line():
    assert configured_upload_interval(Meta(upload_interval=60), {"DEFAULT": {"upload_interval": "1h"}}) == 60
    assert configured_upload_interval(Meta(upload_interval=0), {"DEFAULT": {"upload_interval": "1h"}}) == 0
    assert configured_upload_interval(Meta(), {"DEFAULT": {"upload_interval": "1h"}}) == 3600
    assert configured_upload_interval(Meta(), {"DEFAULT": {}}) == 0
    with pytest.raises(ValueError):
        configured_upload_interval(Meta(), {"DEFAULT": {"upload_interval": "30min"}})


def test_explicit_zero_interval_on_the_command_line(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--upload-interval", "0"], Meta())

    assert meta.upload_interval == 0
    assert configured_upload_interval(meta, {"DEFAULT": {"upload_interval": "1h"}}) == 0


@pytest.mark.parametrize(("value", "valid"), [("30m", True), (90, True), ("30min", False)])
def test_config_validation_rejects_invalid_intervals(value, valid):
    config = {"DEFAULT": {"tmdb_api": "fictional", "upload_interval": value}, "TRACKERS": {}, "TORRENT_CLIENTS": {}}

    _is_valid, errors, _warnings = validate_config(config, [], None)

    assert any("upload_interval" in error for error in errors) is not valid


class _Clock:
    def __init__(self, now: float) -> None:
        self.now = now
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _wait(meta, config, pacer, clock):
    return asyncio.run(wait_before_upload(meta, config, pacer, clock=clock, sleep=clock.sleep))


def test_interval_waits_only_for_the_remaining_time():
    clock = _Clock(BASE + 1_000)
    pacer = UploadPacer(clock)
    pacer.last_upload_at = BASE + 900

    assert _wait(Meta(upload_interval=250), {"DEFAULT": {}}, pacer, clock) is True
    assert clock.now == BASE + 1_150
    assert all(step <= 30 for step in clock.slept)


def test_interval_does_not_wait_before_the_first_upload_or_after_it_elapsed():
    clock = _Clock(BASE + 1_000)
    pacer = UploadPacer(clock)

    assert _wait(Meta(upload_interval=250), {"DEFAULT": {}}, pacer, clock) is False
    pacer.last_upload_at = BASE + 500
    assert _wait(Meta(upload_interval=250), {"DEFAULT": {}}, pacer, clock) is False
    assert clock.slept == []


def test_upload_at_waits_until_the_target():
    target = datetime(2026, 3, 10, 21, 0)
    clock = _Clock(target.timestamp() - 95)

    assert _wait(Meta(upload_at=target.isoformat()), {"DEFAULT": {}}, None, clock) is True
    assert clock.now == target.timestamp()


def test_the_later_of_both_targets_wins():
    target = datetime(2026, 3, 10, 21, 0)
    clock = _Clock(target.timestamp() - 10)
    pacer = UploadPacer(clock)
    pacer.last_upload_at = clock.now

    assert _wait(Meta(upload_at=target.isoformat(), upload_interval=60), {"DEFAULT": {}}, pacer, clock) is True
    assert clock.now == target.timestamp() + 50


def test_debug_mode_does_not_wait():
    clock = _Clock(datetime(2026, 3, 10, 20, 0).timestamp())

    assert _wait(Meta(debug=True, upload_at="2026-03-10T21:00:00"), {"DEFAULT": {}}, None, clock) is False
    assert clock.slept == []


def test_pacer_records_only_successful_uploads():
    clock = _Clock(50.0)
    pacer = UploadPacer(clock)

    pacer.record(Meta(tracker_status={"ALPHA": {"upload": True, "upload_success": False}}))
    assert pacer.last_upload_at is None
    pacer.record(Meta(tracker_status={"ALPHA": {"upload_success": True}}))
    assert pacer.last_upload_at == 50.0


class _Tracker:
    searches: list[str] = []
    uploads: list[str] = []
    results: dict[str, list[dict[str, object]]] = {}

    def __init__(self, config):
        self.config = config
        self.tracker = type(self).__name__.removeprefix("_").upper()

    async def search_existing(self, _meta):
        self.searches.append(self.tracker)
        return self.results.get(self.tracker, [])

    async def upload(self, _meta):
        self.uploads.append(self.tracker)
        return True


class _Alpha(_Tracker):
    pass


class _Beta(_Tracker):
    pass


class _Client:
    async def add_to_client(self, _meta, _tracker):
        return None


@pytest.fixture
def tracker_stage(monkeypatch):
    _Tracker.searches = []
    _Tracker.uploads = []
    _Tracker.results = {}

    class _Setup:
        def __init__(self, config):
            self.config = config

        def trackers_enabled(self, meta):
            return list(meta.trackers)

    class _DupeChecker:
        def __init__(self, config):
            self.config = config

        async def filter_dupes(self, dupes, _meta, _tracker):
            return dupes

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(trackerhandle, "TrackerSetup", _Setup)
    monkeypatch.setattr(trackerhandle, "DupeChecker", _DupeChecker)
    monkeypatch.setattr(trackerhandle, "evaluate_slots", _noop)
    monkeypatch.setattr(trackerhandle, "provision_tracker_torrents", _noop)
    monkeypatch.setattr(trackerhandle, "check_tracker_image_hosts", _noop)
    monkeypatch.setattr(trackerhandle, "record_event_async", _noop)
    return _Tracker


def _run_trackers(meta):
    meta.trackers = ["ALPHA", "BETA"]
    meta.tracker_status = {"ALPHA": {"upload": True}, "BETA": {"upload": True}}
    config = {"DEFAULT": {"smart_image_host_selection": False}, "TRACKERS": {}}
    asyncio.run(trackerhandle.process_trackers(meta, config, _Client(), ["ALPHA", "BETA"], {"ALPHA": _Alpha, "BETA": _Beta}, [], [], bandwidth_control=False))


def test_scheduled_wait_skips_trackers_with_new_dupes(tracker_stage):
    known = {"name": "Fictional.Film.2020.1080p-GRP", "size": 1}
    tracker_stage.results = {"ALPHA": [known], "BETA": [known, {"name": "Fictional.Film.2020.1080p-NEW", "size": 2}]}
    meta = Meta(upload_waited=True, initial_dupes={"ALPHA": [known], "BETA": [known]})

    _run_trackers(meta)

    assert sorted(tracker_stage.searches) == ["ALPHA", "BETA"]
    assert tracker_stage.uploads == ["ALPHA"]
    assert meta.tracker_status["BETA"]["status_message"] == "Skipped due to new dupe found after waiting to upload"


def test_new_slot_evidence_reaches_slot_rules(tracker_stage, monkeypatch):
    known = {"name": "Fictional.Film.2020.1080p-GRP", "size": 1}
    hidden = {"name": "Fictional.Film.2020.1080p.DV-NEW", "size": 3}
    tracker_stage.results = {"ALPHA": [known], "BETA": [known]}
    evaluated: list[str] = []

    class _Block:
        verdict = trackerhandle.Verdict.BLOCK

    async def _slots(_dupes, meta, tracker, _config):
        evaluated.append(tracker)
        return _Block() if hidden in meta.get(f"{tracker}_title_releases", []) else None

    original_search = _Tracker.search_existing

    async def _search(self, meta):
        meta[f"{self.tracker}_title_releases"] = [known, hidden] if self.tracker == "BETA" else [known]
        return await original_search(self, meta)

    monkeypatch.setattr(trackerhandle, "evaluate_slots", _slots)
    monkeypatch.setattr(_Tracker, "search_existing", _search)
    meta = Meta(
        upload_waited=True,
        initial_dupes={"ALPHA": [known], "BETA": [known]},
        initial_title_releases={"ALPHA": [known], "BETA": [known]},
    )

    _run_trackers(meta)

    assert evaluated == ["BETA"]
    assert tracker_stage.uploads == ["ALPHA"]


def test_no_dupe_recheck_without_a_wait(tracker_stage):
    tracker_stage.results = {"BETA": [{"name": "Fictional.Film.2020.1080p-NEW", "size": 2}]}

    _run_trackers(Meta())

    assert tracker_stage.searches == []
    assert sorted(tracker_stage.uploads) == ["ALPHA", "BETA"]

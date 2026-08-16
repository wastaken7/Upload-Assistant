# ruff: noqa: S101

import asyncio

import pytest

import src.get_tracker_data as tracker_data_module
import src.trackers.common as common_module
from src.description_review import draft, load_review, save_review
from src.get_tracker_data import TrackerDataManager
from src.meta import Meta
from src.tracker_descriptions import DescriptionCandidate, TrackerDescriptionMode, add_candidate, description_fingerprint, resolve_description_mode, score_release_name
from src.trackermeta import update_meta_with_unit3d_data
from src.trackers.common import Common


def test_legacy_options_resolve_to_explicit_description_modes():
    assert resolve_description_mode("ids") is TrackerDescriptionMode.IDS
    assert resolve_description_mode("images") is TrackerDescriptionMode.IMAGES
    assert resolve_description_mode("text") is TrackerDescriptionMode.TEXT
    assert resolve_description_mode("text_and_images") is TrackerDescriptionMode.TEXT_AND_IMAGES


def test_missing_or_unknown_explicit_mode_is_rejected():
    with pytest.raises(ValueError, match="tracker_description_mode"):
        resolve_description_mode(None)
    with pytest.raises(ValueError, match="tracker_description_mode"):
        resolve_description_mode("typo")


def test_release_score_prefers_exact_and_explicit_matches():
    assert score_release_name("Film.2026.1080p", "Film.2026.1080p.mkv") > score_release_name("Film.2026.1080p", "Other.2026.720p.mkv")
    assert score_release_name("anything", "unrelated", explicit_id=True) == 100


def test_candidate_audit_hides_raw_text_and_records_hashes():
    meta = Meta({})
    candidate = DescriptionCandidate(source="AITHER", raw_description="original", cleaned_description="clean")
    add_candidate(meta, candidate, selected=True)

    record = meta.description_candidates[0]
    assert "raw_description" not in record
    assert record["raw_sha256"]
    assert record["cleaned_sha256"]
    assert meta.description_provenance == record


def test_fingerprint_changes_when_description_inputs_change():
    meta = Meta({"name": "Release", "description": "one", "image_list": [{"raw_url": "https://one"}]})
    initial = description_fingerprint(meta, "AITHER")
    meta.image_list = [{"raw_url": "https://two"}]
    assert description_fingerprint(meta, "AITHER") != initial


def test_unit3d_import_records_source_and_honors_images_only_mode(tmp_path, monkeypatch):
    async def no_images(_images, _meta):
        return []

    monkeypatch.setattr("src.trackermeta.check_images_concurrently", no_images)

    async def run():
        meta = Meta(
            {
                "base_dir": str(tmp_path),
                "uuid": "release",
                "tracker_ids": {"AITHER": "50049"},
                "tracker_description_mode": "images",
                "tracker_description_raw": {"AITHER": "raw"},
            }
        )
        result = (1, 2, 3, 0, "clean", "MOVIE", None, [{"raw_url": "https://image"}], "Release.mkv")
        assert await update_meta_with_unit3d_data(meta, result, "AITHER")
        assert meta.description == ""
        assert meta.description_candidates[0]["selected"] is False
        assert meta.description_candidates[0]["release_id"] == "50049"

    asyncio.run(run())


def test_unit3d_candidate_keeps_description_in_memory(tmp_path):
    async def run():
        meta = Meta(
            {
                "base_dir": str(tmp_path),
                "uuid": "candidate",
                "tracker_description_mode": "text",
                "persist_description": False,
            }
        )
        result = (1, 2, 3, 0, "clean", "MOVIE", None, [], "Release.mkv")
        assert await update_meta_with_unit3d_data(meta, result, "AITHER")
        assert meta.description == "clean"
        assert not (tmp_path / "tmp" / "candidate" / "DESCRIPTION.txt").exists()

    asyncio.run(run())


def test_selected_tracker_description_can_be_discarded(monkeypatch):
    async def run():
        manager = TrackerDataManager({"DEFAULT": {}, "TRACKERS": {}})
        meta = Meta({"unattended": False})
        candidate = Meta({"description": "tracker text", "description_provenance": {"source": "AITHER"}})
        monkeypatch.setattr("src.get_tracker_data.cli_ui.ask_string", lambda _prompt: "d")

        await manager._review_explicit_tracker_description(meta, "AITHER", candidate)

        assert candidate.description == ""
        assert candidate.description_provenance["discarded"] is True

    asyncio.run(run())


def test_unit3d_source_id_does_not_skip_interactive_description_review(monkeypatch):
    class FakeResponse:
        @staticmethod
        def json():
            return {
                "attributes": {
                    "description": "tracker text",
                    "tmdb_id": 949,
                    "imdb_id": 113277,
                    "tvdb_id": 0,
                    "mal_id": 0,
                    "category": "MOVIE",
                }
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        @staticmethod
        async def get(**_kwargs):
            return FakeResponse()

    async def run():
        messages = []
        monkeypatch.setattr(common_module.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
        monkeypatch.setattr(common_module.cli_ui, "ask_string", lambda *_args, **_kwargs: "d")
        monkeypatch.setattr(common_module.logger, "info", lambda message, **_kwargs: messages.append(str(message)))
        meta = Meta({"tracker_ids": {"AITHER": "123"}, "unattended": False})

        result = await Common({"TRACKERS": {"AITHER": {"api_key": "test"}}}).unit3d_torrent_info(
            "AITHER",
            "https://aither.example/api/torrents/",
            "https://aither.example/api/torrents",
            meta,
            id="123",
            public_torrent_url="https://aither.example/torrents/",
        )

        assert result[4] is None
        assert "Searching for information on [bold cyan]Aither[/bold cyan] (https://aither.example/torrents/123)" in messages

    asyncio.run(run())


def test_webui_tracker_description_is_saved_without_prompting(tmp_path, monkeypatch):
    async def run():
        manager = TrackerDataManager({"DEFAULT": {}, "TRACKERS": {}})
        meta = Meta({"base_dir": str(tmp_path), "uuid": "release", "unattended": False})
        candidate = Meta({"description": "tracker text", "description_provenance": {"source": "AITHER"}})
        monkeypatch.setenv("UA_WEBUI_ACTIVE", "1")
        monkeypatch.setattr("src.get_tracker_data.cli_ui.ask_string", lambda _prompt: (_ for _ in ()).throw(AssertionError("WebUI must not prompt")))
        monkeypatch.setattr("src.get_tracker_data.click.edit", lambda _text: (_ for _ in ()).throw(AssertionError("editor must not open")))

        await manager._review_explicit_tracker_description(meta, "AITHER", candidate)

        assert load_review(tmp_path / "tmp" / "release")["content"] == "tracker text"
        assert candidate.description == "tracker text"

    asyncio.run(run())


def test_description_review_draft_prefers_saved_webui_content(tmp_path):
    temp_dir = tmp_path / "tmp" / "release"
    save_review(temp_dir, "webui text", 4)

    assert draft({"description": "tracker text"}, temp_dir) == ("webui text", 4)


def test_saved_webui_draft_replaces_the_tracker_description(tmp_path):
    from src.description_review import apply_saved_draft

    meta = Meta({"base_dir": str(tmp_path), "uuid": "release", "description": "tracker text"})
    save_review(tmp_path / "tmp" / "release", "edited text", 1)

    apply_saved_draft(meta)

    assert meta.description == "edited text"
    assert meta.description_override == "edited text"


def test_explicit_tracker_ids_are_collected_concurrently_and_best_candidate_is_applied(tmp_path, monkeypatch):
    async def run():
        config = {
            "DEFAULT": {"tracker_comment_only": True, "tracker_description_mode": "text"},
            "TRACKERS": {
                "AITHER": {"use_for_search": True},
                "BLUTOPIA": {"use_for_search": True},
            },
        }
        manager = TrackerDataManager(config)
        running = 0
        peak_running = 0

        async def fake_update(tracker, _instance, candidate, *_args, **_kwargs):
            nonlocal running, peak_running
            assert (tmp_path / "tmp" / candidate.uuid).is_dir()
            running += 1
            peak_running = max(peak_running, running)
            await asyncio.sleep(0.01)
            running -= 1
            candidate.imdb_id = 1 if tracker == "AITHER" else 2
            candidate.description = tracker
            candidate.description_provenance = {"score": 1 if tracker == "AITHER" else 50}
            return candidate, True

        monkeypatch.setattr(manager, "update_metadata_from_explicit_tracker", fake_update)
        monkeypatch.setitem(tracker_data_module.tracker_class_map, "AITHER", lambda **_kwargs: object())
        monkeypatch.setitem(tracker_data_module.tracker_class_map, "BLUTOPIA", lambda **_kwargs: object())

        meta = Meta(
            {
                "base_dir": str(tmp_path),
                "uuid": "release",
                "tracker_ids": {"AITHER": "11", "BLUTOPIA": "22"},
                "unattended": True,
                "tracker_description_mode": "text",
            }
        )
        await manager.get_tracker_data(None, meta, "Release", "Release")

        assert peak_running == 2
        assert meta.matched_tracker == "BLUTOPIA"
        assert meta.imdb_id == 2
        assert meta.description == "BLUTOPIA"

    asyncio.run(run())


def test_tracker_comment_only_defaults_to_skipping_filename_searches(tmp_path, monkeypatch):
    async def run():
        manager = TrackerDataManager({"DEFAULT": {}, "TRACKERS": {"AITHER": {"use_for_search": True}}})
        meta = Meta({"base_dir": str(tmp_path), "uuid": "release"})

        async def unexpected_search(*_args, **_kwargs):
            raise AssertionError("filename-based tracker search must not run")

        monkeypatch.setattr(manager, "update_metadata_from_explicit_tracker", unexpected_search)

        result = await manager.get_tracker_data(None, meta, "Release", "Release")

        assert result is meta
        assert meta.no_tracker_match is False

    asyncio.run(run())

# ruff: noqa: S101

import asyncio
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.description_review import load_review
from src.get_desc import DescriptionBuilder, gen_desc
from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D
from web_ui import server


def test_description_section_controls_default_to_true():
    controls = (
        "audio_spectrogram",
        "bluray",
        "book",
        "custom_header",
        "custom_signature",
        "description",
        "game",
        "languages",
        "logo",
        "mediainfo",
        "menu_screenshots",
        "nfo",
        "screenshots",
        "tonemapped_header",
        "tv_info",
        "ua_signature",
        "user_description",
        "music",
        "dynamic_hdr_plot",
    )
    parameters = inspect.signature(DescriptionBuilder.general_description_generator).parameters

    assert all(parameters[control].default is True for control in controls)


def test_webui_description_api_saves_an_execution_scoped_override(tmp_path, monkeypatch):
    temp_dir = tmp_path / "release"
    temp_dir.mkdir()
    meta_file = temp_dir / "meta.json"
    meta_file.write_text(json.dumps({"uuid": "release", "description": "tracker text"}), encoding="utf-8")

    def resolve(_session_id):
        return temp_dir, meta_file, {"uuid": "release", "description": "tracker text"}

    monkeypatch.setattr(server, "_resolve_execution_description_review", resolve)
    monkeypatch.setattr(server, "_webui_auth_ok", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    with server.app.test_client() as client:
        initial = client.get("/api/execution_description?session_id=session")
        assert initial.status_code == 200
        assert initial.get_json()["content"] == "tracker text"

        response = client.put(
            "/api/execution_description",
            json={"session_id": "session", "content": "edited text", "version": 0},
            headers={"Origin": "http://localhost"},
        )

    assert response.status_code == 200
    assert response.get_json()["version"] == 1
    assert not (temp_dir / "DESCRIPTION.txt").exists()
    assert load_review(temp_dir) == {"content": "edited text", "version": 1}
    assert "description_override" not in json.loads(meta_file.read_text(encoding="utf-8"))


def test_webui_description_api_rejects_stale_save_and_reset_versions(tmp_path, monkeypatch):
    temp_dir = tmp_path / "release"
    temp_dir.mkdir()
    meta_file = temp_dir / "meta.json"
    meta_file.write_text(json.dumps({"uuid": "release", "description": "tracker text"}), encoding="utf-8")

    def resolve(_session_id):
        return temp_dir, meta_file, json.loads(meta_file.read_text(encoding="utf-8"))

    monkeypatch.setattr(server, "_resolve_execution_description_review", resolve)
    monkeypatch.setattr(server, "_webui_auth_ok", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    headers = {"Origin": "http://localhost"}
    with server.app.test_client() as client:
        saved = client.put(
            "/api/execution_description",
            json={"session_id": "session", "content": "first edit", "version": 0},
            headers=headers,
        )
        stale_save = client.put(
            "/api/execution_description",
            json={"session_id": "session", "content": "stale edit", "version": 0},
            headers=headers,
        )
        stale_reset = client.post(
            "/api/execution_description/reset",
            json={"session_id": "session", "source_key": "description", "version": 0},
            headers=headers,
        )

    assert saved.status_code == 200
    assert stale_save.status_code == 409
    assert stale_reset.status_code == 409


def test_base_description_is_kept_in_meta_without_creating_description_file(tmp_path):
    async def run():
        meta = Meta({"base_dir": str(tmp_path), "uuid": "release", "description": "tracker text"})

        await gen_desc(meta, None, None)

        assert meta.description == "tracker text"
        assert not (tmp_path / "tmp" / "release" / "DESCRIPTION.txt").exists()

    asyncio.run(run())


def test_description_file_is_not_rendered_twice_when_both_sections_are_enabled(tmp_path):
    async def run():
        description_file = tmp_path / "description.txt"
        description_file.write_text("release notes", encoding="utf-8")
        meta = Meta({"base_dir": str(tmp_path), "uuid": "release", "description_file": str(description_file)})
        await gen_desc(meta, None, None)
        builder = DescriptionBuilder("TEST", {"DEFAULT": {}, "TRACKERS": {"TEST": {}}})

        result = await builder.general_description_generator(
            meta,
            audio_spectrogram=False,
            bluray=False,
            book=False,
            custom_header=False,
            custom_signature=False,
            game=False,
            logo=False,
            mediainfo=False,
            menu_screenshots=False,
            nfo=False,
            screenshots=False,
            tonemapped_header=False,
            tv_info=False,
            ua_signature=False,
        )

        assert result == "release notes"

    asyncio.run(run())


def test_unit3d_omits_scene_nfo_from_description_but_keeps_attachment(tmp_path):
    async def run():
        temp_dir = tmp_path / "tmp" / "release"
        temp_dir.mkdir(parents=True)
        nfo_content = "scene nfo content"
        (temp_dir / "release.nfo").write_text(nfo_content, encoding="utf-8")
        meta = Meta(
            {
                "base_dir": str(tmp_path),
                "uuid": "release",
                "auto_nfo": True,
                "nfo": True,
                "description_nfo_content": nfo_content,
                "description": f"[center][spoiler=Scene NFO:][code]{nfo_content}[/code][/spoiler][/center]\nRelease notes",
            }
        )
        config = {"DEFAULT": {}, "TRACKERS": {"UNIT3D": {}}}
        builder = DescriptionBuilder("UNIT3D", config)

        description = await builder.general_description_generator(
            meta,
            audio_spectrogram=False,
            bluray=False,
            book=False,
            custom_header=False,
            custom_signature=False,
            game=False,
            languages=False,
            logo=False,
            mediainfo=False,
            menu_screenshots=False,
            nfo=False,
            screenshots=False,
            tonemapped_header=False,
            tv_info=False,
            ua_signature=False,
            user_description=False,
            music=False,
            dynamic_hdr_plot=False,
        )
        files = await UNIT3D(config, "UNIT3D").get_additional_files(meta)

        assert description == "Release notes"
        assert files["nfo"] == ("nfo_file.nfo", nfo_content.encode(), "text/plain")

    asyncio.run(run())


def test_save_review_refuses_a_stale_version_and_keeps_the_draft(tmp_path):
    from src.description_review import ReviewConflictError, save_review

    save_review(tmp_path, "first edit", expected_version=0)

    with pytest.raises(ReviewConflictError) as conflict:
        save_review(tmp_path, "stale edit", expected_version=0)

    assert conflict.value.current_version == 1
    assert load_review(tmp_path) == {"content": "first edit", "version": 1}


def test_seed_review_never_overwrites_an_existing_draft(tmp_path):
    from src.description_review import save_review, seed_review

    assert seed_review(tmp_path, "tracker text") == {"content": "tracker text", "version": 1}
    save_review(tmp_path, "my edit", expected_version=1)

    assert seed_review(tmp_path, "tracker text again") is None
    assert load_review(tmp_path) == {"content": "my edit", "version": 2}


def test_discard_review_blocks_a_save_that_was_in_flight(tmp_path):
    from src.description_review import ReviewConflictError, apply_saved_draft, discard_review, draft, save_review, seed_review

    seed_review(tmp_path, "tracker text")
    panel_version = draft({}, tmp_path)[1]  # the panel loaded the draft before the user discarded it
    discard_review(tmp_path, expected_version=panel_version)

    with pytest.raises(ReviewConflictError):
        save_review(tmp_path, "edited after the fact", expected_version=panel_version)

    assert load_review(tmp_path) == {"content": None, "version": 2}
    assert draft({"description": "tracker text"}, tmp_path) == ("tracker text", 2)
    meta = Meta({"base_dir": str(tmp_path.parent), "uuid": tmp_path.name, "description": "my own text"})
    apply_saved_draft(meta)
    assert meta.description == "my own text"
    assert seed_review(tmp_path, "tracker text") is None  # a discard is not "missing"


def test_review_lock_is_held_across_processes(tmp_path):
    from src.description_review import review_lock, save_review

    holder = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-c",
            "import sys, time; from pathlib import Path; from src.description_review import review_lock\n"
            "with review_lock(Path(sys.argv[1])):\n"
            "    print('locked', flush=True)\n"
            "    time.sleep(5)",
            str(tmp_path),
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "locked"
        with pytest.raises(TimeoutError), review_lock(tmp_path, timeout=0.3):
            pass
    finally:
        holder.kill()
        holder.wait()

    assert save_review(tmp_path, "free again", expected_version=0) == {"content": "free again", "version": 1}

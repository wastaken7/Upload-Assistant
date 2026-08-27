# ruff: noqa: S101

import asyncio
import inspect
import json

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

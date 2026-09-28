# ruff: noqa: S101

import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src import configvalidator
from src.clients import Clients
from src.config_sync import sync_user_config
from src.configvalidator import DEFAULT_KEY_TYPES, validate_config
from src.meta import Meta


def test_find_existing_torrents_skips_unconfigured_client_after_config_sync(tmp_path: Path) -> None:
    config_path = tmp_path / "config.py"
    config_path.write_text("config = {'DEFAULT': {}}\n", encoding="utf-8")
    example_path = Path(__file__).parents[1] / "data" / "example_config.py"

    result = sync_user_config(config_path, example_path)
    config = ast.literal_eval(ast.parse(config_path.read_text(encoding="utf-8")).body[0].value)
    assert result.changed
    assert config["DEFAULT"]["default_torrent_client"] == "qbittorrent"
    assert "TORRENT_CLIENTS" not in config

    clients = Clients(config)
    meta = Meta(base_dir=str(tmp_path), uuid="no-client", client=None)
    with patch.object(clients, "_search_single_client_for_torrent", new_callable=AsyncMock) as search:
        assert asyncio.run(clients.find_existing_torrents(meta)) == []
        search.assert_not_awaited()
    assert meta.client is None


@pytest.mark.parametrize(
    "selected_client,defaults",
    [
        ("qbittorrent", {}),
        (None, {"default_torrent_client": "qbittorrent"}),
        (None, {"injecting_client_list": ["qbittorrent"]}),
    ],
)
@pytest.mark.parametrize("client_section", [{}, {"TORRENT_CLIENTS": {}}])
def test_add_to_client_skips_unconfigured_client(tmp_path: Path, selected_client, defaults, client_section) -> None:
    clients = Clients({"DEFAULT": defaults, "TRACKERS": {"TEST": {}}, **client_section})
    meta = Meta(base_dir=str(tmp_path), uuid="no-client", path=str(tmp_path / "video.mkv"), client=selected_client)
    torrent_path = tmp_path / "tmp" / meta.uuid / "[TEST].torrent"
    torrent_path.parent.mkdir(parents=True)
    torrent_path.touch()

    with (
        patch("src.clients.Torrent.read"),
        patch("src.clients.logger.info") as log,
        patch.object(clients, "remote_path_map", new_callable=AsyncMock) as path_map,
    ):
        asyncio.run(clients.add_to_client(meta, "TEST"))
        log.assert_called_once_with("[bold red]Torrent client 'qbittorrent' not found in config.")
        path_map.assert_not_awaited()


def test_empty_inject_delay_is_a_no_op() -> None:
    sleep_calls = 0

    async def fake_sleep(_: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1

    async def exercise() -> None:
        clients = Clients({"DEFAULT": {"inject_delay": 3}, "TRACKERS": {"TEST": {"inject_delay": ""}}})
        await clients.inject_delay(Meta(), "TEST", "qbit")

    with patch("src.clients.asyncio.sleep", new=fake_sleep):
        asyncio.run(exercise())

    assert sleep_calls == 0


@pytest.mark.parametrize("tracker_settings,expected", [({}, [3]), ({"inject_delay": None}, [3]), ({"inject_delay": 0}, []), ({"inject_delay": 2}, [2])])
def test_inject_delay_inherits_only_when_unset_or_none(tracker_settings, expected) -> None:
    sleep_calls = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    clients = Clients({"DEFAULT": {"inject_delay": 3}, "TRACKERS": {"TEST": tracker_settings}})
    with patch("src.clients.asyncio.sleep", new=fake_sleep):
        asyncio.run(clients.inject_delay(Meta(), "TEST", "qbit"))
    assert sleep_calls == expected


def test_config_validator_declares_image_upload_types() -> None:
    assert DEFAULT_KEY_TYPES["image_upload_concurrency"] == (str, int)
    assert DEFAULT_KEY_TYPES["image_upload_delay"] == (str, float, int)


def test_config_validator_warns_for_invalid_image_upload_limits() -> None:
    is_valid, errors, warnings = validate_config(
        {
            "DEFAULT": {
                "tmdb_api": "test-key",
                "image_upload_concurrency": "not-an-int",
                "image_upload_delay": "-0.5",
            },
            "TRACKERS": {},
        }
    )

    warning_keys = {warning.key for warning in warnings}
    assert is_valid
    assert not errors
    assert {"image_upload_concurrency", "image_upload_delay"} <= warning_keys


def test_config_validator_warns_for_nonfinite_image_upload_delay() -> None:
    _, _, warnings = validate_config(
        {
            "DEFAULT": {"tmdb_api": "test-key", "image_upload_delay": float("nan")},
            "TRACKERS": {},
        }
    )

    assert any(warning.key == "image_upload_delay" for warning in warnings)


def test_config_validator_warns_for_infinite_image_upload_concurrency() -> None:
    _, _, warnings = validate_config(
        {
            "DEFAULT": {"tmdb_api": "test-key", "image_upload_concurrency": float("inf")},
            "TRACKERS": {},
        }
    )

    assert any(warning.key == "image_upload_concurrency" and "Cannot parse" in warning.message for warning in warnings)


def test_config_validator_warns_for_unconfigured_hook_scripts(tmp_path, monkeypatch) -> None:
    hooks_dir = tmp_path / "custom_hooks"
    hooks_dir.mkdir()
    (hooks_dir / "active.py").write_text("", encoding="utf-8")
    (hooks_dir / "inactive.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(configvalidator, "HOOKS_DIR", hooks_dir)

    _, _, warnings = validate_config(
        {
            "DEFAULT": {"tmdb_api": "test-key", "post_upload_hooks": ["active.py"]},
            "TRACKERS": {},
        }
    )

    assert any(warning.key == "post_upload_hooks" and warning.message.endswith(": inactive.py") for warning in warnings)

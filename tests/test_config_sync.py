import ast
from pathlib import Path

import pytest

from src.config_sync import ConfigSyncError, sync_user_config


def _literal_config(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in tree.body
        if (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "config" for target in node.targets))
        or (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config")
    )
    return ast.literal_eval(assignment.value)


def test_sync_adds_missing_nested_values_and_preserves_user_content(tmp_path: Path) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    original = """from typing import Any

# Keep this user comment.
config: dict[str, Any] = {
    "DEFAULT": {
        "tmdb_api": "user-secret",
        "feature": False,
    },
    "TRACKERS": {
        "default_trackers": "FICTIONAL",
        "FICTIONAL": {"api_key": "tracker-secret"},
    },
    "CUSTOM": {"untouched": True},
}
"""
    config_path.write_text(original, encoding="utf-8")
    example_path.write_text(
        """config = {
    "DEFAULT": {
        "tmdb_api": "",
        "feature": True,
        "new_option": 4,
    },
    "TRACKERS": {
        "default_trackers": "",
        "FICTIONAL": {"api_key": "", "new_tracker_option": True},
        "IMAGINARY": {"api_key": ""},
    },
    "USENET": {"enabled": False},
}
""",
        encoding="utf-8",
    )

    result = sync_user_config(config_path, example_path)

    assert result.changed is True
    assert result.backup_path is not None
    assert result.backup_path.read_text(encoding="utf-8") == original
    assert result.added_paths == (
        "DEFAULT.new_option",
        "USENET",
    )
    updated = _literal_config(config_path)
    assert updated["DEFAULT"] == {"tmdb_api": "user-secret", "feature": False, "new_option": 4}
    assert updated["TRACKERS"] == {"default_trackers": "FICTIONAL", "FICTIONAL": {"api_key": "tracker-secret"}}
    assert updated["CUSTOM"] == {"untouched": True}
    assert "# Keep this user comment." in config_path.read_text(encoding="utf-8")


def test_sync_is_idempotent_and_does_not_create_another_backup(tmp_path: Path) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    config_path.write_text("config = {'DEFAULT': {'existing': 1}}\n", encoding="utf-8")
    example_path.write_text("config = {'DEFAULT': {'existing': 0, 'new': 2}}\n", encoding="utf-8")

    first = sync_user_config(config_path, example_path)
    after_first = config_path.read_bytes()
    second = sync_user_config(config_path, example_path)

    assert first.changed is True
    assert second.changed is False
    assert second.backup_path is None
    assert config_path.read_bytes() == after_first
    assert len(list(tmp_path.glob("config.py.backup-*"))) == 1


def test_sync_preserves_a_user_type_conflict_instead_of_replacing_it(tmp_path: Path) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    config_path.write_text("config = {'DEFAULT': 'managed elsewhere', 'CUSTOM': 1}\n", encoding="utf-8")
    example_path.write_text("config = {'DEFAULT': {'new': True}, 'USENET': {'enabled': False}}\n", encoding="utf-8")

    result = sync_user_config(config_path, example_path)

    assert result.added_paths == ("USENET",)
    assert _literal_config(config_path) == {"DEFAULT": "managed elsewhere", "CUSTOM": 1, "USENET": {"enabled": False}}


@pytest.mark.parametrize(
    "source",
    [
        "config = {'DEFAULT':\n",
        "import os\nconfig = {'DEFAULT': {'token': os.environ.get('TOKEN')}}\n",
    ],
)
def test_sync_leaves_unsupported_config_untouched(tmp_path: Path, source: str) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    config_path.write_text(source, encoding="utf-8")
    example_path.write_text("config = {'DEFAULT': {'new': True}}\n", encoding="utf-8")

    with pytest.raises(ConfigSyncError):
        sync_user_config(config_path, example_path)

    assert config_path.read_text(encoding="utf-8") == source
    assert list(tmp_path.glob("config.py.backup-*")) == []


def test_sync_handles_empty_commented_dict_and_missing_trailing_comma(tmp_path: Path) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    config_path.write_text(
        """config = {
    "DEFAULT": {
        # User placeholder.
    },
    "CUSTOM": 1
}
""",
        encoding="utf-8",
    )
    example_path.write_text("config = {'DEFAULT': {'new': True}, 'CUSTOM': 0, 'USENET': {}}\n", encoding="utf-8")

    sync_user_config(config_path, example_path)

    assert _literal_config(config_path) == {"DEFAULT": {"new": True}, "CUSTOM": 1, "USENET": {}}
    assert "# User placeholder." in config_path.read_text(encoding="utf-8")


def test_current_example_can_populate_a_minimal_existing_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.py"
    example_path = Path(__file__).parents[1] / "data" / "example_config.py"
    config_path.write_text(
        "config = {'DEFAULT': {'tmdb_api': 'fictional-key'}, 'TRACKERS': {'default_trackers': ''}}\n",
        encoding="utf-8",
    )

    first = sync_user_config(config_path, example_path)
    second = sync_user_config(config_path, example_path)

    updated = _literal_config(config_path)
    assert first.changed is True
    assert second.changed is False
    assert updated["DEFAULT"]["tmdb_api"] == "fictional-key"
    assert updated["TRACKERS"] == {"default_trackers": ""}
    assert "TORRENT_CLIENTS" not in updated
    assert "metadata_cache_services" not in updated["DEFAULT"]
    assert "tag_overrides" not in updated["DEFAULT"]
    assert updated["USENET"]["enabled"] is False


def test_failed_atomic_replace_keeps_original_and_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    original = "config = {'DEFAULT': {'existing': 1}}\n"
    config_path.write_text(original, encoding="utf-8")
    example_path.write_text("config = {'DEFAULT': {'existing': 0, 'new': 2}}\n", encoding="utf-8")

    def fail_replace(_self: Path, _target: Path) -> None:
        raise OSError("fictional replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(ConfigSyncError, match="fictional replace failure"):
        sync_user_config(config_path, example_path)

    assert config_path.read_text(encoding="utf-8") == original
    backups = list(tmp_path.glob("config.py.backup-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".config.py.*.tmp")) == []


@pytest.mark.parametrize("section", ["TRACKERS", "TORRENT_CLIENTS"])
@pytest.mark.parametrize("contents", [None, {}, {"FICTIONAL": {}}, {"FICTIONAL": {"screens_per_row": 2, "custom": False}}])
def test_sync_leaves_user_managed_sections_byte_for_byte_unchanged(tmp_path: Path, section: str, contents: dict | None) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    user = {"DEFAULT": {"screens_per_row": 5}}
    if contents is not None:
        user[section] = contents
    original = f"config = {user!r}\n"
    config_path.write_text(original, encoding="utf-8")
    example_path.write_text(
        f"config = {{'DEFAULT': {{'screens_per_row': 1}}, {section!r}: "
        "{'FICTIONAL': {'screens_per_row': 1, 'custom_signature': ''}, 'REMOVED': {'enabled': True}}}\n",
        encoding="utf-8",
    )

    result = sync_user_config(config_path, example_path)

    assert not result.changed
    assert result.backup_path is None
    assert config_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("config.py.backup-*")) == []


@pytest.mark.parametrize(
    "default",
    [
        None,
        {},
        {"metadata_cache_services": {}, "tag_overrides": {}},
        {
            "metadata_cache_default_ttl_hours": 24,
            "metadata_cache_services": {"tmdb": {"enabled": False}},
            "tag_overrides": {"CUSTOM": {"custom_signature": "My signature"}},
        },
    ],
)
def test_sync_preserves_optional_overrides_even_when_parent_is_missing(tmp_path: Path, default: dict | None) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    user = {} if default is None else {"DEFAULT": default}
    config_path.write_text(f"config = {user!r}\n", encoding="utf-8")
    example_path.write_text(
        "config = {'DEFAULT': {'new_option': True, "
        "'metadata_cache_services': {'tmdb': {'enabled': True, 'ttl_hours': 168}, 'audible': {'ttl_hours': 168}}, "
        "'tag_overrides': {'EXAMPLE': {'custom_signature': 'Example'}}}}\n",
        encoding="utf-8",
    )

    sync_user_config(config_path, example_path)

    assert _literal_config(config_path)["DEFAULT"] == {**(default or {}), "new_option": True}
    assert not sync_user_config(config_path, example_path).changed


@pytest.mark.parametrize("legacy_value", [False, True])
def test_sync_preserves_legacy_link_setting(tmp_path: Path, legacy_value: bool) -> None:
    from src.config_helpers import should_embed_links

    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    config_path.write_text(f"config = {{'DEFAULT': {{'embed_dupe_links': {legacy_value!r}}}}}\n", encoding="utf-8")
    example_path.write_text("config = {'DEFAULT': {'embed_links': True, 'new_option': 1}}\n", encoding="utf-8")

    result = sync_user_config(config_path, example_path)

    assert result.added_paths == ("DEFAULT.new_option",)
    assert should_embed_links(_literal_config(config_path)["DEFAULT"]) is legacy_value
    assert not sync_user_config(config_path, example_path).changed


@pytest.mark.parametrize("usenet", [{}, {"usenet_uploader": "pesto"}, {"pesto_obfuscation_mode": "article"}])
def test_sync_preserves_legacy_pesto_obfuscation(tmp_path: Path, usenet: dict) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    config_path.write_text(f"config = {{'USENET': {usenet!r}}}\n", encoding="utf-8")
    example_path.write_text("config = {'USENET': {'enabled': False, 'pesto_obfuscation_mode': 'light'}}\n", encoding="utf-8")

    result = sync_user_config(config_path, example_path)

    assert result.added_paths == ("USENET.enabled",)
    assert _literal_config(config_path)["USENET"] == {**usenet, "enabled": False}
    assert not sync_user_config(config_path, example_path).changed

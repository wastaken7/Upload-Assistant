from pathlib import Path

from src.args import configured_tracker_completions


def test_tracker_completions_include_defaults_credentials_and_cookie_files(tmp_path: Path) -> None:
    (tmp_path / "AVISTAZ.txt").write_text("cookie data", encoding="utf-8")
    config = {
        "TRACKERS": {
            "default_trackers": "AITHER",
            "AITHER": {"api_key": ""},
            "AVISTAZ": {"announce_url": ""},
            "BJSHARE": {"cookie_file": "custom-cookie.txt"},
            "BLUTOPIA": {"api_key": "configured-key"},
            "UNCONFIGURED": {"api_key": "  "},
        }
    }

    completions = configured_tracker_completions(config, cookies_dir=tmp_path)

    assert {"aither", "avistaz", "bjshare", "blutopia"} <= completions.keys()
    assert "unconfigured" not in completions


def test_tracker_completions_match_cookie_filenames_case_insensitively(tmp_path: Path) -> None:
    (tmp_path / "my_bJShare_cookies.json").write_text("{}", encoding="utf-8")
    config = {"TRACKERS": {"BJSHARE": {}}}

    completions = configured_tracker_completions(config, cookies_dir=tmp_path)

    assert "bjshare" in completions

"""Keep tests independent of the user's configuration and runtime data."""

import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "real_settings_reauth: do not stub the WebUI settings password confirmation")
    # Runtime paths are resolved at import time, so isolate them before collection.
    test_root = TemporaryDirectory(prefix="upload-assistant-pytest-")
    previous = {name: os.environ.get(name) for name in ("APPDATA", "XDG_CONFIG_HOME", "UA_DATA_DIR")}
    for name in previous:
        os.environ[name] = test_root.name

    def restore_paths() -> None:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        test_root.cleanup()

    config.add_cleanup(restore_paths)
    data_dir = Path(test_root.name) / "data"
    data_dir.mkdir()
    shutil.copyfile(Path(__file__).resolve().parent.parent / "data" / "example_config.py", data_dir / "config.py")


@pytest.fixture(autouse=True)
def _settings_reauth_confirmed(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Treat the WebUI password as recently confirmed, as most route tests stub auth.

    Tests of the confirmation itself use the ``real_settings_reauth`` marker.
    """
    if request.node.get_closest_marker("real_settings_reauth"):
        return
    import web_ui.security as webui_security

    monkeypatch.setattr(webui_security, "_settings_reauth_valid", lambda: True)

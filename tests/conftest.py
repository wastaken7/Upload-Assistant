"""Keep tests independent of the user's Web UI authentication state."""

import os
from tempfile import TemporaryDirectory

import pytest


def pytest_configure(config: pytest.Config) -> None:
    # Web UI paths are resolved when test modules import the server, so isolate
    # them before collection rather than in a test fixture.
    auth_root = TemporaryDirectory(prefix="upload-assistant-pytest-")
    previous = {name: os.environ.get(name) for name in ("APPDATA", "XDG_CONFIG_HOME")}
    for name in previous:
        os.environ[name] = auth_root.name

    def restore_auth_paths() -> None:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        auth_root.cleanup()

    config.add_cleanup(restore_auth_paths)

# ruff: noqa: S101
import importlib.metadata

import packaging.markers

from src import check_requirements


def test_check_dependencies_skips_requirement_with_nonmatching_marker(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (tmp_path / "requirements.txt").write_text('pywinpty==3.0.5 ; sys_platform == "win32"\n', encoding="utf-8")
    monkeypatch.setattr(check_requirements, "__file__", str(source_dir / "check_requirements.py"))

    environment = packaging.markers.default_environment()
    environment["sys_platform"] = "linux"
    monkeypatch.setattr(packaging.markers, "default_environment", lambda: environment)

    def missing_pywinpty(name):
        assert name == "pywinpty"
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(check_requirements.importlib.metadata, "version", missing_pywinpty)

    check_requirements.check_dependencies()

    assert capsys.readouterr().out == ""

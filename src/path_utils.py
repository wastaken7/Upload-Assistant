# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
import sys
from pathlib import Path


def get_resource_path(*parts: str) -> Path:
    """Get the absolute path to a resource, supporting both dev environment and PyInstaller bundles."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS).joinpath(*parts)
    else:
        project_root = Path(__file__).resolve().parent.parent
        return project_root.joinpath(*parts)

def get_bundled_binary_path(tool_name: str, folder_path: str, binary_name: str) -> str | None:
    """Get the path to a bundled binary if running in a frozen environment and the binary exists."""
    if getattr(sys, "frozen", False):
        bundle_binary_path = Path(sys._MEIPASS) / "bin" / tool_name / folder_path / binary_name
        if bundle_binary_path.exists():
            return str(bundle_binary_path)
    return None

def setup_frozen_environment() -> None:
    """Safely prepend frozen bundle paths to PATH env variable, avoiding KeyError."""
    if getattr(sys, "frozen", False):
        meipass = sys._MEIPASS
        bin_dir = os.path.join(meipass, "bin")
        current_path = os.environ.get("PATH", "")
        new_paths = [meipass, bin_dir]
        if current_path:
            new_paths.append(current_path)
        os.environ["PATH"] = os.path.pathsep.join(new_paths)

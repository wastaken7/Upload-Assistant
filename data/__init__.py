"""Compatibility package for user-owned runtime configuration."""

import shutil

from src.app_paths import CODE_DIR, CONFIG_PATH, DATA_DIR, ensure_data_dir

ensure_data_dir()
if not CONFIG_PATH.exists():
    shutil.copy2(CODE_DIR / "data" / "example_config.py", CONFIG_PATH)

# Resolve the user-owned config first; bundled static resources remain available
# from this package directory.
__path__.insert(0, str(DATA_DIR))

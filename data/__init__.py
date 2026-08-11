"""Compatibility package for user-owned runtime configuration."""

import shutil
import warnings

from src.app_paths import CODE_DIR, CONFIG_PATH, DATA_DIR, LEGACY_CONFIG_PATH, ensure_data_dir

ensure_data_dir()
if not CONFIG_PATH.exists():
    if LEGACY_CONFIG_PATH.is_file():
        shutil.copyfile(LEGACY_CONFIG_PATH, CONFIG_PATH)
        warnings.warn(f"Copied legacy configuration to {CONFIG_PATH}. The checkout copy is kept read-only.", stacklevel=2)
    else:
        shutil.copy2(CODE_DIR / "data" / "example_config.py", CONFIG_PATH)

# Resolve the user-owned config first; bundled static resources remain available
# from this package directory.
__path__.insert(0, str(DATA_DIR))

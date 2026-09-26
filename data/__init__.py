"""Compatibility package for user-owned runtime configuration."""

from src.app_paths import DATA_DIR

# Resolve an existing user-owned config first; bundled static resources remain
# available from this package directory.
__path__.insert(0, str(DATA_DIR))

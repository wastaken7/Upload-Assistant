"""Pinned versions and upstream repositories for managed binary dependencies."""

import platform

from bin.binary_dependency_pins import PINS

DEPENDENCY_VERSIONS = {dependency: pin.version for dependency, pin in PINS.items()}
DEPENDENCY_REPOSITORIES = {dependency: pin.repository for dependency, pin in PINS.items()}
DEPENDENCY_CHECKSUMS = {dependency: pin.checksums for dependency, pin in PINS.items()}


def static_release_system(system: str | None = None) -> str:
    """Return the release OS to use for statically linked Linux builds.

    Python 3.13+ reports Android (e.g. Termux) as "android". The go-bdinfo and
    mkbrr Linux builds are statically linked, so they run there unchanged.
    """
    system = (system if system is not None else platform.system()).lower()
    return "linux" if system == "android" else system

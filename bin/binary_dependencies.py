"""Pinned versions and upstream repositories for managed binary dependencies."""

from bin.binary_dependency_pins import PINS

DEPENDENCY_VERSIONS = {dependency: pin.version for dependency, pin in PINS.items()}
DEPENDENCY_REPOSITORIES = {dependency: pin.repository for dependency, pin in PINS.items()}
DEPENDENCY_CHECKSUMS = {dependency: pin.checksums for dependency, pin in PINS.items()}

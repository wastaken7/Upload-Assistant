"""Setuptools hooks for keeping runtime configuration out of distributions."""

from pathlib import Path
from typing import cast

from setuptools import setup  # pyright: ignore[reportMissingModuleSource]
from setuptools.command.build_py import build_py  # pyright: ignore[reportMissingModuleSource]


class SafeBuildPy(build_py):
    """Exclude the user-owned legacy configuration module from every build."""

    def find_package_modules(self, package: str, package_dir: str) -> list[tuple[str, str, str]]:
        modules: list[tuple[str, str, str]] = cast(list[tuple[str, str, str]], super().find_package_modules(package, package_dir))  # pyright: ignore[reportUnknownMemberType]
        return [module for module in modules if module[:2] != ("data", "config")]

    def run(self) -> None:
        super().run()
        # ``build_base`` is persistent, so an older build may already contain
        # this ignored file even after module discovery starts excluding it.
        (Path(self.build_lib) / "data" / "config.py").unlink(missing_ok=True)


setup(cmdclass={"build_py": SafeBuildPy})

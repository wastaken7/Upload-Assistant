"""Setuptools hooks for keeping runtime configuration out of distributions."""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class SafeBuildPy(build_py):
    """Exclude the user-owned legacy configuration module from every build."""

    def find_package_modules(self, package: str, package_dir: str) -> list[tuple[str, str, str]]:
        modules = super().find_package_modules(package, package_dir)
        return [module for module in modules if module[:2] != ("data", "config")]

    def run(self) -> None:
        super().run()
        # ``build_base`` is persistent, so an older build may already contain
        # this ignored file even after module discovery starts excluding it.
        (Path(self.build_lib) / "data" / "config.py").unlink(missing_ok=True)


setup(cmdclass={"build_py": SafeBuildPy})

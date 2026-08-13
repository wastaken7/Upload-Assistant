# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import importlib.metadata
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def check_dependencies() -> None:
    """
    Checks if the Python version is correct and if the dependencies listed in requirements.txt are installed.
    If the Python version is unsupported or packages are missing, it outputs a clear warning and exits.
    If versions mismatch, it prints a warning but allows execution to continue.
    """
    # Verify Python version
    required_version = (3, 14)
    if sys.version_info < required_version:
        print("\n\033[1;31mUNSUPPORTED PYTHON VERSION\033[0m")
        print(f"Error: Upload Assistant requires Python {required_version[0]}.{required_version[1]} or higher.")
        print(f"Your current version: {sys.version.split()[0]} ({sys.executable})")
        print("Please upgrade your Python interpreter or activate the correct virtual environment.\n")
        sys.exit(1)

    # Find requirements.txt in the project root relative to this file
    requirements_file = Path(__file__).resolve().parent.parent / "requirements.txt"
    if not requirements_file.exists():
        return

    missing_packages: list[str] = []
    mismatched_versions: list[str] = []

    # Try importing packaging to use robust specifier matching
    try:
        import packaging.requirements

        has_packaging = True
    except ImportError:
        has_packaging = False
        # If packaging is missing, we list it as missing since it's in requirements.txt
        missing_packages.append("  - packaging: not installed (required by Upload Assistant)")

    try:
        with Path(requirements_file).open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Ignore empty lines, comments or pip flags
                if not line or line.startswith("#") or line.startswith("-"):
                    continue

                # Simple check if packaging is not available
                if not has_packaging:
                    parts = line.split("==")
                    req_name = parts[0].strip()
                    req_version = parts[1].strip() if len(parts) > 1 else None

                    # Normalization
                    norm_name = req_name.lower().replace("_", "-").replace(".", "-")
                    if norm_name == "packaging":
                        continue  # Already handled

                    try:
                        installed_version = importlib.metadata.version(req_name)
                        if req_version and installed_version != req_version:
                            mismatched_versions.append(f"  - {req_name}: installed {installed_version}, required {req_version}")
                    except importlib.metadata.PackageNotFoundError:
                        missing_packages.append(f"  - {req_name}: not installed (required: {line})")
                    continue

                # If packaging is available, use it for parsing
                try:
                    if has_packaging:
                        req = packaging.requirements.Requirement(line)
                        if req.marker is not None and not req.marker.evaluate():
                            continue
                        try:
                            installed_version = importlib.metadata.version(req.name)
                            if not req.specifier.contains(installed_version, prereleases=True):
                                mismatched_versions.append(f"  - {req.name}: installed {installed_version}, required {req.specifier}")
                        except importlib.metadata.PackageNotFoundError:
                            missing_packages.append(f"  - {req.name}: not installed (required: {line})")
                except Exception as exc:
                    # Ignore lines with parsing errors (e.g. custom URLs, local paths)
                    logger.debug(f"Failed to parse requirement line '{line}': {exc}", exc_info=True)
                    continue
    except Exception as e:
        # Prevent check failure from crashing the entire app if requirements.txt cannot be read
        print(f"\033[1;33mError checking requirements: {e}\033[0m")
        return

    if missing_packages or mismatched_versions:
        print("\n\033[1;33mPYTHON DEPENDENCY WARNING\033[0m")
        print("Differences detected compared to your requirements.txt file:\n")

        if missing_packages:
            print("\033[1;31mMissing Packages:\033[0m")
            for pkg in missing_packages:
                print(pkg)
            print()

        if mismatched_versions:
            print("\033[1;33mMismatched/Outdated Versions:\033[0m")
            for pkg in mismatched_versions:
                print(pkg)
            print()

        print("\033[1;32m To fix and update all modules, run this command in your terminal:\033[0m")
        print("   \033[1;36mpip install -r requirements.txt\033[0m")
        print()

        # If there are missing packages, we MUST exit because execution will fail anyway
        if missing_packages:
            print("\n\033[1;31mError: Execution halted due to missing packages.\033[0m\n")
            sys.exit(1)

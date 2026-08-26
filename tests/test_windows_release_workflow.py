from pathlib import Path

ROOT = Path(__file__).parents[1]
CREATE_RELEASE = (ROOT / ".github" / "workflows" / "create-release.yml").read_text(encoding="utf-8")
WINDOWS_INSTALLER = (ROOT / ".github" / "workflows" / "windows-installer.yml").read_text(encoding="utf-8")


def test_windows_installer_runs_only_as_a_reusable_release_build():
    for forbidden_trigger in ("pull_request:", "release:", "workflow_dispatch:"):
        if forbidden_trigger in WINDOWS_INSTALLER:
            raise AssertionError(f"The Windows installer must not run on {forbidden_trigger}")
    if "workflow_call:" not in WINDOWS_INSTALLER:
        raise AssertionError("The Windows installer must run only as a reusable workflow")


def test_release_publication_waits_for_the_windows_installer():
    for expected_text in (
        "uses: ./.github/workflows/windows-installer.yml",
        "needs: [prepare-release, build-windows-installer, build-python-distribution]",
        "ref: ${{ needs.prepare-release.outputs.release_sha }}",
        "GH_REPO: ${{ github.repository }}",
        '--target "$RELEASE_SHA"',
        "Download Windows installer",
        '"$RUNNER_TEMP/windows-installer"/*.exe',
    ):
        if expected_text not in CREATE_RELEASE:
            raise AssertionError(f"The release workflow is missing: {expected_text}")


def test_release_builds_and_publishes_python_distributions_with_oidc():
    for expected_text in (
        "build-python-distribution:",
        "run: uv build",
        "run: uvx twine check dist/*",
        'name.endswith(("/data/config.py", "/requirements.txt"))',
        "name: python-distributions-${{ inputs.version }}",
        "publish-pypi:",
        "name: pypi",
        "id-token: write",
        "uses: pypa/gh-action-pypi-publish@release/v1",
    ):
        if expected_text not in CREATE_RELEASE:
            raise AssertionError(f"The PyPI release workflow is missing: {expected_text}")

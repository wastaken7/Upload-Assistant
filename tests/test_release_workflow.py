from pathlib import Path

ROOT = Path(__file__).parents[1]
CREATE_RELEASE = (ROOT / ".github" / "workflows" / "create-release.yml").read_text(encoding="utf-8")


def test_release_publication_waits_for_python_distributions():
    for expected_text in (
        "needs: [prepare-release, build-python-distribution]",
        "GH_REPO: ${{ github.repository }}",
        '--target "$RELEASE_SHA"',
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

# Publishing to PyPI

Upload Assistant publishes its wheel and source distribution from the existing **Create release** GitHub Actions workflow. The workflow builds and validates both artifacts before creating the GitHub release, then authenticates to PyPI with OpenID Connect. No long-lived PyPI API token is stored in GitHub.

## One-time PyPI setup

Before the first release, create a pending trusted publisher at <https://pypi.org/manage/account/publishing/> with these values:

- PyPI project name: `upload-assistant`
- GitHub owner: `wastaken7`
- GitHub repository: `Upload-Assistant`
- Workflow name: `create-release.yml`
- Environment name: `pypi`

The project name was available when PyPI readiness was implemented, but availability is only guaranteed once the first distribution is published.

Create a protected GitHub environment named `pypi` as well. Requiring an environment reviewer is recommended because PyPI versions cannot be replaced or reused after publication.

## Release

Run the **Create release** workflow from the branch and supply a new version such as `v3.9`. The workflow updates both version declarations, builds the Windows installer and Python distributions, creates the GitHub release, and publishes the same version to PyPI.

To validate artifacts locally without publishing:

```bash
uv build
uvx twine check dist/*
```

Publishing is intentionally performed only by the release workflow. A failed job can be retried; already-uploaded files are skipped to make partial retries safe.

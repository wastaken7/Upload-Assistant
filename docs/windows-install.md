# Windows Install

This guide is for Windows users who want Upload Assistant to use its own Python runtime without changing the Python versions they already keep on `PATH`.

## Installer `.exe` (recommended)

Every published GitHub release includes `Upload-Assistant-Setup-<version>-x64.exe`. Download that file from the release page and run it: the setup wizard installs Upload Assistant, its isolated Python runtime, and FFmpeg without requiring Git, Python, or PowerShell commands from the user.

The wizard offers optional Discord support and can open `ua-config` when it finishes. It embeds the Python wheels from both requirement files, so the initial installation does not need an internet connection. Updates with `ua-update` still download a newer release. Run `ua-config` before the first upload.

The installer is per-user and installs by default under `%LOCALAPPDATA%\Programs\Upload Assistant`. It adds the `ua`, `ua-config`, and `ua-update` launchers to the user `PATH`; open a new terminal after setup before using those commands there.

## What this installer does

The bundled PowerShell installer:

1. Downloads and extracts the Upload Assistant ZIP from GitHub.
2. Downloads and installs an isolated Python `3.14` copy from `python.org` into a dedicated Upload Assistant directory.
3. Does **not** add that Python to the global `PATH`.
4. Optionally downloads and installs FFmpeg into a dedicated Upload Assistant directory.
5. Replaces any existing Upload Assistant files in the installation directory.
6. Creates `.venv`.
7. Installs the base dependencies from `requirements.txt`.
8. Optionally installs Discord support from `requirements-discord.txt`.
9. Creates `run-ua.ps1` for easier execution.
10. Creates global `ua.cmd`, `ua-update.cmd`, and `ua-config.cmd` launchers and adds only that launcher directory to the user `PATH`.

## One-command installation

For a default installation managed in `~/tools/ua`, run this single command in PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command '$p = Join-Path $env:TEMP "ua-install.ps1"; try { Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/wastaken7/Upload-Assistant/development/scripts/install-windows.ps1" -OutFile $p; & $p; exit $LASTEXITCODE } finally { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }'
```

The command downloads the installer temporarily, runs it, and removes the temporary file afterward. It does not change the user's permanent execution policy.

## Quick start

The installer does not require Git, Python, `winget`, or any existing tool on `PATH`. The command above is the complete first-time installation.

To use a different installation directory, download the script and pass `-UaDir` to it. For example:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -UaDir "C:\Apps\Upload-Assistant"
```

Every run downloads a fresh ZIP and replaces the files in that directory.

With optional Discord support:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -WithDiscord
```

## Options

```text
-UaDir PATH             Installation directory (default: ~/tools/ua)
-PythonVersion VERSION  Python minor version to enforce in .venv (default: 3.14)
-PythonInstallDir PATH  Dedicated Python install directory
-FfmpegInstallDir PATH  Dedicated FFmpeg install directory
-PythonDownloadBaseUrl  Base URL for Python downloads (default: python.org FTP)
-RepositoryZipUrl URL   Upload Assistant ZIP URL (default: development branch)
-FfmpegDownloadUrl URL  FFmpeg archive URL (default: gyan.dev essentials ZIP)
-WithDiscord            Install optional Discord dependencies
-ForceUpdate            Replace a mismatched managed Python and recreate the environment
-SkipFfmpegInstall      Skip FFmpeg bootstrap
```

## Notes

- The script keeps Upload Assistant on its own Python runtime and calls that interpreter directly.
- It does not depend on `python.exe` from your existing `PATH`.
- It downloads the Upload Assistant ZIP from GitHub, Python from `python.org`, and FFmpeg from the configured archive URL.
- It adds a dedicated Upload Assistant launcher directory to the user `PATH`, not the isolated Python itself.
- The global `ua`, `ua-update`, and `ua-config` commands use `.cmd` launchers. `ua` and `ua-update` invoke PowerShell with `ExecutionPolicy Bypass`; `ua-config` runs the configuration generator with the isolated Python environment.
- If the script installs FFmpeg itself, it also adds the managed FFmpeg `bin` directory to the user `PATH`.
- On Windows, Upload Assistant already ships with `bin/MI/windows/MediaInfo.exe`, so this installer does not require a separate MediaInfo package to finish setup.

## First configuration

Before the first upload, create or update the configuration with the isolated environment:

```powershell
ua-config
```

## Running Upload Assistant

After configuring Upload Assistant:

```powershell
ua "C:\path\to\content" --trackers yourtracker
```

If `ua` is not recognized yet, close and reopen the terminal once so Windows reloads the updated user `PATH`.

If you prefer the checkout-local runner:

```powershell
cd C:\path\to\your\ua\checkout
powershell -ExecutionPolicy Bypass -File .\run-ua.ps1 "C:\path\to\content" --trackers yourtracker
```

If you prefer the raw environment:

```powershell
cd C:\path\to\your\ua\checkout
.\.venv\Scripts\python.exe .\upload.py "C:\path\to\content" --trackers yourtracker
```

## Updating

You can update from any folder with:

```powershell
ua-update
```

That command downloads a fresh ZIP, replaces the installed files, and refreshes `.venv`, dependencies, and the global launchers. Local changes inside the installation directory are intentionally overwritten.

If you need a full refresh of the isolated environment:

```powershell
ua-update -ForceUpdate
```

If you prefer the repo-local script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update-windows.ps1 -UaDir $PWD
```

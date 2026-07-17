# Windows Install

This guide is for Windows users who want Upload Assistant to use its own Python runtime without changing the Python versions they already keep on `PATH`.

## What this installer does

The bundled PowerShell installer:

1. Installs Git with `winget` if needed.
2. Installs an isolated Python `3.14` copy with `winget` into a dedicated Upload Assistant directory.
3. Does **not** add that Python to the global `PATH`.
4. Optionally installs FFmpeg with `winget`.
5. Clones or updates Upload Assistant.
6. Creates `.venv`.
7. Installs the base dependencies from `requirements.txt`.
8. Optionally installs Discord support from `requirements-discord.txt`.
9. Creates `run-ua.ps1` for easier execution.
10. Creates global `ua` and `ua-update` launchers and adds only that launcher directory to the user `PATH`.

## Bootstrap from a GitHub URL

This is the recommended first-time setup on Windows because it works even before Git is installed and does not depend on any existing Python already on `PATH`.

Copy and paste this into PowerShell:

```powershell
$repoUrl = "https://github.com/wastaken7/Upload-Assistant"
$zipUrl = "$repoUrl/archive/refs/heads/development.zip"
$targetRoot = Join-Path $HOME "Upload-Assistant-bootstrap"
$zipPath = Join-Path $targetRoot "Upload-Assistant.zip"

New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
Expand-Archive -LiteralPath $zipPath -DestinationPath $targetRoot -Force

$repoDir = Get-ChildItem -Path $targetRoot -Directory | Where-Object { $_.Name -like "Upload-Assistant-*" } | Select-Object -First 1 -ExpandProperty FullName
Set-Location $repoDir
.\scripts\install-windows.ps1
```

This flow downloads the repository ZIP first, extracts it, and runs the installer from those extracted files, but lets the installer clone the managed Git checkout into its default location (`~/tools/ua`). That keeps `ua-update` working later.

## Quick start

If you already have a repo checkout, open PowerShell and run:

```powershell
git clone https://github.com/wastaken7/Upload-Assistant.git
cd Upload-Assistant
.\scripts\install-windows.ps1 -UaDir $PWD
```

If you want the installer to manage a separate checkout in `~/tools/ua`, omit `-UaDir $PWD`.

If Git is not installed yet, use a ZIP checkout first:

1. Download the repository ZIP from GitHub.
2. Extract it somewhere under your user profile.
3. Open PowerShell in the extracted `Upload-Assistant` folder.
4. Run:

```powershell
.\scripts\install-windows.ps1
```

That first run can install Git and then clone a proper checkout for future `ua-update` runs. Pass `-UaDir $PWD` only if you intentionally want to keep using the extracted ZIP directory itself, which is not an updatable Git checkout.

With optional Discord support:

```powershell
.\scripts\install-windows.ps1 -WithDiscord
```

## Options

```text
-UaDir PATH             Installation directory (default: ~/tools/ua)
-PythonVersion VERSION  Python minor version to enforce in .venv (default: 3.14)
-PythonPackageId ID     winget package id for Python (default: Python.Python.3.14)
-PythonInstallDir PATH  Dedicated Python install directory
-FfmpegPackageId ID     winget package id for FFmpeg (default: Gyan.FFmpeg)
-WithDiscord            Install optional Discord dependencies
-ForceUpdate            Recreate .venv and reinstall packages
-SkipFfmpegInstall      Skip FFmpeg bootstrap
```

## Notes

- The script keeps Upload Assistant on its own Python runtime and calls that interpreter directly.
- It does not depend on `python.exe` from your existing `PATH`.
- It adds a dedicated Upload Assistant launcher directory to the user `PATH`, not the isolated Python itself.
- On Windows, Upload Assistant already ships with `bin/MI/windows/MediaInfo.exe`, so this installer does not require a separate MediaInfo package to finish setup.

## Running Upload Assistant

After installation:

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

If your install came from a Git checkout, you can update from any folder with:

```powershell
ua-update
```

That command:

1. Verifies the checkout is a Git repo.
2. Runs the normal Windows installer against the same checkout.
3. Pulls the latest changes with `git pull --ff-only`.
4. Refreshes `.venv`, dependencies, and the global launchers.
5. Keeps optional Discord dependencies if they were already installed.

If you need a full refresh of the isolated environment:

```powershell
ua-update -ForceUpdate
```

If you prefer the repo-local script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update-windows.ps1 -UaDir $PWD
```

If you installed from a ZIP instead of a Git checkout, `ua-update` will stop with a message explaining that ZIP installs cannot use `git pull`. In that case, download a fresh ZIP and rerun the installer.

Manual Git-based update is still available:

```powershell
cd C:\path\to\your\ua\checkout
git pull --ff-only
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -UaDir $PWD
```

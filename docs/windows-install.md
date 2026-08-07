# Windows Installation

## Install with the `.exe`

1. Download `Upload-Assistant-Setup-<version>-x64.exe` from the [latest GitHub release](https://github.com/wastaken7/Upload-Assistant/releases).
2. Run the installer and follow the setup wizard.
3. Open a new PowerShell or Command Prompt window after the installation.

The installer includes the Python runtime, dependencies, FFmpeg, and MediaInfo needed by Upload Assistant. Windows users do not need to install Python, Git, or FFmpeg separately.

## Create the configuration

The first Upload Assistant launch creates `data/config.py` from the bundled example automatically. Start the Web UI and use its configuration editor to add API keys, tracker credentials, and torrent clients before your first upload.

## Basic commands

Upload a file or folder:

```powershell
ua "C:\path\to\content" --trackers YOURTRACKER
```

Show all available options:

```powershell
ua --help
```

Update the installed version:

```powershell
ua-update
```

If Windows does not recognize `ua`, close and reopen the terminal so it reloads the updated `PATH`.

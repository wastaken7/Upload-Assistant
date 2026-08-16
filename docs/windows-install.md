# Windows Installation

## Install with the `.exe`

1. Download `Upload-Assistant-Setup-<version>-x64.exe` from the [latest GitHub release](https://github.com/wastaken7/Upload-Assistant/releases).
2. Run the installer and follow the setup wizard.
3. Open a new PowerShell or Command Prompt window after the installation.

The installer automatically sets up the Python runtime and dependencies. On the first upload that needs it, Upload Assistant uses an FFmpeg already on your PATH or downloads its verified FFmpeg runtime into its user data `bin` directory. Windows users do not need to install Python, Git, or FFmpeg separately.

## Create the configuration

The configuration must be created after installing Upload Assistant. In a new terminal, run:

```powershell
ua-config
```

Follow the prompts to add your API keys and tracker credentials. Complete this step before the first upload.

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

If Windows does not recognize `ua` or `ua-config`, close and reopen the terminal so it reloads the updated `PATH`.

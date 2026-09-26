# Windows Installation

## Install with `uv`

1. Install Python 3.14 or newer and [`uv`](https://docs.astral.sh/uv/getting-started/installation/).
2. In PowerShell or Command Prompt, install Upload Assistant:

   ```powershell
   uv tool install upload-assistant
   ```

3. If `uv` reports that its tool directory is not on your `PATH`, run `uv tool update-shell` and open a new terminal.

Upload Assistant uses an FFmpeg already on your PATH or downloads its verified FFmpeg runtime into its user data `bin` directory when needed.

## Create the configuration

Start the Web UI with `ua --webui`. It creates the configuration on first launch; use the configuration page to add your API keys and tracker credentials before the first upload. Alternatively, the first CLI upload command creates the same file and stops so you can edit it before retrying.

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
uv tool upgrade upload-assistant
```

If Windows does not recognize `ua`, run `uv tool update-shell` and open a new terminal.

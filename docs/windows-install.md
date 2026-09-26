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
uv tool upgrade upload-assistant
```

If Windows does not recognize `ua` or `ua-config`, run `uv tool update-shell` and open a new terminal.

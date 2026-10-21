<div align="center">
  <img src="docs/assets/logo.svg" alt="Upload Assistant Logo" width="120" height="120" />
  <h1>Upload-Assistant</h1>
  <p>Prepare media and upload it to supported private trackers and Usenet indexers.</p>

[![Python Version](https://img.shields.io/badge/Python-3.14%2B-blue?logo=python&logoColor=white)](https://www.python.org/) [![License](https://img.shields.io/badge/License-UAPL%20v1.0-orange)](LICENSE) [![Ruff](https://img.shields.io/badge/Ruff-000000?logo=ruff&logoColor=white)](https://github.com/astral-sh/ruff) [![Pyright](https://img.shields.io/badge/Pyright-strict-brightgreen)](https://github.com/microsoft/pyright) [![code style: prettier](https://img.shields.io/badge/code%20style-prettier-ff69b4.svg)](https://prettier.io) [![Docker Image CI](https://github.com/wastaken7/Upload-Assistant/actions/workflows/docker-image.yml/badge.svg)](https://github.com/wastaken7/Upload-Assistant/actions/workflows/docker-image.yml)
</div>

Upload Assistant collects metadata, generates screenshots and artwork, creates torrent or NZB files, and publishes releases to the destinations you choose. Use it through a browser interface (WebUI) or the command line (CLI).

<img width="3840" height="2160" alt="1" src="https://github.com/user-attachments/assets/b375a324-2925-4e70-90e6-136881099b3e" />

---

<img width="5760" height="3240" alt="2" src="https://github.com/user-attachments/assets/613b35a6-1523-431a-8a55-3884f5db48d4" />

---

<img width="5739" height="4143" alt="3" src="https://github.com/user-attachments/assets/9164de0f-7901-4a1b-a567-10f97f3cf33b" />

---

**New here? Follow [Start here](#start-here) to install the app, configure one destination, and make your first upload through the WebUI.**

> [!IMPORTANT]
> This is a modified version of Upload Assistant and is not affiliated with or endorsed by Audionut.

## Contents

- [Before you start](#before-you-start)
- [Start here](#start-here)
- [Your first upload](#your-first-upload)
- [Troubleshooting](#troubleshooting)
- [Updating](#updating)
- [Command-line usage](#command-line-usage)
- [Configuration file location](#configuration-file-location)
- [Other installation options](#other-installation-options)
- [Guides and advanced workflows](#guides-and-advanced-workflows)
- [Supported sites](#supported-sites)
- [Fork features and differences from upstream](#fork-features--differences-from-upstream-audionutupload-assistant)
- [Help](#help)
- [Attributions](#attributions)
- [Contributors](#contributors)

## Before you start

For your first torrent upload, have these ready:

- **A file or folder to upload.** Start with one item whose category is supported by your chosen tracker.
- **An account with upload permission on that tracker.** Upload Assistant does not create tracker accounts or grant upload permission. Check the site's upload rules first.
- **The tracker's credentials.** Depending on the site, this may be an API key, login details, or a personal announce URL. An API key lets the app use your account; an announce URL tells your torrent client how to connect to the tracker.
- **The metadata and image services required for your content.** Metadata means information such as title, year, author, or artist. An image host stores screenshots and artwork used in the release description.
- **A plan for seeding.** A torrent client such as qBittorrent shares the uploaded content. Configure automatic client integration or add the torrent yourself after uploading.

You only need to configure the services you will use. Usenet users should follow the [Usenet guide](docs/usenet.md) for posting-server and indexer requirements.

## Start here

This walkthrough installs the published release and runs the WebUI on your own computer. For Docker, Unraid, or a seedbox, use [Other installation options](#other-installation-options).

### 1. Install uv

`uv` installs Upload Assistant and manages its Python environment.

Choose your operating system below. Run commands in a terminal, one block at a time.

<details open>
<summary><strong>Windows — PowerShell</strong></summary>

Open the Start menu, search for **PowerShell**, and open it. Install `uv` with:

```powershell
winget install --id=astral-sh.uv -e
```

If `winget` is unavailable, use an alternative from the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

Close PowerShell and open a new window after installation.

</details>

<details>
<summary><strong>Linux — Terminal</strong></summary>

Open a terminal and install `uv` using the [official installer](https://docs.astral.sh/uv/getting-started/installation/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close the terminal and open a new window after installation.

</details>

<details>
<summary><strong>macOS — Terminal</strong></summary>

Open **Terminal** and install `uv` using the [official installer](https://docs.astral.sh/uv/getting-started/installation/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close Terminal and open a new window after installation.

</details>

**Check:** Run `uv --version`. You should see a version number. If the command is not recognized, revisit the installer instructions before continuing.

### 2. Install Upload Assistant

In your new terminal window, run:

```text
uv tool install upload-assistant
```

`uv` creates an isolated environment and installs a compatible Python version (3.14 or newer) if needed. The installed app is called `ua`, and you can run it from any directory.

**Windows:** The app uses FFmpeg already on your PATH or downloads a verified FFmpeg runtime when needed. FFmpeg is the program used to process video and capture screenshots.

**Linux / macOS:** Install FFmpeg with your system's package manager. Choose only the command for your system:

| System              | Command                   |
| ------------------- | ------------------------- |
| Debian / Ubuntu     | `sudo apt install ffmpeg` |
| Arch Linux          | `sudo pacman -S ffmpeg`   |
| Fedora              | `sudo dnf install ffmpeg` |
| macOS with Homebrew | `brew install ffmpeg`     |

On macOS, if you do not have Homebrew, follow the [FFmpeg download options](https://ffmpeg.org/download.html) or install [Homebrew](https://brew.sh/) first.

**Check:** Run:

```text
ua --help
```

You should see the available commands and options. If `ua` is not recognized, run `uv tool update-shell`, close the terminal, and open it again.

### 3. Open the WebUI

Start the app with the folder that contains your media. **Replace the example path with an existing folder on your computer.** Keep the double quotes, especially if the path contains spaces.

**Windows — PowerShell:**

```powershell
ua "D:\MyMovies,G:\" --webui
```

You can specify multiple browse roots by separating them with commas. In this example, the WebUI can browse `D:\MyMovies` and the entire `G:\` drive, subject to your operating system's file permissions. The File Browser omits hidden and system items. To limit browsing to your media, replace `G:\` with a specific folder such as `G:\Media`.

**Linux / macOS — Terminal:**

```bash
ua "/path/to/media" --webui
```

Open **<http://127.0.0.1:5000>** in a browser on the same computer. On your first visit, enter the setup code printed in the terminal, then create a username and password for the WebUI's local account. This account is separate from your tracker accounts.

**Check:** You should see the Upload workspace and be able to browse the folder you supplied.

Keep the terminal open while using the WebUI. To stop the app when finished, press **Ctrl+C** in that terminal. Start it with the same command next time.

The folder you supply controls what the WebUI can browse. If you already set `UA_BROWSE_ROOTS`, that setting overrides command-line folders. See the [browse roots guide](docs/web-ui.md#browse-roots).

> Running the app on another machine? Paths refer to files on that machine, and `127.0.0.1` refers to the device where you open the browser. Follow the [remote-access guidance](docs/web-ui.md#security-and-administration) before changing the listening address. Docker paths are explained in the [Docker WebUI guide](docs/docker-gui.md).

### 4. Configure one destination

The app creates its configuration file on first WebUI launch. Open **Configuration** and set up the services for your first upload:

| Section           | What to enter                                                                                                                                                                                            |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Metadata services | Add a TMDb API key from [TMDb API settings](https://www.themoviedb.org/settings/api); the app currently requires it before running uploads. Configure any additional providers needed for your category. |
| Image hosts       | Choose a host accepted by your tracker and supply its API key if required. This is where screenshots and artwork are uploaded.                                                                           |
| Trackers          | Configure one supported tracker with the credentials it requires. Check the [supported sites table](#supported-sites) for category support and its CLI identifier.                                       |
| Torrent clients   | Configure your client connection and select it as the default if you want torrents added automatically. The client must be able to access the content being uploaded.                                    |

**Review Pending changes and click Save Config.** Leaving the page does not save staged edits.

**Check:** Confirm the changes were saved before returning to Upload. For field-by-field explanations, use the [configuration reference](docs/example-config.md). Keep API keys, passwords, and personal announce URLs private.

## Your first upload

1. Open **Upload** and select **one file or folder** in **File Browser**.
2. Select **one configured tracker** for this run.
3. Leave optional arguments at their defaults unless your content or tracker requires an override.
4. Click **Execute Upload**. This starts the upload workflow and can publish to the selected destination.
5. Read the live output and answer prompts at the bottom of the output panel. Review the metadata and, when offered, **Screenshots** and **Description** before continuing.
6. Check the final result for your destination. If the app reports a duplicate or an error, read that message before retrying.
7. Open the destination site and confirm the release or draft exists. If you configured client integration, check that the torrent is in your client and seeding. Otherwise, add the torrent yourself and verify the client finds the existing data.

**A finished process alone does not confirm a successful upload.** Check the destination's result and the seeding status. Some trackers create a draft that still needs to be published on the site.

Once this works, add more trackers, explore arguments, or set up queues. The [WebUI quick start](docs/web-ui-basic.md) and [full WebUI guide](docs/web-ui.md) cover the rest of the interface.

## Troubleshooting

| Problem                                     | What to check first                                                                                                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `uv` is not recognized                      | Close and reopen the terminal after installing it. If it still fails, follow the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).                               |
| `ua` is not recognized                      | Run `uv tool update-shell`, then close and reopen the terminal.                                                                                                                                  |
| The browser cannot open the WebUI           | Keep the terminal running and look for startup errors. Use `http://127.0.0.1:5000` on the computer running the app, or the address you explicitly configured.                                    |
| The port is already in use                  | Stop the other instance or use `ua "YOUR_MEDIA_FOLDER" --webui 127.0.0.1:5001`, then open `http://127.0.0.1:5001`. Replace the folder placeholder first.                                         |
| The File Browser cannot see my folder       | Restart with the correct folder path. Check whether `UA_BROWSE_ROOTS` overrides it. For Docker, check container paths and volume mappings.                                                       |
| Configuration changes disappeared           | Review **Pending changes** and click **Save Config** before leaving the page.                                                                                                                    |
| A tracker rejects authentication            | Check its configured credentials and your account's upload permission. A reachability/status check does not validate credentials.                                                                |
| Screenshots or image uploads fail           | Check FFmpeg, the chosen image host, its credentials, and whether the tracker accepts that host. See [FFmpeg troubleshooting](docs/ffmpeg-max-workers-issues.md).                                |
| The torrent was uploaded but is not seeding | Check the client connection, default client, and content paths. Remote clients may require local/remote path mapping. See [torrent client configuration](docs/configuration.md#torrent-clients). |

Still stuck? See [Help](#help) and include the relevant error message.

## Updating

For the published release installed above, stop the app and run:

```text
uv tool upgrade upload-assistant
```

Then start it again with your usual command.

On startup, the app adds missing general settings without changing existing values. When this changes `config.py`, it creates a timestamped backup beside the file. Tracker/client sections and optional cache-service/tag overrides are left untouched; add new tracker/client options manually when needed. See the [example configuration](data/example_config.py) for available settings.

If you installed from GitHub, use the [GitHub update command](#development-version-from-github) instead.

## Command-line usage

The CLI uses the same configuration as the WebUI. After configuring the app, run an upload from any directory:

**Windows:**

```powershell
ua "D:\Media\Example.Movie.2025.mkv" --trackers AITHER
```

**Linux / macOS:**

```bash
ua "/path/to/media/Example.Movie.2025.mkv" --trackers AITHER
```

Replace the path with your own file or folder and `AITHER` with your configured tracker's identifier from [Supported sites](#supported-sites). These commands start a real upload workflow.

Options normally follow the path. To see all options:

```text
ua --help
```

If you prefer to configure the app without the WebUI, your first CLI upload command creates `config.py` and stops so you can edit it. Fill in the required settings, then run the command again. See [Configuration file location](#configuration-file-location).

For all flags and queue input modes, see [CLI arguments](docs/cli-args.md). For command completion in your shell, see [Shell completions](docs/shell-completions.md).

## Configuration file location

The installed app stores `config.py` outside the installation directory:

| Platform      | Default file location                            |
| ------------- | ------------------------------------------------ |
| Windows       | `%LOCALAPPDATA%\Upload-Assistant\data\config.py` |
| Linux / macOS | `~/.local/share/Upload-Assistant/data/config.py` |

On Windows, paste `%LOCALAPPDATA%\Upload-Assistant\data` into File Explorer's address bar to open the folder. On Linux/macOS, `$XDG_DATA_HOME` replaces `~/.local/share` when set. Existing Linux/macOS installations may still use the lowercase `upload-assistant` folder if the `Upload-Assistant` folder does not exist.

Setting `UA_DATA_DIR` overrides the application data location: the configuration is then in the `data` subfolder of that directory. See the [configuration reference](docs/example-config.md).

For manual edits, stop the app, make a copy of `config.py`, edit it in a plain-text/code editor, and restart. The file is Python code; preserve its quotes, commas, and indentation.

## Other installation options

### Docker and Unraid

Use the [Docker guide](docs/docker.md) for container installation and the [Docker WebUI / Unraid guide](docs/docker-gui.md) for browser access, persistent configuration, and media volume mappings.

A community walkthrough is available at <https://videos.badkitty.zone/ua>.

### Seedbox and Linux without root access

Follow the [Seedbox / Linux installation guide](docs/seedbox.md).

### Development version from GitHub

For the latest repository version instead of the published package:

```text
uv tool install git+https://github.com/wastaken7/Upload-Assistant.git
```

This installation requires Git. If `uv` reports an existing installation, use `--force` to replace it. To update an installation from GitHub, stop the app and run:

```text
uv tool install --force git+https://github.com/wastaken7/Upload-Assistant.git
```

## Guides and advanced workflows

| I want to...                                   | Read this                                                                |
| ---------------------------------------------- | ------------------------------------------------------------------------ |
| Learn the full browser interface               | [WebUI guide](docs/web-ui.md)                                            |
| Understand configuration fields                | [Configuration reference](docs/example-config.md)                        |
| Find CLI options or create a queue             | [CLI arguments](docs/cli-args.md)                                        |
| Upload to Usenet and indexers                  | [Usenet guide](docs/usenet.md)                                           |
| Control upload order and qBittorrent bandwidth | [Upload order and bandwidth](docs/upload-order-and-bandwidth-control.md) |
| Browse the rest of the documentation           | [Documentation home](docs/home.md)                                       |

## Supported Sites

<details>
<summary><strong>Click to view Supported Torrent Trackers</strong></summary>

|                                                                                               | Site                   | Usage                  | Supported Categories         |
| --------------------------------------------------------------------------------------------- | ---------------------- | ---------------------- | ---------------------------- |
| <img src="web_ui/static/img/trackers/1ptba.png" width="16" height="16" />                     | 1PTBA                  | 1PTBA                  | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/aither.png" width="16" height="16" />                    | Aither                 | AITHER                 | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/alpharatio.png" alt="" width="16" height="16" />         | AlphaRatio             | ALPHARATIO             | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/anthelion.png" width="16" height="16" />                 | Anthelion              | ANTHELION              | MOVIE                        |
| <img src="web_ui/static/img/trackers/asiancinema.png" width="16" height="16" />               | AsianCinema            | ASIANCINEMA            | MOVIE, TV, MUSIC             |
| <img src="web_ui/static/img/trackers/avistaz.png" width="16" height="16" />                   | AvistaZ                | AVISTAZ                | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/beyondhd.png" alt="" width="16" height="16" />           | BeyondHD               | BEYONDHD               | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/bithdtv.png" width="16" height="16" />                   | BitHDTV                | BITHDTV                | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/bitporn.png" width="16" height="16" />                   | BitPorn                | BITPORN                | XXX                          |
| <img src="web_ui/static/img/trackers/blutopia.png" width="16" height="16" />                  | Blutopia               | BLUTOPIA               | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/bjshare.png" alt="" width="16" height="16" />            | BJ-Share               | BJSHARE                | MOVIE, TV, BOOK, GAME, XXX   |
| <img src="web_ui/static/img/trackers/brasiltracker.png" width="16" height="16" />             | BrasilTracker          | BRASILTRACKER          | MOVIE, TV, BOOK, GAME        |
| <img src="web_ui/static/img/trackers/broadcasthenet.png" width="16" height="16" />            | BroadcasTheNet         | BROADCASTHENET         | TV                           |
| <img src="web_ui/static/img/trackers/capybarabr.png" width="16" height="16" />                | CapybaraBR             | CAPYBARABR             | MOVIE, TV, BOOK, GAME        |
| <img src="web_ui/static/img/trackers/cathoderaytube.png" width="16" height="16" />            | Cathode-Ray.Tube       | CATHODERAYTUBE         | MOVIE, TV, GAME              |
| <img src="web_ui/static/img/trackers/cinematik.png" width="16" height="16" />                 | Cinematik              | CINEMATIK              | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/cinemaz.png" width="16" height="16" />                   | CinemaZ                | CINEMAZ                | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/darkpeers.png" width="16" height="16" />                 | DarkPeers              | DARKPEERS              | MOVIE, TV, BOOK, GAME, MUSIC |
| <img src="web_ui/static/img/trackers/desitorrents.png" width="16" height="16" />              | DesiTorrents           | DESITORRENTS           | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/digitalcore.png" width="16" height="16" />               | DigitalCore            | DIGITALCORE            | MOVIE, TV, BOOK, GAME, MUSIC |
| <img src="web_ui/static/img/trackers/dreadvault.png" alt="" width="16" height="16" />         | DreadVault             | DREADVAULT             | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/emuwarez.png" alt="" width="16" height="16" />           | eMuwarez               | EMUWAREZ               | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/filelist.png" width="16" height="16" />                  | FileList               | FILELIST               | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/flood.png" width="16" height="16" />                     | Flood                  | FLOOD                  | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/funfile.png" width="16" height="16" />                   | FunFile                | FUNFILE                | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/greatposterwall.png" alt="" width="16" height="16" />    | Great Poster Wall      | GREATPOSTERWALL        | MOVIE                        |
| <img src="web_ui/static/img/trackers/hawkeuno.png" width="16" height="16" />                  | hawke-uno              | HAWKEUNO               | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/hdbits.png" width="16" height="16" />                    | HDBits                 | HDBITS                 | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/hdspace.png" width="16" height="16" />                   | HD-Space               | HDSPACE                | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/hdtorrents.png" width="16" height="16" />                | HD-Torrents            | HDTORRENTS             | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/homiehelpdesk.png" width="16" height="16" />             | HomieHelpDesk          | HOMIEHELPDESK          | MOVIE, TV, BOOK, GAME, MUSIC |
| <img src="web_ui/static/img/trackers/immortalseed.png" width="16" height="16" />              | ImmortalSeed           | IMMORTALSEED           | MOVIE, TV, BOOK, MUSIC, GAME |
| <img src="web_ui/static/img/trackers/infinityhd.png" width="16" height="16" />                | InfinityHD             | INFINITYHD             | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/iptorrents.png" width="16" height="16" />                | IPTorrents             | IPTORRENTS             | MOVIE, TV, BOOK, GAME, MUSIC |
| <img src="web_ui/static/img/trackers/itatorrents.png" width="16" height="16" />               | ItaTorrents            | ITATORRENTS            | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/lajidui.png" width="16" height="16" />                   | lajidui                | LAJIDUI                | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/lemonhd.png" width="16" height="16" />                   | LemonHD                | LEMONHD                | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/lastdigitalunderground.png" width="16" height="16" />    | LastDigitalUnderground | LASTDIGITALUNDERGROUND | MOVIE, TV, BOOK              |
| <img src="web_ui/static/img/trackers/latteam.png" width="16" height="16" />                   | Lat-Team               | LATTEAM                | MOVIE, TV, BOOK              |
| <img src="web_ui/static/img/trackers/locadora.png" width="16" height="16" />                  | Locadora               | LOCADORA               | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/longpt.png" width="16" height="16" />                    | LongPT                 | LONGPT                 | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/lst.png" width="16" height="16" />                       | LST                    | LST                    | MOVIE, TV, BOOK, MUSIC, XXX  |
| <img src="web_ui/static/img/trackers/luminarr.png" width="16" height="16" />                  | Luminarr               | LUMINARR               | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/makingoff.png" width="16" height="16" />                 | MakingOff              | MAKINGOFF              | MOVIE                        |
| <img src="web_ui/static/img/trackers/midnightscene.png" width="16" height="16" />             | MidnightScene          | MIDNIGHTSCENE          | MOVIE, TV, GAME, MUSIC       |
| <img src="web_ui/static/img/trackers/mteam.png" width="16" height="16" />                     | M-Team                 | MTEAM                  | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/nebulance.png" width="16" height="16" />                 | Nebulance              | NEBULANCE              | TV                           |
| <img src="web_ui/static/img/trackers/nordicquality.png" width="16" height="16" />             | NordicQuality          | NORDICQUALITY          | MOVIE, TV, MUSIC, BOOK, GAME |
| <img src="web_ui/static/img/trackers/oldtoonsworld.png" width="16" height="16" />             | OldToonsWorld          | OLDTOONSWORLD          | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/onlyencodes.png" width="16" height="16" />               | OnlyEncodes+           | ONLYENCODES            | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/orpheus.png" width="16" height="16" />                   | Orpheus                | ORPHEUS                | MUSIC                        |
| <img src="web_ui/static/img/trackers/passthepopcorn.png" width="16" height="16" />            | PassThePopcorn         | PASSTHEPOPCORN         | MOVIE                        |
| <img src="web_ui/static/img/trackers/peergarden.png" width="16" height="16" />                | PeerGarden             | PEERGARDEN             | MOVIE, TV, GAME, BOOK, MUSIC |
| <img src="web_ui/static/img/trackers/polishtorrent.png" alt="" width="16" height="16" />      | Polish Torrent         | POLISHTORRENT          | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/portugas.png" width="16" height="16" />                  | Portugas               | PORTUGAS               | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/privatehd.png" width="16" height="16" />                 | PrivateHD              | PRIVATEHD              | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/ptgtk.png" width="16" height="16" />                     | PT GTK                 | PTGTK                  | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/ptzone.png" width="16" height="16" />                    | PTZone                 | PTZONE                 | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/ptcafe.png" alt="" width="16" height="16" />             | PTCafe                 | PTCAFE                 | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/pterclub.png" width="16" height="16" />                  | PTerClub               | PTERCLUB               | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/ptfans.png" width="16" height="16" />                    | PTFans                 | PTFANS                 | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/ptskit.png" width="16" height="16" />                    | PTSKIT                 | PTSKIT                 | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/qingwa.png" width="16" height="16" />                    | QingWa                 | QINGWA                 | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/racing4everyone.png" width="16" height="16" />           | Racing4Everyone        | RACING4EVERYONE        | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/railgunpt.png" width="16" height="16" />                 | RailgunPT              | RAILGUNPT              | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/rastastugan.png" width="16" height="16" />               | Rastastugan            | RASTASTUGAN            | MOVIE, TV, BOOK, GAME, MUSIC |
| <img src="web_ui/static/img/trackers/reelflix.png" width="16" height="16" />                  | ReelFLiX               | REELFLIX               | MOVIE                        |
| <img src="web_ui/static/img/trackers/retroflix.png" width="16" height="16" />                 | RetroFlix              | RETROFLIX              | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/retromoviesclub.png" alt="" width="16" height="16" />    | Retro Movies Club      | RETROMOVIESCLUB        | MOVIE                        |
| <img src="web_ui/static/img/trackers/rockethd.png" width="16" height="16" />                  | RocketHD               | ROCKETHD               | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/samaritano.png" width="16" height="16" />                | Samaritano             | SAMARITANO             | MOVIE, TV, BOOK, GAME        |
| <img src="web_ui/static/img/trackers/seedpool.png" width="16" height="16" />                  | seedpool               | SEEDPOOL               | MOVIE, TV, BOOK, GAME, MUSIC |
| <img src="web_ui/static/img/trackers/shareisland.png" width="16" height="16" />               | ShareIsland            | SHAREISLAND            | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/skipthecommercials.png" alt="" width="16" height="16" /> | SkipTheCommerials      | SKIPTHECOMMERCIALS     | MOVIE (Documentary only), TV |
| <img src="web_ui/static/img/trackers/speedapp.png" width="16" height="16" />                  | SpeedApp               | SPEEDAPP               | MOVIE, TV, BOOK, GAME, MUSIC |
| <img src="web_ui/static/img/trackers/swarmazon.png" width="16" height="16" />                 | Swarmazon              | SWARMAZON              | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/theleachzone.png" width="16" height="16" />              | The Leach Zone         | THELEACHZONE           | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/theoldschool.png" alt="" width="16" height="16" />       | The Old School         | THEOLDSCHOOL           | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/torrenteros.png" width="16" height="16" />               | Torrenteros            | TORRENTEROS            | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/torrenthr.png" width="16" height="16" />                 | TorrentHR              | TORRENTHR              | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/torrentleech.png" width="16" height="16" />              | TorrentLeech           | TORRENTLEECH           | MOVIE, TV, BOOK, GAME, MUSIC |
| <img src="web_ui/static/img/trackers/totheglory.png" width="16" height="16" />                | ToTheGlory             | TOTHEGLORY             | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/tvchaosuk.png" alt="" width="16" height="16" />          | TV Chaos UK            | TVCHAOSUK              | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/xingyungept.png" width="16" height="16" />               | XingyungePT            | XINGYUNGEPT            | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/ulcx.png" width="16" height="16" />                      | ULCX                   | ULCX                   | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/utopia.png" width="16" height="16" />                    | UTOPIA                 | UTOPIA                 | MOVIE, TV                    |
| <img src="web_ui/static/img/trackers/vultu.png" width="16" height="16" />                     | vultu                  | VULTU                  | MOVIE, TV, GAME              |
| <img src="web_ui/static/img/trackers/yuscene.png" width="16" height="16" />                   | YUSCENE                | YUSCENE                | MOVIE, TV, BOOK, GAME, MUSIC |
| <img src="web_ui/static/img/trackers/zenith.png" width="16" height="16" />                    | Zenith                 | ZENITH                 | MOVIE, TV, BOOK, GAME, MUSIC |

</details>

<details>
<summary><strong>Click to view Supported Usenet Indexers</strong></summary>

|                                                                                 | Site        | Usage       | Supported Categories         |
| ------------------------------------------------------------------------------- | ----------- | ----------- | ---------------------------- |
| <img src="web_ui/static/img/trackers/curupira.png" width="16" height="16" />    | Curupira    | CURUPIRA    | MOVIE, TV, BOOK, GAME        |
| <img src="web_ui/static/img/trackers/drunkenslug.png" width="16" height="16" /> | DrunkenSlug | DRUNKENSLUG | MOVIE, TV, BOOK, GAME        |
| <img src="web_ui/static/img/trackers/nzbgeek.png" width="16" height="16" />     | NZBGeek     | NZBGEEK     | MOVIE, TV, BOOK, GAME, MUSIC |
| <img src="web_ui/static/img/trackers/nzbnest.png" width="16" height="16" />     | NzbNest     | NZBNEST     | MOVIE, TV, BOOK, GAME, MUSIC |

</details>

## Fork Features & Differences from Upstream (Audionut/Upload-Assistant)

This branch introduces new media categories and automation features not present in the upstream Audionut repository:

### 1. New Media Category Support

- **Ebook & Audiobook (`BOOK` Category)**:
  - **Automatic Type Detection**: Classifies uploads into Ebooks (PDF, EPUB, MOBI), Comics/Manga (CBR, CBZ), Newspapers, or Audiobooks.
  - **Local Metadata Extraction**: Reads metadata from OPF files in EPUB/MOBI, `ComicInfo.xml` in CBR/CBZ, parses tags via Mutagen for audiobooks, and uses PyMuPDF (`fitz`) with checksum-validated regex to extract ISBNs from PDFs.
  - **API Integrations**: Queries **MyAnonamouse (MAM) API**, **Google Books API**, and **OpenLibrary API** for automated metadata lookup.
  - **Artwork & Screenshot Generation**: Renders gallery screenshots from PDF/EPUB pages, extracts cover artwork, and auto-generates `POSTER.png`.
  - **Smart Duplicate Checking**: Custom rules distinguishing formats (e.g., EPUB vs PDF) and audiobooks vs ebooks, with tracker-specific overrides.
- **Video Game (`GAME` Category)**:
  - **Game Directory Parsing**: Priority scans for executables (`.exe`), disc images (`.iso`), or archives (`.rar`, `.zip`, etc.) in the upload path.
  - **GazelleGames, IGDB & Steam Metadata APIs**: Uses exact GazelleGames torrent comments or a guarded title search for game metadata, then fills missing fields and artwork through Twitch/IGDB and Steam.
  - **Platform Detection**: Identifies systems (PC, PS5, Switch, Xbox Series X|S, etc.) and enforces platform-group duplicate checks (so Switch uploads aren't blocked by PC dupes).
  - **Platform-specific Prompts**: Attended prompts for console TV standard (NTSC/PAL) and region codes (USA/EUR/JPN) for trackers like BJSHARE.
- **Music (`MUSIC` Category)**:
  - **Local Tag & Metadata Extraction**: Parses audio tags, cue sheets, and rip logs (EAC, XLD, etc.) using Mutagen to extract tracklists, artists, and audio metadata.
  - **Discogs & MusicBrainz APIs**: Optionally queries external APIs (Discogs via release/master ID or URL, and MusicBrainz) for metadata enrichment.
  - **Artwork & Cover Extraction**: Automatically searches for local cover images or extracts embedded artwork from FLAC/MP3/M4A tags to upload to image hosts.
  - **Preflight & Rule Validation**: Enforces mechanical validation for audio formats, sample/bit rates, track counts, and hybrid setups before uploading.
- **Adult Video (`XXX` Category)**:
  - **Automatic Detection & Metadata**: Recognizes supported adult-platform release names, extracts common title, studio, and date fields, and builds descriptive keywords.
  - **Contact Sheets & Artwork**: Generates one configurable contact sheet per video and creates a fallback cover from the source when artwork is not supplied.
  - **Workflow Guide**: See the dedicated [XXX category upload guide](docs/xxx-upload.md) for naming, overrides, WebUI usage, and supported destinations.

### 2. Audio Stream Spectrogram Generation

- **Spectrogram Extraction & Plotting**: Use `-as` / `--audio-spectrogram` to automatically extract audio streams from MKVs, Blu-ray BDInfo, music tracks, or audiobook chapters using FFmpeg and plot frequency/time graphs (inferno theme) via `librosa` and `matplotlib`. Music and audiobook processing is capped by `audio_spectrogram_max_files`.
- **Dynamic HDR Metadata Plots**: Use `--dynamic-hdr-plot` to create and upload separate Dolby Vision and HDR10+ metadata plots. The required `dovi_tool` and `hdr10plus_tool` binaries are downloaded automatically for the current platform on first use.
- **Automated Upload**: Automatically uploads generated spectrograms along with your screenshots for release verification.
- **Stream Selection**: Supports targeting specific tracks using `-ast` / `--audio-spectrogram-tracks` (e.g., track indexes or `all`).

### 3. Upload Order & qBittorrent Bandwidth Control

Sequence Usenet and torrent tracker uploads while limiting contention with qBittorrent. See the dedicated [upload order and bandwidth control guide](docs/upload-order-and-bandwidth-control.md) for configuration and every supported workflow.

### 4. Argument-Embedded Text Queue

- **Custom Parameter Queues**: When running batch uploads with a `.txt` queue file, each line is treated as an independent execution command.
- **shlex-Split Parsing**: Allows specifying unique CLI arguments (e.g., different IMDB IDs, tags, or tracker targets) for each file/folder on its respective line.
- **Resume Capability**: Logs processed lines to prevent reprocessing completed uploads if a queue run is interrupted.

### 5. Usenet & Indexer Posting

- **Usenet Upload Support**: Automatically archives and splits files/folders (via `7z`), generates parity recovery blocks (via `par2`), and uploads them to Usenet (via `nyuu`).
- **Anonymity & Privacy**: Generates randomized poster details and obfuscates post subject lines to protect privacy.
- **Indexer Integration**: Automatically uploads the generated `.nzb` file to configured Usenet indexers.

### 6. Interactive Screenshot Review Workflow

- **Manual Screenshot Review**: Inspect, add, delete, or replace/recapture individual frames before uploading through the interactive Web UI.

### 7. Persistent TTL-Based Metadata Cache

- **Provider-Scoped API Caching**: Disk-cached metadata for TMDb, IMDb, TVDB, TVmaze, OpenLibrary, IGDB, GazelleGames, Discogs, and MusicBrainz.
- **Performance & Rate Limit Protection**: Configurable TTL and negative caching reuse fetched metadata across runs, avoiding redundant API calls and preventing rate-limiting bans.

### 8. Modern Web UI & Real-Time Engine

- **Full Parity Web UI**: Modern interface providing full feature parity with CLI options (`--webui`).
- **Private Local Statistics**: A dedicated Stats workspace tracks daily upload outcomes, cache efficiency, logical API operations, torrent/NZB creation, destinations, and categories without storing media names, paths, external IDs, URLs, or credentials.
- **Real-Time Execution & Presets**: Live log streams, real-time preparation preview, preset saving, and interactive screenshot management.

## Help

For bugs or setup questions, [open a GitHub issue](https://github.com/wastaken7/Upload-Assistant/issues). Include your operating system, installation method (published package, GitHub, or Docker), command or WebUI steps, and the relevant error output. Remove API keys, passwords, personal announce URLs, and other private details before sharing logs or screenshots.

If you prefer not to create a GitHub account, use the [Signal group](https://signal.group/#CjQKILmkUCLe5mZULkQGI6B5knmX1ytrIBFicpJ_NZGAHmOrEhDD5F7ctp-obLeLOsa0yCoJ).

## Attributions

Built with [autobrr/go-bdinfo](https://github.com/autobrr/go-bdinfo)

Features automated binary managers for:

- [nyuu](https://github.com/animetosho/nyuu)
- [par2cmdline-turbo](https://github.com/animetosho/par2cmdline-turbo)
- [pesto](https://github.com/franzopl/pesto)
- [7-Zip](https://www.7-zip.org/)

<p>
  <a href="https://github.com/autobrr/mkbrr"><img src="https://github.com/autobrr/mkbrr/blob/main/.github/assets/mkbrr-dark.png?raw=true" alt="mkbrr" height="40px;"></a>&nbsp;&nbsp;
  <a href="https://github.com/autobrr/qui"><img src="https://github.com/autobrr/qui/blob/develop/documentation/static/img/qui.png?raw=true" alt="qui" height="40px;"></a>&nbsp;&nbsp;
  <a href="https://ffmpeg.org/"><img src="https://i.postimg.cc/xdj3BS7S/FFmpeg-Logo-new-svg.png" alt="FFmpeg" height="40px;"></a>&nbsp;&nbsp;
  <a href="https://mediaarea.net/en/MediaInfo"><img src="https://i.postimg.cc/vTkjXmHh/Media-Info-Logo-svg.png" alt="Mediainfo" height="40px;"></a>&nbsp;&nbsp;
  <a href="https://www.themoviedb.org/"><img src="https://i.postimg.cc/1tpXHx3k/blue-square-2-d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.png" alt="TMDb" height="40px;"></a>&nbsp;&nbsp;
  <a href="https://www.imdb.com/"><img src="https://i.postimg.cc/CLVmvwr1/IMDb-Logo-Rectangle-Gold-CB443386186.png" alt="IMDb" height="40px;"></a>&nbsp;&nbsp;
  <a href="https://thetvdb.com/"><img src="https://i.postimg.cc/Hs1KKqsS/logo1.png" alt="TheTVDB" height="40px;"></a>&nbsp;&nbsp;
  <a href="https://www.tvmaze.com/"><img src="https://i.postimg.cc/2jdRzkJp/tvm-header-logo.png" alt="TVmaze" height="40px"></a>
</p>

## Contributors

[![Contributors](https://contrib.rocks/image?repo=wastaken7/Upload-Assistant)](https://github.com/wastaken7/Upload-Assistant/graphs/contributors)

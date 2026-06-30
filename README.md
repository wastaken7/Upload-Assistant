# Upload Assistant

[![Python Version](https://img.shields.io/badge/Python-3.14%2B-blue?logo=python&logoColor=white)](https://www.python.org/) [![License](https://img.shields.io/badge/License-UAPL%20v1.0-orange)](LICENSE) [![Ruff](https://img.shields.io/badge/Ruff-000000?logo=ruff&logoColor=white)](https://github.com/astral-sh/ruff) [![Pyright](https://img.shields.io/badge/Pyright-strict-brightgreen)](https://github.com/microsoft/pyright) [![Docker Image CI](https://github.com/wastaken7/Upload-Assistant/actions/workflows/docker-image.yml/badge.svg)](https://github.com/wastaken7/Upload-Assistant/actions/workflows/docker-image.yml)

> [!IMPORTANT]
> **This is a modified version of the Upload Assistant project and is not affiliated with or endorsed by Audionut.**

## Fork Features & Differences from Upstream (Audionut/Upload-Assistant)

This branch introduces new media categories and automation features not present in the upstream Audionut repository:

### 1. New Media Category Support

* **Ebook & Audiobook (`BOOK` Category)**:
  * **Automatic Type Detection**: Classifies uploads into Ebooks (PDF, EPUB, MOBI), Comics/Manga (CBR, CBZ), Newspapers, or Audiobooks.
  * **Local Metadata Extraction**: Reads metadata from OPF files in EPUB/MOBI, `ComicInfo.xml` in CBR/CBZ, parses tags via Mutagen for audiobooks, and uses PyMuPDF (`fitz`) with checksum-validated regex to extract ISBNs from PDFs.
  * **API Integrations**: Queries **MyAnonamouse (MAM) API**, **Google Books API**, and **OpenLibrary API** for automated metadata lookup.
  * **Artwork & Screenshot Generation**: Renders gallery screenshots from PDF/EPUB pages, extracts cover artwork, and auto-generates `POSTER.png`.
  * **Smart Duplicate Checking**: Custom rules distinguishing formats (e.g., EPUB vs PDF) and audiobooks vs ebooks, with tracker-specific overrides.
* **Video Game (`GAME` Category)**:
  * **Game Directory Parsing**: Priority scans for executables (`.exe`), disc images (`.iso`), or archives (`.rar`, `.zip`, etc.) in the upload path.
  * **IGDB & Steam Metadata API**: Queries Twitch/IGDB API for storyline, ratings, involved companies, release year, genre mapping, and downloads cover images. Fetches PC system requirements via Steam Store API.
  * **Platform Detection**: Identifies systems (PC, PS5, Switch, Xbox Series X|S, etc.) and enforces platform-group duplicate checks (so Switch uploads aren't blocked by PC dupes).
  * **Platform-specific Prompts**: Attended prompts for console TV standard (NTSC/PAL) and region codes (USA/EUR/JPN) for trackers like BJS.

### 2. Audio Stream Spectrogram Generation

* **Spectrogram Extraction & Plotting**: Use `-as` / `--audio-spectrogram` to automatically extract audio streams from MKVs or Blu-ray BDInfo using FFmpeg and plot frequency/time graphs (inferno theme) via `librosa` and `matplotlib`.
* **Automated Upload**: Automatically uploads generated spectrograms along with your screenshots for release verification.
* **Stream Selection**: Supports targeting specific tracks using `-ast` / `--audio-spectrogram-tracks` (e.g., track indexes or `all`).

### 3. qBittorrent Bandwidth Control

* **Traffic Control**: Prevents overloading your connection during uploads using `-qbcon` / `--qbit-bw-control`.
* **Dynamic Wait**: Pauses uploading if your active client upload speed exceeds a threshold (`qbit_bandwidth_threshold` KB/s) and resumes once it stays below the limit for a set time (`qbit_bandwidth_time` seconds).
* **Safe Rechecking**: Performs a second duplicate check after the bandwidth wait to ensure a duplicate wasn't posted while the client was waiting.

### 4. Argument-Embedded Text Queue

* **Custom Parameter Queues**: When running batch uploads with a `.txt` queue file, each line is treated as an independent execution command.
* **shlex-Split Parsing**: Allows specifying unique CLI arguments (e.g., different IMDB IDs, tags, or tracker targets) for each file/folder on its respective line.
* **Resume Capability**: Logs processed lines to prevent reprocessing completed uploads if a queue run is interrupted.

### 5. Extended Tracker Support

* **Added Trackers**: Zenith (ZNTH), MidnightScene (MS), M-Team (MTEAM), LongPT (LPT), lajidui (LAJIDUI), ptcafe (PTCAFE), PTFans (PTFANS), PT GTK (PTGTK), RailgunPT (RPT).

### 6. Usenet & Indexer Posting

* **Usenet Upload Support**: Automatically archives and splits files/folders (via `7z`), generates parity recovery blocks (via `par2`), and uploads them to Usenet (via `nyuu`).
* **Anonymity & Privacy**: Generates randomized poster details and obfuscates post subject lines to protect privacy.
* **Indexer Integration**: Automatically uploads the generated `.nzb` file to configured Usenet indexers.

## Supported Sites

<details>
<summary><strong>Click to view Supported Torrent Trackers</strong></summary>

| Site | Acronym | Supported Categories |
|------|---------| -------------------- |
| Aither | AITHER | MOVIE, TV |
| Alpharatio | AR | MOVIE, TV |
| Amigos-Share | ASC | MOVIE, TV, BOOK, GAME |
| Anthelion | ANT | MOVIE |
| AsianCinema | ACM | MOVIE, TV |
| Aura4K | A4K | MOVIE, TV |
| AvistaZ | AZ | MOVIE, TV |
| Beyond-HD | BHD | MOVIE, TV |
| BitHDTV | BHDTV | MOVIE, TV |
| Blutopia | BLU | MOVIE, TV |
| BrasilJapão-Share | BJS | MOVIE, TV, BOOK, GAME |
| BrasilTracker | BT | MOVIE, TV, BOOK, GAME |
| CapybaraBR | CBR | MOVIE, TV, BOOK, GAME |
| Cinematik | TIK | MOVIE, TV |
| CinemaZ | CZ | MOVIE, TV |
| DarkPeers | DP | MOVIE, TV, BOOK, GAME |
| DesiTorrents | DT | MOVIE, TV |
| DigitalCore | DC | MOVIE, TV, BOOK, GAME |
| Emuwarez | EMUW | MOVIE, TV |
| FileList | FL | MOVIE, TV |
| Friki | FRIKI | MOVIE, TV |
| FunFile | FF | MOVIE, TV |
| GreatPosterWall | GPW | MOVIE |
| hawke-uno | HUNO | MOVIE, TV |
| HDBits | HDB | MOVIE, TV |
| HD-Space | HDS | MOVIE, TV |
| HD-Torrents | HDT | MOVIE, TV |
| HomieHelpDesk | HHD | MOVIE, TV, BOOK, GAME |
| ImmortalSeed | IS | MOVIE, TV, BOOK |
| InfinityHD | IHD | MOVIE, TV |
| ItaTorrents | ITT | MOVIE, TV |
| lajidui | LAJIDUI | MOVIE, TV |
| LastDigitalUnderground | LDU | MOVIE, TV, BOOK |
| Lat-Team | LT | MOVIE, TV, BOOK |
| Locadora | LCD | MOVIE, TV |
| LongPT | LPT | MOVIE, TV |
| LST | LST | MOVIE, TV, BOOK |
| Luminarr | LUME | MOVIE, TV |
| MidnightScene | MS | MOVIE, TV |
| MoreThanTV | MTV | MOVIE, TV |
| M-Team | MTEAM | MOVIE, TV |
| Nebulance | NBL | TV |
| OldToonsWorld | OTW | MOVIE, TV |
| OnlyEncodes+ | OE | MOVIE, TV |
| PassThePopcorn | PTP | MOVIE |
| PolishTorrent | PTT | MOVIE, TV |
| Portugas | PT | MOVIE, TV |
| PrivateHD | PHD | MOVIE, TV |
| PT GTK | PTGTK | MOVIE, TV |
| ptcafe | PTCAFE | MOVIE, TV |
| PTerClub | PTER | MOVIE, TV |
| PTFans | PTFANS | MOVIE, TV |
| PTSKIT | PTS | MOVIE, TV |
| Racing4Everyone | R4E | MOVIE, TV |
| RailgunPT | RPT | MOVIE, TV |
| Rastastugan | RAS | MOVIE, TV, BOOK, GAME |
| ReelFLiX | RF | MOVIE |
| RetroFlix | RTF | MOVIE, TV |
| Samaritano | SAM | MOVIE, TV, BOOK, GAME |
| seedpool | SP | MOVIE, TV |
| ShareIsland | SHRI | MOVIE, TV |
| SkipTheCommerials | STC | MOVIE, TV |
| SpeedApp | SPD | MOVIE, TV, BOOK, GAME |
| Swarmazon | SN | MOVIE, TV |
| The Leach Zone | TLZ | MOVIE, TV |
| TheOldSchool | TOS | MOVIE, TV |
| Torrenteros | TTR | MOVIE, TV |
| TorrentHR | THR | MOVIE, TV |
| TorrentLeech | TL | MOVIE, TV, BOOK, GAME |
| ToTheGlory | TTG | MOVIE, TV |
| TVChaosUK | TVC | MOVIE, TV |
| ULCX | ULCX | MOVIE, TV |
| UTOPIA | UTP | MOVIE, TV |
| YOiNKED | YOINK | MOVIE, TV |
| YUSCENE | YUS | MOVIE, TV, BOOK, GAME |
| Zenith | ZNTH | MOVIE, TV, BOOK, GAME |

</details>

<details>
<summary><strong>Click to view Supported Usenet Indexers</strong></summary>

| Site | Acronym | Supported Categories |
|------|---------| -------------------- |
| Curupira | CRP | MOVIE, TV, BOOK, GAME |
| DrunkenSlug | DS | MOVIE, TV, BOOK, GAME |

</details>

## **Setup:**

* **REQUIRES AT LEAST PYTHON 3.14 AND PIP3**
* Also needs MediaInfo and ffmpeg installed on your system
  * On Windows systems, ffmpeg must be added to PATH (<https://windowsloop.com/install-ffmpeg-windows-10/>)
  * On linux systems, get it from your favorite package manager
  * If you have issues with ffmpeg, such as `max workers` errors, see this [wiki](docs/ffmpeg---max-workers-issues.md)
* Get the source:
  * Clone the repo to your system `git clone https://github.com/wastaken7/Upload-Assistant.git`
  * Fetch all of the release tags `git fetch --all --tags`
  * Check out the specifc release: see [releases](https://github.com/wastaken7/Upload-Assistant/releases)
  * `git checkout tags/tagname` where `tagname` is the release name, eg `v5.0.0`
  * or download a zip of the source from the releases page and create/overwrite a local copy.
* Install necessary python modules `pip3 install --user -U -r requirements.txt`
  * `sudo apt install pip` if needed
* If you receive an error about externally managed environment, or otherwise wish to keep UA python separate:
  * Install virtual python environment `python3 -m venv venv`
  * Activate the virtual environment `source venv/bin/activate`
  * Then install the requirements `pip install -r requirements.txt`
* From the installation directory, run `python3 config-generator.py`
* OR
* Copy `data/example_config.py` to `data/config.py`, leaving `data/example_config.py` intact.
* NOTE: New users who use the webui will have the config file generated automatically.
* Edit `config.py` to use your information (more detailed information in example config options: [docs/example-config.md](docs/example-config.md))
  * tmdb_api key can be obtained from <https://www.themoviedb.org/settings/api>
  * image host api keys can be obtained from their respective sites

    **Additional Resources are found in the [wiki](docs/Home.md)**

   Feel free to contact me if you need help, I'm not that hard to find.

## **Updating:**

* To update first navigate into the Upload-Assistant directory: `cd Upload-Assistant`
* `git fetch --all --tags`
* `git checkout tags/tagname`
* Or download a fresh zip from the releases page and overwrite existing files
* Run `python3 -m pip install --user -U -r requirements.txt` to ensure dependencies are up to date
* Run `python3 config-generator.py` and select to grab new UA config options.

## **CLI Usage:**

  `python3 upload.py "/path/to/content" --args`

  Args are OPTIONAL and ALWAYS follow path, for a list of acceptable args, pass `--help`.
  Path works best in quotes.

* CLI arguments: [docs/cli-args.md](docs/cli-args.md)
* Usenet uploading: [docs/usenet.md](docs/usenet.md)

## **Docker Usage:**

  Visit our wonderful [docker usage](docs/docker-wiki-full.md)

  Also see this excellent video put together by a community member <https://videos.badkitty.zone/ua>

  Web UI setup (Docker GUI / Unraid): [docs/docker-gui-wiki-full.md](docs/docker-gui-wiki-full.md)
  Web UI docs: [docs/web-ui.md](docs/web-ui.md)

## **Attributions:**

Built with updated BDInfoCLI from <https://github.com/rokibhasansagar/BDInfoCLI-ng>

Features automated binary managers for:

* [nyuu](https://github.com/animetosho/nyuu)
* [par2cmdline-turbo](https://github.com/animetosho/par2cmdline-turbo)
* [pesto](https://github.com/franzopl/pesto)
* [7-Zip](https://www.7-zip.org/)

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

# Game Category Upload Guide

The Upload Assistant supports the `GAME` category, enabling automated metadata gathering from **IGDB** and **Steam**, platform detection, custom duplicate checking, and specialized formatting for various trackers.

---

## 1. Overview & Supported Formats

When uploading a game, the assistant automatically parses the target path to locate relevant files, which prioritizes files using the following order:

1. **Executable files (`.exe`)** (ordered by file size, descending)
2. **Disc images (`.iso`)** (ordered by file size, descending)
3. **Compressed archives (`.rar`, `.zip`, `.7z`, `.tar`, `.gz`)** (ordered by file size, descending)
4. **Largest file** as fallback

---

## 2. Metadata Extraction & Priority Flow

To gather rich metadata with minimal manual input, the Upload Assistant implements a hierarchical resolution flow:

$$\text{CLI Overrides} > \text{IGDB ID Search} > \text{Steam ID from NFO} > \text{Cleaned Title Search on IGDB} > \text{CLI Prompting}$$

### A. NFO Parsing for Steam IDs

If not overridden manually, the script scans all `.nfo` files inside the upload directory for a Steam store link (`store.steampowered.com/app/(\d+)`). If found, it queries IGDB directly using the extracted Steam App ID.

### B. IGDB API Integration

The assistant communicates with the **Twitch/IGDB API** to fetch:

- **Game Title & Release Year**
- **IGDB Rating & Vote Count**
- **Overview / Storyline**
- **Genres & Keywords**
- **Developer & Publisher** (from involved companies)
- **Supported Languages** (including translation/support types)
- **Cover Image** (downloaded, converted, and saved locally to `POSTER.png`)
- **IGDB Screenshot Gallery Links** (cached to `image_data.json`)

### C. Steam API Integration

If a Steam App ID is resolved via IGDB or NFO, the assistant fetches additional game details directly from the Steam Store API:

- **System Requirements**: PC minimum and recommended requirements are extracted and stored in `requirements_minimum` and `requirements_recommended`.

---

## 3. Platform Detection & Mapping

The assistant auto-detects the platform by parsing the directory/file name for common terms (e.g. `nsw`, `ps5`, `xboxone`, `pc`, etc.) and matching them against the list of platforms retrieved from IGDB.

If a manual override is used, the platform argument is cleaned and mapped into standard names:

- `pc` $\rightarrow$ `PC`
- `ps5` $\rightarrow$ `PS5`
- `ps4` $\rightarrow$ `PS4`
- `ps3` $\rightarrow$ `PS3`
- `ps2` $\dots$ $\rightarrow$ `PS2` / `PS1`
- `switch` $\rightarrow$ `Switch`
- `3ds` / `nds` $\rightarrow$ `3DS` / `DS`
- `xbox` / `x360` / `xone` / `xsx` $\rightarrow$ `Xbox` / `Xbox 360` / `Xbox One` / `Xbox Series X|S`
- `wii` / `wiiu` $\rightarrow$ `Wii` / `Wii U`
- `mac` / `linux` $\rightarrow$ `Mac` / `Linux`

---

## 4. Duplicate Checking Rules

The duplicate checking module implements custom rules for games to avoid false positives:

### A. Platform Compatibility Filtering

Before comparing titles, the assistant maps the target platform and duplicate platform into broad compatibility groups:

- **PlayStation Group**: `playstation`, `ps5`, `ps4`, `ps3`, `ps2`, `ps1`, `psp`, `vita`
- **Xbox Group**: `xbox`
- **PC Group**: default fallback (e.g., PC, Windows, Mac, Linux)

If the target game platform group does not match the duplicate's platform group, the entry is excluded from the duplicates list (i.e. you can upload a Switch version of a game even if the PC version is already on the tracker).

### B. Title Normalization & Cleaning

Game titles are aggressively cleaned to ensure precise comparison:

1. converted to lowercase.
2. Trailing tags/release group suffixes are removed.
3. Versions, build identifiers, and updates (e.g. `v1.0.4`, `build 239`, `patch 2`, `version`) are stripped.
4. Publication years (e.g. 1900-2100) are removed.
5. Platform names and keywords are removed (`pc`, `windows`, `ps5`, etc.).
6. Store/source tags are removed (`gog`, `steam`, `epic`, `repack`, `cracked`, `crack`, `setup`, `download`).
7. Punctuation (`.`, `_`, `[`, `]`, `(`, `)`, `-`, `:`, `+`) are replaced with spaces.

### C. Matching Conditions

A duplicate is confirmed if:

- The cleaned target title is an exact match for the cleaned duplicate title.
- The cleaned target title is a word-bounded substring of the cleaned duplicate title, or vice-versa.

---

## 5. Console Prompting & User Flow

In attended mode, the terminal guides the user to fill in missing fields and review final details:

- **Missing Fields**: If essential fields (`title`, `year`, `platform`, `game_subcategory`) are missing, the console prompts you to supply them before generating the torrent name. The game version is used when detected or supplied with `--game-version`, but is not prompted for or required for unattended uploads.
- **PC Installation Notes Check**: For PC game uploads, if no installation instructions are provided via description file or custom description link, a yellow warning is shown: `Installation instructions missing. Use -df or -dp to add them.`

---

## 6. CLI Arguments

You can override auto-detected values or pass specific parameters using the following command-line flags:

| Flag     | Full Argument               | Accepted Values                                                                                                        | Description                                           |
| :------- | :-------------------------- | :--------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------- |
| `-plat`  | `--platform`, `--platforms` | `pc`, `ps5`, `ps4`, `ps3`, `ps2`, `xbox`, `x360`, `xone`, `xsx`, `switch`, `3ds`, `nds`, `wiiu`, `wii`, `mac`, `linux` | Overrides the target game platform                    |
| `-gv`    | `--game-version`            | e.g. `v1.15`, `Build 1002`                                                                                             | Overrides the game version                            |
| `-gsc`   | `--game-subcategory`        | `full_game`, `full_game_dlc`, `dlc`, `update`                                                                          | Specifies the category/format of the game release     |
| `-igdb`  | `--igdb`                    | e.g. `119388`                                                                                                          | Explicitly sets the IGDB game ID to query             |
| `-steam` | `--steam`                   | e.g. `413150` or full Store URL                                                                                        | Explicitly sets the Steam App ID/URL to fetch details |

---

## 7. Configuration Options

To query the IGDB metadata server, Twitch API credentials must be configured. Add the following keys to your `config.py` file:

```python
config = {
    "DEFAULT": {
        # Twitch developer credentials (https://dev.twitch.tv/console)
        "twitch_client_id": "YOUR_TWITCH_CLIENT_ID",
        "twitch_client_secret": "YOUR_TWITCH_CLIENT_SECRET",
    }
}
```

---

## 8. Example Commands

### Basic upload (auto-detects title, version, platform)

```bash
python upload.py "/path/to/Cool.Game.PC.v1.0-GROUP" --category game
```

### Force metadata query using a specific IGDB ID or Steam ID

```bash
python upload.py "/path/to/Cool.Game.PC.v1.0-GROUP" --category game --igdb 000000
python upload.py "/path/to/Cool.Game.PC.v1.0-GROUP" --category game --steam 000000
```

### Override platform, subcategory, and version manually

```bash
python upload.py "/path/to/Cool.Game-Now.Even.Cooler.DLC-GROUP" --category game --platform switch --game-subcategory dlc --game-version "v1.3.0"
```

### Upload to a specific tracker with installation notes

```bash
python upload.py "/path/to/pc_game" --category game --platform pc --descfile "/path/to/install_instructions.txt" --site-upload CAPYBARABR
```

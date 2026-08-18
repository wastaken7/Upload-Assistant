# UNIT3D ID Report & Diff Exporter

Userscript that extracts and compares **Category**, **Type**, **Resolution**, **Region**, **Genre**, and **Distributor** IDs on UNIT3D sites (both search/filter and upload pages).

It automatically fetches the standard defaults from Upload-Assistant's GitHub repository (`data/unit3d_default_ids.json`), compares them with the tracker's IDs, and exports a clean JSON containing **only custom or tracker-specific overrides** with alphabetically sorted keys.

## Features

- ⚡ **Export Diff JSON**: Downloads `<site>-custom-ids.json` containing only IDs that differ from standard UNIT3D defaults.
- 📦 **Export All JSON**: Downloads `<site>-all-ids.json` containing all extracted IDs alphabetically sorted.
- 📝 **Export Markdown**: Downloads `<site>-ids.md` with side-by-side tables for human inspection.
- 🔤 **Alphabetical Sort**: All JSON dictionaries and keys are strictly sorted in alphabetical order.

## Installation

1. Install [Tampermonkey](https://www.tampermonkey.net/) or [Violentmonkey](https://violentmonkey.github.io/).
2. Open [`UNIT3D-id-report.user.js`](./UNIT3D-id-report.user.js).
3. Copy its contents into a new userscript in your manager.
4. Save it and navigate to any UNIT3D torrents or upload page.

## Usage

When compatible fields are detected on the page, the **UNIT3D ID Tools** panel appears in the bottom-right corner with one-click export actions.

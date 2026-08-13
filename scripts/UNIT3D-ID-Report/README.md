# UNIT3D ID Report

Userscript that adds a button to UNIT3D torrent pages to export **Category**, **Type**, and **Resolution** IDs to a Markdown file.

## Installation

1. Install [Tampermonkey](https://www.tampermonkey.net/) or [Violentmonkey](https://violentmonkey.github.io/).
2. Open [`UNIT3D-id-report.user.js`](./UNIT3D-id-report.user.js).
3. Copy its contents into a new userscript in your chosen manager.
4. Save it and open a UNIT3D-compatible torrent page.

The script runs on URLs matching the `*/torrents*` pattern.

## Usage

When compatible fields are found, the **Export IDs (.md)** button appears in the lower-right corner of the page.

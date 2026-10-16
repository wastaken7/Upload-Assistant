# Importing IDs and Descriptions from Other Trackers

Upload Assistant can reuse information from a release that already exists on another tracker. Depending on your settings, it can import:

- **IDs**: IMDb, TMDb, TVDB and MAL, which make metadata matching more accurate.
- **Description text**: for example, the detailed notes that a remux or encode group posted on the original tracker.
- **Screenshots**: the images in the original description. When enough valid images are imported, Upload Assistant does not need to take its own.

The imported description is then included in the description that Upload Assistant builds for each tracker you upload to.

## Quick checklist

If the import is not working, check these items in order. All of them must be true.

1. The source tracker has `"use_for_search": True` in its `TRACKERS` config block, and its API credentials are filled in (see [Supported source trackers](#supported-source-trackers)).
2. `DEFAULT.tracker_description_mode` is `"text"` or `"text_and_images"` if you want the description text. With `"ids"` or `"images"` the text is never imported.
3. You are not running with `--onlyID`, which forces `ids` mode for that run.
4. Upload Assistant knows the torrent ID on the source tracker. With the default `"tracker_comment_only": True`, that means one of:
   - the same torrent from that tracker is loaded in your torrent client (see [How the source torrent is found](#how-the-source-torrent-is-found)), or
   - you pass it manually with `--tracker-id`.

If you are still stuck, run with `--debug` and check the log. See [Troubleshooting](#troubleshooting).

## Configuration

### `tracker_description_mode` (DEFAULT)

Controls what is imported from the source tracker:

| Mode              | IDs | Description text | Screenshots |
| :---------------- | :-: | :--------------: | :---------: |
| `ids`             | Yes |        No        |     No      |
| `images`          | Yes |        No        |     Yes     |
| `text` (default)  | Yes |       Yes        |     No      |
| `text_and_images` | Yes |       Yes        |     Yes     |

`--onlyID` forces `ids` for a single run without changing your config.

Imported screenshots are downloaded and checked before use. Broken links, non-image responses and images whose resolution does not match the release are discarded.

### `tracker_comment_only` (DEFAULT, default `True`)

- `True`: only query a tracker when its torrent ID is already known, either from a torrent comment in your client or from `--tracker-id`. Searches by file name are disabled.
- `False`: when no torrent ID is known, also search the supported trackers by file name (see [Searching by file name](#searching-by-file-name)).

The default is `True` because a search by file name can match the wrong release. An ID from your client or from `--tracker-id` always identifies the exact torrent.

### `use_for_search` (per tracker)

Each source tracker must opt in:

```python
"HDBITS": {
    "use_for_search": True,
    "username": "your_username",
    "passkey": "your_passkey",
    ...
},
```

A tracker without `use_for_search: True` is never queried for metadata, even when its torrent ID is known. Configuring a tracker only for uploading is not enough.

### `skip_auto_torrent` (DEFAULT, default `False`)

Must be `False` for Upload Assistant to look for the release in your torrent client. `-sat` / `--skip_auto_torrent` disables that search for one run, and `skip_auto_torrent_personalrelease` disables it for personal releases.

## How the source torrent is found

Upload Assistant identifies the source torrent in this order:

1. **`--tracker-id`**: you pass the tracker and torrent ID, or the torrent URL:

   ```bash
   upload.py "/path/to/release" --tracker-id HDB=123456
   upload.py "/path/to/release" --tracker-id https://hdbits.org/details.php?id=123456
   upload.py "/path/to/release" --tracker-id PTP=12345 --tracker-id BLU=67890
   ```

   Tracker aliases such as `HDB`, `PTP`, `BHD`, `BLU` and `BTN` are accepted. `--tracker-id` can be repeated, and it works even with `tracker_comment_only: True`.

2. **Torrent comment in your client**: when `skip_auto_torrent` is `False`, Upload Assistant searches the clients in `searching_client_list` (or `default_torrent_client`) for a torrent with the same files. If that torrent's comment contains a link to a tracker's torrent page, such as `https://hdbits.org/details.php?id=123456`, the ID is taken from it. Most trackers write this link into the comment automatically.

   You can also point at a specific torrent in your client with `-th` / `--torrenthash HASH`.

3. **Search by file name**: only when `tracker_comment_only` is `False` and no ID was found by the steps above.

In practice, the import works automatically when you upload a release you downloaded from the source tracker and are still seeding from it in your client. If your copy came from somewhere else, pass `--tracker-id`.

### Several trackers found at once

When torrent IDs for more than one enabled tracker are found, each tracker is queried and the results are ranked by how much they add (new IDs, description, images). In an interactive run you are asked to pick one; press Enter to take the best-ranked result. Unattended runs use the best-ranked result.

### Searching by file name

With `tracker_comment_only: False` and no known ID, trackers are tried in this order, stopping at the first match:

1. PassThePopcorn (skipped for TV)
2. HDBits
3. BeyondHD
4. The UNIT3D trackers with `use_for_search: True`, in alphabetical order

A search by file name is also skipped when Sonarr or Radarr already returned IDs for the release.

## Supported source trackers

| Tracker              | Credentials needed       | IDs                   | Description text | Screenshots |
| :------------------- | :----------------------- | :-------------------- | :--------------: | :---------: |
| PassThePopcorn (PTP) | `ApiUser`, `api_key`     | IMDb                  |       Yes        |     Yes     |
| HDBits (HDB)         | `username`, `passkey`    | IMDb, TVDB            |       Yes        |     Yes     |
| BeyondHD (BHD)       | `api_key`, `bhd_rss_key` | IMDb, TMDb            |       Yes        |     Yes     |
| UNIT3D trackers      | `api_key`                | TMDb, IMDb, TVDB, MAL |       Yes        |     Yes     |
| BroadcasTheNet (BTN) | `api_key`                | IMDb, TVDB            |        No        |     No      |
| Anthelion (ANT)      | `api_key`                | IMDb, TMDb            |        No        |     No      |

Notes:

- "UNIT3D trackers" covers every tracker that Upload Assistant talks to through the UNIT3D API, such as Aither and Blutopia.
- BTN is only queried for TV releases.
- Anthelion is not queried for disc releases. Its example config block has no `use_for_search` line, so add `"use_for_search": True` yourself to enable it.
- Trackers not listed here are not used as metadata sources, even when their torrent ID appears in a comment.

## What happens to the imported description

1. **Cleaning**: the description is cleaned with rules specific to each source tracker, for example removing HDBits-hosted images and links, which would not work on other sites.
2. **Review**: in an interactive run, Upload Assistant shows the cleaned text and asks you to keep it (Enter), edit it (`e`, opens your editor) or discard it (`d`). When using the WebUI, the imported text is offered in the description review step. Unattended runs keep it without asking.
3. **Placement**: the description is added to the description that Upload Assistant builds for each target tracker, in the "API Overview / Synopsis" block (see [Description Builder](description-builder.md)), followed by your own description file or link if you supplied one.

## Troubleshooting

Run with `--debug` (this goes through the steps without uploading) and look for these messages:

- **`Skipping filename-based tracker metadata searches because DEFAULT.tracker_comment_only is enabled.`**
  No torrent ID was known. Pass `--tracker-id`, make sure the source torrent is in your client, or set `tracker_comment_only` to `False`.
- **`Tracker X is not enabled for metadata search, skipping`**
  Set `"use_for_search": True` for that tracker.
- **`Waiting for tracker metadata candidate cooldowns`**
  The same tracker was queried a few seconds ago (15 seconds, 60 for PTP). The run waits and continues.
- **`HDBITS description empty`**
  HDBits was queried, but the torrent has no description or `tracker_description_mode` does not import text.
- **`BEYONDHD API or RSS key not found`**
  Fill in both `api_key` and `bhd_rss_key`.
- **No tracker message at all**
  Check that `skip_auto_torrent` is `False` and that your client appears in `searching_client_list` or `default_torrent_client`.

Other things to check:

- The description appears but without screenshots: the mode is `text`. Use `text_and_images` to also import images.
- Screenshots were imported but some are missing: images that failed the link or resolution check are dropped. The log lists each rejected image and the reason.
- The wrong release was imported: this can only happen with a search by file name. Keep `tracker_comment_only` on `True`, or pass the exact torrent with `--tracker-id`.

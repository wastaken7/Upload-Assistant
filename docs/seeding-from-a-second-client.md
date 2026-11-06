# Seeding From a Second Client (Seedbox)

This guide is for you if the same files live in **two places**, each with its own qBittorrent:

- **Computer A**: where Upload Assistant (UA) runs and reads the files to make the upload.
- **Client B**: another qBittorrent, usually a seedbox, that already has a copy of the same files and seeds them.

After an upload, you want the new torrent to seed from **both** A and B, without copying anything or downloading it again.

UA can do this. You add B to the list of clients that receive new torrents, and you turn on one option for B: `match_existing_content`.

## In short

1. Add both clients to `TORRENT_CLIENTS`.
2. List both in `injecting_client_list`.
3. In client B, set `"match_existing_content": "require"`.

That's it. You don't need `local_path`/`remote_path` or linking for B.

## How it works

Every time UA adds a new torrent to B, it does this:

1. It asks B for its list of torrents.
2. It looks for a **complete** torrent that holds **the same files** as the new one: same names and same sizes.
3. If it finds one, it adds the new torrent **pointing at that torrent's folder**. B already has every file, so it starts seeding straight away.
4. If it finds none, the option decides what happens (see step 4 below).

UA does not copy, move or rename anything on B. It only reads B's torrent list and adds the new torrent.

## Do I need this?

| Your setup                                                                                                          | What to do                                                                        |
| ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Only one qBittorrent                                                                                                | Nothing. You don't need this option.                                              |
| UA and qBittorrent in Docker, on the same machine                                                                   | Use `local_path`/`remote_path`. You don't need this option.                       |
| A second client that **already has** the files (seedbox, NAS, another PC)                                           | Use this guide, with `"require"`.                                                 |
| A second client that sees the **same disk** under another path, usually has the files, and should get every torrent | Use `"prefer"` and set `local_path`/`remote_path` for the times no copy is found. |

## Step-by-step setup

### 1. Open your config file

Edit the `config.py` that UA reads, not the bundled `data/example_config.py`:

- Windows: `%LOCALAPPDATA%\Upload-Assistant\data\config.py`
- Linux/macOS: `~/.local/share/Upload-Assistant/data/config.py`
- Custom state directory: `<UA_DATA_DIR>/data/config.py`

Or use the WebUI config page (see [Using the WebUI](#using-the-webui)).

### 2. Add both clients

Both must be qBittorrent (`"torrent_client": "qbit"`). The names (`local_qbit`, `seedbox_qbit`) are up to you.

```python
"TORRENT_CLIENTS": {
    # Client A: the qBittorrent on the computer where UA runs.
    "local_qbit": {
        "torrent_client": "qbit",
        "qbit_url": "http://127.0.0.1",
        "qbit_port": "8080",
        "qbit_user": "your-user",
        "qbit_pass": "your-password",
    },
    # Client B: the seedbox.
    "seedbox_qbit": {
        "torrent_client": "qbit",
        "qbit_url": "https://seedbox.example.com",
        "qbit_port": "443",
        "qbit_user": "your-user",
        "qbit_pass": "your-password",
        # Optional, but much faster on seedboxes with many torrents:
        # "qui_proxy_url": "http://your-qui-host:7476/proxy/<client-api-key>",
        # The new option:
        "match_existing_content": "require",
    },
},
```

### 3. List both clients in `injecting_client_list`

In the `DEFAULT` section:

```python
"injecting_client_list": ["local_qbit", "seedbox_qbit"],
```

UA adds every new torrent to each client in this list, in order.

> [!IMPORTANT]
> If you pass `--client NAME` on the command line, UA uses **only** that client and ignores `injecting_client_list`.

### 4. Choose between `prefer` and `require`

| Value       | When B has the files                     | When B does **not** have the files                                                         |
| ----------- | ---------------------------------------- | ------------------------------------------------------------------------------------------ |
| `"require"` | Adds the torrent, seeding from B's copy. | **Skips B.** Nothing is added to B. This is not an error: client A still gets the torrent. |
| `"prefer"`  | Adds the torrent, seeding from B's copy. | Adds the torrent the normal way, as if the option were off (see below).                    |
| `""` (off)  | Ignored; always uses the normal way.     | Normal way.                                                                                |

**Not sure? Use `"require"`.** A seedbox normally can't see computer A's disk, so the normal way would only give B a broken torrent pointing at a folder that doesn't exist. With `"require"`, B only gets torrents it can actually seed.

Use `"prefer"` only when B can see the same files through a path mapping and you want B to receive every torrent.

"The normal way" means B's usual settings apply:

- With `linking` set to `hardlink` or `symlink`, UA creates the links and adds the torrent from the linked folder. If linking fails and `allow_fallback` is `False`, nothing is added to B.
- Without linking, UA uses `local_path`/`remote_path` to translate the path.

### Using the WebUI

1. Open the config page and go to **Torrent Clients**.
2. Open client B. In the **Existing Content** group, set **Match Existing Content** to **Require Existing Copy** (or **Prefer Existing Copy**).
3. In the `DEFAULT` settings, put both clients in the injecting client list.
4. Save.

## What counts as "the same files"

UA compares the **name** (including folders) and the **size** of every file. A torrent in B counts only when:

- it is **100% complete**;
- it is not in an error state (`error`, `missingFiles`, `moving`);
- **every** file of the new torrent exists in it, with the same size;
- its total size is the same as the new torrent's, or a little bigger: up to 10% or 512 MiB more, whichever is larger. The extra room is for files like an NFO or a sample.

Examples, using a fictional release:

| B has                                                             | You upload                                                    | Result                                                                  |
| ----------------------------------------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `Example.Movie.2024-GROUP/movie.mkv`                              | The folder `Example.Movie.2024-GROUP`                         | ✅ Match                                                                |
| `Example.Movie.2024-GROUP/movie.mkv` + `movie.nfo` + `sample.mkv` | The folder, without the NFO and sample                        | ✅ Match: extra files in B are fine                                     |
| `Example.Movie.2024-GROUP/movie.mkv`                              | Only the file `movie.mkv`                                     | ✅ Match: UA points at the folder inside B                              |
| `Other.Folder.Name/movie.mkv` + `movie.srt`                       | The folder `Example.Movie.2024-GROUP` with the same two files | ✅ Match: UA adds it with qBittorrent's "Don't create subfolder" layout |
| `Example.Movie.2024-GROUP/movie.mkv` (another size)               | The folder                                                    | ❌ No match: a different size means different content                   |
| `Example.Movie.2024-GROUP/movie.mkv` at 80%                       | The folder                                                    | ❌ No match: incomplete torrent                                         |
| Only `movie.mkv`, without `movie.srt`                             | The folder with `movie.mkv` + `movie.srt`                     | ❌ No match: a file is missing                                          |
| A full season pack                                                | One episode                                                   | ❌ No match: the season is far bigger than the episode                  |

> [!NOTE]
> UA compares names and sizes, not the bytes inside the files. Two different files with exactly the same name and size would count as a match. This is very unlikely for real releases.

## What you'll see in the log

| Message                                                                                                        | What it means                                                                | What to do                                                                                   |
| -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `TRACKER: seedbox_qbit already has these files (torrent NAME); seeding from PATH`                              | UA found B's copy and will add the torrent pointing at it.                   | Nothing, unless a later line reports an error. You can check the torrent in B.               |
| `TRACKER: seedbox_qbit has no complete copy of these files; not adding the torrent to it.`                     | `"require"`: UA found no matching copy in B, so B was skipped.               | Expected if B really doesn't have them. If it does, see [Troubleshooting](#troubleshooting). |
| `TRACKER: seedbox_qbit has no complete copy of these files; adding it with the usual linking or path mapping.` | `"prefer"`: no copy found; UA will add the torrent the normal way.           | Check the torrent in B, and B's linking or `local_path`/`remote_path` settings.              |
| `Could not list torrents to find existing content: ...` or `Could not read the files of torrent HASH ...`      | UA couldn't read B's torrent list or a torrent's files, so it found no copy. | Check that B's qBittorrent (or its qui proxy) is reachable and that the login works.         |
| `seedbox_qbit: ignoring unsupported match_existing_content value '...'`                                        | Typo in the value.                                                           | Use exactly `"prefer"`, `"require"` or `""`.                                                 |
| `TRACKER: qBittorrent reports 'missingFiles' for the added torrent. Check that its files exist under PATH`     | The client can't find the files at the path it was given.                    | Fix the path or mapping, then run "Force recheck" on that torrent in qBittorrent.            |

## Testing it safely

`--debug` doesn't upload the release to any tracker (screenshots still go to your image host as usual), but with most trackers it **does** add a test torrent to your clients. That torrent has a fake tracker (`https://fake.tracker`), so it never announces anywhere real. This makes `--debug` a good way to test the setup:

1. Pick something you know is on both A and B, and run UA on it with `--debug` and a single tracker. If the log says `Torrent file ...[TRACKER_DEBUG].torrent does not exist, cannot add to client`, that tracker doesn't create a test torrent in debug mode: try again with another tracker.
2. In the log, look for the line `already has these files ... seeding from ...`.
3. In B's qBittorrent, find the new torrent. It has the release's name, so it sits next to the torrent B already had; the test one is the torrent whose tracker is `fake.tracker`. Check that its save path is B's folder and that it isn't stuck on "Missing files".
4. If you want to be completely sure, right-click it and choose **Force recheck**. It should end at 100%.
5. Remove the test torrent (the one with the `fake.tracker` tracker) from **both** clients.

> [!WARNING]
> When you remove the test torrent, **do not** tick "Also delete the files on the hard disk". It points at the same files your real torrents seed. Removing only the torrent is safe: it has its own hash, so your real torrents are not touched.

If you'd rather not get test torrents at all, add `--no-seed` to the command. UA then adds nothing to any client, but you also can't see this feature work.

## Troubleshooting

**B has the files, but UA says "no complete copy".**

- Is there a `Could not list torrents` or `Could not read the files` line just before it? Then UA couldn't talk to B. Check B's qBittorrent or qui proxy, then try again.
- Is B's torrent 100% complete? Partly downloaded torrents, or torrents with skipped files, don't count.
- Was a file renamed, removed, or added in B? Names and sizes must match.
- Is B's torrent in an error state? Fix it in qBittorrent first, then try again.
- Is the new torrent much smaller than B's, like one episode from a season pack? That isn't supported.
- Does B's torrent have a different name? UA checks torrents with the same name first, then the 25 closest in size. In a big library, a renamed copy can fall outside those 25.

**It's slow.**

UA reads B's whole torrent list once per tracker upload. With tens of thousands of torrents this can take several seconds through the normal qBittorrent WebUI. Setting `qui_proxy_url` for B makes it much faster.

**B gets nothing at all, not even a log line.**

- Is B in `injecting_client_list`, with exactly the same name as in `TORRENT_CLIENTS`?
- Did you pass `--client`? That overrides the list.
- Does the tracker have `client_to_skip` with B's name?

**I use hardlinks or symlinks on client A. Does that matter?**

No. Linking is a per-client setting. When B already has the files, UA doesn't create links for B.

## Limits

- **qBittorrent only.** rTorrent, Deluge and Transmission ignore `match_existing_content`.
- **No hash check.** Like every torrent UA adds, the new torrent is added without checking the files (seed mode). The name-and-size match makes a wrong folder very unlikely. If qBittorrent later reports missing files, UA warns you, but qBittorrent sometimes only notices when a peer asks for data.
- **B has to have the files already.** UA never copies or downloads anything to B.

## Related options

- `injecting_client_list` (in `DEFAULT`): clients that receive new torrents. When it is empty, only `default_torrent_client` receives them.
- `searching_client_list` (in `DEFAULT`): a separate list of clients that UA searches for an existing torrent whose hashes it can reuse. Being in this list doesn't make a client receive new torrents.
- `local_path` / `remote_path`: path mapping for clients that see the same disk under another path. See [configuration.md](configuration.md#torrent-clients).
- `content_layout`: the qBittorrent layout used for normal additions. With `match_existing_content`, UA picks the layout that matches B's copy.
- `allow_fallback`: with linking turned on, adds the torrent at the original path when linking isn't possible, including when no `linked_folder` matches the drive.

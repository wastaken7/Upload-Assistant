# Music uploads

Use `--category music` for a directory (or a supported audio file) containing one release. The preparation stage is read-only: it parses tags and technical stream data with Mutagen, records logs/cues/artwork/scans, derives disc layout, and writes `tmp/<uuid>/music_release.json` with each field's provenance.

Local tags are authoritative. Folder names fill only missing data; optional MusicBrainz enrichment is disabled by default and never replaces stronger local values. Enable it with `DEFAULT["music_enrichment_enabled"] = True` only when external corroboration is wanted.

Discogs is enabled by default. If no release/master ID is supplied, the program searches by the locally determined artist and album and keeps only exact artist-and-title matches. Candidates with a Discogs medium incompatible with the upload (for example, DVD when the upload is WEB) are removed. One remaining exact match is used automatically; with several matches, interactive mode asks you to choose a pressing or skip it, while unattended mode skips the ambiguous result. An exact release can provide concrete date, label, catalogue number, country, genres and medium; a master can corroborate the original group year. All calls are cached, read-only and rate-limited. Responses are persisted under `tmp/music_metadata_cache/` and reused in later runs. Pass `--no-music-discogs` to disable this lookup completely. Add `DEFAULT["music_discogs_token"]` optionally to use your own Discogs rate limit. The token is never saved in the metadata snapshot or logged.

## CLI overrides

Use the existing `--year` for the original release/group year and `--edition` for an explicitly distinct edition. MUSIC-specific corrections are applied after local analysis, so they intentionally override tags, folder inference and optional external enrichment:

```text
--music-artist "Artist One & Artist Two" --music-album "Album"
--music-media web --music-release-type album --music-release-year 2024
--music-label "Example Records" --music-catalogue-number ABC-123
--edition "Deluxe Edition" --music-edition-year 2025
--music-genre "Rock, Alternative Rock" --poster "C:\covers\album.jpg"
--music-discogs-id "https://www.discogs.com/release/1234567"
# or: --music-discogs-release-id 1234567 --music-discogs-master-id 765432
```

`--poster` accepts either an existing local image or a public HTTP(S) URL and saves it as `tmp/<uuid>/artwork/POSTER.png`; use `--banner` for `POSTER_BANNER.png`. `--music-enrich` enables MusicBrainz only for the current run; `--no-music-enrich` disables it even when the default configuration enables enrichment. `--music-discogs-id` accepts a bare release ID, a Discogs release/master URL, or `release/123`/`master/123`; the explicit release/master variants make the intent unambiguous. The legacy `--source WEB` and `--source DVD` are also reused for MUSIC when they map unambiguously to a supported music medium; use `--music-media` for all other media.

The analyzer keeps the original album group, a concrete release, and an audio-distinct edition separate. A leading folder year is the original group year; tag dates, imprint and catalogue identify the concrete release; they do not by themselves prove a different edition. Edition fields are populated only from explicit remaster/deluxe/reissue evidence and are confirmed when incomplete. Multi-artist tags are preserved as separate main artists, and a rip log from EAC/XLD/CUERipper/whipper can establish `CD` media without guessing from a `.log` filename alone.

For scene WEB releases, `.nfo` sidecars are read as auxiliary, lower-confidence evidence: retail date, store URL, label, genre, declared source and declared stream quality are retained without replacing file tags. `.m3u` and `.sfv` files are checked for membership only; no hashes are calculated and no source file is changed. Invisible Unicode format controls in tags are removed so visually identical names do not become distinct tracker titles.

## Orpheus

Configure the `TRACKERS["ORPHEUS"]` entry with an API token and announce URL. The adapter performs a few narrow, read-only `browse` requests for duplicate checking and builds the Gazelle upload fields only after the normal Upload Assistant confirmation workflow reaches the tracker.

Orpheus's `image` field is optional, but artwork improves the catalog. MUSIC first selects a local `cover`/`front`/`folder` image when present, otherwise extracts a front-cover image embedded in FLAC, MP3 or MP4/M4A tags. After the normal user confirmation, it uploads that single local image through the configured image host (the Orpheus form recommends imgbb) and reuses its cached raw URL; a user-supplied link always takes precedence. Discogs, Facebook CDN, Photobucket and ptpimg artwork links are omitted because the Orpheus form disallows them. Debug never calls the image host and still prints a complete payload with the optional image field omitted.

### Edition information

Orpheus keeps release information (year, label, catalogue number, title) in its edition fields. The edition year comes from `--music-edition-year`, `--music-release-year`, the retail date, or the initial year when it cannot predate the source medium (CD 1982, DVD 1996, SACD/WEB 1999, BD 2006). It is never guessed: when no concrete year exists, the upload stops and asks for one. If the release cannot be identified, pass `--music-unknown-release` to submit it as an Unknown Release (rule 2.1.19).

A label, catalogue number or edition title found only in the folder name is not sent on its own. Interactive runs ask about each one before the upload is confirmed, and a confirmed value is used as if it had been passed with `--music-label`, `--music-catalogue-number` or `--edition`. Unattended runs leave it out and show a warning.

Orpheus API requests are retried after timeouts, connection failures and rate-limit or server errors, up to `max_retries` attempts (set under `TRACKERS["ORPHEUS"]` or `DEFAULT`). The upload itself is retried only when Orpheus certainly did not receive it: the connection failed, or the site answered 429 or 503. After a read timeout or another server error the upload may already exist, so it is reported instead of repeated; check the site before uploading again.

### Preflight

The preflight enforces mechanical rules before a torrent is created:

- formats and containers (FLAC, MP3, AAC in `.m4a`/`.mp4`, AC3, DTS; Ogg Vorbis is rejected), FLAC bit depth, allowed sample rates, the MP3 CBR ceiling, 44.1 kHz MP3s from CD, mixed encoder settings and technical hybrids;
- the server's file rules: allowed extensions only (for example `.webp`, `.tif`, `.wav` or `Thumbs.db` are rejected), no `\ : ? < > * | "`, no blacklisted site names, and paths of at most 255 characters;
- required Artist, Album, Title and Track Number tags, embedded artwork plus padding of at most 1024 KiB per file, and MQA-encoded FLAC;
- Do Not Upload list artists, releases, labels and P2P/scene/seller sources.

Leading spaces, missing track numbers in file names, unnecessary nested folders and ID3 tags inside FLAC are reported as warnings because they make a torrent trumpable. Provenance-dependent questions—transcodes, official status, watermarking, edition correctness and source medium—remain warnings for human review rather than being claimed as proven. For a transcode review, generate spectrograms with `-as`/`--audio-spectrogram`.

### Upload form fields

- MP3 bitrates use the LAME preset from the file header (V0, V1, V2, APS, APX, 320); other values use the form's "Other" bitrate.
- Tags are converted to Orpheus tag syntax, official synonyms are preferred (for example `dnb` becomes `drum.and.bass`), and per-upload tags such as `flac`, `v0` or `vinyl` are dropped.
- Main artists come from the tags. Guests come from "feat." track credits; composers and conductors are added for classical music and soundtracks. Use `--music-artist-role "Name=guest; Name=composer"` for other credits (main, guest, composer, conductor, dj, remixer, producer, arranger).
- The release description lists hybrid per-track differences, the MP3 encoder, the scene release name (for scene uploads), `--music-watermark "NOTE"`, and lineage from `--music-lineage PATH` or a lineage text file in the release.
- `--music-showcase` marks a Showcase release.

### Duplicates, requests and logs

The duplicate review lists each torrent in a matching group with its edition, medium, format, encoding and log score, and labels it as a dupe, a trump or allowed to coexist. A slot check box then recommends allow, block or review, as for video trackers (`DEFAULT["slot_rules"]` turns it off). It applies the dupe and trump rules: lossy bitrates and LAME presets, AAC, 16-bit and 24-bit FLAC sample rate tiers, vinyl slots, CD rip log scores, cue sheets, scene releases, cassettes, Unknown Releases and single-edition bootlegs (rules 2.2, 2.5, 2.6.2 and 2.10). When a torrent in the group may compete with the upload, one more read-only `torrentgroup` request reads the site's trumpable flags and the folder names, which usually show the sample rate. Unattended runs upload when the check allows it and skip when it blocks. After a trump, report the old torrent (rule 2.2.3).

Request search (`-req`) compares open Music requests with the upload's format, bitrate, media, log and cue. To fill one, pass `--music-request-id ID_OR_URL`; the request is checked first and the upload stops if it is filled, mismatched or incompatible. `--music-group-id ID_OR_URL` adds the upload to an existing group after confirming the group title.

`--music-check-log` sends each rip log to the Orpheus logchecker, which only scores it and changes nothing on the site, and shows the score, checksum state and deductions before uploading. For CD FLAC this runs during the duplicate review, so the slot check can decide log trumps.

No API key, token or tracker response is written into the music snapshot or payload preview.

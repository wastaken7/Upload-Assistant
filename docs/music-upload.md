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

Configure the `TRACKERS["ORPHEUS"]` entry with an API token and announce URL. The adapter performs one narrow, read-only `browse` request for duplicate checking and builds the Gazelle upload fields only after the normal Upload Assistant confirmation workflow reaches the tracker.

Orpheus's `image` field is optional, but artwork improves the catalog. MUSIC first selects a local `cover`/`front`/`folder` image when present, otherwise extracts a front-cover image embedded in FLAC, MP3 or MP4/M4A tags. After the normal user confirmation, it can upload that single local image through the configured image host and reuse its cached raw URL; a user-supplied link always takes precedence. Discogs, Facebook CDN and Photobucket artwork links are omitted because the Orpheus form disallows them. Debug never calls the image host and still prints a complete payload with the optional image field omitted.

The preflight enforces mechanical rules (allowed format/container, FLAC bit depth/sample rate, MP3 CBR ceiling, technical hybrids, required artist/album and split-track evidence). It deliberately reports provenance-dependent questions—transcodes, official status, watermarking, edition correctness and source medium—as warnings for human review rather than claiming to prove them automatically.

No API key, token or tracker response is written into the music snapshot or payload preview.

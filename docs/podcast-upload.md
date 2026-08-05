# Podcast uploads to Unwalled

Configure `TRACKERS.UNWALLED.api_key` with an API token created in Unwalled and `TRACKERS.UNWALLED.announce_url` with your personal announce URL. Keep both values private. The optional `category` and `type` configuration values can hold either their displayed names or numeric ids.

Upload an audio or video podcast with:

```bash
python upload.py "/path/to/podcast" \
  --category podcast \
  --trackers UNWALLED \
  --podcast-title "Example Show [2026/MP3 - 128kbps]" \
  --podcast-cover "/path/to/cover.jpg" \
  --podcast-banner "/path/to/banner.jpg" \
  --unwalled-category "Technology" \
  --unwalled-type "Free Audio" \
  --descfile "/path/to/description.txt"
```

The Unwalled adapter discovers category and type ids across the paginated torrent results returned by the tracker's UNIT3D API. A positive numeric id can be supplied when a name is not present in those results, including categories or types that do not yet have a torrent.

The preparation flow rejects mixed audio/video torrents, media whose extension disagrees with its detected content, compressed archives (including files disguised with a media extension), symbolic links, invalid nested filenames, missing or unsuitable artwork, and uploads whose final `.torrent` plus cover and banner reach 1 MiB. It rejects reused V2 or hybrid torrents and creates a V1 private torrent with the configured personal announce URL and `source=Unwalled`. Debug mode always uses a fake announce URL. The cover must be a square JPEG of at least 400x400; the distinct banner must be a 16:9 JPEG of at least 960x540.

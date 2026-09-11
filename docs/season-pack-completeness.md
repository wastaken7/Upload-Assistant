# Season pack completeness

For TV season packs, UA checks that episode numbering includes E01 and has no
missing numbers through the highest episode found. It also fetches each season's
current episode list from TVDB and compares the unique episode numbers and count.
For example, E02–E10 reports E01 missing; E01–E09 reports E10 missing if TVDB lists
ten episodes. Duplicate files do not increase the episode count, and filenames
such as S03E01E02 count as two episodes.

TVDB verification uses its [default season order](https://github.com/thetvdb/v4-api/blob/main/README.md)
and includes all numbered episodes listed for the season. Different release
numbering, split seasons, anime absolute numbering, and episodes listed before
release can cause a mismatch. UA shows the missing or unexpected episode numbers.
When episodes are missing, it asks whether the pack is really incomplete:

- **y**: Continue and add `INCOMPLETE` after the season number on supported trackers.
- **n**: Treat the mismatch as a false alarm and continue without adding the marker.
- **q**, an empty answer, or another answer: Abort.

When there are only extra episodes, UA warns that the pack may contain special
episodes or use different numbering. It asks whether to continue (`y`/`yes`) or
abort (any other answer), without offering or adding `INCOMPLETE`. If episodes
are missing as well as extra, the missing-episode confirmation above still applies.

The confirmed marker is supported by **RocketHD, LST, Aither, HDBits, ULCX,
hawke-uno, YUSCENE, OldToonsWorld, OnlyEncodes, PrivateHD, CinemaZ, AvistaZ,
HD-Torrents, Rastastugan, DarkPeers, IPTorrents, HD-Space, and TorrentLeech**.
For example:
`Example Show S03 INCOMPLETE 1080p DSNP WEB-DL ...`.
Other tracker titles retain their existing naming rules. The season metadata
remains `S03`, so the marker does not affect API season fields or episode searches.
The marker also appears in IPTorrents post-upload title edits and in hawke-uno's
submitted title and torrent filename. Dotted release names use `S03.INCOMPLETE`.

The TVDB check requires a resolved TVDB series ID and configured TVDB access.
It fetches all pages for the season, without relying on the legacy series cache.
If TVDB is unavailable, its response is invalid, or pagination fails, UA warns that
TVDB verification could not be completed and still checks local numbering.

In unattended mode without confirmation, UA logs mismatches and continues without
automatically adding the marker. Use unattended confirmation to answer the same
question as in interactive mode.

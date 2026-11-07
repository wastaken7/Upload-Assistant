# XXX Category Upload Guide

Upload Assistant supports adult video releases through the `XXX` category. The workflow avoids movie and TV metadata lookups, derives available metadata from the release name and, with an API key, from ThePornDB and BLVCKOUT, creates contact sheets, and routes the result only to destinations that advertise XXX support.

## Category detection

Upload Assistant automatically selects `XXX` when a video file, or a directory containing video files, has `XXX` or a recognized adult-platform marker in its name. Generic words are intentionally not enough to classify a non-video download as XXX.

Use an explicit category when the release name is not recognized:

```bash
python upload.py "/path/to/release" --category xxx
```

The CLI value is lowercase `xxx`; it is normalized internally to `XXX`. In the WebUI, add `--category xxx` through the argument sidebar or custom arguments field.

## Naming and metadata

The supported scene-style filename forms are:

```text
Studio.YYYY.Title.XXX[.Format][-Group]
Studio.YY.MM.DD.Title.XXX[.Format][-Group]
```

For example, `Studio.26.08.21.Performer.Scene.XXX.MP4-GROUP` supplies:

- studio/publisher: `Studio`;
- release date: `2026-08-21`;
- year: `2026`;
- title: `Performer Scene`.

Recognized platform and descriptive terms from the release name become tracker keywords. Values supplied with `--keywords` are normalized and merged with the detected keywords.

Without a metadata match, performers are taken from dated names such as `Studio.YY.MM.DD.First.Last.And.Other.Name.Title.XXX`, when the words after the date are written as names and are not known content tags.

## Metadata lookup (ThePornDB and BLVCKOUT)

With an API key, Upload Assistant looks the release up and fills the title, studio, release date, year, performers, tags, synopsis, cover and banner. Add the keys under `DEFAULT`:

```python
"tpdb_api_key": "",      # ThePornDB API token: scenes and movies
"blvckout_api_key": "",  # BLVCKOUT read API key: movies
"xxx_metadata_lookup": True,
"xxx_generate_names": True,
```

The lookup tries, in this order:

1. an ID given with `--tpdb` or `--blvckout`, or confirmed for the same release in an earlier run (see [Saved IDs and answers](web-ui.md#saved-ids-and-answers));
2. a JAV product code (`ABC-123`) on ThePornDB's JAV catalogue;
3. the file hash (OSHASH) of a single-video release on ThePornDB, which identifies the exact scene;
4. for dated scenes (`Studio.YY.MM.DD.…`, `Studio YY.MM.DD …` or `[Site.com] YY.MM.DD …`, as BitPorn uploads are named): the full name, then every scene of that site and day, then the first words of the title;
5. for other names: the site and title of `[Site.com] Performer - Title 2026` names, movies and scenes by title (movie-like names, such as `DVDRip`, `Vol. 3` or a year in brackets, search movies first), and the part after ` - ` in `Studio - Title` names;
6. a BLVCKOUT movie search, when ThePornDB found nothing plausible.

A result is used without asking only when it is clearly the release, with nothing that contradicts it (another date, another studio, a very different runtime):

- the same file hash or JAV product code;
- the same day and site with a matching title or a performer named in the release name, or exactly the same title on the same day (the site may be abbreviated in the name);
- a performer named in the release name together with the scene's title;
- a movie with exactly this title from the same year, or the only movie with this numbered title (`… 13`). A generic title alone is not enough.

When several results are plausible, Upload Assistant asks which one is the release (`xxx.match`); unattended runs skip the lookup instead of guessing. Answer in advance with `--answer xxx.match=tpdb:scenes/ID`, `--answer xxx.match=blvckout:ID` or `--answer xxx.match=none`. An answer, given or remembered for the release, is used before any search, so `none` also keeps a confident result from being applied.

Packs and site rips are not looked up. A release with several videos is a movie in parts or a collection, never one scene, so it is only looked up as a movie. Results are cached like other metadata (`metadata_cache_services` → `tpdb` and `blvckout`).

ThePornDB tags are added to the keywords (without shop labels such as "Feature" or combined `A - B` genres), which ExoticaZ and DirtyBytes turn into their own tags. For scenes and JAV titles, the cover and banner are the scene's original image; ThePornDB's `poster` for those is a cropped thumbnail with the site's logo, so it is not used. For movies, the cover is the front cover. Signed or extensionless artwork links are downloaded for the upload but not published, because they can expire.

When a dated scene's filename is not scene-style (for example `clip_0123.mp4`), `xxx_generate_names` names the upload from the match, such as `Studio.26.08.21.Performer.Name.Scene.Title.XXX.1080p.MP4`. Scene-style names (dots, no spaces, an `.XXX` marker), movie titles and JAV product codes are always kept, and `--name` always wins.

Values given on the command line (`--publisher`, `--year`, `--overview`, `--cast`, `--poster`, `--banner`, `--name`) take precedence over provider data; `--cast` replaces the provider's performers, and `--publisher` and `--cast` are also used in a built name. When the release is prepared again (for example after editing at the confirmation prompt), whatever the earlier match filled in is undone before the lookup decides again.

## Overrides

Use these arguments when automatic metadata needs correction:

| Argument                       | Purpose                                                |
| ------------------------------ | ------------------------------------------------------ |
| `--tpdb scenes/ID`             | Use this ThePornDB scene (`movies/ID` for a movie).    |
| `--blvckout ID`                | Use this BLVCKOUT movie.                               |
| `--name "RELEASE_NAME"`        | Override the generated upload name or title.           |
| `--cast "Name One,Name Two"`   | Supply a comma-separated performer list.               |
| `--publisher "Studio"`         | Override the detected studio/publisher.                |
| `--year YYYY`                  | Override the detected year.                            |
| `--keywords "tag one,tag two"` | Add keywords to those detected from the name.          |

## Contact sheets and artwork

XXX releases generate one evenly sampled contact sheet per video instead of the normal individual screenshot set. The defaults produce a 12-row by 5-column PNG for each of up to six videos. Configure this behavior under `DEFAULT`:

```python
"xxx_contact_sheet_rows": "12",
"xxx_contact_sheet_columns": "5",
"xxx_contact_sheet_max_videos": "6",
"xxx_contact_sheet_animated_webp": False,
"xxx_contact_sheet_animation_seconds": "5",
"xxx_single_file_screens": "0",
```

Set `xxx_contact_sheet_animated_webp` to create animated WebP sheets. For a release containing one video, `xxx_single_file_screens` adds that many normal screenshots alongside its contact sheet; BJShare expects at least two screenshots for single-file XXX uploads.

If no artwork is available, Upload Assistant creates a fallback poster from a source-video frame. `--poster` and `--banner` accept either an existing local image or a public HTTP(S) URL and take precedence over generated artwork:

```bash
python upload.py "/path/to/release" --category xxx \
  --poster "/path/to/cover.jpg" --banner "https://images.example/banner.jpg"
```

XXX descriptions include a details block with the studio, network, release date, performers, tags, runtime and synopsis when they are known.

During a WebUI run, **Now Processing** shows the current XXX details and cover. Generated screenshots can be inspected through the standard screenshot review workflow. When the displayed cover was generated locally, the WebUI also allows generating another frame-based cover.

## Supported destinations

The current XXX upload destinations are:

- **BitPorn (`BITPORN`)**: XXX-only UNIT3D tracker. The category follows the release format first (packs → Collection, VR, ThePornDB movies → Movie, JAV and Japanese sites → Asian, creator platforms → Fansite), then genre words in the name, then ThePornDB tags that describe who is in the scene (gay, trans, lesbian, Asian, interracial, ebony, BBW, mature). Tags for acts are not used; without a signal the category is Uncategorized. Frames between the listed resolutions use the closest one (VR 2880p → 6K, 4096p → 8K). Uploads the cover, banner and contact sheets directly.
- **DirtyBytes (`DIRTYBYTES`)**: XXX-only tracker; picks the Scene, Movies, VR180 or Packs category and resolution from the release name and video height, sends studio, performers, keywords, year, runtime and MediaInfo, and attaches the cover and contact sheets directly.
- **BJShare (`BJSHARE`)**: accepts XXX video uploads and uses the supplied or detected title, year, studio, performers, media details, artwork, and screenshots.
- **LST (`LST`)**: maps XXX to its adult category using the standard UNIT3D upload fields.
- **SUIO (`SUIO`)**: accepts XXX Usenet posts and maps HD/UHD and other resolutions to its adult categories.

Other configured destinations are filtered out when they do not advertise `XXX` support.

## Examples

Upload a conventionally named release and let Upload Assistant extract its metadata:

```bash
python upload.py "/media/Studio.26.08.21.Performer.Scene.XXX.1080p.WEB-DL-GROUP"
```

Force the category and correct all common metadata fields:

```bash
python upload.py "/media/custom-release" --category xxx \
  --name "Studio - Scene Title" --publisher "Studio" --year 2026 \
  --cast "Performer One,Performer Two" --keywords "fansite,4k"
```

Upload only to a supported destination:

```bash
python upload.py "/media/custom-release" --category xxx --site-upload BITPORN
```

The same arguments are available in the WebUI sidebar and are appended to the custom argument string before execution.

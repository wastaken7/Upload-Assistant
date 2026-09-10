# XXX Category Upload Guide

Upload Assistant supports adult video releases through the `XXX` category. The workflow avoids movie and TV metadata lookups, derives available metadata from the release name, creates contact sheets, and routes the result only to destinations that advertise XXX support.

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

Use these existing overrides when automatic metadata needs correction:

| Argument                       | Purpose                                       |
| ------------------------------ | --------------------------------------------- |
| `--name "RELEASE_NAME"`        | Override the generated upload name or title.  |
| `--cast "Name One,Name Two"`   | Supply a comma-separated performer list.      |
| `--publisher "Studio"`         | Override the detected studio/publisher.       |
| `--year YYYY`                  | Override the detected year.                   |
| `--keywords "tag one,tag two"` | Add keywords to those detected from the name. |

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

During a WebUI run, **Now Processing** shows the current XXX details and cover. Generated screenshots can be inspected through the standard screenshot review workflow. When the displayed cover was generated locally, the WebUI also allows generating another frame-based cover.

## Supported destinations

The current XXX upload destinations are:

- **BitPorn (`BITPORN`)**: XXX-only UNIT3D tracker; derives its category from release-name keywords and uploads the cover, banner, and contact sheets directly.
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

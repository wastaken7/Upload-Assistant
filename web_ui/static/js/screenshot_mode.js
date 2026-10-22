// Loaded only for the authenticated Upload page with ?screenshot=1.
(() => {
  const release =
    "The.Automation.Menace.1968.Hybrid.2160p.UHD.BluRay.REMUX.DV.HDR10Plus.HEVC.DTS-HD.MA.5.1-Group";
  const path = `E:\\Movies\\${release}`;
  const progress = [
    ["mkbrr", "mkbrr hashing...", 64, 100, "percent", "100 MiB/s | ETA: 04:27"],
    [
      "usenet",
      "Creating Usenet archive",
      8,
      100,
      "percent",
      "6.1 GiB / 72.3 GiB processed",
    ],
    ["ffmpeg", "FFmpeg screenshots", 3, 6, "frames", "3/6 frames completed"],
    [
      "spectrogram",
      "Generating audio spectrogram",
      1,
      3,
      "items",
      "Rendering audio streams",
    ],
    [
      "hdr",
      "Generating dynamic HDR plots",
      1,
      2,
      "items",
      "Processing dynamic metadata",
    ],
    ["image-upload-1", "Uploading images", 4, 6, "images", "imgbox"],
    [
      "bandwidth",
      "Waiting for bandwidth",
      2350,
      2000,
      "kbps",
      "Average over last 20/60s",
    ],
  ].map(([id, label, current, total, unit, detail]) => ({
    id,
    label,
    current,
    total,
    unit,
    detail,
    status: "running",
  }));
  // Flat SVG "frames" stand in for real captures, so no real media ships.
  const frame = (hue, index) =>
    `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">' +
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
        `<stop offset="0" stop-color="hsl(${hue},45%,24%)"/>` +
        `<stop offset="1" stop-color="hsl(${(hue + 40) % 360},55%,8%)"/>` +
        "</linearGradient></defs>" +
        '<rect width="1920" height="1080" fill="url(#g)"/>' +
        `<circle cx="${560 + index * 160}" cy="${380 + (index % 3) * 90}" r="${180 + index * 12}" fill="hsl(${(hue + 180) % 360},60%,60%)" opacity=".18"/>` +
        '<rect y="760" width="1920" height="320" fill="#000" opacity=".35"/>' +
        `<text x="96" y="980" fill="#fff" opacity=".55" font-family="sans-serif" font-size="56">Frame ${index + 1}</text>` +
        "</svg>",
    )}`;
  const screenshots = [205, 25, 160, 280, 45, 330].map((hue, index) => {
    const url = frame(hue, index);
    return {
      id: `demo-${index + 1}`,
      filename: `${release}-${String(index).padStart(2, "0")}.png`,
      size: Math.round([4.8, 6.1, 5.2, 7.4, 3.9, 6.6][index] * 1024 * 1024),
      source: index === 5 ? "addition" : "local",
      group: "main",
      image_url: url,
      full_image_url: url,
      can_replace: index !== 5,
      can_delete: true,
    };
  });
  const descriptionContent = `[center][b]The Automation Menace (1968)[/b][/center]

[b]Overview[/b]
The machines took over the assembly lines. Then they took over the city.

[b]Notes[/b]
[list]
[*]Hybrid remux with Dolby Vision and HDR10+ metadata
[*]Ten subtitle tracks
[/list]`;
  const description = {
    success: true,
    content: descriptionContent,
    version: 1,
    sources: [
      {
        key: "description_template_content",
        label: "Template",
        content: descriptionContent,
      },
    ],
  };
  // Other upload tabs shown next to the demo run; they are display-only.
  const tabs = [
    {
      title: "The Automation Menace (1968)",
      detail: release,
      status: "running",
    },
    { title: "Signal From Orbit (1974)", detail: "", status: "input" },
    { title: "Queue (3)", detail: "", status: "scheduled" },
    { title: "Harbor Lights S01", detail: "", status: "done" },
  ];
  const media = {
    media_id: "screenshot-demo",
    title: "The Automation Menace",
    year: "1968",
    category: "MOVIE",
    type: "REMUX",
    source: "BluRay",
    resolution: "2160p",
    path,
    name: release.replaceAll(".", " "),
    genres: ["Science Fiction", "Mystery", "Adventure"],
    metadata_sources: [
      { key: "tmdb", label: "TMDb", value: "0000" },
      { key: "imdb", label: "IMDb", value: "tt0000000" },
    ],
    overview:
      "The Automation Menace is a 1950s-style science-fiction thriller about a prosperous industrial city that embraces a revolutionary automation system promising faster production, cheaper goods, and a brighter future. When the machines take over, who is left in control?",
    detail_sections: [
      {
        key: "movie",
        label: "Movie details",
        items: [
          { key: "audio", label: "Audio", value: "DTS-HD MA 5.1" },
          {
            key: "video",
            label: "Video",
            value: "HEVC · Dolby Vision · HDR10+",
          },
        ],
      },
    ],
    audio_tracks: [
      {
        language: "English",
        language_code: "en",
        format: "DTS-HD MA",
        channels: "5.1",
        default: true,
      },
    ],
    subtitle_tracks: [
      { language: "English", language_code: "en", format: "PGS" },
      {
        language: "Portuguese (Brazil)",
        language_code: "pt-BR",
        format: "PGS",
      },
      { language: "Spanish", language_code: "es", format: "PGS" },
      { language: "French", language_code: "fr", format: "PGS" },
      { language: "German", language_code: "de", format: "PGS" },
      { language: "Italian", language_code: "it", format: "PGS" },
      { language: "Japanese", language_code: "ja", format: "PGS" },
      { language: "Korean", language_code: "ko", format: "PGS" },
      { language: "Chinese", language_code: "zh", format: "PGS" },
      { language: "Dutch", language_code: "nl", format: "PGS" },
    ].map((track, index) => ({ ...track, index: index + 1 })),
    progress,
  };
  const output = `<pre><span style="color:#ffff00">$ python upload.py "${path}"\n→ Starting execution...</span>
<span style="color:#00cc00">Gathering info for ${release}</span>
<span style="color:#aaaa00">Building meta data.....</span>

<span style="color:#00aaaa">Title.....</span> The Automation Menace (1968)
<span style="color:#00aaaa">Category..</span> MOVIE
<span style="color:#00aaaa">Overview..</span> ${media.overview}
<span style="color:#00aaaa">Genre.....</span> Science Fiction, Mystery, Adventure
<span style="color:#00aaaa">TMDB......</span> https://www.themoviedb.org/movie/0000
<span style="color:#00aaaa">IMDB......</span> https://www.imdb.com/title/tt0000000
<span style="color:#00aaaa">Resolution</span> 2160p
<span style="color:#00aaaa">Source....</span> BluRay
<span style="color:#00aaaa">Type......</span> REMUX
<span style="color:#00aaaa">Group Tag.</span> Group

<b>Base Name:</b> ${media.name}

<span style="color:#00cc00">Preparing screenshots, torrent and Usenet archive...</span></pre>`;

  const mediainfo = {
    success: true,
    kind: "mediainfo",
    reports: [
      {
        key: "mediainfo",
        label: "MediaInfo",
        content: `General
Complete name                            : ${release}.mkv
Format                                   : Matroska
File size                                : 72.3 GiB
Duration                                 : 1 h 54 min
Overall bit rate                         : 90.4 Mb/s

Video
ID                                       : 1
Format                                   : HEVC
HDR format                               : Dolby Vision, Profile 7.6, BL+EL+RPU / SMPTE ST 2094 App 4, HDR10+ Profile B compatible
Width                                    : 3 840 pixels
Height                                   : 2 160 pixels
Frame rate                               : 23.976 (24000/1001) FPS
Bit depth                                : 10 bits

Audio
ID                                       : 3
Format                                   : DTS XLL
Commercial name                          : DTS-HD Master Audio
Channel(s)                               : 6 channels
Language                                 : English
Default                                  : Yes

${media.subtitle_tracks
  .map(
    (track) => `Text #${track.index}
ID                                       : ${track.index + 3}
Format                                   : PGS
Language                                 : ${track.language}`,
  )
  .join("\n\n")}`,
      },
    ],
  };

  // Structured events for the GUI output view: the run is paused at a dupe
  // prompt, with fictional trackers in each result state.
  const gib = (value) => Math.round(value * 1024 ** 3);
  const gui = (data) => ({ type: "gui", data });
  const guiEvents = [
    gui({ kind: "stage", key: "prep", status: "start" }),
    gui({ kind: "stage", key: "prep", status: "done" }),
    gui({ kind: "stage", key: "confirm", status: "start" }),
    gui({ kind: "stage", key: "confirm", status: "done" }),
    gui({ kind: "stage", key: "dupes", status: "start" }),
    gui({
      kind: "notice",
      level: "warning",
      text: "Image host returned a slow response; retrying with the next host.",
    }),
    gui({
      kind: "notice",
      level: "attention",
      text: "Distributor 'Fictional Media' is not recognized.",
      tracker: "HELIX",
      key: "distributor:HELIX",
    }),
    gui({
      kind: "slot",
      tracker: "NOVA",
      verdict: "review",
      title: "Review before uploading",
      reason: "A remux with the same audio already fills the UHD slot.",
      slot: "UHD Remux",
      why: "Your release adds HDR10+ metadata, which may qualify it as a trump.",
      rules:
        "Rules as of 2026-01-01. This is only a recommendation; tracker rules change over time.",
    }),
    gui({
      kind: "dupes",
      tracker: "NOVA",
      trumpable: false,
      entries: [
        {
          name: "The Automation Menace 1968 2160p UHD BluRay REMUX DV HEVC DTS-HD MA 5.1-Other",
          size: gib(71.9),
          diff_pct: -1,
          color: "#ff0000",
        },
        {
          name: "The Automation Menace 1968 1080p BluRay REMUX AVC DTS-HD MA 5.1-Other",
          size: gib(34.2),
          diff_pct: -53,
          color: "#00ff00",
        },
      ],
    }),
    gui({
      kind: "tracker",
      tracker: "ORBIT",
      status: "pending",
      message: "No potential dupes found",
    }),
    gui({
      kind: "tracker",
      tracker: "ZENITH",
      status: "dupe",
      message: "Possible dupe on this tracker",
    }),
    gui({
      kind: "tracker",
      tracker: "HELIX",
      status: "skipped",
      message: "Not uploading: missing distributor information.",
    }),
    gui({
      kind: "prompt",
      action: "open",
      id: 1,
      type: "yes_no",
      question: "Upload to NOVA anyway?",
      default: false,
      context: { kind: "dupes", tracker: "NOVA" },
    }),
    gui({ kind: "prompt", action: "close", id: 1 }),
    gui({
      kind: "prompt",
      action: "open",
      id: 3,
      type: "text",
      question: "Input args that need correction e.g. (--tag NTb --category tv --tmdb 12345), 'continue' to keep them, or 'skip' to skip this upload",
      context: { kind: "edit_args", values: { "--category": "movie", "--tmdb": "movie/0000", "--tag": "Group" }, applied: "", actions: [["continue", "Continue without changes"], ["skip", "Skip this upload"]] },
    }),
    { type: "prompt_state", awaiting: true, input_type: "yes_no" },
  ];

  window.UAScreenshotMode = {
    media,
    output,
    guiEvents,
    screenshots,
    description,
    mediainfo,
    tabs,
    // Fail closed for every API call, including shared helpers and mutations.
    // The demo has no backend session and never falls through to a real fetch.
    async apiFetch() {
      return new Response(
        JSON.stringify({
          success: false,
          error:
            "API actions are disabled in screenshot mode. Remove ?screenshot=1 to use the app.",
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      );
    },
  };
})();

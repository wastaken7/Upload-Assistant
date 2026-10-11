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
  ].map(([id, label, current, total, unit, detail]) => ({
    id,
    label,
    current,
    total,
    unit,
    detail,
    status: "running",
  }));
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

  window.UAScreenshotMode = {
    media,
    output,
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

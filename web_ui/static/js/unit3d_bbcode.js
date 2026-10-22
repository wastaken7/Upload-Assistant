// BBCode support for the description editor, modelled on UNIT3D, the
// framework most supported trackers run. parseUnit3dBbcode ports
// app/Helpers/Bbcode.php so the preview matches what those sites render, and
// the toolbar mirrors the buttons and insert behaviour of UNIT3D's
// bbcode-input component. Kept free of React and the DOM so it can be tested
// with node:test; the caller still sanitizes the returned HTML.
(() => {
  const block = (tag, openHtml, closeHtml) => ({
    openBbcode: new RegExp(`\\[${tag}\\]`, "iy"),
    closeBbcode: `[/${tag}]`,
    openHtml,
    closeHtml,
    block: true,
  });
  const inline = (tag, openHtml, closeHtml) => ({
    ...block(tag, openHtml, closeHtml),
    block: false,
  });
  const withParam = (definition, pattern, closeTag) => ({
    ...definition,
    openBbcode: new RegExp(`\\[${pattern}\\]`, "iy"),
    closeBbcode: `[/${closeTag}]`,
  });

  // Order matters: the first opening pattern that matches wins, as in UNIT3D.
  const PARSERS = [
    ...[1, 2, 3, 4, 5, 6].map((level) => [
      `h${level}`,
      block(`h${level}`, `<h${level}>`, `</h${level}>`),
    ]),
    ["bold", inline("b", "<b>", "</b>")],
    ["italic", inline("i", "<i>", "</i>")],
    ["underline", inline("u", "<u>", "</u>")],
    ["linethrough", inline("s", "<s>", "</s>")],
    [
      "size",
      withParam(
        inline(
          "size",
          '<span style="font-size: clamp(10px, $1px, 100px);">',
          "</span>",
        ),
        "size=(\\d+)",
        "size",
      ),
    ],
    [
      "font",
      withParam(
        inline("font", '<span style="font-family: $1;">', "</span>"),
        "font=([a-z0-9 ]+)",
        "font",
      ),
    ],
    [
      "color",
      withParam(
        inline("color", '<span style="color: $1;">', "</span>"),
        "color=(\\#[a-f0-9]{3,4}|\\#[a-f0-9]{6}|\\#[a-f0-9]{8}|[a-z]+)",
        "color",
      ),
    ],
    ...["center", "left", "right"].map((align) => [
      align,
      block(
        align,
        `<div class="bbcode-rendered__${align}" style="text-align: ${align};">`,
        "</div>",
      ),
    ]),
    ["quote", block("quote", "<blockquote>", "</blockquote>")],
    [
      "namedquote",
      withParam(
        block(
          "quote",
          '<blockquote><i class="fas fa-quote-left"></i> <cite>Quoting $1:</cite><p>',
          "</p></blockquote>",
        ),
        "quote=(.*?)",
        "quote",
      ),
    ],
    [
      "orderedlistnumerical",
      withParam(block("list", "<ol>", "</ol>"), "list=1", "list"),
    ],
    [
      "orderedlistalpha",
      withParam(block("list", '<ol type="a">', "</ol>"), "list=a", "list"),
    ],
    ["unorderedlist", block("list", "<ul>", "</ul>")],
    [
      "code",
      // UNIT3D wires the copy button with Alpine; the editor wires it itself.
      block(
        "code",
        '<div class="bbcode-rendered__clipboard"><pre><code>',
        '</code></pre><div class="bbcode-rendered__clipboard-container"><button type="button" class="bbcode-rendered__clipboard-button" title="Copy"></button></div></div>',
      ),
    ],
    ["pre", inline("pre", "<code>", "</code>")],
    ["alert", block("alert", '<div class="bbcode-rendered__alert">', "</div>")],
    ["note", block("note", '<div class="bbcode-rendered__note">', "</div>")],
    ["sub", inline("sub", "<sub>", "</sub>")],
    ["sup", inline("sup", "<sup>", "</sup>")],
    ["small", inline("small", "<small>", "</small>")],
    ["table", block("table", "<table>", "</table>")],
    ["table-row", block("tr", "<tr>", "</tr>")],
    ["table-header", block("th", "<th>", "</th>")],
    ["table-data", block("td", "<td>", "</td>")],
    [
      "spoiler",
      inline(
        "spoiler",
        '<details><summary>Spoiler</summary><div style="text-align:left;">',
        "</div></details>",
      ),
    ],
    [
      "named-spoiler",
      withParam(
        inline(
          "spoiler",
          '<details><summary>$1</summary><div style="text-align:left;">',
          "</div></details>",
        ),
        "spoiler=(.*?)",
        "spoiler",
      ),
    ],
  ];
  const PARSERS_BY_NAME = Object.fromEntries(PARSERS);
  const URL_PROTOCOL_WHITELIST = [
    "http",
    "https",
    "irc",
    "ftp",
    "sftp",
    "magnet",
  ];

  // Same escaping as PHP's htmlspecialchars with ENT_QUOTES | ENT_HTML5.
  const escapeHtml = (value) =>
    value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&apos;");

  // UNIT3D also routes non-whitelisted images through an image proxy and
  // resolves root-relative links against the tracker. Neither applies to a
  // local preview, so those URLs are left for the caller's sanitizer.
  const sanitizeUrl = (url) => {
    if (url.startsWith("/")) return url;
    const scheme = url.match(/^([a-z][a-z0-9+.-]*):/i)?.[1]?.toLowerCase();
    const absolute = URL_PROTOCOL_WHITELIST.includes(scheme)
      ? url
      : `https://${url}`;
    try {
      if (/\s/.test(absolute)) return "Broken link";
      new URL(absolute);
      return absolute;
    } catch (_error) {
      return "Broken link";
    }
  };

  const youtubeEmbed = (id) =>
    `<iframe width="560" height="315" src="https://www.youtube-nocookie.com/embed/${id}?rel=0" allow="autoplay; encrypted-media" allowfullscreen></iframe>`;

  // UNIT3D opens comparisons in a full-screen viewer; the preview shows the
  // same screenshots side by side inside a collapsible block instead.
  const renderComparison = (_match, names, body) => {
    const comparates = names.split(/\s*,\s*/);
    const urls = body.split(/\s*(?:,|\s)\s*/).map((url) => sanitizeUrl(url));
    const rows = [];
    for (let index = 0; index < urls.length; index += comparates.length) {
      rows.push(urls.slice(index, index + comparates.length));
    }
    const columns = `grid-template-columns: repeat(${comparates.length}, minmax(0, 1fr));`;
    const title = comparates
      .map((name, index) =>
        index === comparates.length - 1
          ? `${name}:`
          : `${name} <span class="comparison__divider">vs</span>`,
      )
      .join(" ");
    const screenshots = rows
      .map(
        (row, rowIndex) =>
          `<li><ul class="comparison__row" style="${columns}">${row
            .map(
              (url, index) =>
                `<li class="comparison__image-container"><figure class="comparison__figure">${
                  rowIndex === 0
                    ? `<figcaption class="comparison__figcaption">${comparates[index] || ""}</figcaption>`
                    : ""
                }<img class="comparison__image" src="${url}" loading="lazy"></figure></li>`,
            )
            .join("")}</ul></li>`,
      )
      .join("");
    return `<details class="comparison"><summary class="comparison__text">${title} <span class="comparison__button">Show</span></summary><ul class="comparison__screenshots">${screenshots}</ul></details>`;
  };

  // Removes the line breaks around a block tag so block BBCode can sit on its
  // own lines without adding extra spacing. Returns the new source and index.
  const handleBlockElementSpacing = (
    source,
    index,
    tagStartIndex,
    tagStopIndex,
  ) => {
    let text = source;
    let nextIndex = index;
    for (let pass = 0; pass < 2; pass++) {
      const stopIndex = text.length - 1;
      if (
        tagStopIndex + 2 <= stopIndex &&
        text.substr(tagStopIndex + 1, 2) === "\r\n"
      ) {
        text = text.slice(0, tagStopIndex + 1) + text.slice(tagStopIndex + 3);
      } else if (
        tagStopIndex + 1 <= stopIndex &&
        text[tagStopIndex + 1] === "\n"
      ) {
        text = text.slice(0, tagStopIndex + 1) + text.slice(tagStopIndex + 2);
      }
    }
    if (tagStartIndex >= 2 && text.substr(tagStartIndex - 2, 2) === "\r\n") {
      text = text.slice(0, tagStartIndex - 2) + text.slice(tagStartIndex);
      nextIndex -= 2;
    } else if (tagStartIndex >= 1 && text[tagStartIndex - 1] === "\n") {
      text = text.slice(0, tagStartIndex - 1) + text.slice(tagStartIndex);
      nextIndex -= 1;
    }
    return { source: text, index: nextIndex };
  };

  const parseUnit3dBbcode = (content, replaceLineBreaks = true) => {
    let source = escapeHtml(String(content ?? ""));

    // Void elements and tags whose content moves into an attribute.
    source = source.split("[*]").join("<li>").split("[hr]").join("<hr>");
    source = source
      .replace(/\[url\](.*?)\[\/url\]/gi, (_match, url) => {
        const safeUrl = sanitizeUrl(url);
        return `<a href="${safeUrl}">${safeUrl}</a>`;
      })
      .replace(
        /\[url=(.*?)\](.*?)\[\/url\]/gi,
        (_match, url, text) => `<a href="${sanitizeUrl(url)}">${text}</a>`,
      )
      .replace(
        /\[img\](.*?)\[\/img\]/gi,
        (_match, url) =>
          `<img src="${sanitizeUrl(url)}" loading="lazy" class="img-responsive" style="display: inline !important;">`,
      )
      .replace(
        /\[img width=(\d+)\](.*?)\[\/img\]/gi,
        (_match, width, url) =>
          `<img src="${sanitizeUrl(url)}" loading="lazy" width="${width}px">`,
      )
      .replace(
        /\[img=(\d+)(?:x\d+)?\](.*?)\[\/img\]/gi,
        (_match, width, url) =>
          `<img src="${sanitizeUrl(url)}" loading="lazy" width="${width}px">`,
      )
      .replace(/\[youtube\]([a-z0-9_-]{11})\[\/youtube\]/gi, (_match, id) =>
        youtubeEmbed(id),
      )
      .replace(/\[video\]([a-z0-9_-]{11})\[\/video\]/gi, (_match, id) =>
        youtubeEmbed(id),
      )
      .replace(
        /\[video=&quot;youtube&quot;\]([a-z0-9_-]{11})\[\/video\]/gi,
        (_match, id) => youtubeEmbed(id),
      )
      .replace(
        /\[comparison=([\s\S]*?)\]\s*([\s\S]*?)\s*\[\/comparison\]/gi,
        renderComparison,
      );

    const openedElements = [];
    let index = 0;
    while (index < source.length) {
      index = source.indexOf("[", index);
      if (index === -1 || index + 1 >= source.length) break;

      if (source[index + 1] === "/" && openedElements.length) {
        const name = openedElements.pop();
        const element = PARSERS_BY_NAME[name];
        const tag = source.substr(index, element.closeBbcode.length);
        // A closing tag that does not match the innermost open element stays
        // as text, and that element stays open.
        if (tag.toLowerCase() === element.closeBbcode.toLowerCase()) {
          source =
            source.slice(0, index) +
            element.closeHtml +
            source.slice(index + element.closeBbcode.length);
          if (replaceLineBreaks && element.block) {
            ({ source, index } = handleBlockElementSpacing(
              source,
              index,
              index,
              index + element.closeHtml.length - 1,
            ));
          }
        } else {
          openedElements.push(name);
        }
      } else {
        for (const [name, element] of PARSERS) {
          element.openBbcode.lastIndex = index;
          const match = element.openBbcode.exec(source);
          if (!match) continue;
          const replacement = element.openHtml.replace(
            /\$1/g,
            () => match[1] ?? "",
          );
          source =
            source.slice(0, index) +
            replacement +
            source.slice(index + match[0].length);
          if (replaceLineBreaks && element.block) {
            ({ source, index } = handleBlockElementSpacing(
              source,
              index,
              index,
              index + replacement.length - 1,
            ));
          }
          openedElements.push(name);
          break;
        }
      }
      index++;
    }

    while (openedElements.length) {
      source += PARSERS_BY_NAME[openedElements.pop()].closeHtml;
    }
    if (replaceLineBreaks) {
      source = source.replace(/\r?\n/g, "<br>");
    }
    return source;
  };

  // The toolbar of UNIT3D's BBCode input, in its order and groups.
  const UNIT3D_BBCODE_TOOLBAR = Object.freeze([
    [
      { title: "Bold", icon: "bold", open: "[b]", close: "[/b]", key: "b" },
      {
        title: "Italics",
        icon: "italic",
        open: "[i]",
        close: "[/i]",
        key: "i",
      },
      {
        title: "Underline",
        icon: "underline",
        open: "[u]",
        close: "[/u]",
        key: "u",
      },
      {
        title: "Strikethrough",
        icon: "strikethrough",
        open: "[s]",
        close: "[/s]",
      },
    ],
    [
      {
        title: "Insert image",
        icon: "image",
        open: "[img=350]",
        close: "[/img]",
      },
      {
        title: "Insert YouTube",
        icon: "circle-play",
        open: '[video="youtube"]',
        close: "[/video]",
      },
      { title: "Link", icon: "link", open: "[url]", close: "[/url]" },
    ],
    [
      {
        title: "Unordered list",
        icon: "list",
        open: "\n[list]\n[*]",
        close: "\n[/list]\n",
      },
      {
        title: "Ordered list",
        icon: "list-ordered",
        open: "\n[list=1]\n[*]",
        close: "\n[/list]\n",
      },
    ],
    [
      {
        title: "Font color",
        icon: "palette",
        open: "[color=]",
        close: "[/color]",
      },
      {
        title: "Font size",
        icon: "a-large-small",
        open: "[size=]",
        close: "[/size]",
      },
      { title: "Font family", icon: "type", open: "[font=]", close: "[/font]" },
    ],
    [
      {
        title: "Align left",
        icon: "align-left",
        open: "\n[left]\n",
        close: "\n[/left]\n",
      },
      {
        title: "Align center",
        icon: "align-center",
        open: "\n[center]\n",
        close: "\n[/center]\n",
      },
      {
        title: "Align right",
        icon: "align-right",
        open: "\n[right]\n",
        close: "\n[/right]\n",
      },
    ],
    [
      {
        title: "Quote",
        icon: "quote",
        open: "\n[quote]\n",
        close: "\n[/quote]\n",
      },
      { title: "Code", icon: "code", open: "[code]", close: "[/code]" },
      {
        title: "Spoiler",
        icon: "eye-off",
        open: "[spoiler]",
        close: "[/spoiler]",
      },
      { title: "Note", icon: "sticky-note", open: "[note]", close: "[/note]" },
      {
        title: "Alert",
        icon: "triangle-alert",
        open: "[alert]",
        close: "[/alert]",
      },
      {
        title: "Table",
        icon: "table",
        open: "[table]\n[tr]\n[td]",
        close: "[/td]\n[/tr]\n[/table]",
      },
    ],
  ]);

  // Wraps the selection in a tag pair, or unwraps it when the selection is
  // already exactly wrapped by it. Tags ending in "=" leave the caret on the
  // parameter, as UNIT3D does.
  const insertBbcodeTags = (value, start, end, openTag, closeTag) => {
    // The selection must hold both tags; a caret between "[/b]" and "[b]"
    // would otherwise match and corrupt the text.
    const alreadyNested =
      end - start >= openTag.length + closeTag.length &&
      value.substring(start, start + openTag.length) === openTag &&
      value.substring(end - closeTag.length, end) === closeTag;
    const nextValue = alreadyNested
      ? value.substring(0, start) +
        value.substring(start + openTag.length, end - closeTag.length) +
        value.substring(end)
      : value.substring(0, start) +
        openTag +
        value.substring(start, end) +
        closeTag +
        value.substring(end);

    let selectionStart = start;
    let selectionEnd;
    if (openTag.endsWith("=]")) {
      selectionStart = start + openTag.length - 1;
      selectionEnd = selectionStart;
    } else if (start === end) {
      selectionStart = start + openTag.length;
      selectionEnd = selectionStart;
    } else if (alreadyNested) {
      selectionEnd = end - openTag.length - closeTag.length;
    } else {
      selectionEnd = end + openTag.length + closeTag.length;
    }
    return { value: nextValue, selectionStart, selectionEnd };
  };

  window.UAUnit3dBbcode = {
    UNIT3D_BBCODE_TOOLBAR,
    insertBbcodeTags,
    parseUnit3dBbcode,
  };
})();

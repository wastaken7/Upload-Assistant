const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const loadBbcode = () => {
  const context = { window: {}, URL };
  vm.runInNewContext(
    fs.readFileSync(
      path.join(__dirname, "../web_ui/static/js/unit3d_bbcode.js"),
      "utf8",
    ),
    context,
  );
  return context.window.UAUnit3dBbcode;
};

const { parseUnit3dBbcode, insertBbcodeTags, UNIT3D_BBCODE_TOOLBAR } =
  loadBbcode();

const YOUTUBE_FRAME =
  '<iframe width="560" height="315" src="https://www.youtube-nocookie.com/embed/abcdefghijk?rel=0" allow="autoplay; encrypted-media" allowfullscreen></iframe>';

test("escapes HTML before parsing tags", () => {
  assert.equal(
    parseUnit3dBbcode('<script>alert("x")</script> & [b]bold[/b]'),
    "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; <b>bold</b>",
  );
});

test("renders inline formatting like UNIT3D", () => {
  assert.equal(
    parseUnit3dBbcode(
      "[B]b[/b] [i]i[/i] [u]u[/u] [s]s[/s] [sub]1[/sub][sup]2[/sup] [small]x[/small] [pre]p[/pre]",
    ),
    "<b>b</b> <i>i</i> <u>u</u> <s>s</s> <sub>1</sub><sup>2</sup> <small>x</small> <code>p</code>",
  );
  assert.equal(
    parseUnit3dBbcode(
      "[size=24]big[/size][font=Courier New]mono[/font][color=#ff0000]red[/color]",
    ),
    '<span style="font-size: clamp(10px, 24px, 100px);">big</span>' +
      '<span style="font-family: Courier New;">mono</span>' +
      '<span style="color: #ff0000;">red</span>',
  );
});

test("leaves tags with invalid parameters as text", () => {
  assert.equal(
    parseUnit3dBbcode("[color=red;x]text[/color] [font=a;b]f[/font]"),
    "[color=red;x]text[/color] [font=a;b]f[/font]",
  );
});

test("removes line breaks around block tags", () => {
  assert.equal(
    parseUnit3dBbcode("Intro\n[center]\nMiddle\n[/center]\n\nAfter\nEnd"),
    'Intro<div class="bbcode-rendered__center" style="text-align: center;">Middle</div>After<br>End',
  );
  assert.equal(
    parseUnit3dBbcode("[list]\r\n[*]One\r\n[*]Two\r\n[/list]"),
    "<ul><li>One<br><li>Two</ul>",
  );
  assert.equal(
    parseUnit3dBbcode("[list=1][*]a[/list][list=a][*]b[/list][hr]"),
    '<ol><li>a</ol><ol type="a"><li>b</ol><hr>',
  );
});

test("keeps mismatched closing tags as text and closes open tags", () => {
  assert.equal(parseUnit3dBbcode("[b]x[/i]"), "<b>x[/i]</b>");
  assert.equal(
    parseUnit3dBbcode("[spoiler]hidden"),
    '<details><summary>Spoiler</summary><div style="text-align:left;">hidden</div></details>',
  );
});

test("renders quotes, spoilers, notes, alerts and tables", () => {
  assert.equal(
    parseUnit3dBbcode("[quote=Example User]Hi[/quote]"),
    '<blockquote><i class="fas fa-quote-left"></i> <cite>Quoting Example User:</cite><p>Hi</p></blockquote>',
  );
  assert.equal(
    parseUnit3dBbcode("[spoiler=Full MediaInfo]x[/spoiler]"),
    '<details><summary>Full MediaInfo</summary><div style="text-align:left;">x</div></details>',
  );
  assert.equal(
    parseUnit3dBbcode("[note]n[/note][alert]a[/alert]"),
    '<div class="bbcode-rendered__note">n</div><div class="bbcode-rendered__alert">a</div>',
  );
  assert.equal(
    parseUnit3dBbcode("[table]\n[tr]\n[th]H[/th]\n[td]D[/td]\n[/tr]\n[/table]"),
    "<table><tr><th>H</th><td>D</td></tr></table>",
  );
  assert.match(
    parseUnit3dBbcode("[code]x = 1[/code]"),
    /^<div class="bbcode-rendered__clipboard"><pre><code>x = 1<\/code><\/pre>/,
  );
});

test("sanitizes link and image URLs", () => {
  assert.equal(
    parseUnit3dBbcode("[url=example.test/page]site[/url]"),
    '<a href="https://example.test/page">site</a>',
  );
  assert.equal(
    parseUnit3dBbcode("[url]https://example.test/?a=1&b=2[/url]"),
    '<a href="https://example.test/?a=1&amp;b=2">https://example.test/?a=1&amp;b=2</a>',
  );
  assert.equal(
    parseUnit3dBbcode("[url]javascript:alert(1)[/url]"),
    '<a href="Broken link">Broken link</a>',
  );
  assert.equal(
    parseUnit3dBbcode(
      "[img]https://img.test/a.png[/img][img=350]https://img.test/b.png[/img][img width=200]https://img.test/c.png[/img]",
    ),
    '<img src="https://img.test/a.png" loading="lazy" class="img-responsive" style="display: inline !important;">' +
      '<img src="https://img.test/b.png" loading="lazy" width="350px">' +
      '<img src="https://img.test/c.png" loading="lazy" width="200px">',
  );
});

test("embeds YouTube videos", () => {
  assert.equal(
    parseUnit3dBbcode(
      '[youtube]abcdefghijk[/youtube][video]abcdefghijk[/video][video="youtube"]abcdefghijk[/video]',
    ),
    YOUTUBE_FRAME.repeat(3),
  );
  assert.equal(
    parseUnit3dBbcode("[youtube]short[/youtube]"),
    "[youtube]short[/youtube]",
  );
});

test("renders comparisons with one column per source", () => {
  const html = parseUnit3dBbcode(
    "[comparison=Source, Encode]\nhttps://img.test/1.png https://img.test/2.png\nhttps://img.test/3.png, https://img.test/4.png\n[/comparison]",
  );
  assert.match(
    html,
    /^<details class="comparison"><summary class="comparison__text">Source <span class="comparison__divider">vs<\/span> Encode:/,
  );
  assert.equal(html.match(/<img /g).length, 4);
  assert.equal(html.match(/<figcaption /g).length, 2);
  assert.equal(html.match(/repeat\(2, minmax\(0, 1fr\)\)/g).length, 2);
  assert.doesNotMatch(html, /<br>/);
});

test("wraps the selection like UNIT3D's editor", () => {
  assert.deepEqual(
    { ...insertBbcodeTags("say hello", 4, 9, "[b]", "[/b]") },
    { value: "say [b]hello[/b]", selectionStart: 4, selectionEnd: 16 },
  );
  assert.deepEqual(
    { ...insertBbcodeTags("say ", 4, 4, "[b]", "[/b]") },
    { value: "say [b][/b]", selectionStart: 7, selectionEnd: 7 },
  );
});

test("unwraps a selection that is already wrapped", () => {
  assert.deepEqual(
    { ...insertBbcodeTags("say [b]hello[/b]", 4, 16, "[b]", "[/b]") },
    { value: "say hello", selectionStart: 4, selectionEnd: 9 },
  );
});

test("inserts at a caret between two tag pairs instead of unwrapping", () => {
  assert.deepEqual(
    { ...insertBbcodeTags("[b]a[/b][b]b[/b]", 8, 8, "[b]", "[/b]") },
    {
      value: "[b]a[/b][b][/b][b]b[/b]",
      selectionStart: 11,
      selectionEnd: 11,
    },
  );
});

test("puts the caret on the parameter of tags ending in =", () => {
  assert.deepEqual(
    { ...insertBbcodeTags("red", 0, 3, "[color=]", "[/color]") },
    { value: "[color=]red[/color]", selectionStart: 7, selectionEnd: 7 },
  );
});

test("toolbar tags render through the parser", () => {
  const parameters = { "[color=]": "red", "[size=]": "12", "[font=]": "Arial" };
  for (const tool of UNIT3D_BBCODE_TOOLBAR.flat()) {
    const open = tool.open.replace("=]", `=${parameters[tool.open] || ""}]`);
    const content = tool.icon === "circle-play" ? "abcdefghijk" : "x";
    const html = parseUnit3dBbcode(`${open}${content}${tool.close}`);
    assert.doesNotMatch(html, /\[\/?[a-z]+/i, `${tool.title}: ${html}`);
  }
});

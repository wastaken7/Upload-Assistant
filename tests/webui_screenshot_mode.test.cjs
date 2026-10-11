const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const assert = require("node:assert/strict");
const babel = require("../web_ui/static/js/node_modules/@babel/core");
const read = (file) =>
  fs.readFileSync(path.join(__dirname, "../web_ui/static/js", file), "utf8");
const source = read("screenshot_mode.js");
const shared = read("shared_utils.js");
const ast = babel.parseSync(shared, { parserOpts: { plugins: ["jsx"] } });
const helper = ast.program.body[0].expression.callee.body.body.find(
  (node) => node.id?.name === "uaApiFetch",
);

function fixture(demo) {
  const context = vm.createContext({
    window: {},
    Response,
    loadCsrfToken: async () => {
      throw new Error("Unexpected CSRF request");
    },
    fetch: async () => {
      throw new Error("Unexpected network request");
    },
  });
  if (demo) vm.runInContext(source, context);
  vm.runInContext(shared.slice(helper.start, helper.end), context);
  return context;
}

test("demo reads and writes never reach the network or CSRF helpers", async () => {
  const context = fixture(true);
  for (const method of ["GET", "POST", "PUT", "PATCH", "DELETE"]) {
    for (const endpoint of [
      "/api/execute",
      "/api/kill",
      "/api/input",
      "/api/browse_roots",
      "/api/trackers",
      "/api/config_update",
      "/logout",
      "/unknown",
    ]) {
      const response = await context.uaApiFetch(endpoint, { method });
      assert.equal(response.status, 409);
      assert.equal((await response.json()).success, false);
    }
  }
});

test("normal mode keeps the existing authenticated network path", async () => {
  const context = fixture(false);
  let csrfCalls = 0;
  context.loadCsrfToken = async () => {
    csrfCalls++;
  };
  context.uaCsrfToken = "fictional-token";
  context.fetch = async (url, options) => {
    assert.equal(url, "/api/browse_roots");
    assert.equal(options.headers["X-CSRF-Token"], "fictional-token");
    return new Response("{}", { status: 200 });
  };
  const response = await context.uaApiFetch("/api/browse_roots");
  assert.equal(response.status, 200);
  assert.equal(csrfCalls, 1);
});

test("demo metadata and progress remain stable across API actions", async () => {
  const context = fixture(true);
  const demo = context.window.UAScreenshotMode;
  const before = JSON.stringify(demo.media);
  assert.equal(demo.media.title, "The Automation Menace");
  assert.equal(demo.media.progress.length, 5);
  assert.ok(
    demo.media.progress.every(
      (item) => item.current > 0 && item.current < item.total,
    ),
  );
  assert.ok(demo.output.includes(demo.media.path));
  await context.uaApiFetch("/api/kill", { method: "POST" });
  assert.equal(JSON.stringify(demo.media), before);
});

const appSource = read("app.js");
const appAst = babel.parseSync(appSource, { parserOpts: { plugins: ["jsx"] } });
const controls = appAst.program.body.find(
  (node) => node.id?.name === "ScreenshotModeControls",
);
const selectArtwork = controls.body.body.find(
  (node) => node.declarations?.[0]?.id.name === "selectArtwork",
);

test("poster and backdrop use separate browser storage and survive storage failure", () => {
  for (const [label, key, storageAvailable] of [
    ["Poster", "ua_screenshot_poster", true],
    ["Poster", "ua_screenshot_poster", false],
    ["Backdrop", "ua_screenshot_backdrop", true],
    ["Backdrop", "ua_screenshot_backdrop", false],
  ]) {
    let poster;
    let message;
    let savedKey;
    const context = vm.createContext({
      label,
      key,
      onSelect: (value) => {
        poster = value;
      },
      setMessage: (value) => {
        message = value;
      },
      localStorage: {
        setItem: (key) => {
          savedKey = key;
          if (!storageAvailable) throw new Error("Storage full");
        },
      },
      FileReader: class {
        readAsDataURL() {
          this.result = "data:image/png;base64,fictional-poster";
          this.onload();
        }
      },
      event: {
        target: {
          files: [{ type: "image/png", size: 1024 }],
          value: "poster.png",
        },
      },
    });
    vm.runInContext(
      appSource.slice(selectArtwork.start, selectArtwork.end),
      context,
    );
    vm.runInContext("selectArtwork(event, label, key, onSelect)", context);
    assert.equal(poster, "data:image/png;base64,fictional-poster");
    assert.equal(savedKey, key);
    assert.ok(message.startsWith(label));
    assert.equal(context.event.target.value, "");
    assert.ok(
      message.includes(storageAvailable ? "saved" : "unavailable or full"),
    );
  }
});

test("artwork selection rejects oversized images and other file types before reading", () => {
  for (const file of [
    { type: "image/svg+xml", size: 1024 },
    { type: "image/jpeg", size: 5 * 1024 * 1024 },
  ]) {
    let message;
    const context = vm.createContext({
      setMessage: (value) => {
        message = value;
      },
      FileReader: class {
        constructor() {
          throw new Error("Must not read rejected files");
        }
      },
      event: { target: { files: [file], value: "poster" } },
    });
    vm.runInContext(
      appSource.slice(selectArtwork.start, selectArtwork.end),
      context,
    );
    vm.runInContext("selectArtwork(event, 'Backdrop')", context);
    assert.ok(message.includes("up to 4 MiB"));
  }
});

test("demo subtitles resolve to ten distinct available flags", () => {
  const context = fixture(true);
  vm.runInContext(read("language_flags_data.js"), context);
  vm.runInContext(read("language_flags.js"), context);
  const tracks = context.window.UAScreenshotMode.media.subtitle_tracks;
  const flags = tracks.map((track) =>
    context.window.getUAPreviewLanguageFlag(
      track.language,
      track.language_code,
    ),
  );
  assert.equal(tracks.length, 10);
  assert.ok(flags.every(Boolean));
  assert.equal(new Set(flags).size, 10);
  assert.equal(new Set(tracks.map((track) => track.index)).size, 10);
  for (const flag of flags) {
    assert.ok(fs.existsSync(path.join(__dirname, "../web_ui", flag)));
  }
});

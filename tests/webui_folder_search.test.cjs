const fs = require("node:fs");
const vm = require("node:vm");
const test = require("node:test");
const assert = require("node:assert/strict");
const babel = require("../web_ui/static/js/node_modules/@babel/core");
const source = fs.readFileSync(
  require.resolve("../web_ui/static/js/app.js"),
  "utf8",
);
const nodes = [];
function walk(node) {
  if (!node || typeof node !== "object") return;
  if (node.type) nodes.push(node);
  for (const [key, value] of Object.entries(node)) {
    if (["loc", "comments", "tokens"].includes(key)) continue;
    if (Array.isArray(value)) value.forEach(walk);
    else if (value && typeof value === "object") walk(value);
  }
}
walk(babel.parseSync(source, { parserOpts: { plugins: ["jsx"] } }));
function fixture() {
  let timer;
  const requests = [];
  const context = vm.createContext({
    console,
    Promise,
    Set,
    encodeURIComponent,
    API_BASE: "/api",
    fileBrowserSearchId: { current: 0 },
    fileBrowserSearchTimer: { current: null },
    fileBrowserSearchCompletion: { current: null },
    fileBrowserSearchQuery: { current: "" },
    fileBrowserFolderOnlyRef: { current: false },
    fileBrowserFolderRef: { current: "" },
    expandedFolders: new Set(),
    setFileBrowserSearch(value) {
      context.query = value;
      context.fileBrowserSearch = value;
    },
    setFileBrowserSearchResults(value) {
      context.results = value;
      context.fileBrowserSearchResults = value;
    },
    setFileBrowserSearchLoading(value) {
      context.loading = value;
      context.fileBrowserSearchLoading = value;
    },
    setFileBrowserFolderOnly(value) {
      context.mode = value;
    },
    setFileBrowserFolder(value) {
      context.folder = value;
    },
    setExpandedFolders() {},
    setLoadingFolders() {},
    loadFolderContents: async () => {},
    setTimeout(fn) {
      timer = fn;
      return 1;
    },
    clearTimeout() {
      timer = null;
    },
    apiFetch: async (url) => {
      requests.push(url);
      return { ok: true, json: async () => ({ success: true, items: [] }) };
    },
  });
  for (const name of [
    "invalidateFileBrowserSearch",
    "changeFileBrowserSearchMode",
    "setFileBrowserSearchFolder",
    "handleFileBrowserSearch",
    "toggleFolder",
    "collapseFileBrowser",
  ]) {
    const node = nodes.findLast(
      (n) => n.type === "VariableDeclarator" && n.id.name === name,
    );
    assert.ok(node, `Missing ${name}`);
    vm.runInContext(
      `var ${name} = ${source.slice(node.init.start, node.init.end)};`,
      context,
    );
  }
  return { context, requests, run: () => timer?.(), queued: () => timer };
}

test("optional scope follows navigation, retains query, blocks missing scope and never scans on toggle", async () => {
  const { context: c, requests, run } = fixture();
  assert.match(
    source,
    /\[fileBrowserFolderOnly, setFileBrowserFolderOnly\] = useState\(false\)/,
  );
  c.handleFileBrowserSearch("movie");
  await run();
  assert.equal(
    new URL(requests[0], "https://example.test").searchParams.has("path"),
    false,
  );
  c.changeFileBrowserSearchMode(true);
  assert.equal(c.query, "movie");
  assert.equal(requests.length, 1);
  await c.handleFileBrowserSearch("movie");
  assert.equal(
    c.results,
    null,
    "Missing scope must leave tree navigation available",
  );
  assert.match(source, /Select a folder in the tree before searching/);
  assert.equal(requests.length, 1);
  await c.toggleFolder("/media/parent");
  await c.toggleFolder("/media/parent/child");
  c.handleFileBrowserSearch("movie");
  await run();
  assert.equal(
    new URL(requests.at(-1), "https://example.test").searchParams.get("path"),
    "/media/parent/child",
  );
  await c.toggleFolder("/media/parent");
  assert.equal(c.fileBrowserFolderRef.current, "/media/parent");
  c.collapseFileBrowser();
  assert.equal(c.fileBrowserFolderRef.current, "");
  assert.equal(c.query, "movie");
  assert.equal(c.results, null);
  c.directories = [{ path: "/media/visible", type: "folder", children: [] }];
  c.sortItems = (items) => items;
  const visible = nodes.findLast(
    (node) =>
      node.type === "VariableDeclarator" && node.id.name === "getVisiblePaths",
  );
  vm.runInContext(
    `var getVisiblePaths = ${source.slice(visible.init.start, visible.init.end)};`,
    c,
  );
  assert.deepEqual(
    Array.from(c.getVisiblePaths()),
    ["/media/visible"],
    "Retained query must not hide tree paths from range/select-all operations",
  );
});

test("mode changes cancel queued searches and invalidate in-flight results", async () => {
  const { context: c, requests, run, queued } = fixture();
  c.handleFileBrowserSearch("queued");
  const alreadyQueued = queued();
  c.changeFileBrowserSearchMode(true);
  await alreadyQueued();
  assert.equal(requests.length, 0);
  c.setFileBrowserSearchFolder("/media/child");
  let finish;
  c.apiFetch = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  c.handleFileBrowserSearch("movie");
  const pending = run();
  c.changeFileBrowserSearchMode(false);
  finish({
    ok: true,
    json: async () => ({ success: true, items: [{ name: "stale" }] }),
  });
  await pending;
  assert.equal(c.results, null);
  assert.equal(c.loading, false);
});

test("old refresh callbacks read current mode in both directions", async () => {
  for (const enabled of [true, false]) {
    const { context: c, requests, run } = fixture();
    const oldHandler = c.handleFileBrowserSearch;
    c.fileBrowserFolderOnlyRef.current = !enabled;
    c.setFileBrowserSearchFolder("/media/child");
    c.changeFileBrowserSearchMode(enabled);
    oldHandler("fresh movie");
    await run();
    assert.equal(
      new URL(requests[0], "https://example.test").searchParams.get("path"),
      enabled ? "/media/child" : null,
    );
  }
});

test("tree navigation keeps all-locations results and HTML errors stay readable", async () => {
  const { context: c, run } = fixture();
  c.console = { ...console, error() {} };
  c.handleFileBrowserSearch("movie");
  await run();
  assert.ok(c.results, "Search should produce results");
  await c.toggleFolder("/media/parent");
  assert.ok(c.results, "Navigation must not clear all-locations results");
  c.changeFileBrowserSearchMode(true);
  c.handleFileBrowserSearch("movie");
  await run();
  await c.toggleFolder("/media/parent");
  assert.ok(c.results, "Re-activating the same scope must not clear results");
  c.apiFetch = async () => ({
    ok: false,
    status: 504,
    json: async () => {
      throw new SyntaxError("Unexpected token '<'");
    },
  });
  c.handleFileBrowserSearch("movie");
  await run();
  assert.equal(c.results.error, "Search request failed (504)");
});

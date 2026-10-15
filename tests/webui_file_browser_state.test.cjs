const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const babel = require("../web_ui/static/js/node_modules/@babel/core");
const source = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/app.js"),
  "utf8",
);
const ast = babel.parseSync(source, { parserOpts: { plugins: ["jsx"] } });
const nodes = [];
function walk(n) {
  if (!n || typeof n !== "object") return;
  if (n.type) nodes.push(n);
  for (const [k, v] of Object.entries(n)) {
    if (["loc", "tokens", "comments"].includes(k)) continue;
    if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") walk(v);
  }
}
walk(ast);
const declarations = new Map(
  nodes
    .filter(
      (n) => n.type === "VariableDeclarator" && n.id.type === "Identifier",
    )
    .map((n) => [n.id.name, n.init]),
);
const context = vm.createContext({
  console,
  Set,
  Map,
  Number,
  JSON,
  Promise,
  encodeURIComponent,
  AbortController,
  TextDecoder,
  Date,
  setTimeout,
  clearTimeout,
});
function load(name) {
  const n = declarations.get(name);
  vm.runInContext(`var ${name} = ${source.slice(n.start, n.end)};`, context);
}
const saved = new Map();
context.storage = { get: (k) => saved.get(k), set: (k, v) => saved.set(k, v) };
for (const n of [
  "FILE_BROWSER_EXPANDED_KEY",
  "FILE_BROWSER_SCROLL_KEY",
  "FILE_BROWSER_SORT_KEY",
  "getStoredExpandedFolders",
  "sortFolderPathsByDepth",
  "getFileBrowserRestorePaths",
  "getStoredFileBrowserSort",
])
  load(n);
const plain = (value) => JSON.parse(JSON.stringify(value));
test("file-browser persistence, restoration, refresh and execution outcomes", async () => {
  assert.equal(context.getStoredExpandedFolders().size, 0);
  for (const v of ["bad", "{}", "null"]) {
    saved.set(context.FILE_BROWSER_EXPANDED_KEY, v);
    assert.equal(context.getStoredExpandedFolders().size, 0);
  }
  saved.set(
    context.FILE_BROWSER_EXPANDED_KEY,
    JSON.stringify(["/data/a/b", null, "/data", 42, "", "/data/a", "/data"]),
  );
  assert.deepEqual(
    [...context.sortFolderPathsByDepth(context.getStoredExpandedFolders())],
    ["/data", "/data/a", "/data/a/b"],
  );
  saved.set(context.FILE_BROWSER_SORT_KEY, "size-desc");
  assert.deepEqual(plain(context.getStoredFileBrowserSort()), {
    by: "size",
    order: "desc",
  });
  let tree = [];
  const requests = [];
  context.API_BASE = "/api";
  context.setDirectories = (next) => {
    tree = typeof next === "function" ? next(tree) : next;
  };
  context.expandedFoldersRef = { current: context.getStoredExpandedFolders() };
  context.setFileBrowserRestoring = (value) => {
    context.restoring = value;
  };
  const folder = (path, children = []) => ({ path, type: "folder", children });
  const responses = {
    "/api/browse_roots": { success: true, items: [folder("/data")] },
    "/api/browse?path=%2Fdata": { success: true, items: [folder("/data/a")] },
    "/api/browse?path=%2Fdata%2Fa": {
      success: true,
      items: [folder("/data/a/b")],
    },
    "/api/browse?path=%2Fdata%2Fa%2Fb": {
      success: true,
      items: [{ path: "/data/a/b/movie.mkv", type: "file" }],
    },
  };
  context.apiFetch = async (url) => {
    requests.push(url);
    return { json: async () => responses[url] };
  };
  for (const n of [
    "updateDirectoryTree",
    "loadFolderContents",
    "loadBrowseRoots",
  ])
    load(n);
  await context.loadBrowseRoots();
  assert.deepEqual(requests, Object.keys(responses));
  assert.equal(
    tree[0].children[0].children[0].children[0].path,
    "/data/a/b/movie.mkv",
  );
  assert.equal(context.restoring, false);
  await context.loadFolderContents("/data");
  assert.equal(tree[0].children[0].children[0].children.length, 1);
  context.expandedFoldersRef.current = new Set(["/data/a/b"]);
  requests.length = 0;
  await context.loadBrowseRoots();
  assert.deepEqual(requests, Object.keys(responses));
  assert.equal(tree[0].children[0].children[0].children.length, 1);
  assert.deepEqual([...context.expandedFoldersRef.current], ["/data/a/b"]);
  context.expandedFoldersRef.current = context.getStoredExpandedFolders();

  const refreshStates = [];
  const manualSearches = [];
  context.fileBrowserRefreshing = false;
  context.setFileBrowserRefreshing = (value) => refreshStates.push(value);
  context.fileBrowserSearchQuery = { current: "new download" };
  let finishManualSearch;
  let manualSearchStarted;
  const searchStarted = new Promise((resolve) => {
    manualSearchStarted = resolve;
  });
  context.handleFileBrowserSearch = (query) => {
    manualSearches.push(query);
    manualSearchStarted();
    return new Promise((resolve) => {
      finishManualSearch = resolve;
    });
  };
  load("refreshFileBrowser");
  requests.length = 0;
  const manualRefresh = context.refreshFileBrowser();
  await searchStarted;
  assert.deepEqual(refreshStates, [true]);
  assert.deepEqual(requests, Object.keys(responses));
  assert.deepEqual(manualSearches, ["new download"]);
  finishManualSearch();
  await manualRefresh;
  assert.deepEqual(refreshStates, [true, false]);

  let delayResolve;
  let delay;
  context.setTimeout = (fn, ms) => {
    delay = ms;
    delayResolve = fn;
  };
  context.fileBrowserSearchQuery = { current: "movie" };
  const searches = [];
  context.handleFileBrowserSearch = (q) => searches.push(q);
  load("refreshFileBrowserAfterUpload");
  requests.length = 0;
  const refresh = context.refreshFileBrowserAfterUpload();
  assert.equal(delay, 500);
  assert.equal(requests.length, 0);
  context.expandedFoldersRef.current = new Set(["/data/a", "/data"]);
  context.fileBrowserSearchQuery.current = "latest";
  delayResolve();
  await refresh;
  assert.deepEqual(requests, Object.keys(responses).slice(1, 3));
  assert.deepEqual(searches, ["latest"]);
  requests.length = 0;
  const cancelled = new AbortController();
  const pending = context.refreshFileBrowserAfterUpload(cancelled.signal);
  cancelled.abort();
  delayResolve();
  await pending;
  assert.equal(requests.length, 0);
  assert.equal(searches.length, 1);

  context.fileBrowserSearchTimer = { current: null };
  context.fileBrowserSearchCompletion = { current: null };
  context.fileBrowserSearchId = { current: 0 };
  context.setFileBrowserSearch = () => {};
  let searchLoading = false;
  context.setFileBrowserSearchLoading = (value) => {
    searchLoading = value;
  };
  context.setFileBrowserSearchResults = () => {};
  context.clearTimeout = () => {};
  load("handleFileBrowserSearch");
  const duringDebounce = new AbortController();
  context.handleFileBrowserSearch("movie", duringDebounce.signal);
  assert.equal(delay, 300);
  assert.equal(searchLoading, true);
  duringDebounce.abort();
  assert.equal(searchLoading, false);
  delayResolve();
  await Promise.resolve();
  assert.equal(requests.length, 0);

  let finishSearch;
  context.apiFetch = () =>
    new Promise((resolve) => {
      finishSearch = () =>
        resolve({ ok: true, json: async () => ({ success: true }) });
    });
  const duringRequest = new AbortController();
  context.handleFileBrowserSearch("movie", duringRequest.signal);
  const searchWork = delayResolve();
  assert.equal(searchLoading, true);
  duringRequest.abort();
  assert.equal(searchLoading, false);
  finishSearch();
  await searchWork;

  const olderSearch = new AbortController();
  context.handleFileBrowserSearch("movie", olderSearch.signal);
  const olderWork = delayResolve();
  const finishOlderSearch = finishSearch;
  const newerSearch = new AbortController();
  context.handleFileBrowserSearch("movie", newerSearch.signal);
  olderSearch.abort();
  assert.equal(searchLoading, true);
  finishOlderSearch();
  await olderWork;
  assert.equal(searchLoading, true);
  newerSearch.abort();
  assert.equal(searchLoading, false);

  let finishFirstFolder;
  let firstFolderRequested;
  const firstFolderStarted = new Promise((resolve) => {
    firstFolderRequested = resolve;
  });
  context.fileBrowserSearchQuery.current = "";
  context.expandedFoldersRef.current = new Set(["/data", "/data/a"]);
  context.apiFetch = (url) => {
    requests.push(url);
    firstFolderRequested();
    return new Promise((resolve) => {
      finishFirstFolder = () => resolve({ json: async () => responses[url] });
    });
  };
  const duringFolder = new AbortController();
  const interruptedRefresh = context.refreshFileBrowserAfterUpload(
    duringFolder.signal,
  );
  delayResolve();
  await firstFolderStarted;
  assert.deepEqual(requests, ["/api/browse?path=%2Fdata"]);
  const treeBeforeAbort = JSON.stringify(tree);
  duringFolder.abort();
  finishFirstFolder();
  await interruptedRefresh;
  assert.deepEqual(requests, ["/api/browse?path=%2Fdata"]);
  assert.equal(JSON.stringify(tree), treeBeforeAbort);

  const layout = nodes.find(
    (n) =>
      n.type === "CallExpression" &&
      n.callee.name === "useLayoutEffect" &&
      source.slice(n.start, n.end).includes("fileBrowserRef.current"),
  );
  const scroll = nodes.find(
    (n) =>
      n.type === "JSXAttribute" &&
      n.name.name === "onScroll" &&
      source.slice(n.start, n.end).includes("FILE_BROWSER_SCROLL_KEY"),
  );
  context.fileBrowserScrollTopRef = { current: 345 };
  context.fileBrowserRef = { current: { scrollTop: 0 } };
  context.fileBrowserRestoring = true;
  vm.runInContext(
    `var layout = ${source.slice(layout.arguments[0].start, layout.arguments[0].end)}; var scroll = ${source.slice(scroll.value.expression.start, scroll.value.expression.end)};`,
    context,
  );
  context.layout();
  context.scroll({ currentTarget: { scrollTop: 0 } });
  assert.equal(context.fileBrowserScrollTopRef.current, 345);
  context.fileBrowserRestoring = false;
  context.layout();
  assert.equal(context.fileBrowserRef.current.scrollTop, 345);
  context.scroll({ currentTarget: { scrollTop: 567 } });
  assert.equal(saved.get(context.FILE_BROWSER_SCROLL_KEY), "567");
  context.fileBrowserRef.current = { scrollTop: 0 };
  context.layout();
  assert.equal(context.fileBrowserRef.current.scrollTop, 567);

  // Execute the actual SSE reader with minimal UI stubs.
  // Reconnect backoff needs real timers; the refresh check above faked them.
  context.setTimeout = setTimeout;
  context.clearTimeout = clearTimeout;
  const tabRuntime = {
    controller: null,
    lastFullHash: "",
    lastSeq: 0,
    sessionRecord: "",
    run: { sessionId: "", isExecuting: true },
    output: { appendChild: () => {} },
    awaiting: false,
    waiting: new Set(),
    result: "",
  };
  Object.assign(context, {
    hasDescFile: false,
    hasDescLink: false,
    customArgs: "",
    activeTabIdRef: { current: "tab-1" },
    getTabRuntime: () => tabRuntime,
    updateTabRun: () => {},
    refreshUploadTabStatus: () => {},
    appendSystemMessage: () => {},
    applyProgressEvent: () => {},
    appendHtmlFragment: () => {},
    sanitizeHtml: (html) => html,
    dismissTabSession: () => {},
    schedulingEnabled: true,
    window: {},
    refreshCount: 0,
  });
  context.refreshFileBrowserAfterUpload = async () => {
    context.refreshCount++;
  };
  for (const name of [
    "SESSION_STREAM_STALL_MS",
    "SESSION_RECONNECT_ATTEMPTS",
    "SCHEDULE_POLL_MS",
    "sharedSessionsPoll",
    "pollSessionsShared",
    "waitForReconnect",
    "waitForScheduledStart",
    "followScheduledSession",
    "readSessionChunk",
    "readSessionStream",
    "followSession",
    "finishTabSession",
    "executeSinglePath",
  ])
    load(name);
  for (const [code, count, aborted] of [
    [0, 1, false],
    [1, 0, false],
    [null, 0, false],
    [0, 0, true],
  ]) {
    context.refreshCount = 0;
    let read = false;
    context.apiFetch = async () => ({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (read) return { done: true };
            read = true;
            if (aborted) tabRuntime.controller.abort();
            return {
              done: false,
              value: new TextEncoder().encode(
                code === null
                  ? `data: {"type":"finished","exit_code":null}\n`
                  : `data: {"type":"exit","code":${code}}\ndata: {"type":"exit","code":${code}}\n`,
              ),
            };
          },
        }),
      },
    });
    await context.executeSinglePath("/data/a", "session");
    assert.equal(context.refreshCount, count);
    assert.equal(
      tabRuntime.result,
      aborted ? "" : code === 0 || code === null ? "done" : "error",
    );
    tabRuntime.result = "";
  }

  // A dropped connection reattaches after the last applied event.
  let cancelledReaders = 0;
  const streamOf = (text) => ({
    ok: true,
    body: {
      getReader: () => {
        let sent = false;
        return {
          read: async () => {
            if (sent) return { done: true };
            sent = true;
            return { done: false, value: new TextEncoder().encode(text) };
          },
          cancel: async () => {
            cancelledReaders++;
          },
        };
      },
    },
  });
  const streamRequests = [];
  context.apiFetch = async (url) => {
    streamRequests.push(url);
    if (url.endsWith("/execute"))
      return streamOf(
        'data: {"type":"replay_done"}\ndata: {"type":"html","data":"first","seq":1}\n',
      );
    return streamOf(
      'data: {"type":"html","data":"first","seq":1}\ndata: {"type":"exit","code":0,"seq":2}\ndata: {"type":"finished","exit_code":0}\n',
    );
  };
  tabRuntime.run.sessionId = "session";
  context.refreshCount = 0;
  assert.equal(await context.executeSinglePath("/data/a", "session"), true);
  assert.deepEqual(streamRequests, [
    "/api/execute",
    "/api/session_stream?session_id=session&after=1",
  ]);
  assert.equal(tabRuntime.lastSeq, 2);
  assert.equal(context.refreshCount, 1);
  // The stream that delivered "finished" is released right away.
  assert.equal(cancelledReaders, 1);

  // With every slot busy the server schedules the upload; the tab waits on the
  // session list without holding a stream open, then follows it once started.
  context.SCHEDULE_POLL_MS = 5;
  const scheduledRequests = [];
  let polls = 0;
  context.apiFetch = async (url, options = {}) => {
    scheduledRequests.push(url);
    if (url.endsWith("/execute")) {
      assert.equal(JSON.parse(options.body).schedule, true);
      return streamOf('data: {"type":"scheduled"}\n');
    }
    if (url.endsWith("/sessions")) {
      polls++;
      return {
        ok: true,
        json: async () => ({
          sessions: [{ session_id: "session", scheduled: polls < 2 }],
        }),
      };
    }
    return streamOf(
      'data: {"type":"started","seq":1}\ndata: {"type":"exit","code":0,"seq":2}\ndata: {"type":"finished","exit_code":0}\n',
    );
  };
  assert.equal(await context.executeSinglePath("/data/a", "session"), true);
  assert.deepEqual(scheduledRequests, [
    "/api/execute",
    "/api/sessions",
    "/api/sessions",
    "/api/session_stream?session_id=session&after=0",
  ]);
  assert.equal(tabRuntime.scheduled, false);
});

test("external HTTP(S) output anchors get safe targets without changing internal links or styling", () => {
  const makeLink = (href) => ({
    href,
    target: "",
    rel: "",
    textContent: "Result text",
    style: "color: cyan",
    getAttribute(name) {
      return name === "href" ? href : null;
    },
  });
  const links = [
    "https://tracker.example/result",
    "http://tracker.example/result",
    "//tracker.example/result",
    "/config",
    "#output",
    "https://ua.example/config",
    "mailto:help@example.com",
    "https://[invalid",
  ].map(makeLink);
  const wrapper = { innerHTML: "", querySelectorAll: () => links };
  context.document = { createElement: () => wrapper };
  context.URL = URL;
  context.window = {
    location: { href: "https://ua.example/", origin: "https://ua.example" },
  };
  context.sanitizeHtml = (html) => html;
  load("createUploadOutputFragment");
  assert.equal(context.createUploadOutputFragment("<p>Output</p>"), wrapper);
  for (const link of links.slice(0, 3)) {
    assert.equal(link.target, "_blank");
    assert.equal(link.rel, "noopener noreferrer");
    assert.equal(link.textContent, "Result text");
    assert.equal(link.style, "color: cyan");
  }
  for (const link of links.slice(3)) assert.equal(link.target, "");
});

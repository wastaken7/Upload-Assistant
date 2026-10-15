const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const babel = require("../web_ui/static/js/node_modules/@babel/core");

const source = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/app.js"),
  "utf8",
);
const ast = babel.parseSync(source, { parserOpts: { plugins: ["jsx"] } });
const declarations = new Map();
function walk(node) {
  if (!node || typeof node !== "object") return;
  if (node.type === "VariableDeclarator" && node.id.type === "Identifier")
    declarations.set(node.id.name, node.init);
  for (const [key, value] of Object.entries(node)) {
    if (["loc", "tokens", "comments"].includes(key)) continue;
    if (Array.isArray(value)) value.forEach(walk);
    else if (value && typeof value === "object") walk(value);
  }
}
walk(ast);
const plain = (value) => JSON.parse(JSON.stringify(value));

const fakeElement = () => ({
  children: [],
  textContent: "",
  style: {},
  appendChild(child) {
    this.children.push(child);
  },
  replaceChildren() {
    this.children = [];
  },
});

const STATE = {
  sessionId: "",
  isExecuting: false,
  isTerminalView: false,
  progressItems: [],
  selectedPath: "",
  selectedPaths: [],
  manualPathsText: null,
  customArgs: "",
  pathInputError: "",
  selectedArgumentPreset: "",
  userInput: "",
  uploadTabs: [],
  activeTabId: "",
  pendingCloseTabId: "",
};

function setup() {
  const context = vm.createContext({
    Set,
    Map,
    String,
    window: {},
    document: { createElement: fakeElement },
    setTimeout: () => {},
    screenshotMode: null,
    richOutputRef: { current: null },
    API_BASE: "/api",
    kills: [],
    apiFetch: async (url, options) => {
      context.kills.push([url, JSON.parse(options.body).session_id]);
      return { ok: true };
    },
    console,
  });
  for (const [name, initial] of Object.entries(STATE)) {
    context[name] = structuredClone(initial);
    const setter = `set${name[0].toUpperCase()}${name.slice(1)}`;
    context[setter] = (value) => {
      context[name] =
        typeof value === "function" ? value(context[name]) : value;
    };
  }
  for (const name of [
    "MAX_UPLOAD_TABS",
    "createUploadTabForm",
    "createUploadTabRuntime",
    "getUploadTabStatus",
    "sortProgressItems",
    "getTabRuntime",
    "refreshUploadTabStatus",
    "updateTabRun",
    "scrollTabOutput",
    "applyProgressEvent",
    "appendSystemMessage",
    "appendWelcomeMessage",
    "switchUploadTab",
    "createEmptyUploadTab",
    "addUploadTab",
    "closeUploadTab",
    "requestCloseUploadTab",
    "dismissTabSession",
    "UPLOAD_TAB_DRAFTS_KEY",
    "uploadTabFormHasContent",
    "loadUploadTabDrafts",
    "saveUploadTabDrafts",
    "setUploadTabTitle",
  ]) {
    const node = declarations.get(name);
    vm.runInContext(
      `var ${name} = ${source.slice(node.start, node.end)};`,
      context,
    );
  }
  context.uploadTabs = [{ id: "tab-1", number: 1, title: "", status: "idle" }];
  context.activeTabId = "tab-1";
  context.activeTabIdRef = { current: "tab-1" };
  context.uploadTabCounterRef = { current: 1 };
  context.tabRuntimeRef = {
    current: new Map([["tab-1", context.createUploadTabRuntime()]]),
  };
  return context;
}

const statusOf = (context, id) =>
  context.uploadTabs.find((tab) => tab.id === id).status;

test("background tab output, progress and run state never touch the visible tab", () => {
  const context = setup();
  context.updateTabRun("tab-1", { isExecuting: true, sessionId: "first" });
  context.customArgs = "--unattended";
  context.addUploadTab();

  assert.equal(context.activeTabIdRef.current, "tab-2");
  assert.equal(context.isExecuting, false);
  assert.equal(context.sessionId, "");
  assert.equal(context.customArgs, "");

  context.appendSystemMessage("background line", "info", "tab-1");
  context.applyProgressEvent(
    { id: "mkbrr-hash", status: "running", label: "Hashing" },
    "tab-1",
  );
  context.updateTabRun("tab-1", { isExecuting: false });

  const background = context.getTabRuntime("tab-1");
  assert.equal(
    background.output.children.at(-1).textContent,
    "background line",
  );
  assert.deepEqual(plain(context.progressItems), []);
  assert.equal(background.view.progressItems[0].id, "mkbrr-hash");
  assert.equal(context.isExecuting, false);
  assert.equal(statusOf(context, "tab-1"), "idle");

  context.switchUploadTab("tab-1");
  assert.equal(context.customArgs, "--unattended");
  assert.equal(context.progressItems[0].id, "mkbrr-hash");
  assert.equal(context.isExecuting, false);
});

test("tab status reports shared-resource waits and pending prompts", () => {
  const context = setup();
  context.updateTabRun("tab-1", { isExecuting: true });
  assert.equal(statusOf(context, "tab-1"), "running");

  context.applyProgressEvent({ id: "wait-torrent-hash", status: "waiting" });
  assert.equal(statusOf(context, "tab-1"), "waiting");

  const runtime = context.getTabRuntime("tab-1");
  runtime.awaiting = true;
  context.refreshUploadTabStatus("tab-1");
  assert.equal(statusOf(context, "tab-1"), "input");

  runtime.awaiting = false;
  context.applyProgressEvent({ id: "wait-torrent-hash", status: "completed" });
  assert.equal(statusOf(context, "tab-1"), "running");

  runtime.result = "error";
  context.updateTabRun("tab-1", { isExecuting: false });
  assert.equal(statusOf(context, "tab-1"), "error");
});

test("no more than the maximum number of tabs can be opened", () => {
  const context = setup();
  for (let i = 0; i < context.MAX_UPLOAD_TABS + 2; i++) context.addUploadTab();
  assert.equal(context.uploadTabs.length, context.MAX_UPLOAD_TABS);
});

test("closing a running tab asks first, then kills only its own session", async () => {
  const context = setup();
  context.updateTabRun("tab-1", { isExecuting: true, sessionId: "first" });
  context.addUploadTab();
  context.switchUploadTab("tab-1");
  let aborted = false;
  context.getTabRuntime("tab-1").controller = {
    abort: () => {
      aborted = true;
    },
  };

  context.requestCloseUploadTab("tab-1");
  assert.equal(context.pendingCloseTabId, "tab-1");
  assert.equal(context.uploadTabs.length, 2);

  await context.closeUploadTab("tab-1");
  assert.equal(aborted, true);
  assert.deepEqual(plain(context.kills), [["/api/kill", "first"]]);
  assert.deepEqual(plain(context.uploadTabs.map((tab) => tab.id)), ["tab-2"]);
  assert.equal(context.activeTabIdRef.current, "tab-2");
  assert.equal(context.getTabRuntime("tab-1"), undefined);

  // Late events from the killed run are dropped instead of resurrecting it.
  context.appendSystemMessage("late", "info", "tab-1");
  context.updateTabRun("tab-1", { isExecuting: false });
  assert.equal(context.getTabRuntime("tab-1"), undefined);
});

test("idle tabs close immediately; closing the last tab resets it", async () => {
  const context = setup();
  context.addUploadTab();
  context.requestCloseUploadTab("tab-2");
  assert.deepEqual(plain(context.uploadTabs.map((tab) => tab.id)), ["tab-1"]);
  assert.equal(context.activeTabIdRef.current, "tab-1");

  context.customArgs = "--anon";
  await context.closeUploadTab("tab-1");
  assert.equal(context.uploadTabs.length, 1);
  const [fresh] = context.uploadTabs;
  assert.notEqual(fresh.id, "tab-1");
  assert.equal(fresh.number, 1);
  assert.equal(context.activeTabIdRef.current, fresh.id);
  assert.equal(context.customArgs, "");
  assert.equal(context.getTabRuntime("tab-1"), undefined);
  assert.deepEqual(plain(context.kills), []);
});

test("resetting the only tab while it runs asks first, then kills it", async () => {
  const context = setup();
  context.updateTabRun("tab-1", { isExecuting: true, sessionId: "only" });
  context.requestCloseUploadTab("tab-1");
  assert.equal(context.pendingCloseTabId, "tab-1");

  await context.closeUploadTab("tab-1");
  assert.deepEqual(plain(context.kills), [["/api/kill", "only"]]);
  assert.equal(context.uploadTabs.length, 1);
  assert.equal(context.isExecuting, false);
  assert.equal(context.sessionId, "");
});

test("closing a finished tab forgets its server session", async () => {
  const context = setup();
  context.addUploadTab();
  const finished = context.getTabRuntime("tab-2");
  finished.sessionRecord = "finished-session";
  finished.result = "done";

  await context.closeUploadTab("tab-2");
  assert.deepEqual(plain(context.kills), [
    ["/api/session_dismiss", "finished-session"],
  ]);
});

test("server labels replace the tab title and keep the release name for the tooltip", () => {
  const context = setup();
  context.setUploadTabTitle(
    "tab-1",
    "Fictional Journey (2024)",
    "Fictional.Journey.2024.1080p",
  );
  context.setUploadTabTitle("tab-1", "", "ignored");
  assert.equal(context.uploadTabs[0].title, "Fictional Journey (2024)");
  assert.equal(context.uploadTabs[0].detail, "Fictional.Journey.2024.1080p");
});

test("prepared tab forms survive a reload through browser storage", () => {
  const context = setup();
  const stored = new Map();
  context.window.localStorage = {
    getItem: (key) => stored.get(key) ?? null,
    setItem: (key, value) => stored.set(key, value),
    removeItem: (key) => stored.delete(key),
  };
  context.saveUploadTabDrafts([
    {
      form: {
        selectedPath: "/media/Fictional Journey 2024",
        customArgs: "--anon",
      },
    },
  ]);
  stored.set(
    context.UPLOAD_TAB_DRAFTS_KEY,
    JSON.stringify([
      ...JSON.parse(stored.get(context.UPLOAD_TAB_DRAFTS_KEY)),
      { form: { selectedPath: "", customArgs: "" } },
      "not a draft",
    ]),
  );
  assert.deepEqual(plain(context.loadUploadTabDrafts()), [
    {
      form: {
        selectedPath: "/media/Fictional Journey 2024",
        customArgs: "--anon",
      },
    },
  ]);

  context.saveUploadTabDrafts([]);
  assert.equal(stored.has(context.UPLOAD_TAB_DRAFTS_KEY), false);

  // Unavailable storage never breaks the page.
  context.window.localStorage = {
    getItem: () => {
      throw new Error("blocked");
    },
    setItem: () => {
      throw new Error("blocked");
    },
  };
  assert.deepEqual(plain(context.loadUploadTabDrafts()), []);
  context.saveUploadTabDrafts([{ form: { customArgs: "--anon" } }]);
});

test("a scheduled upload has its own tab status", () => {
  const context = setup();
  const runtime = context.getTabRuntime("tab-1");
  runtime.scheduled = true;
  context.updateTabRun("tab-1", { isExecuting: true });
  assert.equal(statusOf(context, "tab-1"), "scheduled");
  runtime.scheduled = false;
  context.refreshUploadTabStatus("tab-1");
  assert.equal(statusOf(context, "tab-1"), "running");
});

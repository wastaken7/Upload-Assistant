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
const nodes = [];
function walk(node) {
  if (!node || typeof node !== "object") return;
  if (node.type) nodes.push(node);
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

function setup() {
  const context = vm.createContext({ Set, Map, Date, JSON, window: {} });
  Object.assign(context, {
    selectedPath: "",
    selectedPaths: [],
    manualPathsText: null,
    pathInputError: "",
    isExecuting: false,
    directories: [],
    getVisiblePaths: () => [],
    richOutputRef: { current: { innerHTML: "previous output" } },
    API_BASE: "/api",
    setSelectedPath: (value) => {
      context.selectedPath = value;
    },
    setSelectedPaths: (value) => {
      context.selectedPaths =
        typeof value === "function" ? value(context.selectedPaths) : value;
    },
    setManualPathsText: (value) => {
      context.manualPathsText = value;
    },
    setPathInputError: (value) => {
      context.pathInputError = value;
    },
    setSelectedName: () => {},
    setIsExecuting: (value) => {
      context.isExecuting = value;
    },
    setSessionId: () => {},
  });
  for (const name of [
    "parseUploadPaths",
    "handlePathInputChange",
    "executeCommand",
    "handleTogglePathSelect",
    "handleToggleSelectAll",
  ]) {
    const node = declarations.get(name);
    vm.runInContext(
      `var ${name} = ${source.slice(node.start, node.end)};`,
      context,
    );
  }
  return context;
}

test("pasted paths preserve spaces, accept CRLF and quotes, and ignore blanks and duplicates", () => {
  const context = setup();
  assert.deepEqual(
    plain(
      context.parseUploadPaths(
        '  "D:\\Media\\Fictional Journey.mkv"\r\n\r\nD:\\Media\\Second.mkv\r\nD:\\Media\\Second.mkv\n',
      ),
    ),
    [
      { path: "D:\\Media\\Fictional Journey.mkv", line: 1, args: "" },
      { path: "D:\\Media\\Second.mkv", line: 3, args: "" },
    ],
  );
});

test("typing Enter preserves the draft and updates the queue; clearing removes stale browser selection", () => {
  const context = setup();
  context.selectedPath = "/media/old.mkv";
  context.selectedPaths = [{ path: "/media/first.mkv", args: "--anon" }];
  context.handlePathInputChange("/media/first.mkv\n");
  assert.equal(context.manualPathsText, "/media/first.mkv\n");
  assert.equal(context.selectedPaths.length, 1);
  assert.equal(context.selectedPaths[0].args, "--anon");
  context.handlePathInputChange("/media/first.mkv\n/media/second.mkv");
  assert.equal(context.selectedPaths.length, 2);
  context.handlePathInputChange("");
  assert.equal(context.selectedPath, "");
  assert.equal(context.selectedPaths.length, 0);
});

test("all pasted paths are prepared before execution and line errors prevent any upload", async () => {
  const context = setup();
  context.handlePathInputChange("/media/first.mkv\n\n/private/second.mkv");
  let uploads = 0;
  context.executeSinglePath = async () => {
    uploads++;
  };
  context.apiFetch = async (url, options) => {
    assert.equal(url, "/api/save_queue");
    assert.deepEqual(
      plain(JSON.parse(options.body).items).map((item) => item.path),
      ["/media/first.mkv", "/private/second.mkv"],
    );
    return {
      ok: false,
      json: async () => ({
        success: false,
        item: 2,
        error: "Path outside allowed roots",
      }),
    };
  };
  await context.executeCommand();
  assert.equal(uploads, 0);
  assert.match(context.pathInputError, /^Line 3:/);
  assert.equal(context.richOutputRef.current.innerHTML, "previous output");
  assert.equal(context.isExecuting, false);
});

test("multiline input executes the issued queue and single input executes its validated path", async () => {
  for (const text of [
    "/media/first.mkv",
    "/media/first.mkv\n/media/second.mkv",
  ]) {
    const context = setup();
    context.handlePathInputChange(text);
    const issuedPath = text.includes("\n")
      ? "/state/tmp/webui_queue_issued.txt"
      : text;
    const uploads = [];
    context.apiFetch = async () => ({
      ok: true,
      json: async () => ({ success: true, path: issuedPath }),
    });
    context.executeSinglePath = async (path) => {
      uploads.push(path);
    };
    await context.executeCommand();
    assert.deepEqual(uploads, [issuedPath]);
    assert.equal(context.isExecuting, false);
  }
});

test("browser checkboxes replace the draft without losing the edited selection", () => {
  const context = setup();
  context.handlePathInputChange("/media/first.mkv\n/media/second.mkv");
  context.handleTogglePathSelect("/media/second.mkv");
  assert.equal(context.manualPathsText, null);
  assert.equal(context.selectedPath, "/media/first.mkv");
  assert.equal(context.selectedPaths.length, 1);
});

test("selecting all preserves item arguments and selections outside the visible list", () => {
  const context = setup();
  context.selectedPaths = [
    { path: "/media/outside.mkv", args: "--anon" },
    { path: "/media/first.mkv", args: "--debug" },
  ];
  context.getVisiblePaths = () => ["/media/first.mkv", "/media/second.mkv"];
  const setPaths = context.setSelectedPaths;
  context.setSelectedPaths = (value) => {
    // React may evaluate updater callbacks repeatedly; they must remain pure.
    if (typeof value === "function") {
      const setPath = context.setSelectedPath;
      context.setSelectedPath = () => assert.fail("Nested state update");
      try {
        value(context.selectedPaths);
      } finally {
        context.setSelectedPath = setPath;
      }
    }
    setPaths(value);
  };
  context.handleToggleSelectAll();
  assert.deepEqual(plain(context.selectedPaths), [
    { path: "/media/outside.mkv", args: "--anon" },
    { path: "/media/first.mkv", args: "--debug" },
    { path: "/media/second.mkv", args: "" },
  ]);
  context.handleToggleSelectAll();
  assert.deepEqual(plain(context.selectedPaths), [
    { path: "/media/outside.mkv", args: "--anon" },
  ]);
  context.handleTogglePathSelect("/media/first.mkv");
  context.handleTogglePathSelect("/media/outside.mkv");
  assert.equal(context.selectedPath, "/media/first.mkv");
});

test("executing pasted paths retains each item's edited arguments", async () => {
  const context = setup();
  context.handlePathInputChange("/media/first.mkv\n/media/second.mkv");
  context.selectedPaths[0].args = "--anon";
  context.selectedPaths[1].args = "--debug";
  context.apiFetch = async (url, options) => {
    assert.deepEqual(
      plain(JSON.parse(options.body).items).map((item) => item.args),
      ["--anon", "--debug"],
    );
    return {
      ok: true,
      json: async () => ({
        success: true,
        path: "/state/tmp/webui_queue_fictional.txt",
      }),
    };
  };
  context.executeSinglePath = async () => {};
  await context.executeCommand();
});

for (const [renderer, activation] of [
  ["renderFileTree", "activateTreeItem"],
  ["renderSearchResults", "activateSearchResult"],
]) {
  test(`${renderer}: checkbox clicks accumulate files and folders into an executable queue`, async () => {
    const context = setup();
    context.isMobile = false;
    context.toggleFolder = () =>
      assert.fail("Checkbox click expanded a folder");
    const renderNode = declarations.get(renderer);
    const checkbox = nodes.find(
      (node) =>
        node.type === "JSXOpeningElement" &&
        node.name.name === "input" &&
        node.start > renderNode.start &&
        node.end < renderNode.end &&
        node.attributes.some(
          (attribute) =>
            attribute.name?.name === "type" &&
            attribute.value?.value === "checkbox",
        ),
    );
    for (const [attribute, binding] of [
      ["onClick", "checkboxClick"],
      ["onChange", "checkboxChange"],
    ]) {
      const handler = checkbox.attributes.find(
        (node) => node.name?.name === attribute,
      )?.value.expression;
      vm.runInContext(
        `var ${binding} = ${handler ? source.slice(handler.start, handler.end) : "() => {}"};`,
        context,
      );
    }
    const activateNode = declarations.get(activation);
    vm.runInContext(
      `var activateRow = ${source.slice(activateNode.start, activateNode.end)};`,
      context,
    );
    const items = [
      {
        path: "/media/Fictional Season",
        name: "Fictional Season",
        type: "folder",
      },
      {
        path: "/media/Fictional Film.mkv",
        name: "Fictional Film.mkv",
        type: "file",
      },
      { path: "/media/Another Season", name: "Another Season", type: "folder" },
    ];
    const clickCheckbox = (item) => {
      context.item = item;
      let stopped = false;
      context.checkboxClick({
        stopPropagation: () => {
          stopped = true;
        },
      });
      if (!stopped) context.activateRow();
      context.checkboxChange({ stopPropagation: () => {} });
    };
    items.forEach(clickCheckbox);
    assert.deepEqual(
      plain(context.selectedPaths).map((item) => item.path),
      items.map((item) => item.path),
    );
    let uploadedPath;
    context.apiFetch = async (url, options) => {
      assert.equal(url, "/api/save_queue");
      assert.deepEqual(
        JSON.parse(options.body).items.map((item) => item.path),
        items.map((item) => item.path),
      );
      assert.equal(JSON.parse(options.body).return_single_path, false);
      return {
        ok: true,
        json: async () => ({
          success: true,
          path: "/state/tmp/webui_queue_selected.txt",
        }),
      };
    };
    context.executeSinglePath = async (path) => {
      uploadedPath = path;
    };
    await context.executeCommand();
    assert.equal(uploadedPath, "/state/tmp/webui_queue_selected.txt");
    items.forEach(clickCheckbox);
    assert.equal(context.selectedPaths.length, 0);
    assert.equal(context.selectedPath, "");
  });
}

test("empty input, excessive paths and duplicate execution do not make requests", async () => {
  const context = setup();
  context.apiFetch = async () => {
    assert.fail("Unexpected request");
  };
  await context.executeCommand();
  assert.match(context.pathInputError, /Enter or select/);
  context.handlePathInputChange(
    Array.from({ length: 1001 }, (_, i) => `/media/Fictional ${i}.mkv`).join(
      "\n",
    ),
  );
  await context.executeCommand();
  assert.match(context.pathInputError, /Maximum 1000/);
  context.isExecuting = true;
  await context.executeCommand();
});

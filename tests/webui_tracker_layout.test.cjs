const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const context = vm.createContext({ window: {} });
vm.runInContext(
  fs.readFileSync(
    path.join(__dirname, "../web_ui/static/js/tracker_layout.js"),
    "utf8",
  ),
  context,
);
const model = context.window.UATrackerLayout;
const plain = (value) => JSON.parse(JSON.stringify(value));
const catalog = ["AITHER", "BLUTOPIA", "LST", "ULCX"].map((name) => ({ name }));
const fixture = () =>
  model.normalize({
    pinned: [],
    groups: [
      { id: "movies", name: "Movies", trackers: ["BLUTOPIA", "AITHER"] },
    ],
    ungrouped: [],
  });
const order = (layout, id, visible = catalog) =>
  plain(
    model
      .sections(layout, visible)
      .find((section) => section.id === id)
      .trackers.map((tracker) => tracker.name),
  );

test("invalid browser preferences fall back safely and stored groups are normalized", () => {
  for (const stored of [null, "broken json", "null", "[]", "123"]) {
    assert.deepEqual(plain(model.load({ get: () => stored })), {
      pinned: [],
      groups: [],
      ungrouped: [],
    });
  }
  assert.deepEqual(
    plain(
      model.load({
        get: () => {
          throw Error("blocked storage");
        },
      }),
    ),
    plain(model.normalize(null)),
  );
  const layout = model.normalize({
    pinned: ["AITHER", "AITHER", null],
    groups: [
      null,
      { id: "pinned", name: "Reserved" },
      { id: "movies", name: " Movies ", trackers: ["AITHER", "AITHER"] },
      { id: "movies", name: "Duplicate" },
      { id: "tv", name: "TV", trackers: ["AITHER", "LST"] },
    ],
    ungrouped: ["AITHER", "ULCX", "ULCX"],
  });
  assert.deepEqual(plain(layout), {
    pinned: ["AITHER"],
    groups: [
      { id: "movies", name: "Movies", trackers: ["AITHER"] },
      { id: "tv", name: "TV", trackers: ["LST"] },
    ],
    ungrouped: ["ULCX"],
  });
});

test("pinning shows one card and unpinning restores its group and order", () => {
  const original = fixture();
  const pinned = model.togglePin(original, "AITHER");
  assert.deepEqual(order(pinned, model.PINNED), ["AITHER"]);
  assert.deepEqual(order(pinned, "movies"), ["BLUTOPIA"]);
  assert.deepEqual(order(model.togglePin(pinned, "AITHER"), "movies"), [
    "BLUTOPIA",
    "AITHER",
  ]);
  assert.deepEqual(plain(original), plain(fixture()));
});

test("moving between groups unpins and assigns each tracker once", () => {
  let layout = model.togglePin(fixture(), "AITHER");
  layout = model.moveTracker(
    layout,
    "AITHER",
    model.UNGROUPED,
    "ULCX",
    catalog,
  );
  assert.deepEqual(order(layout, model.PINNED), []);
  assert.deepEqual(order(layout, "movies"), ["BLUTOPIA"]);
  assert.deepEqual(order(layout, model.UNGROUPED), ["LST", "AITHER", "ULCX"]);
  layout = model.moveTracker(layout, "LST", "movies", "BLUTOPIA", catalog);
  assert.deepEqual(order(layout, "movies"), ["LST", "BLUTOPIA"]);
  assert.deepEqual(order(layout, model.UNGROUPED), ["AITHER", "ULCX"]);
});

test("drop into pinned remembers membership and supports reordering pins", () => {
  let layout = model.moveTracker(
    fixture(),
    "AITHER",
    model.PINNED,
    null,
    catalog,
  );
  layout = model.moveTracker(layout, "LST", model.PINNED, "AITHER", catalog);
  assert.deepEqual(order(layout, model.PINNED), ["LST", "AITHER"]);
  assert.deepEqual(order(model.togglePin(layout, "AITHER"), "movies"), [
    "BLUTOPIA",
    "AITHER",
  ]);
});

test("ungrouped reordering includes new catalog entries and survives reload", () => {
  let layout = model.normalize(null);
  layout = model.moveTracker(
    layout,
    "ULCX",
    model.UNGROUPED,
    "AITHER",
    catalog,
  );
  layout = model.moveTracker(
    layout,
    "BLUTOPIA",
    model.UNGROUPED,
    null,
    catalog,
  );
  const reloaded = model.load({ get: () => JSON.stringify(layout) });
  assert.deepEqual(
    order(reloaded, model.UNGROUPED, [...catalog, { name: "NEW" }]),
    ["ULCX", "AITHER", "LST", "BLUTOPIA", "NEW"],
  );
});

test("filtering configured trackers preserves hidden membership and preferences", () => {
  let layout = fixture();
  layout.groups[0].trackers.push("OFFLINE");
  layout.pinned.push("OFFLINE");
  layout = model.moveTracker(
    layout,
    "ULCX",
    model.UNGROUPED,
    "LST",
    catalog.slice(2),
  );
  assert.ok(layout.groups[0].trackers.includes("OFFLINE"));
  assert.ok(layout.pinned.includes("OFFLINE"));
  assert.deepEqual(order(layout, "movies"), ["BLUTOPIA", "AITHER"]);
  assert.deepEqual(
    order(layout, model.PINNED, [...catalog, { name: "OFFLINE" }]),
    ["OFFLINE"],
  );
});

test("removing a group returns its trackers to ungrouped and preserves pins", () => {
  const layout = model.removeGroup(
    model.togglePin(fixture(), "AITHER"),
    "movies",
  );
  assert.equal(layout.groups.length, 0);
  assert.deepEqual(order(layout, model.PINNED), ["AITHER"]);
  assert.deepEqual(order(model.togglePin(layout, "AITHER"), model.UNGROUPED), [
    "BLUTOPIA",
    "AITHER",
    "LST",
    "ULCX",
  ]);
});

test("groups can be reordered and stale drag targets are harmless", () => {
  const layout = model.normalize({
    groups: ["a", "b", "c"].map((id) => ({ id, name: id })),
  });
  assert.deepEqual(
    plain(model.moveGroup(layout, "c", "a").groups.map((group) => group.id)),
    ["c", "a", "b"],
  );
  assert.deepEqual(
    plain(model.moveGroup(layout, "a").groups.map((group) => group.id)),
    ["b", "c", "a"],
  );
  assert.equal(model.moveGroup(layout, "missing", "a"), layout);
  assert.equal(model.moveTracker(layout, "AITHER", "missing"), layout);
  assert.equal(model.moveTracker(layout, "AITHER", "a", "AITHER"), layout);
});

test("reordering preserves the saved place of pinned and hidden ungrouped trackers", () => {
  let layout = model.normalize({
    ungrouped: ["LST", "AITHER", "BLUTOPIA", "ULCX"],
  });
  layout = model.togglePin(layout, "AITHER");
  layout = model.moveTracker(
    layout,
    "ULCX",
    model.UNGROUPED,
    "BLUTOPIA",
    catalog,
  );
  assert.deepEqual(order(model.togglePin(layout, "AITHER"), model.UNGROUPED), [
    "LST",
    "AITHER",
    "ULCX",
    "BLUTOPIA",
  ]);
  assert.deepEqual(
    order(
      layout,
      model.UNGROUPED,
      catalog.filter((tracker) => tracker.name !== "LST"),
    ),
    ["ULCX", "BLUTOPIA"],
  );
});

/** Exercise the organizer's real layout handlers without a DOM or uploads. */
function organizerFixture(initial, props = {}) {
  const babel = require("../web_ui/static/js/node_modules/@babel/core");
  const source = fs.readFileSync(
    path.join(__dirname, "../web_ui/static/js/app.js"),
    "utf8",
  );
  const ast = babel.parseSync(source, { parserOpts: { plugins: ["jsx"] } });
  const component = ast.program.body.find(
    (node) => node.id?.name === "TrackerOrganizer",
  );
  const end = component.body.body.find(
    (node) => node.type === "ReturnStatement",
  ).start;
  const states = [];
  const stored = new Map([[model.STORAGE_KEY, JSON.stringify(initial)]]);
  const dragRef = { current: null };
  const refs = [dragRef];
  let stateIndex = 0;
  let refIndex = 0;
  const scope = vm.createContext({
    window: { UATrackerLayout: model },
    storage: {
      get: (key) => stored.get(key),
      set: (key, value) => stored.set(key, value),
    },
    useState: (initial) => {
      const index = stateIndex++;
      if (!(index in states))
        states[index] = typeof initial === "function" ? initial() : initial;
      return [
        states[index],
        (next) => {
          states[index] =
            typeof next === "function" ? next(states[index]) : next;
        },
      ];
    },
    useRef: (initial) => {
      const index = refIndex++;
      if (!(index in refs)) refs[index] = { current: initial };
      return refs[index];
    },
    useEffect: (effect) => effect(),
  });
  const renderBody = vm.runInContext(
    `(function({trackers, catalog, editing, disabled}) { ${source.slice(component.body.start + 1, end)} return { startDrag, allowDrop, drop, chooseMoveTarget, nudgeTracker }; })`,
    scope,
  );
  return {
    render: () => {
      stateIndex = 0;
      refIndex = 0;
      return renderBody({
        trackers: catalog,
        catalog,
        editing: true,
        disabled: false,
        ...props,
      });
    },
    layout: () => states[0],
    stored,
    dragRef,
  };
}
const dragEvent = () => ({
  prevented: false,
  stopped: false,
  dataTransfer: {
    data: {},
    setData(type, value) {
      this.data[type] = value;
    },
  },
  preventDefault() {
    this.prevented = true;
  },
  stopPropagation() {
    this.stopped = true;
  },
});

test("non-drag moves assign groups, unpin, return to Ungrouped and persist", () => {
  const layout = model.togglePin(fixture(), "AITHER");
  layout.groups.push({ id: "tv", name: "TV", trackers: [] });
  const page = organizerFixture(layout);
  page.render().chooseMoveTarget("AITHER", "tv");
  assert.deepEqual(order(page.layout(), model.PINNED), []);
  assert.deepEqual(order(page.layout(), "movies"), ["BLUTOPIA"]);
  assert.deepEqual(order(page.layout(), "tv"), ["AITHER"]);
  page.render().chooseMoveTarget("AITHER", model.UNGROUPED);
  assert.deepEqual(order(page.layout(), "tv"), []);
  assert.ok(order(page.layout(), model.UNGROUPED).includes("AITHER"));
  page.render().chooseMoveTarget("AITHER", model.PINNED);
  assert.deepEqual(order(page.layout(), model.PINNED), ["AITHER"]);
  page.render();
  assert.deepEqual(
    plain(model.load({ get: (key) => page.stored.get(key) })),
    plain(page.layout()),
  );
});

test("non-drag moves are ignored outside edit mode and during a run", () => {
  for (const props of [{ editing: false }, { disabled: true }]) {
    const original = fixture();
    const page = organizerFixture(original, props);
    page.render().chooseMoveTarget("AITHER", model.UNGROUPED);
    page.render().nudgeTracker(model.sections(original, catalog)[1], 1, -1);
    assert.deepEqual(plain(page.layout()), plain(original));
  }
});

test("tracker option reordering stays inside its group and ignores boundary moves", () => {
  const page = organizerFixture(fixture());
  const movies = () => model.sections(page.layout(), catalog)[1];
  page.render().nudgeTracker(movies(), 1, -1);
  assert.deepEqual(order(page.layout(), "movies"), ["AITHER", "BLUTOPIA"]);
  page.render().nudgeTracker(movies(), 0, -1);
  assert.deepEqual(order(page.layout(), "movies"), ["AITHER", "BLUTOPIA"]);
  page.render().nudgeTracker(movies(), 0, 1);
  assert.deepEqual(order(page.layout(), "movies"), ["BLUTOPIA", "AITHER"]);
  page.render().nudgeTracker(movies(), 1, 1);
  assert.deepEqual(order(page.layout(), "movies"), ["BLUTOPIA", "AITHER"]);
  assert.deepEqual(order(page.layout(), model.UNGROUPED), ["LST", "ULCX"]);
});

test("native tracker drag handlers accept drops, reorder cards and persist the result", () => {
  const page = organizerFixture(fixture());
  let handlers = page.render();
  const start = dragEvent();
  handlers.startDrag(start, { type: "tracker", id: "LST" });
  assert.equal(start.dataTransfer.data["text/plain"], "LST");
  assert.equal(start.dataTransfer.effectAllowed, "move");
  // React rerenders during drag-over without losing the dragged item.
  handlers = page.render();
  const over = dragEvent();
  handlers.allowDrop(over, "movies", "AITHER");
  assert.equal(over.prevented, true);
  const drop = dragEvent();
  page.render().drop(drop, "movies", "AITHER");
  assert.equal(drop.stopped, true);
  assert.equal(page.dragRef.current, null);
  assert.deepEqual(order(page.layout(), "movies"), [
    "BLUTOPIA",
    "LST",
    "AITHER",
  ]);
  page.render();
  assert.deepEqual(
    plain(model.load({ get: (key) => page.stored.get(key) })),
    plain(page.layout()),
  );
});

test("group drag handlers reorder headings while external drags and running edits are ignored", () => {
  const layout = fixture();
  layout.groups.push({ id: "tv", name: "TV", trackers: ["LST"] });
  const page = organizerFixture(layout);
  const external = dragEvent();
  page.render().allowDrop(external, "movies");
  assert.equal(external.prevented, false);
  page.render().startDrag(dragEvent(), { type: "group", id: "tv" });
  const invalid = dragEvent();
  page.render().allowDrop(invalid, model.PINNED);
  assert.equal(invalid.prevented, false);
  page.render().drop(dragEvent(), "movies");
  assert.deepEqual(plain(page.layout().groups.map((group) => group.id)), [
    "tv",
    "movies",
  ]);
  const busy = organizerFixture(layout, { disabled: true });
  const start = dragEvent();
  busy.render().startDrag(start, { type: "tracker", id: "LST" });
  assert.equal(start.prevented, true);
  assert.equal(busy.dragRef.current, null);
});

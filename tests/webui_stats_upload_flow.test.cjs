const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const babel = require("../web_ui/static/js/node_modules/@babel/core");
const source = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/stats_app.js"),
  "utf8",
);
const ast = babel.parseSync(source, { parserOpts: { plugins: ["jsx"] } });
const context = vm.createContext({});
for (const node of ast.program.body) {
  if (
    node.id?.name === "groupUploadFlow" ||
    node.declarations?.some((d) => d.id.name === "UPLOAD_FLOW_TRACKER_LIMIT")
  ) {
    vm.runInContext(source.slice(node.start, node.end), context);
  }
}
const group = (sankey, showAll) =>
  JSON.parse(JSON.stringify(context.groupUploadFlow(sankey, showAll)));

function fixture(count) {
  const trackers = Array.from({ length: count }, (_, i) => ({
    id: `tracker:FICTIONAL${i}`,
    kind: "tracker",
    label: `FICTIONAL${i}`,
    total: i + 2,
  }));
  return {
    nodes: [
      {
        id: "routes",
        kind: "root",
        total: trackers.reduce((n, t) => n + t.total, 0),
      },
      ...trackers,
      { id: "outcome:uploaded", kind: "outcome", total: count },
      {
        id: "outcome:error",
        kind: "outcome",
        total: (count * (count + 1)) / 2,
      },
    ],
    links: trackers.flatMap((t) => [
      { source: "routes", target: t.id, value: t.total },
      { source: t.id, target: "outcome:uploaded", value: 1 },
      { source: t.id, target: "outcome:error", value: t.total - 1 },
    ]),
  };
}

test("upload flow groups smaller trackers and preserves route and outcome totals", () => {
  const input = fixture(10);
  const original = JSON.stringify(input);
  const result = group(input);
  const trackers = result.nodes.filter((n) => n.kind === "tracker");
  assert.deepEqual(
    trackers.slice(0, 7).map((n) => n.label),
    [9, 8, 7, 6, 5, 4, 3].map((i) => `FICTIONAL${i}`),
  );
  assert.equal(trackers.length, 8);
  assert.equal(trackers[7].label, "others");
  assert.equal(trackers[7].total, 9);
  const othersId = trackers[7].id;
  assert.deepEqual(
    result.links.filter((l) => l.source === othersId),
    [
      { source: othersId, target: "outcome:uploaded", value: 3 },
      { source: othersId, target: "outcome:error", value: 6 },
    ],
  );
  for (const id of ["routes", "outcome:uploaded", "outcome:error"]) {
    const total = (links) =>
      links
        .filter((l) => l.source === id || l.target === id)
        .reduce((n, l) => n + l.value, 0);
    assert.equal(total(result.links), total(input.links));
  }
  const ids = new Set(result.nodes.map((n) => n.id));
  assert.ok(result.links.every((l) => ids.has(l.source) && ids.has(l.target)));
  assert.equal(JSON.stringify(input), original);
  assert.deepEqual(group(input, true), input);
  assert.deepEqual(group(input, false), result);
});

test("upload flow leaves up to seven trackers and empty data unchanged", () => {
  for (const count of [0, 1, 7]) {
    const input = fixture(count);
    assert.deepEqual(group(input), input);
  }
  assert.deepEqual(group(undefined), { nodes: [], links: [] });
});

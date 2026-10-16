const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const babel = require("../web_ui/static/js/node_modules/@babel/core");

const source = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/shared_utils.js"),
  "utf8",
);
const ast = babel.parseSync(source);
const context = vm.createContext({});
const names = new Set([
  "UA_CHANGELOG_AREAS",
  "UA_CHANGELOG_TYPES",
  "UA_TRACKER_SCOPES",
  "UA_CORE_SCOPES",
  "getUAChangelogArea",
  "parseUAReleaseNotes",
  "getUAChangelogAreaCounts",
]);
for (const node of ast.program.body[0].expression.callee.body.body) {
  if (
    names.has(node.id?.name) ||
    node.declarations?.some((declaration) => names.has(declaration.id.name))
  ) {
    vm.runInContext(source.slice(node.start, node.end), context);
  }
}

for (const summary of [
  "chore(deps): update mkbrr to v1.26.0 by @github-actions[bot]",
  "chore(deps-dev): bump the npm_and_yarn group across 1 directory with 2 updates by @dependabot[bot]",
  "chore(deps): bump urllib3 from 2.7.0 to 2.8.0 in the uv group across 1 directory",
  "build(dependencies): update ffmpeg to 9.0.2",
  "chore(dependency): pin an image host library",
  "update mkbrr to v1.26.0 by @github-actions[bot]",
  "Update Python dependencies",
  "Bump the npm_and_yarn group across 1 directory with 2 updates by @dependabot[bot]",
  "Bump the npm_and_yarn group across 1 directory with 2 updates by `@dependabot`[bot]",
]) {
  test(`dependency changes get their own area: ${summary}`, () => {
    const entry = context.parseUAReleaseNotes(`* ${summary}`).entries[0];
    assert.equal(entry.area, "dependencies");
  });
}

test("unscoped human group updates remain in Core", () => {
  const parsed = context.parseUAReleaseNotes(
    "* Bump the UI group with 2 updates by @someone",
  );
  assert.equal(parsed.entries[0].area, "core");
});

test("grouping preserves contributor attribution, type, scope, and PR link", () => {
  const url = "https://github.com/wastaken7/Upload-Assistant/pull/644";
  const entry = context.parseUAReleaseNotes(
    `## Maintenance\n* chore(deps): update mkbrr to v1.26.0 by @github-actions[bot] in ${url}`,
  ).entries[0];
  assert.equal(
    entry.summary,
    "update mkbrr to v1.26.0 by @github-actions[bot]",
  );
  assert.equal(entry.url, url);
  assert.equal(entry.type, "chore");
  assert.equal(entry.scope, "deps");
});

test("existing areas and contributor notes remain separate from dependency updates", () => {
  const parsed = context.parseUAReleaseNotes(`
## What's Changed
* fix(webui): update timeout to 5 minutes
* fix(seedpool): preserve filenames
* feat(config): add session settings
* fix(core): handle disconnects
* chore(deps): update ffmpeg to 9.0.2
## New Contributors
* @someone made their first contribution
`);
  assert.deepEqual(
    Array.from(parsed.entries, (entry) => entry.area),
    ["webui", "trackers", "configuration", "core", "dependencies"],
  );
  assert.equal(parsed.supplemental.length, 1);
  const counts = context.getUAChangelogAreaCounts([{ parsed }]);
  assert.equal(counts.all, 5);
  for (const area of [
    "webui",
    "trackers",
    "configuration",
    "core",
    "dependencies",
  ]) {
    assert.equal(counts[area], 1);
  }
  assert.equal(context.getUAChangelogAreaCounts([]).dependencies, 0);
});

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const loadBuilder = () => {
  const context = { window: {} };
  vm.runInNewContext(
    fs.readFileSync(
      path.join(__dirname, "../web_ui/static/js/argument_builder.js"),
      "utf8",
    ),
    context,
  );
  return context.window.UAArgumentBuilder;
};

const builder = loadBuilder();
const plain = (value) => JSON.parse(JSON.stringify(value));
const same = (actual, expected) => assert.deepEqual(plain(actual), expected);

const catalog = [
  {
    label: "--category",
    kind: "choice",
    choices: ["movie", "tv", "music"],
    aliases: ["-c"],
  },
  { label: "--tmdb", kind: "value", aliases: ["-tmdb"] },
  { label: "--tag", kind: "multi", aliases: ["-g"] },
  { label: "--tracker-id", kind: "append" },
  { label: "--debug", kind: "flag" },
  { label: "--nohash", kind: "flag" },
  { label: "--rehash", kind: "flag" },
  { label: "--imdb", kind: "value", conflicts: ["--no-imdb"] },
  { label: "--no-imdb", kind: "flag", conflicts: ["--imdb"] },
  { label: "--platform", kind: "value", aliases: ["--platforms"] },
  { label: "--platforms", kind: "value", aliases: ["--platform"] },
  { label: "--descfile", kind: "value" },
];
const index = builder.createArgumentIndex(catalog);
const key = (option) => builder.keyForOption(index, option);

test("tokenize follows POSIX shlex quoting", () => {
  const { tokens, unclosed } = builder.tokenize(
    `--a 'x y' "q \\"z\\"" b\\ c 'C:\\dir'`,
  );
  same(
    tokens.map((token) => token.value),
    ["--a", "x y", 'q "z"', "b c", "C:\\dir"],
  );
  assert.equal(unclosed, false);
  assert.equal(builder.tokenize(`--a "open`).unclosed, true);
});

test("quoteArgument matches shlex.quote", () => {
  assert.equal(builder.quoteArgument("movie/123"), "movie/123");
  assert.equal(builder.quoteArgument("a b"), "'a b'");
  assert.equal(builder.quoteArgument("it's"), `'it'"'"'s'`);
  assert.equal(builder.quoteArgument(""), "''");
  assert.equal(builder.quoteArgument("C:\\x"), "'C:\\x'");
});

test("aliases, prefixes and = values resolve to one control", () => {
  const parsed = builder.parseArguments(
    "-c tv --tmdb=tv/12 --platforms pc --categ movie",
    index,
  );
  same(plain(parsed.occurrences.map((item) => [item.key, item.value])), [
    ["--category", "tv"],
    ["--tmdb", "tv/12"],
    ["--platform", "pc"],
    ["--category", "movie"],
  ]);
  assert.equal(
    builder.getArgumentState(parsed, key("--platforms")).value,
    "pc",
  );
});

test("setArgumentValue edits only its own option", () => {
  const text = "--debug  -c tv   --tag Group One --nohash";
  assert.equal(
    builder.setArgumentValue(text, index, key("--category"), "movie"),
    "--debug  -c movie   --tag Group One --nohash",
  );
  assert.equal(
    builder.setArgumentValue(text, index, key("--tag"), "New Group"),
    "--debug  -c tv   --tag 'New Group' --nohash",
  );
  assert.equal(
    builder.setArgumentValue(text, index, key("--tmdb"), "movie/5"),
    "--debug  -c tv   --tag Group One --nohash --tmdb movie/5",
  );
  // A choice without a value is invalid, so clearing it removes the option.
  assert.equal(
    builder.setArgumentValue(text, index, key("--category"), ""),
    "--debug   --tag Group One --nohash",
  );
  // Options that may run bare keep the flag when cleared.
  assert.equal(
    builder.setArgumentValue(text, index, key("--tag"), ""),
    "--debug  -c tv   --tag --nohash",
  );
  assert.equal(builder.setArgumentValue("", index, key("--tmdb"), ""), "");
});

test("prefixed entries edit their own repeated occurrence", () => {
  const text = "--tracker-id PTP=1 --tracker-id BLU=2";
  const id = key("--tracker-id");
  const parsed = builder.parseArguments(text, index);
  assert.equal(builder.getArgumentState(parsed, id, "BLU=").value, "2");
  assert.equal(
    builder.setArgumentValue(text, index, id, "9", { prefix: "BLU=" }),
    "--tracker-id PTP=1 --tracker-id BLU=9",
  );
  assert.equal(
    builder.setArgumentValue(text, index, id, "", { prefix: "PTP=" }),
    "--tracker-id BLU=2",
  );
  assert.equal(
    builder.setArgumentValue(text, index, id, "3", { prefix: "HDB=" }),
    "--tracker-id PTP=1 --tracker-id BLU=2 --tracker-id HDB=3",
  );
});

test("flags toggle and removal drops every spelling", () => {
  assert.equal(
    builder.setArgumentFlag("-c tv", index, key("--debug"), true),
    "-c tv --debug",
  );
  assert.equal(
    builder.setArgumentFlag(
      "--debug -c tv --debug",
      index,
      key("--debug"),
      false,
    ),
    "-c tv",
  );
  assert.equal(
    builder.removeArgument(
      "--platform pc --platforms ps5 --debug",
      index,
      key("--platforms"),
    ),
    "--debug",
  );
});

test("findArgumentIssues reports advisory problems", () => {
  const types = (text) =>
    builder.findArgumentIssues(text, index).map((issue) => issue.type);
  same(types("--debug -c tv"), []);
  same(types("--debugg"), ["unknown"]);
  assert.match(
    builder.findArgumentIssues("--debugg", index)[0].message,
    /Did you mean --debug\?/,
  );
  same(types("--tmdb"), ["missing"]);
  same(types("-c films"), ["choice"]);
  same(types("--imdb tt1 --no-imdb"), ["conflict"]);
  same(types("--nohash --rehash"), ["conflict"]);
  same(types("-c tv --category movie"), ["duplicate"]);
  same(types("--tracker-id A=1 --tracker-id B=2"), []);
  same(types("stray --debug"), ["stray"]);
  same(types("--descfile 'open"), ["unclosed"]);
});

test("choices compare case-insensitively when the parser lower-cases them", () => {
  const caseIndex = builder.createArgumentIndex([
    {
      label: "--platform",
      kind: "choice",
      choices: ["pc", "ps5"],
      case_insensitive: true,
    },
    { label: "--imghost", kind: "choice", choices: ["imgbox"] },
  ]);
  const types = (text) =>
    builder.findArgumentIssues(text, caseIndex).map((issue) => issue.type);
  same(types("--platform PC"), []);
  same(types("--platform xbox"), ["choice"]);
  same(types("--imghost IMGBOX"), ["choice"]);
  assert.equal(
    builder.matchChoice({ choices: ["pc"], case_insensitive: true }, "PC"),
    "pc",
  );
  assert.equal(builder.matchChoice({ choices: ["pc"] }, "PC"), "");
});

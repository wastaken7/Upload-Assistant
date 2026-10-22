// Reads and edits the Upload page's argument string for the Arguments panel.
// The string stays the source of truth: each control rewrites only the
// characters of its own option, so hand-written text is kept as typed.
// Kept free of React and the DOM so it can be tested with node:test.
(() => {
  const isSpace = (ch) =>
    ch === " " || ch === "\t" || ch === "\n" || ch === "\r";

  // Splits like Python's shlex.split (POSIX mode), which the server uses,
  // and keeps each token's character range in the original text.
  const tokenize = (text) => {
    const source = String(text || "");
    const tokens = [];
    let unclosed = false;
    let i = 0;
    while (i < source.length) {
      while (i < source.length && isSpace(source[i])) i += 1;
      if (i >= source.length) break;
      const start = i;
      let value = "";
      while (i < source.length && !isSpace(source[i])) {
        const ch = source[i];
        if (ch === "'") {
          const close = source.indexOf("'", i + 1);
          if (close === -1) {
            unclosed = true;
            value += source.slice(i + 1);
            i = source.length;
          } else {
            value += source.slice(i + 1, close);
            i = close + 1;
          }
        } else if (ch === '"') {
          i += 1;
          while (i < source.length && source[i] !== '"') {
            const next = source[i + 1];
            if (source[i] === "\\" && (next === '"' || next === "\\")) {
              value += next;
              i += 2;
            } else {
              value += source[i];
              i += 1;
            }
          }
          if (i >= source.length) unclosed = true;
          i += 1;
        } else if (ch === "\\") {
          if (i + 1 < source.length) value += source[i + 1];
          else unclosed = true;
          i += 2;
        } else {
          value += ch;
          i += 1;
        }
      }
      tokens.push({ value, start, end: Math.min(i, source.length) });
    }
    return { tokens, unclosed };
  };

  // Python's shlex.quote, so the server reads back exactly this value.
  const quoteArgument = (value) => {
    const text = String(value);
    if (text === "") return "''";
    if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(text)) return text;
    return `'${text.replace(/'/g, "'\"'\"'")}'`;
  };

  // argparse treats "-1" as a value because no option looks like a number.
  const looksLikeOption = (value) =>
    value.length > 1 && value.startsWith("-") && !/^-\d/.test(value);

  // Options of one parser action (such as -c and --category, or --platform
  // and --platforms) share a key, so any spelling finds the same control.
  const optionKey = (item) =>
    [item.label, ...(item.aliases || [])]
      .filter((option) => option.startsWith("--"))
      .sort()[0] || item.label;

  const createArgumentIndex = (catalog) => {
    const items = new Map();
    const byOption = new Map();
    (Array.isArray(catalog) ? catalog : []).forEach((item) => {
      if (!item || typeof item.label !== "string") return;
      const key = optionKey(item);
      if (!items.has(key)) items.set(key, item);
      [item.label, ...(item.aliases || [])].forEach((option) => {
        if (!byOption.has(option)) byOption.set(option, key);
      });
    });
    const longOptions = [...byOption.keys()].filter((option) =>
      option.startsWith("--"),
    );
    return { items, byOption, longOptions };
  };

  const keyForOption = (index, option) => index.byOption.get(option) || "";

  // argparse also accepts any unambiguous prefix of a long option.
  const resolveOption = (index, option) => {
    const exact = keyForOption(index, option);
    if (exact || !option.startsWith("--")) return exact;
    const keys = new Set(
      index.longOptions
        .filter((candidate) => candidate.startsWith(option))
        .map((candidate) => index.byOption.get(candidate)),
    );
    return keys.size === 1 ? [...keys][0] : "";
  };

  const parseArguments = (text, index) => {
    const { tokens, unclosed } = tokenize(text);
    const occurrences = [];
    const unknown = [];
    const stray = [];
    let i = 0;
    while (i < tokens.length) {
      const token = tokens[i];
      i += 1;
      if (!looksLikeOption(token.value)) {
        stray.push(token);
        continue;
      }
      const equals = token.value.startsWith("--")
        ? token.value.indexOf("=")
        : -1;
      const option = equals > 0 ? token.value.slice(0, equals) : token.value;
      const key = resolveOption(index, option);
      const kind = key ? index.items.get(key).kind || "value" : "multi";
      const values = equals > 0 ? [token.value.slice(equals + 1)] : [];
      let end = token.end;
      if (kind !== "flag" && equals <= 0) {
        // Unknown options keep their values, so removing one removes both.
        const limit = kind === "multi" ? Infinity : 1;
        while (
          i < tokens.length &&
          values.length < limit &&
          !looksLikeOption(tokens[i].value)
        ) {
          values.push(tokens[i].value);
          end = tokens[i].end;
          i += 1;
        }
      }
      const occurrence = {
        key,
        option,
        start: token.start,
        end,
        values,
        value: values.join(" "),
        hasValue: values.length > 0,
      };
      (key ? occurrences : unknown).push(occurrence);
    }
    return { occurrences, unknown, stray, unclosed };
  };

  const matchesPrefix = (occurrence, prefix) =>
    !prefix || occurrence.value.toUpperCase().startsWith(prefix.toUpperCase());

  // The control's view of an option: whether it is present and its value.
  const getArgumentState = (parsed, key, prefix = "") => {
    const occurrence = parsed.occurrences.find(
      (item) => item.key === key && matchesPrefix(item, prefix),
    );
    if (!occurrence) return { present: false, value: "", occurrence: null };
    const value = prefix
      ? occurrence.value.slice(prefix.length)
      : occurrence.value;
    return { present: true, value, occurrence };
  };

  const removeRange = (text, start, end) => {
    let from = start;
    let to = end;
    while (from > 0 && isSpace(text[from - 1])) from -= 1;
    if (from === 0) {
      while (to < text.length && isSpace(text[to])) to += 1;
    }
    return text.slice(0, from) + text.slice(to);
  };

  const appendArgument = (text, addition) => {
    const trimmed = String(text || "").replace(/\s+$/, "");
    return trimmed ? `${trimmed} ${addition}` : addition;
  };

  const formatArgument = (option, value) =>
    value === "" ? option : `${option} ${quoteArgument(value)}`;

  const removeOccurrences = (text, occurrences) =>
    [...occurrences]
      .sort((a, b) => b.start - a.start)
      .reduce(
        (result, item) => removeRange(result, item.start, item.end),
        text,
      );

  // Sets one option's value. An empty value keeps a bare option that may run
  // without one, and removes options that need one (choices and prefixed
  // entries such as --tracker-id PTP=).
  const setArgumentValue = (text, index, key, value, options = {}) => {
    const source = String(text || "");
    const item = index.items.get(key);
    if (!item) return source;
    const prefix = options.prefix || "";
    const nextValue = String(value ?? "");
    const target =
      options.occurrence ||
      getArgumentState(parseArguments(source, index), key, prefix).occurrence;
    const removes = nextValue === "" && (prefix || item.kind === "choice");
    const written = prefix && nextValue !== "" ? prefix + nextValue : nextValue;
    if (!target) {
      if (nextValue === "") return source;
      return appendArgument(
        source,
        formatArgument(options.option || item.label, written),
      );
    }
    if (removes) return removeRange(source, target.start, target.end);
    return (
      source.slice(0, target.start) +
      formatArgument(target.option, written) +
      source.slice(target.end)
    );
  };

  const setArgumentFlag = (text, index, key, enabled, option = "") => {
    const source = String(text || "");
    const item = index.items.get(key);
    if (!item) return source;
    const present = parseArguments(source, index).occurrences.filter(
      (occurrence) => occurrence.key === key,
    );
    if (enabled) {
      return present.length
        ? source
        : appendArgument(source, option || item.label);
    }
    return removeOccurrences(source, present);
  };

  const removeArgument = (text, index, key, prefix = "") => {
    const source = String(text || "");
    return removeOccurrences(
      source,
      parseArguments(source, index).occurrences.filter(
        (occurrence) =>
          occurrence.key === key && matchesPrefix(occurrence, prefix),
      ),
    );
  };

  const removeOccurrence = (text, occurrence) =>
    removeRange(String(text || ""), occurrence.start, occurrence.end);

  const editDistance = (a, b) => {
    const previous = Array.from({ length: b.length + 1 }, (_, j) => j);
    for (let i = 1; i <= a.length; i += 1) {
      let diagonal = previous[0];
      previous[0] = i;
      for (let j = 1; j <= b.length; j += 1) {
        const above = previous[j];
        previous[j] = Math.min(
          previous[j] + 1,
          previous[j - 1] + 1,
          diagonal + (a[i - 1] === b[j - 1] ? 0 : 1),
        );
        diagonal = above;
      }
    }
    return previous[b.length];
  };

  const suggestOption = (index, option) => {
    const normalized = option.replace(/^-+/, "--").replace(/_/g, "-");
    let best = "";
    let bestDistance = Infinity;
    index.longOptions.forEach((candidate) => {
      const distance = editDistance(normalized, candidate.replace(/_/g, "-"));
      if (distance < bestDistance) {
        best = candidate;
        bestDistance = distance;
      }
    });
    return bestDistance <= Math.max(2, Math.floor(normalized.length / 4))
      ? best
      : "";
  };

  // Pairs the parser accepts together but that undo each other.
  const EXTRA_CONFLICTS = [
    ["--nohash", "--rehash"],
    ["--skip-dupe-check", "--double-dupe-check"],
    ["--no-music-discogs", "--music-discogs-id"],
    ["--no-music-discogs", "--music-discogs-release-id"],
    ["--no-music-discogs", "--music-discogs-master-id"],
  ];

  // The parser lower-cases some values before it checks their choices.
  const matchChoice = (item, value) => {
    const choices = Array.isArray(item.choices) ? item.choices : [];
    if (!item.case_insensitive) return choices.includes(value) ? value : "";
    const lowered = value.toLowerCase();
    return choices.find((choice) => choice.toLowerCase() === lowered) || "";
  };

  // Advisory problems with the string. The server still validates the run.
  const findArgumentIssues = (text, index) => {
    const parsed = parseArguments(text, index);
    const issues = [];
    if (parsed.unclosed) {
      issues.push({
        type: "unclosed",
        message: "A quotation mark is not closed.",
      });
    }
    parsed.unknown.forEach((occurrence) => {
      const suggestion = suggestOption(index, occurrence.option);
      issues.push({
        type: "unknown",
        option: occurrence.option,
        suggestion,
        message: suggestion
          ? `Unknown option ${occurrence.option}. Did you mean ${suggestion}?`
          : `Unknown option ${occurrence.option}.`,
      });
    });
    parsed.stray.forEach((token) => {
      issues.push({
        type: "stray",
        value: token.value,
        message: `"${token.value}" does not belong to an option. Content paths go in the path field.`,
      });
    });
    const seen = new Map();
    parsed.occurrences.forEach((occurrence) => {
      const item = index.items.get(occurrence.key);
      const kind = item.kind || "value";
      if (
        !occurrence.hasValue &&
        (kind === "value" || kind === "choice" || kind === "append")
      ) {
        issues.push({
          type: "missing",
          option: occurrence.option,
          message: `${occurrence.option} needs a value.`,
        });
      }
      if (
        kind === "choice" &&
        occurrence.hasValue &&
        Array.isArray(item.choices) &&
        !matchChoice(item, occurrence.value)
      ) {
        issues.push({
          type: "choice",
          option: occurrence.option,
          message: `${occurrence.option} does not accept "${occurrence.value}". Choose one of: ${item.choices.join(", ")}.`,
        });
      }
      if (kind !== "append" && seen.has(occurrence.key)) {
        issues.push({
          type: "duplicate",
          option: occurrence.option,
          message: `${occurrence.option} is set more than once; the last value wins.`,
        });
      }
      seen.set(occurrence.key, occurrence.option);
    });
    const pairs = new Set();
    const addConflict = (firstKey, secondKey) => {
      if (!firstKey || !secondKey || firstKey === secondKey) return;
      if (!seen.has(firstKey) || !seen.has(secondKey)) return;
      const pair = [firstKey, secondKey].sort().join(" ");
      if (pairs.has(pair)) return;
      pairs.add(pair);
      issues.push({
        type: "conflict",
        options: [seen.get(firstKey), seen.get(secondKey)],
        message: `${seen.get(firstKey)} and ${seen.get(secondKey)} cannot be used together.`,
      });
    };
    seen.forEach((_option, key) => {
      (index.items.get(key).conflicts || []).forEach((other) =>
        addConflict(key, keyForOption(index, other)),
      );
    });
    EXTRA_CONFLICTS.forEach(([first, second]) =>
      addConflict(keyForOption(index, first), keyForOption(index, second)),
    );
    return issues;
  };

  window.UAArgumentBuilder = {
    tokenize,
    quoteArgument,
    createArgumentIndex,
    keyForOption,
    parseArguments,
    getArgumentState,
    setArgumentValue,
    setArgumentFlag,
    removeArgument,
    removeOccurrence,
    findArgumentIssues,
    matchChoice,
  };
})();

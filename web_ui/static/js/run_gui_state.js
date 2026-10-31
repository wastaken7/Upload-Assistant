// State for the upload page's GUI output mode. The server forwards the
// child's structured run events as "gui" session events; this reducer turns
// them, plus prompt and exit events, into the blocks the GUI renders.
// Kept free of React and the DOM so it can be tested with node:test.
(() => {
  const RUN_GUI_STAGES = Object.freeze([
    { key: "prep", label: "Metadata", icon: "file-search" },
    { key: "confirm", label: "Confirm", icon: "clipboard-check" },
    { key: "dupes", label: "Dupe check", icon: "copy-check" },
    { key: "screens", label: "Screenshots", icon: "images" },
    { key: "torrent", label: "Torrent", icon: "magnet" },
    { key: "upload", label: "Upload", icon: "cloud-upload" },
    { key: "requests", label: "Requests", icon: "hand-coins" },
  ]);
  const MAX_NOTICES = 200;
  const MAX_REQUESTS = 100;

  const createRunGuiState = () => ({
    items: [],
    currentItem: 0,
    stages: {},
    notices: [],
    noticeSeq: 0,
    prompt: null,
    // The last "Is this correct?" summary, shown again while correcting it.
    lastConfirm: null,
    awaiting: false,
    inputType: null,
    dupes: {},
    dupeReviews: {},
    slots: {},
    trackers: {},
    requests: [],
    finished: false,
    exitCode: null,
  });

  const text = (value) => (typeof value === "string" ? value : "");
  /** Normalize only the published run settings used by release badges. */
  const readRunOptions = (options) =>
    options && typeof options === "object" && !Array.isArray(options)
      ? {
          debug: options.debug === true,
          noSeed: options.no_seed === true,
          skipImagehostUpload: options.skip_imghost_upload === true,
          noHash: options.nohash === true,
          ffDebug: options.ffdebug === true,
          clientDisabled: options.client_disabled === true,
          category: text(options.category),
          prepDirectory: text(options.prep_directory),
        }
      : null;

  /** Describe whether debug options apply and explain their effects for this run. */
  const getDebugRunRows = (options) => {
    if (!options?.debug) return [];
    const rows = [
      {
        flag: "--debug",
        label: "Basic Debug",
        enabled: true,
        detail: "Tracker uploads are disabled.",
      },
      {
        flag: "-ns / --no-seed",
        label: "Skip client addition",
        enabled: options.noSeed,
        detail: options.noSeed
          ? "Prepared torrents will not be added to a client."
          : options.noHash
            ? "Client addition is disabled by --nohash."
            : options.clientDisabled
              ? "Client addition is disabled by --client none."
              : "Prepared torrents may be added to configured clients.",
      },
      {
        flag: "-siu / --skip-imagehost-upload",
        label: "Skip image uploads",
        enabled: options.skipImagehostUpload,
        detail: options.skipImagehostUpload
          ? "Screenshots will not be uploaded to an image host."
          : options.category === "MUSIC"
            ? "MUSIC artwork hosting is skipped during debug runs."
            : "Screenshots may still be uploaded to an image host.",
      },
    ];
    if (options.noHash)
      rows.push({
        flag: "--nohash",
        label: "Skip torrent hashing",
        enabled: true,
        detail: "New torrent hashing is disabled.",
      });
    if (options.ffDebug)
      rows.push({
        flag: "--ffdebug",
        label: "Verbose FFmpeg output",
        enabled: true,
        detail: "Extra FFmpeg information is shown while taking screenshots.",
      });
    return rows;
  };
  // Only plain hex colours from the server reach an inline style.
  const hexColor = (value) =>
    typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value) ? value : "";
  const releaseEntries = (entries) =>
    (Array.isArray(entries) ? entries : [])
      .filter((entry) => entry && text(entry.name))
      .map((entry) => ({
        name: text(entry.name),
        link: text(entry.link),
        size: Number.isFinite(entry.size) ? entry.size : null,
        diffPct: Number.isFinite(entry.diff_pct) ? entry.diff_pct : null,
        color: hexColor(entry.color),
      }));
  // A cover is a public image or the server's per-item endpoint, never a path.
  const artworkUrl = (value) =>
    typeof value === "string" &&
    /^(https?:\/\/|\/api\/execution_item_cover\?)/i.test(value)
      ? value
      : "";
  const itemOf = (data, state) =>
    Number.isInteger(data.item) ? data.item : state.currentItem;
  const trackerKey = (item, tracker) => `${item}:${tracker}`;

  /** Return { notices, noticeSeq } with one notice added or its repeat counted. */
  const addNotice = (state, data, item, group = "") => {
    const level = text(data.level);
    const message = text(data.text);
    if (!["error", "warning", "attention"].includes(level) || !message) {
      return state;
    }
    const tracker = text(data.tracker);
    const key = `${item}|${group}|${text(data.key) || `${level}|${tracker}|${message}`}`;
    const existing = state.notices.findIndex((notice) => notice.key === key);
    if (existing !== -1) {
      const next = [...state.notices];
      const previous = next[existing];
      // A keyed notice can be reworded (e.g. a different region); keep the latest text.
      next[existing] = {
        ...previous,
        level,
        text: message,
        count: previous.count + 1,
      };
      return { ...state, notices: next };
    }
    const noticeSeq = state.noticeSeq + 1;
    const notice = {
      id: noticeSeq,
      key,
      level,
      text: message,
      tracker,
      group,
      item,
      count: 1,
    };
    const next = [...state.notices, notice];
    return {
      ...state,
      noticeSeq,
      notices: next.length > MAX_NOTICES ? next.slice(-MAX_NOTICES) : next,
    };
  };

  const reduceGuiData = (state, data) => {
    const item = itemOf(data, state);
    switch (data.kind) {
      case "item": {
        if (!Number.isInteger(data.index)) return state;
        const items = state.items.filter((entry) => entry.index !== data.index);
        items.push({
          index: data.index,
          total: Number.isInteger(data.total) ? data.total : 0,
          name: text(data.name),
          personalRelease: data.personal_release === true,
          runOptions: readRunOptions(data.run_options),
          artwork: artworkUrl(data.artwork),
        });
        items.sort((a, b) => a.index - b.index);
        return { ...state, items, currentItem: data.index };
      }
      case "stage": {
        const key = text(data.key);
        if (!RUN_GUI_STAGES.some((stage) => stage.key === key)) return state;
        const stages = { ...state.stages };
        stages[item] = { ...(stages[item] || {}), [key]: text(data.status) };
        return { ...state, stages };
      }
      case "notice":
        return addNotice(state, data, item);
      case "notice_group": {
        const group = text(data.group);
        let next = {
          ...state,
          notices: state.notices.filter(
            (notice) => !(notice.group === group && notice.item === item),
          ),
        };
        (Array.isArray(data.notices) ? data.notices : []).forEach((notice) => {
          next = addNotice(next, notice || {}, item, group);
        });
        return next;
      }
      case "prompt": {
        if (data.action === "close") {
          if (!state.prompt || state.prompt.id !== data.id) return state;
          return { ...state, prompt: null };
        }
        if (data.action !== "open" || !Number.isInteger(data.id)) return state;
        const context =
          data.context && typeof data.context === "object" ? data.context : {};
        return {
          ...state,
          lastConfirm:
            context.kind === "confirm" ? { item, context } : state.lastConfirm,
          prompt: {
            id: data.id,
            type: ["yes_no", "choice", "multi_choice", "text"].includes(
              data.type,
            )
              ? data.type
              : "text",
            question: text(data.question),
            choices: Array.isArray(data.choices) ? data.choices.map(text) : [],
            default:
              typeof data.default === "boolean"
                ? data.default
                : text(data.default),
            context,
            item,
            answered: false,
          },
        };
      }
      case "dupes": {
        const tracker = text(data.tracker);
        if (!tracker) return state;
        const entries = releaseEntries(data.entries);
        const key = trackerKey(item, tracker);
        const previous = state.dupes[key];
        // The latest list decides the label: after a declined trump prompt the
        // regular dupe list follows and is no longer "trumpable".
        return {
          ...state,
          dupes: {
            ...state.dupes,
            [key]: {
              tracker,
              item,
              entries: entries.length ? entries : previous?.entries || [],
              note: text(data.note) || previous?.note || "",
              trumpable: Boolean(data.trumpable),
            },
          },
        };
      }
      case "dupe_review": {
        const trackers = [
          ...new Set(
            (Array.isArray(data.trackers) ? data.trackers : [])
              .map(text)
              .filter(Boolean),
          ),
        ];
        const started = [
          ...new Set(
            (Array.isArray(data.started) ? data.started : [])
              .map(text)
              .filter((tracker) => trackers.includes(tracker)),
          ),
        ];
        return {
          ...state,
          dupeReviews: {
            ...state.dupeReviews,
            [item]: {
              trackers,
              started,
              checking:
                Number.isInteger(data.checking) && data.checking > 0
                  ? data.checking
                  : 0,
            },
          },
        };
      }
      case "slot": {
        const tracker = text(data.tracker);
        if (!tracker) return state;
        return {
          ...state,
          slots: {
            ...state.slots,
            [trackerKey(item, tracker)]: {
              tracker,
              item,
              verdict: text(data.verdict),
              title: text(data.title),
              reason: text(data.reason),
              slot: text(data.slot),
              why: text(data.why),
              conflicts: releaseEntries(data.conflicts),
              notes: (Array.isArray(data.notes) ? data.notes : [])
                .map(text)
                .filter(Boolean),
              rules: text(data.rules),
            },
          },
        };
      }
      case "tracker": {
        const tracker = text(data.tracker);
        if (!tracker) return state;
        const key = trackerKey(item, tracker);
        const previous = state.trackers[key] || {};
        // A final snapshot has no link or duration; keep the live result's.
        return {
          ...state,
          trackers: {
            ...state.trackers,
            [key]: {
              tracker,
              item,
              order: previous.order ?? Object.keys(state.trackers).length,
              status: text(data.status) || previous.status || "pending",
              link: text(data.link) || previous.link || "",
              torrentId: text(data.torrent_id) || previous.torrentId || "",
              message:
                data.status === "success"
                  ? text(data.message)
                  : text(data.message) || previous.message || "",
              duration: Number.isFinite(data.duration)
                ? data.duration
                : (previous.duration ?? null),
            },
          },
        };
      }
      case "request": {
        const tracker = text(data.tracker);
        const name = text(data.name);
        if (!tracker || !name) return state;
        const link = text(data.link);
        const key = `${item}|${tracker}|${link || name}`;
        if (state.requests.some((request) => request.key === key)) return state;
        const requests = [
          ...state.requests,
          {
            key,
            tracker,
            item,
            name,
            link,
            reward: text(data.reward),
            status: text(data.status),
            exact: Boolean(data.exact),
          },
        ];
        return { ...state, requests: requests.slice(-MAX_REQUESTS) };
      }
      default:
        return state;
    }
  };

  /** Apply one session event (any type) to the GUI state. */
  const reduceRunGuiEvent = (state, event) => {
    if (!event || typeof event !== "object") return state;
    if (event.type === "gui") {
      const data = event.data;
      if (!data || typeof data !== "object") return state;
      return reduceGuiData(state, data);
    }
    if (event.type === "prompt_state") {
      const awaiting = Boolean(event.awaiting);
      return {
        ...state,
        awaiting,
        inputType: awaiting ? event.input_type || "text" : null,
      };
    }
    if (event.type === "exit" || event.type === "finished") {
      const code = Number.isInteger(event.code)
        ? event.code
        : Number.isInteger(event.exit_code)
          ? event.exit_code
          : state.exitCode;
      return {
        ...state,
        finished: true,
        exitCode: code,
        awaiting: false,
        prompt: null,
      };
    }
    return state;
  };

  /**
   * Mark the open prompt as answered so its buttons stop accepting input, or
   * reopen it (answered = false) when sending the answer failed. ``promptId``
   * limits the change to that prompt, in case another one has opened since.
   */
  const markRunGuiPromptAnswered = (state, answered = true, promptId = null) =>
    state.prompt && (promptId === null || state.prompt.id === promptId)
      ? { ...state, prompt: { ...state.prompt, answered } }
      : state;

  const TRACKER_STATUS_ORDER = {
    failed: 0,
    pending: 1,
    success: 2,
    dupe: 3,
    banned: 4,
    skipped: 5,
  };

  /** Derive the lists each GUI block renders. */
  const selectRunGuiView = (state) => {
    const multipleItems = state.items.length > 1;
    const trackers = Object.values(state.trackers).sort(
      (a, b) =>
        a.item - b.item ||
        (TRACKER_STATUS_ORDER[a.status] ?? 9) -
          (TRACKER_STATUS_ORDER[b.status] ?? 9) ||
        a.tracker.localeCompare(b.tracker),
    );
    const counts = {
      success: 0,
      failed: 0,
      dupe: 0,
      banned: 0,
      skipped: 0,
      pending: 0,
    };
    trackers.forEach((entry) => {
      const status = entry.status in counts ? entry.status : "skipped";
      counts[status] += 1;
    });
    const currentStages = state.stages[state.currentItem] || {};
    const stages = RUN_GUI_STAGES.map((stage) => {
      let status = currentStages[stage.key] || "";
      // A stage still "start" after the run ended never finished.
      if (state.finished && status === "start") status = "fail";
      return { ...stage, status };
    });
    // "Needs attention" covers the item being processed now. Once a tracker
    // has a result row, or its item is finished, its slot check, dupes and
    // notices move under Results, so older warnings never look current.
    const isCurrent = (item) => !state.finished && item === state.currentItem;
    const hasRow = (item, tracker) =>
      Boolean(tracker && state.trackers[trackerKey(item, tracker)]);
    const attentionNotices = state.notices.filter(
      (notice) => notice.level === "attention",
    );
    const needsReview = (slot) =>
      slot.verdict === "block" || slot.verdict === "review";
    const cards = new Map();
    const card = (item, tracker) => {
      const key = trackerKey(item, tracker);
      if (!cards.has(key)) {
        cards.set(key, {
          key,
          item,
          tracker,
          slot: null,
          dupe: null,
          notices: [],
        });
      }
      return cards.get(key);
    };
    Object.values(state.slots).forEach((slot) => {
      card(slot.item, slot.tracker).slot = slot;
    });
    Object.values(state.dupes).forEach((dupe) => {
      card(dupe.item, dupe.tracker).dupe = dupe;
    });
    attentionNotices
      .filter((notice) => notice.tracker)
      .forEach((notice) =>
        card(notice.item, notice.tracker).notices.push(notice),
      );

    const attentionCards = [];
    const trackerDetails = {};
    const itemNotes = {};
    const archive = (item) => {
      itemNotes[item] = itemNotes[item] || {
        cards: [],
        notices: [],
        problems: [],
      };
      return itemNotes[item];
    };
    cards.forEach((entry) => {
      const relevant =
        entry.dupe ||
        entry.notices.length ||
        (entry.slot &&
          (needsReview(entry.slot) || entry.slot.conflicts.length > 0));
      if (!relevant) return;
      if (hasRow(entry.item, entry.tracker)) {
        trackerDetails[entry.key] = entry;
      } else if (isCurrent(entry.item)) {
        attentionCards.push(entry);
      } else {
        archive(entry.item).cards.push(entry);
      }
    });
    const currentNotices = [];
    attentionNotices
      .filter((notice) => !notice.tracker)
      .forEach((notice) => {
        if (isCurrent(notice.item)) currentNotices.push(notice);
        else archive(notice.item).notices.push(notice);
      });
    // Errors and warnings follow the same rule, but stay listed after the run
    // ends: only those of an earlier queue item move under its results.
    // Anything else (e.g. before the first item) concerns the whole run.
    const isEarlierItem = (item) =>
      item !== state.currentItem &&
      state.items.some((entry) => entry.index === item);
    const currentErrors = [];
    const currentWarnings = [];
    state.notices
      .filter(
        (notice) => notice.level === "error" || notice.level === "warning",
      )
      .forEach((notice) => {
        if (!isEarlierItem(notice.item)) {
          (notice.level === "error" ? currentErrors : currentWarnings).push(
            notice,
          );
        } else {
          archive(notice.item).problems.push(notice);
        }
      });

    const review =
      state.prompt?.context?.kind === "dupes"
        ? state.dupeReviews[state.prompt.item]
        : null;
    const reviewIndex = review
      ? review.started.indexOf(state.prompt.context.tracker)
      : -1;
    const dupeReview =
      reviewIndex >= 0
        ? {
            index: reviewIndex + 1,
            total: review.trackers.length,
            checking: review.checking,
          }
        : null;

    return {
      multipleItems,
      items: state.items,
      currentItem: state.items.find(
        (entry) => entry.index === state.currentItem,
      ),
      stages,
      hasStages: stages.some((stage) => stage.status),
      prompt: state.prompt,
      dupeReview,
      lastConfirm: state.lastConfirm,
      awaiting: state.awaiting,
      inputType: state.inputType,
      errors: currentErrors,
      warnings: currentWarnings,
      attention: attentionNotices,
      attentionCards,
      attentionNotices: currentNotices,
      trackerDetails,
      itemNotes,
      slots: state.slots,
      dupes: state.dupes,
      trackers,
      requests: state.requests,
      counts,
      finished: state.finished,
      exitCode: state.exitCode,
    };
  };

  // Upload data previews on the "Is this correct?" prompt. Each tracker's
  // form lists its fields; drop-down lists are shared in a table, by id.
  const PAYLOAD_KINDS = new Set([
    "text",
    "choice",
    "flag",
    "readonly",
    "deferred",
  ]);

  const readPayloadPreviews = (context) => {
    const source = context && typeof context === "object" ? context : {};
    const tables = {};
    for (const table of Array.isArray(source.payload_choices)
      ? source.payload_choices
      : []) {
      if (
        table &&
        typeof table.id === "string" &&
        Array.isArray(table.choices)
      ) {
        tables[table.id] = table.choices
          .filter((pair) => Array.isArray(pair) && pair.length === 2)
          .map(([value, label]) => [String(value), String(label)]);
      }
    }
    return (Array.isArray(source.payloads) ? source.payloads : [])
      .filter((preview) => preview && typeof preview.tracker === "string")
      .map((preview) => ({
        tracker: preview.tracker,
        name: text(preview.name),
        fields: (Array.isArray(preview.fields) ? preview.fields : [])
          .filter(
            (field) =>
              field &&
              typeof field.key === "string" &&
              PAYLOAD_KINDS.has(field.kind),
          )
          .map((field) => {
            const choices = tables[field.choices] || [];
            // A drop-down whose list was too long to send is shown, not edited.
            const editable =
              field.kind === "text" ||
              field.kind === "flag" ||
              (field.kind === "choice" && choices.length > 0);
            return {
              key: field.key,
              label: text(field.label) || field.key,
              kind: field.kind,
              value:
                field.kind === "flag"
                  ? field.value === true
                  : text(field.value),
              display: text(field.display),
              choices,
              max: Number.isInteger(field.max) ? field.max : 255,
              numeric: field.numeric === true,
              note: text(field.note),
              role: text(field.role),
              editable,
            };
          }),
      }));
  };

  /** The value shown for a field: the edited one, or what the run reported. */
  const payloadFieldValue = (field, edits, tracker) => {
    const changed = edits && edits[tracker];
    return changed && field.key in changed ? changed[field.key] : field.value;
  };

  /** Edits with one field set; a value equal to the original is dropped. */
  const updatePayloadEdits = (edits, tracker, field, value) => {
    const next = { ...(edits || {}) };
    const forTracker = { ...(next[tracker] || {}) };
    if (value === field.value) delete forTracker[field.key];
    else forTracker[field.key] = value;
    if (Object.keys(forTracker).length) next[tracker] = forTracker;
    else delete next[tracker];
    return next;
  };

  /** Why an edited value would be refused by the run, or "" when it is fine. */
  const payloadFieldError = (field, value) => {
    if (field.kind === "flag")
      return typeof value === "boolean" ? "" : "Invalid value";
    if (field.kind === "choice") {
      return field.choices.some(([option]) => option === value)
        ? ""
        : "Pick a value from the list";
    }
    if (field.kind !== "text" || typeof value !== "string") return "";
    const trimmed = value.trim();
    if (/[\r\n]/.test(value)) return "Use a single line";
    if (trimmed.length > field.max) return `At most ${field.max} characters`;
    if (!trimmed && field.value.trim()) return "Cannot be empty";
    if (field.numeric && trimmed && !/^[0-9]+$/.test(trimmed))
      return "Numbers only";
    return "";
  };

  /** Edits that the run would refuse, as ``{tracker: {key: message}}``. */
  const payloadEditErrors = (previews, edits) => {
    const errors = {};
    for (const preview of previews) {
      const changed = (edits || {})[preview.tracker] || {};
      for (const field of preview.fields) {
        if (!(field.key in changed)) continue;
        const message = payloadFieldError(field, changed[field.key]);
        if (message) {
          errors[preview.tracker] = {
            ...(errors[preview.tracker] || {}),
            [field.key]: message,
          };
        }
      }
    }
    return errors;
  };

  // Fields whose value comes from the release's metadata: changing them here
  // fixes only this tracker's form, so the advice names the correction that
  // fixes it everywhere (the name, the description and the dupe check too).
  const PAYLOAD_ROLE_ADVICE = Object.freeze({
    name: "Retyping the name changes only this form. If part of it is wrong (title, year, edition, group, source), answer No and correct that part (for example --imdb, --tmdb, --year, --edition or --tag).",
    title:
      "This title comes from IMDb/TMDB. If it is the wrong work, answer No and correct it with --imdb or --tmdb.",
    external_id:
      "The name, description, artwork and dupe check were made for the current ID. If it is wrong, answer No and correct it with --tmdb, --imdb, --tvdb, --mal or --tvmaze.",
    category:
      "The name, IDs and description were made for this category. If it is wrong, answer No and correct it with --category.",
    release_type:
      "If the type or source is wrong, answer No and correct it with --type or --source; the name and the dupe check use it.",
    resolution:
      "If the resolution is wrong, answer No and correct it with --resolution; the name and the dupe check use it.",
    season_episode:
      "If the season or episode is wrong, answer No and correct it with --season or --episode; the name uses it.",
    group:
      "If the group is wrong, answer No and correct it with --tag; the name uses it.",
    edition:
      "If the edition is wrong, answer No and correct it with --edition; the name uses it.",
    staff_flag:
      "Usually only staff or approved internal groups may set this; the tracker may reject the upload.",
  });
  // Roles whose value appears in the release name.
  const NAME_PART_ROLES = new Set([
    "release_type",
    "resolution",
    "season_episode",
    "group",
    "edition",
  ]);
  // Roles the name and description are built from as a whole.
  const NAME_SOURCE_ROLES = new Set(["external_id", "category", "title"]);

  /** The advice shown next to a field before it is changed, or "". */
  const payloadRoleAdvice = (role) => PAYLOAD_ROLE_ADVICE[role] || "";

  /** How a field's original value reads, to look for it in the name. */
  const payloadOriginalLabel = (field) => {
    if (field.kind !== "choice") return String(field.value || "");
    const match = field.choices.find(([option]) => option === field.value);
    const label = field.display || (match ? match[1] : field.value);
    return String(label)
      .replace(/\s*\([^)]*\)$/, "")
      .split(" / ")[0];
  };

  /** The part of the original value worth finding in the name ("1080p" in "1080p / 1440p"). */
  const payloadNameToken = (field) => {
    const label = payloadOriginalLabel(field).trim();
    if (field.role === "resolution") {
      const resolution = label.match(/\b\d{3,4}[pi]\b/i);
      return resolution ? resolution[0] : "";
    }
    return label.length >= 2 && !/^\d+$/.test(label) ? label : "";
  };

  /**
   * Warnings for one tracker's changed fields, as ``{key: message}``.
   *
   * Changing what the name is made of while leaving the name as it is makes
   * the form disagree with itself, so those warnings say so.
   */
  const payloadEditWarnings = (preview, edits) => {
    const changed = (edits || {})[preview.tracker] || {};
    const nameField = preview.fields.find(
      (field) => field.role === "name" && field.kind === "text",
    );
    const nameKept = Boolean(nameField) && !(nameField.key in changed);
    const name = nameField ? String(nameField.value).toLowerCase() : "";
    const warnings = {};
    for (const field of preview.fields) {
      if (!(field.key in changed) || !PAYLOAD_ROLE_ADVICE[field.role]) continue;
      const value = changed[field.key];
      // Clearing a staff option is always allowed.
      if (
        field.role === "staff_flag" &&
        (value === false || value === "0" || value === "")
      ) {
        continue;
      }
      let message = PAYLOAD_ROLE_ADVICE[field.role];
      if (nameKept && NAME_PART_ROLES.has(field.role)) {
        const token = payloadNameToken(field);
        message +=
          token && name.includes(token.toLowerCase())
            ? ` The name still says "${token}".`
            : " The name was not changed.";
      } else if (nameKept && NAME_SOURCE_ROLES.has(field.role)) {
        message +=
          " The name was not changed and still describes the previous one.";
      }
      warnings[field.key] = message;
    }
    return warnings;
  };

  /** The "yes" answer, carrying changed run options and upload data. */
  const buildConfirmAnswer = (runOptionValues, payloadEdits) => {
    const values = { ...(runOptionValues || {}) };
    if (payloadEdits && Object.keys(payloadEdits).length) {
      values.payload_edits = payloadEdits;
    }
    return Object.keys(values).length ? `yes ${JSON.stringify(values)}` : "yes";
  };

  const api = {
    RUN_GUI_STAGES,
    createRunGuiState,
    readPayloadPreviews,
    payloadFieldValue,
    updatePayloadEdits,
    payloadEditErrors,
    payloadRoleAdvice,
    payloadEditWarnings,
    buildConfirmAnswer,
    reduceRunGuiEvent,
    markRunGuiPromptAnswered,
    selectRunGuiView,
    getDebugRunRows,
  };
  window.UARunGui = api;
})();

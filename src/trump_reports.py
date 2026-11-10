# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Trump reports: telling a tracker that an upload replaces a torrent already on the site.

The whole flow lives here. During the duplicate review, ``find_candidates``
lists the torrents the upload may replace and ``review`` asks every question
(which torrent, existing reports, comparison, note) in one go. The answers
are stored per tracker in ``meta.trump_plans``. After the uploads,
``submit_reports`` sends one report per tracker whose upload finished; it asks
nothing.

A tracker opts in by setting ``trump_support`` and implementing
``trump_report_request`` (and ``find_trump_reports`` when the site can list
existing reports).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, cast

import cli_ui
import httpx
from rich.markup import escape

from src import webui_events
from src.console import logger, prompt_in_thread
from src.manual_input import prompt_session
from src.meta import Meta
from src.slot_rules.models import SlotDecision, Verdict

# Why the upload replaces the torrent, from the most to the least certain.
EXACT_MATCH = "exact_match"
TRUMPABLE = "trumpable"
SLOT_RULES = "slot_rules"
SEASON_PACK = "season_pack"

REASON_LABELS = {
    EXACT_MATCH: "same files as your upload",
    TRUMPABLE: "marked trumpable on the site",
    SLOT_RULES: "your upload takes its slot",
    SEASON_PACK: "episode contained in your season pack",
}
REPORT_MESSAGES = {
    EXACT_MATCH: "exact filename trump",
    TRUMPABLE: "trumpable release trump",
    SLOT_RULES: "slot trump",
    SEASON_PACK: "season pack trump",
}


@dataclass(frozen=True)
class TrumpSupport:
    """What a tracker's trump reports need."""

    # Existing reports for a torrent can be listed (``find_trump_reports``).
    searchable: bool = False
    # Reports need comparison screenshots (never asked for TV packs).
    comparison: bool = False
    # Reports take a free-text reason from the user (never asked for TV packs).
    note: bool = False


@dataclass
class TrumpCandidate:
    """A torrent on the site that the upload may replace."""

    entry: dict[str, Any]
    reason: str
    # The rule behind a slot-rules candidate, in plain words.
    detail: str = ""
    rules_url: str = ""

    @property
    def torrent_id(self) -> str:
        return str(self.entry.get("id") or "")

    @property
    def name(self) -> str:
        return str(self.entry.get("name") or "")


@dataclass
class TrumpPlan:
    """A trump report to send once the upload to ``tracker`` finished."""

    tracker: str
    reported_id: str
    reported_name: str
    reason: str
    reported_link: str = ""
    detail: str = ""
    rules_url: str = ""
    # "description" when the comparison is in the upload description.
    comparison: str = ""
    reported_screenshots: list[str] = field(default_factory=lambda: list[str]())
    trumping_screenshots: list[str] = field(default_factory=lambda: list[str]())
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrumpPlan:
        known = {name: data[name] for name in cls.__dataclass_fields__ if name in data}
        return cls(**known)


class ReviewOutcome(Enum):
    # A report will be sent after the upload.
    PLANNED = "planned"
    # No report; the normal duplicate question decides the upload.
    DECLINED = "declined"
    # The user chose not to upload to this tracker.
    SKIP_UPLOAD = "skip_upload"


def support(tracker: Any) -> TrumpSupport | None:
    """The tracker's trump report support (class or instance), or None."""
    value = getattr(tracker, "trump_support", None)
    return value if isinstance(value, TrumpSupport) else None


def get_plan(meta: Meta, tracker: str) -> TrumpPlan | None:
    raw = (meta.trump_plans or {}).get(tracker)
    return TrumpPlan.from_dict(raw) if isinstance(raw, Mapping) else None


def is_exact_trump(meta: Meta, tracker: str) -> bool:
    """Whether the upload to ``tracker`` re-uploads the exact files of the torrent it trumps."""
    plan = get_plan(meta, tracker)
    return plan is not None and plan.reason == EXACT_MATCH


def slot_trumps(decision: SlotDecision | None) -> bool:
    """Whether slot rules say the upload replaces releases in its slot."""
    return decision is not None and decision.verdict is Verdict.ALLOW and decision.trump and bool(decision.conflicts)


def _season_pack_episode(meta: Meta, tracker: str) -> dict[str, Any] | None:
    """One episode the season pack replaces, preferring the upload's own group."""
    matched = cast(list[Any], meta.get(f"{tracker}_matched_episode_ids") or [])
    episodes: list[dict[str, Any]] = [cast(dict[str, Any], entry) for entry in matched if isinstance(entry, dict)]
    episodes = [entry for entry in episodes if entry.get("id")]
    if not episodes:
        return None
    tag = (meta.tag or "").lstrip("-").lower()
    if tag:
        for entry in episodes:
            name = str(entry.get("name", "")).lower()
            if name.endswith(tag) or f"-{tag}" in name:
                return entry
    return episodes[0]


def _same_files(meta: Meta, entry: Mapping[str, Any]) -> bool:
    """Whether the torrent holds exactly the upload's files (by file name)."""
    local = sorted(Path(str(path)).name.lower() for path in (meta.filelist or []) if path)
    raw: Any = entry.get("files") or []
    items = [str(item) for item in cast(list[Any], raw)] if isinstance(raw, list) else [str(raw)]
    # Some sites send the file list as one comma-separated string.
    if len(items) == 1 and "," in items[0]:
        items = items[0].split(",")
    remote = sorted(Path(item.strip()).name.lower() for item in items if item.strip())
    return bool(local) and local == remote


def find_candidates(meta: Meta, tracker: str, dupes: Sequence[Any], slot_decision: SlotDecision | None) -> list[TrumpCandidate]:
    """Torrents on ``tracker`` the upload may replace, each listed once with its strongest reason."""
    found: list[TrumpCandidate] = []
    seen: set[str] = set()

    def add(entry: Mapping[str, Any], reason: str, *, detail: str = "", rules_url: str = "") -> None:
        torrent_id = str(entry.get("id") or "")
        # A report names the torrent by its ID; without one nothing can be reported.
        if not torrent_id or torrent_id in seen:
            return
        seen.add(torrent_id)
        found.append(TrumpCandidate(dict(entry), reason, detail, rules_url))

    entries = [cast(dict[str, Any], entry) for entry in dupes if isinstance(entry, dict)]
    if meta.filename_match and meta.file_count_match:
        for entry in entries:
            if f"{entry.get('name')} = {entry.get('link', None)}" == meta.filename_match and _same_files(meta, entry):
                add(entry, EXACT_MATCH)
    if found:
        # Uploading the same files again is only allowed as the trump of that torrent.
        return found
    for entry in entries:
        if entry.get("trump_target"):
            add(entry, TRUMPABLE)
    if slot_decision is not None and slot_trumps(slot_decision):
        for entry in slot_decision.conflicts:
            add(entry, SLOT_RULES, detail=slot_decision.why, rules_url=slot_decision.rules_url)
    if meta.tv_pack:
        episode = _season_pack_episode(meta, tracker)
        if episode is not None:
            add(episode, SEASON_PACK)
    return found


def report_message(meta: Meta, plan: TrumpPlan) -> str:
    """The message sent with a report; trackers may add to it."""
    message = f"{meta.ua_name or 'Upload Assistant'} {REPORT_MESSAGES.get(plan.reason, 'trump')}"
    if plan.detail:
        message += f": {plan.detail}"
    if plan.comparison == "description":
        message += " - Comparison screenshots are in the description."
    if plan.note:
        message += f" - {plan.note}"
    return message


async def _ask_yes_no(question: str, *, default: bool = False) -> bool:
    async with prompt_session():
        return bool(await prompt_in_thread(cli_ui.ask_yes_no, question, default=default))


async def _ask_string(question: str, *, default: str = "") -> str:
    async with prompt_session():
        return str(await prompt_in_thread(cli_ui.ask_string, question, default=default) or "").strip()


def _links(text: str) -> list[str]:
    return [link.strip() for link in text.split(",") if link.strip()]


class _DeclinedError(Exception):
    """The user left a required trump answer empty."""


async def _choose(candidates: list[TrumpCandidate], tracker: str, describe: Callable[[Mapping[str, Any]], str]) -> TrumpCandidate | None:
    """Ask which torrent the upload replaces; None means no trump report."""
    for candidate in candidates:
        logger.info(f"[bold cyan]{describe(candidate.entry)}[/bold cyan] [dim]({REASON_LABELS[candidate.reason]})[/dim]", extra={"highlighter": None})
        if candidate.detail:
            logger.info(f"  [dim]{candidate.detail}[/dim]")
    logger.info(f"[yellow]{tracker} accepts trump reports: if your upload replaces one of these, the old torrent can be reported after uploading.[/yellow]")
    if len(candidates) == 1:
        return candidates[0] if await _ask_yes_no(f"Are you trumping this release on {tracker}?", default=False) else None

    labels = [f"{candidate.name} ({REASON_LABELS[candidate.reason]})" for candidate in candidates]
    for number, label in enumerate(labels, start=1):
        logger.info(f"  {number}. {escape(label)}", extra={"highlighter": None})
    with webui_events.numbered_options(labels, actions=[("", "Not trumping")], hint=f"Pick the torrent your upload replaces on {tracker}."):
        answer = await _ask_string("Enter the number of the release you are trumping, or press Enter if you are not trumping:")
    # isdecimal, not isdigit: int() rejects digits such as "²".
    if answer.isdecimal() and 1 <= int(answer) <= len(candidates):
        return candidates[int(answer) - 1]
    return None


async def _proceed_despite_reports(tracker_instance: Any, tracker: str, candidate: TrumpCandidate, meta: Meta) -> bool:
    """Check the site for reports on the torrent; False means the user does not want to upload."""
    reports = await tracker_instance.find_trump_reports(meta, candidate.torrent_id)
    if reports is None:
        with webui_events.field_prompt(
            "Trump report",
            {"Tracker": tracker, "Trumped torrent": candidate.name},
            hint=f"{tracker} did not answer the search for existing trump reports, so another upload may already be replacing this torrent.",
        ):
            return await _ask_yes_no(f"Could not check existing trump reports on {tracker}. Upload and report the trump anyway?", default=False)
    if not reports:
        return True

    logger.info(f"[bold yellow]Found {len(reports)} existing trump report(s) on {tracker} for this release[/bold yellow]")
    summary: dict[str, Any] = {"Tracker": tracker}
    for report in reports:
        trumping: list[dict[str, Any]] = [cast(dict[str, Any], torrent) for torrent in cast(list[Any], report.get("trumping_torrent") or []) if isinstance(torrent, dict)]
        names = ", ".join(str(torrent.get("name", "Unknown")) for torrent in trumping)
        title = str(report.get("title") or "")
        solved = bool(report.get("solved"))
        # Titles and names come from the site: print them as plain text, not Rich markup.
        logger.info(f"  [cyan]Report ID:[/cyan] {escape(str(report.get('id')))} - [cyan]Title:[/cyan] {escape(title)}{' [dim](solved)[/dim]' if solved else ''}")
        if names:
            logger.info(f"  [bold green]Already being trumped by:[/bold green] {escape(names)}")
        elif solved:
            logger.info("  [yellow]This report is already solved.[/yellow]")
        else:
            logger.info("  [yellow]The trumping torrent for this report seems to be in the moderation queue.[/yellow]")
        status = "Solved" if solved else "In moderation queue"
        summary[f"Report {report.get('id')}"] = f"{title} (trumped by: {names})" if names else (f"{title} ({status.lower()})" if title else status)
    with webui_events.field_prompt("Existing trump reports", summary, hint=f"Found {len(reports)} existing trump report(s) on {tracker} for this release."):
        return await _ask_yes_no("Do you want to proceed with the upload anyway?", default=False)


async def _ask_comparison(plan: TrumpPlan, tracker: str, release: str) -> None:
    """Fill the comparison a report needs; raises ``_DeclinedError`` when none is given."""
    question, buttons = (
        "Enter 'd' if the comparison is in the description, 'L' to paste links, or press Enter if you are not trumping:",
        [
            ("d", "In the description"),
            ("L", "Paste links"),
            ("", "Not trumping"),
        ],
    )
    with webui_events.field_prompt(
        "Trump report comparison",
        {"Tracker": tracker, "Release": release, "Trumped torrent": plan.reported_name},
        hint=f"{tracker} needs comparison screenshots for trump reports.",
        actions=buttons,
    ):
        where = await _ask_string(question)
    if where.lower() == "d":
        plan.comparison = "description"
        return
    if where.lower() != "l":
        raise _DeclinedError
    summary = {"Tracker": tracker, "Trumped torrent": plan.reported_name, "Trumped torrent screenshots": ""}
    hint = "Comma-separated screenshot links. Leaving it blank means you are not trumping."
    with webui_events.field_prompt("Trump report comparison", summary, focus="Trumped torrent screenshots", hint=hint, actions=[("", "Not trumping")]):
        plan.reported_screenshots = _links(await _ask_string("Paste screenshot links for the torrent you are trumping (comma-separated):"))
    if not plan.reported_screenshots:
        raise _DeclinedError
    summary = {**summary, "Trumped torrent screenshots": ", ".join(plan.reported_screenshots), "Your upload screenshots": ""}
    with webui_events.field_prompt("Trump report comparison", summary, focus="Your upload screenshots", hint=hint, actions=[("", "Not trumping")]):
        plan.trumping_screenshots = _links(await _ask_string("Paste screenshot links for your upload (comma-separated):"))
    if not plan.trumping_screenshots:
        raise _DeclinedError


async def review(
    meta: Meta,
    tracker: str,
    tracker_instance: Any,
    candidates: list[TrumpCandidate],
    describe: Callable[[Mapping[str, Any]], str],
) -> ReviewOutcome:
    """Ask every trump question for one tracker and store the plan in ``meta.trump_plans``.

    Only call this for interactive runs: every answer defaults to no report.
    EOFError (Ctrl+C at a prompt) propagates to the caller.
    """
    meta.trump_plans.pop(tracker, None)
    tracker_support = support(tracker_instance)
    if tracker_support is None or not candidates:
        return ReviewOutcome.DECLINED

    webui_events.dupes(
        tracker,
        [candidate.entry for candidate in candidates],
        source_size=meta.source_size,
        trumpable=True,
        note=f"Your upload may replace {'this release' if len(candidates) == 1 else 'one of these releases'}. {tracker} accepts a trump report for it after uploading.",
    )
    logger.info("[bold red]Trumpable found![/bold red]", extra={"ua_gui": False})
    candidate = await _choose(candidates, tracker, describe)
    if candidate is None:
        return ReviewOutcome.DECLINED

    if tracker_support.searchable and not await _proceed_despite_reports(tracker_instance, tracker, candidate, meta):
        logger.info(f"[bold red]{tracker}: not uploading, as chosen at the trump report question.[/bold red]")
        return ReviewOutcome.SKIP_UPLOAD

    plan = TrumpPlan(
        tracker=tracker,
        reported_id=candidate.torrent_id,
        reported_name=candidate.name,
        reason=candidate.reason,
        reported_link=str(candidate.entry.get("link") or ""),
        detail=candidate.detail,
        rules_url=candidate.rules_url,
    )
    try:
        if tracker_support.comparison and not meta.tv_pack:
            await _ask_comparison(plan, tracker, meta.name or meta.title or "")
        if tracker_support.note and not meta.tv_pack:
            summary = {"Tracker": tracker, "Trumped torrent": plan.reported_name, "Report message": report_message(meta, plan)}
            with webui_events.field_prompt(
                "Trump report", summary, hint="Added to the report message. Leave it blank to send the report without it.", actions=[("", "No reason")]
            ):
                plan.note = await _ask_string(f"Enter a reason for the trump report on {tracker} (optional):")
    except _DeclinedError:
        logger.info(f"[yellow]{tracker}: no comparison given, so no trump report will be sent.[/yellow]")
        return ReviewOutcome.DECLINED

    meta.trump_plans[tracker] = plan.to_dict()
    logger.info(f"[green]{tracker}: a trump report for {escape(plan.reported_name)} will be sent after the upload.[/green]")
    return ReviewOutcome.PLANNED


async def submit_reports(meta: Meta, config: dict[str, Any], tracker_class_map: Mapping[str, Any]) -> dict[str, bool]:
    """Send the planned report of every tracker whose upload finished; returns each tracker's result."""
    results: dict[str, bool] = {}
    for tracker in list(meta.trump_plans or {}):
        plan = get_plan(meta, tracker)
        status = cast(Mapping[str, Any], (meta.tracker_status or {}).get(tracker) or {})
        tracker_cls = tracker_class_map.get(tracker)
        if plan is None or tracker_cls is None or status.get("upload") is not True:
            continue
        tracker_instance = tracker_cls(config=config)
        if support(tracker_instance) is None:
            continue
        trumping_id = status.get("torrent_id")
        if not trumping_id and not meta.debug:
            logger.info(f"[red]{tracker}: the upload did not return a torrent ID, so the trump report was not sent.[/red]")
            results[tracker] = False
            continue
        logger.info(f"[yellow]Submitting trump report to {tracker}.....")
        results[tracker] = await _send(meta, config, tracker, tracker_instance, plan, trumping_id)
    return results


async def _send(meta: Meta, config: dict[str, Any], tracker: str, tracker_instance: Any, plan: TrumpPlan, trumping_id: Any) -> bool:
    try:
        url, payload = tracker_instance.trump_report_request(plan, trumping_id, report_message(meta, plan))
    except ValueError as e:
        logger.info(f"[red]{tracker}: the trump report could not be built ({e}).[/red]")
        return False
    if meta.debug:
        logger.info("[bold yellow]Debug mode enabled, skipping actual trump report creation.[/bold yellow]")
        logger.info(f"[cyan]POST URL: {url}[/cyan]")
        logger.info(f"[cyan]Payload: {payload}[/cyan]")
        return True

    from src.api_key_expiry import observe_tracker_response

    headers = {"Authorization": f"Bearer {tracker_instance.api_key}", "Content-Type": "application/json", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url=url, headers=headers, json=payload)
    except httpx.TimeoutException:
        logger.info(f"[bold red]{tracker}: the trump report request timed out after 10 seconds.[/bold red]")
        return False
    except httpx.RequestError as e:
        logger.info(f"[bold red]{tracker}: the trump report request failed: {e}[/bold red]")
        return False
    observe_tracker_response(config, meta, tracker, response)
    if response.status_code in (200, 201):
        logger.info(f"[bold green]Successfully created trump report on {tracker}[/bold green]")
        return True
    logger.info(f"[bold red]{tracker}: failed to create the trump report. HTTP Status: {response.status_code}[/bold red]")
    return False

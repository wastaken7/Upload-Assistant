# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Fill an XXX release's metadata from ThePornDB and BLVCKOUT.

The lookup tries, in order: an ID given with ``--tpdb``/``--blvckout`` (or
remembered from an earlier run), the main video's file hash on ThePornDB, a
ThePornDB search with the release name, then a BLVCKOUT movie search. A
result is used without asking only when it is clearly the release (same file
hash, or a matching title plus the same date or studio). Otherwise the
plausible results are offered in an ``xxx.match`` question; unattended runs
skip them.

Values given on the command line always win over provider data.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from src.blvckout import LABEL as BLVCKOUT_LABEL
from src.blvckout import BlvckoutClient
from src.blvckout import parse_reference as parse_blvckout_reference
from src.config_helpers import parse_bool
from src.console import logger
from src.manual_input import Choice, Question, ask
from src.media_extensions import VIDEO_EXTENSIONS
from src.meta import Meta
from src.tpdb import LABEL as TPDB_LABEL
from src.tpdb import TpdbClient
from src.tpdb import parse_reference as parse_tpdb_reference
from src.xxx_match import (
    MatchScore,
    ReleaseFacts,
    XxxRelease,
    bracketed_site_parts,
    bracketed_year,
    build_release_name,
    compact,
    confident_choice,
    dated_name_parts,
    is_pack_name,
    is_stable_image_url,
    jav_code,
    looks_like_movie,
    oshash,
    performers_from_name,
    rank,
    search_title,
)

MATCH_QUESTION_KEY = "xxx.match"
_NO_MATCH = "none"
_LABELS = {"tpdb": TPDB_LABEL, "blvckout": BLVCKOUT_LABEL}
_KIND_LABELS = {"scenes": "scene", "movies": "movie", "jav": "JAV"}
_BRACKETED_YEAR = re.compile(r"\s*[(\[](?:19|20)\d{2}[)\]]")


def is_scene_style_name(name: str) -> bool:
    """Whether a name already follows scene naming (dots, no spaces, an ``.XXX`` marker)."""
    return bool(name) and " " not in name and bool(re.search(r"(?i)[.]XXX(?:[.-]|$)", name))


def release_name(meta: Meta) -> str:
    return str(meta.scene_name or meta.basename_no_ext or "")


def generated_release_name(meta: Meta) -> str:
    """The scene-style name built from the chosen match, or "" when the release keeps its own."""
    if not meta.xxx_rename or meta.manual_name is not None:
        return ""
    release = XxxRelease.from_dict(meta.xxx_match)
    if release is None:
        return ""
    # --publisher and --cast correct the provider's studio and performers in the name too.
    release = replace(release, studio=str(meta.book_publisher or "").strip() or release.studio, performers=list(meta.manual_cast or release.performers))
    container = meta.container or Path(str(meta.filelist[0] if meta.filelist else meta.path or "")).suffix.lstrip(".")
    return build_release_name(release, resolution=str(meta.resolution or ""), container=container)


def _main_videos(meta: Meta) -> list[Path]:
    paths = [Path(str(path)) for path in meta.filelist or []]
    if not paths and meta.path:
        paths = [Path(str(meta.path))]
    return [path for path in paths if path.suffix.casefold() in VIDEO_EXTENSIONS and "sample" not in path.name.casefold()]


def _facts(meta: Meta, name: str, single_video: bool) -> ReleaseFacts:
    date = str(meta.release_date or "")
    date = date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else ""
    studio = str(meta.publisher or "")
    title = str(meta.title or "")
    name_year: int | None = None
    parts = None if date and studio else dated_name_parts(name)
    if parts:
        # "Studio YY.MM.DD Title" with spaces, which the scene-name parser does not read.
        studio, date, title = studio or parts[0], date or parts[1], title or parts[2]
    elif not (date and studio) and (bracketed := bracketed_site_parts(name)):
        # "[Site.com] YY.MM.DD Performer - Title [1080p]", as BitPorn uploads are named.
        studio, date, name_year = studio or bracketed[0], date or bracketed[1], bracketed[2]
        title = title or bracketed[3]
    year = meta.year if isinstance(meta.year, int) and meta.year > 0 else name_year or bracketed_year(name) or (int(date[:4]) if date else None)
    title = _BRACKETED_YEAR.sub("", title or search_title(name)).strip()
    return ReleaseFacts(
        title=title,
        studio=studio,
        date=date,
        year=year,
        duration_minutes=int(meta.video_duration) if single_video and meta.video_duration else None,
        code=jav_code(name),
    )


def _scene_query(facts: ReleaseFacts) -> str:
    """A query TPDB's parser reads well: ``site.YYYY-MM-DD.title`` when the name gave those."""
    if facts.studio and facts.date and facts.title:
        return f"{compact(facts.studio)}.{facts.date}.{facts.title}"
    return facts.title


def _word_query(title: str) -> str:
    """The first words of a title for a free-word search, which fails on long phrases."""
    words = [word for word in re.split(r"[\s._]+", title) if word and word.casefold() not in {"and", "&", "the", "a", "an"}]
    return " ".join(words[:4])


def _describe(release: XxxRelease) -> str:
    when = release.date or (str(release.year) if release.year else "")
    performers = ", ".join(release.performers[:3]) + (" …" if len(release.performers) > 3 else "")
    parts = [part for part in (release.studio, when, release.title, performers) if part]
    return f"{_LABELS.get(release.provider, release.provider)} {_KIND_LABELS.get(release.kind, release.kind)}: {' | '.join(parts)}"


class XxxMetadataLookup:
    def __init__(self, config: dict[str, Any], meta: Meta) -> None:
        default: Any = config.get("DEFAULT", {})
        self.default: dict[str, Any] = cast(dict[str, Any], default) if isinstance(default, dict) else {}
        user_agent = " ".join(part for part in (meta.ua_name or "Upload-Assistant", meta.current_version) if part)
        self.tpdb = TpdbClient(str(self.default.get("tpdb_api_key") or ""), base_dir=meta.base_dir, user_agent=user_agent)
        self.blvckout = BlvckoutClient(str(self.default.get("blvckout_api_key") or ""), base_dir=meta.base_dir, user_agent=user_agent)

    @property
    def enabled(self) -> bool:
        return parse_bool(self.default.get("xxx_metadata_lookup", True), default=True)

    async def _manual(self, meta: Meta) -> XxxRelease | None:
        if meta.tpdb_manual:
            reference = parse_tpdb_reference(meta.tpdb_manual)
            if reference is None:
                logger.warning(f"[yellow]--tpdb {meta.tpdb_manual!r} is not a ThePornDB ID or link; ignoring it.[/yellow]")
            elif not self.tpdb.enabled:
                logger.warning("[yellow]--tpdb needs DEFAULT.tpdb_api_key; ignoring it.[/yellow]")
            else:
                release = await self.tpdb.detail(*reference)
                if release:
                    return release
                logger.warning(f"[yellow]{TPDB_LABEL}: nothing found for {meta.tpdb_manual}; searching instead.[/yellow]")
        if meta.blvckout_manual:
            identity = parse_blvckout_reference(meta.blvckout_manual)
            if identity is None:
                logger.warning(f"[yellow]--blvckout {meta.blvckout_manual!r} is not a BLVCKOUT ID or link; ignoring it.[/yellow]")
            elif not self.blvckout.enabled:
                logger.warning("[yellow]--blvckout needs DEFAULT.blvckout_api_key; ignoring it.[/yellow]")
            else:
                release = await self.blvckout.detail(identity)
                if release:
                    return release
                logger.warning(f"[yellow]{BLVCKOUT_LABEL}: nothing found for {meta.blvckout_manual}; searching instead.[/yellow]")
        return None

    async def _details(self, release: XxxRelease) -> XxxRelease:
        """Prefer the full record of a chosen search result; keep the result when that fails."""
        if release.provider == "tpdb":
            # ThePornDB search results already carry the full record.
            if release.performers or release.description:
                return release
            detailed = await self.tpdb.detail(release.kind, release.id)
        else:
            detailed = await self.blvckout.detail(release.id)
        return detailed or release

    async def _search(self, meta: Meta, name: str) -> tuple[XxxRelease | None, list[MatchScore]]:
        """Return a confident match, or None and the results ranked for a person to choose from."""
        videos = _main_videos(meta)
        facts = _facts(meta, name, len(videos) == 1)
        found: list[XxxRelease] = []
        ranked: list[MatchScore] = []

        def decide() -> XxxRelease | None:
            nonlocal ranked
            ranked = rank(found, facts)
            best = confident_choice(ranked)
            return best.release if best else None

        def plausible() -> bool:
            return any(item.plausible for item in ranked)

        steps: list[tuple[str, str]] = []
        if self.tpdb.enabled:
            if facts.code:
                steps.append(("jav", facts.code))
            if facts.date:
                # A dated scene: the full name, then every scene of that site and day, then free words.
                steps.append(("scenes", _scene_query(facts)))
                if facts.studio:
                    steps.append(("scenes", f"{compact(facts.studio)} {facts.date}"))
                steps.append(("words", _word_query(facts.title)))
            elif not facts.code:
                movie_like = meta.is_disc == "DVD" or looks_like_movie(name)
                if facts.studio:
                    # "[Site.com] Performer - Title 2026": the site and the scene title.
                    steps.append(("scenes", f"{compact(facts.studio)} {facts.title.partition(' - ')[2] or facts.title}"))
                steps.extend([("movies", facts.title), ("scenes", facts.title)] if movie_like else [("scenes", facts.title), ("movies", facts.title)])
                _left, separator, right = facts.title.partition(" - ")
                if separator and len(right) >= 3:
                    # "Studio - Title" or "Performer - Title": also search the title alone.
                    steps.extend([("movies-if-none", right), ("scenes-if-none", right)])

        if len(videos) >= 2:
            # Several videos are a movie in parts or a collection, never one scene:
            # a dated name would otherwise give one scene's metadata to all of them.
            steps = [step for step in steps if step[0] in ("jav", "movies", "movies-if-none")]

        if self.tpdb.enabled and len(videos) == 1:
            file_hash = await asyncio.to_thread(oshash, videos[0])
            if file_hash:
                found.extend(await self.tpdb.find_by_hash(file_hash))
                match = decide()
                if match:
                    return match, ranked

        for kind, query in steps:
            if kind == "words":
                # Reached only without a confident match, which a plausible result with a
                # conflicting runtime cannot become; the free-word search may still find it.
                found.extend(await self.tpdb.search_words(query))
            elif kind.endswith("-if-none"):
                if plausible():
                    continue
                found.extend(await self.tpdb.search(kind.removesuffix("-if-none"), query))
            else:
                found.extend(await self.tpdb.search(kind, query))
            match = decide()
            if match:
                return match, ranked

        if self.blvckout.enabled and not facts.code and (not facts.date or not plausible()):
            found.extend(await self.blvckout.search(facts.title))
            match = decide()
            if match:
                return match, ranked
        return None, ranked

    async def _choose(self, meta: Meta, name: str, ranked: list[MatchScore]) -> XxxRelease | None:
        plausible = [item.release for item in ranked if item.plausible][:6]
        if not plausible:
            return None
        choices = (*(Choice(release.token, _describe(release)) for release in plausible), Choice(_NO_MATCH, "None of these"))
        answer = await ask(
            meta,
            Question(
                key=MATCH_QUESTION_KEY,
                kind="choice",
                prompt="Which result is this release?",
                title="XXX metadata match",
                choices=choices,
                default=_NO_MATCH,
                hint="The release name did not identify one result with certainty. Use --tpdb or --blvckout to give the ID instead.",
                summary={"Release": name},
                unattended="default",
            ),
        )
        return next((release for release in plausible if release.token == answer), None)

    async def _answered(self, meta: Meta) -> tuple[bool, XxxRelease | None]:
        """Use an ``xxx.match`` answer (``--answer`` or remembered) before any search result."""
        given = meta.answers.get(MATCH_QUESTION_KEY)
        answer = str(given if given is not None else meta.manual_answers.get(MATCH_QUESTION_KEY) or "").strip()
        if not answer:
            return False, None
        if given is not None:
            meta.manual_answers[MATCH_QUESTION_KEY] = answer
        if answer.casefold() == _NO_MATCH:
            logger.info("[yellow]XXX metadata lookup skipped: the xxx.match answer is none.[/yellow]")
            return True, None
        provider, _separator, reference = answer.partition(":")
        release = None
        if provider == "tpdb" and (tpdb_reference := parse_tpdb_reference(reference)) and self.tpdb.enabled:
            release = await self.tpdb.detail(*tpdb_reference)
        elif provider == "blvckout" and (identity := parse_blvckout_reference(reference)) and self.blvckout.enabled:
            release = await self.blvckout.detail(identity)
        if release is None:
            logger.info(f"[yellow]Ignoring the xxx.match answer {answer!r}: it names no available result.[/yellow]")
            meta.manual_answers.pop(MATCH_QUESTION_KEY, None)
            return False, None
        return True, release

    async def find(self, meta: Meta) -> XxxRelease | None:
        manual = await self._manual(meta)
        if manual:
            return manual
        answered, release = await self._answered(meta)
        if answered:
            return release
        if not self.tpdb.enabled and not self.blvckout.enabled:
            return None
        name = release_name(meta)
        if is_pack_name(name):
            logger.debug("XXX metadata lookup skipped: packs and site rips are not one scene or movie.")
            return None
        match, ranked = await self._search(meta, name)
        if match is None:
            match = await self._choose(meta, name, ranked)
            if match is None:
                if not ranked:
                    logger.info("[yellow]No ThePornDB or BLVCKOUT result matches this release.[/yellow]")
                return None
        return await self._details(match)


def _assign(meta: Meta, field_name: str, value: Any) -> None:
    """Set a field from a match and note its earlier value, so forget_release() can restore it."""
    applied = meta.xxx_applied
    if field_name not in applied:
        applied[field_name] = [getattr(meta, field_name), value]
    else:
        applied[field_name][1] = value
    setattr(meta, field_name, value)


def forget_release(meta: Meta) -> None:
    """Undo what an earlier match applied, unless something changed those fields since.

    A confirmation edit prepares the release again on the same ``meta``; the
    lookup then decides afresh, and nothing from the earlier match (IDs,
    artwork, tags, name) may survive when another result, or none, is chosen.
    """
    applied = dict(meta.xxx_applied or {})
    meta.xxx_applied = {}
    for field_name, (previous, value) in applied.items():
        if getattr(meta, field_name) == value:
            setattr(meta, field_name, previous)
            if field_name in ("artwork_url", "artwork_download_url") and not meta.explicit_poster:
                # The prepared file came from that link; prepare_artwork() looks again.
                meta.artwork_path = ""
            if field_name == "artwork_banner_url" and not meta.explicit_banner:
                meta.artwork_banner_path = None
    meta.xxx_match = {}
    meta.xxx_source_url = ""
    meta.tpdb_id = meta.blvckout_id = ""
    meta.xxx_performers = []
    meta.xxx_rename = False


def apply_release(meta: Meta, release: XxxRelease, *, rename: bool) -> None:
    """Copy a match into the release metadata; values given on the command line are kept."""
    forget_release(meta)
    meta.xxx_match = release.to_dict()
    meta.xxx_source_url = release.url
    # Only the ID of the chosen result is kept and remembered.
    if release.provider == "tpdb":
        meta.tpdb_id = release.ref
    else:
        meta.blvckout_id = release.ref
    if release.title:
        _assign(meta, "title", release.title)
    if release.studio and not meta.book_publisher:
        _assign(meta, "publisher", release.studio)
    if release.date:
        _assign(meta, "release_date", release.date)
    if release.year and meta.manual_year in (None, "", 0, "0"):
        _assign(meta, "year", release.year)
    if release.description and not meta.manual_overview:
        _assign(meta, "overview", release.description)
    if release.performers:
        meta.xxx_performers = list(release.performers)
    if release.tags:
        keywords = [str(keyword) for keyword in meta.keywords or []]
        seen = {keyword.casefold() for keyword in keywords}
        for tag in release.tags:
            if tag.casefold() not in seen:
                seen.add(tag.casefold())
                keywords.append(tag)
        _assign(meta, "keywords", keywords)
    if release.poster_url and not meta.explicit_poster and not meta.artwork_url and not meta.artwork_download_url:
        # Signed or extensionless links can expire; download those instead of publishing them.
        _assign(meta, "artwork_url" if is_stable_image_url(release.poster_url) else "artwork_download_url", release.poster_url)
    if release.banner_url and release.banner_url != release.poster_url and not meta.explicit_banner and not meta.artwork_banner_url:
        _assign(meta, "artwork_banner_url", release.banner_url)
    # Only a dated scene gets a built name; movie and JAV names (titles, product codes) are kept.
    is_scene = release.kind == "scenes" and bool(release.studio and release.date)
    meta.xxx_rename = rename and is_scene and meta.manual_name is None and not is_scene_style_name(release_name(meta))


async def lookup_xxx_metadata(meta: Meta, config: dict[str, Any]) -> None:
    """Fill title, studio, date, performers, tags, synopsis and artwork for an XXX release."""
    if meta.category != "XXX":
        return
    forget_release(meta)
    lookup = XxxMetadataLookup(config, meta)
    release = await lookup.find(meta) if lookup.enabled else None
    if release is not None:
        apply_release(meta, release, rename=parse_bool(lookup.default.get("xxx_generate_names", True), default=True))
        how = " (same file hash)" if release.via_hash else ""
        logger.info(f"[green]{_describe(release)}{how}[/green]")
    # Also for a match without performers: a dated name may still give them.
    if not meta.xxx_performers and not meta.manual_cast:
        meta.xxx_performers = performers_from_name(release_name(meta))

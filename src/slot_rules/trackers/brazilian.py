# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""CapybaraBR (Regras de Trump) and Samaritano (Aplicação de duplicidade), transcribed 2026-10-15."""

from collections.abc import Sequence

from src.slot_rules.base import SlotRules, is_repack_of
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import ENCODE, REMUX, WEBDL, ReleaseProfile, audio_family, channel_count

GIB = 1024**3
PORTUGUESE = "pt"
COMPLETE_DUAL_RULE = "Complete DUAL releases (original audio + PT-BR dub + PT-BR subtitles) take priority over dub-only and subtitle-only releases of any type."


def is_dual(profile: ReleaseProfile) -> bool | None:
    """Original audio plus a Brazilian Portuguese dub."""
    if profile.audio_languages is None:
        return None
    return PORTUGUESE in profile.audio_languages and len(profile.audio_languages) > 1


def has_pt_subs(profile: ReleaseProfile) -> bool | None:
    if profile.subtitle_languages is None:
        return None
    return PORTUGUESE in profile.subtitle_languages


SUMMARIES = {
    Verdict.ALLOW: "Your release is different enough from the ones on the site.",
    Verdict.BLOCK: "A similar release is already on the site.",
    Verdict.REVIEW: "A similar release is on the site, but some details could not be compared.",
}


def _combine(results: list[tuple[ReleaseProfile, Verdict, str]]) -> tuple[Verdict, str, list[ReleaseProfile]]:
    for verdict in (Verdict.BLOCK, Verdict.REVIEW):
        matching = [(profile, reason) for profile, result, reason in results if result is verdict]
        if matching:
            return verdict, matching[0][1], [profile for profile, _ in matching]
    return Verdict.ALLOW, "; ".join(reason for _, _, reason in results), [profile for profile, _, _ in results]


class CapybaraBRSlotRules(SlotRules):
    TRACKER = "CAPYBARABR"

    def audio_trump(self, new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
        if is_repack_of(new, old):
            return Verdict.ALLOW, "A REPACK/PROPER replaces the original release from the same group."
        new_dual, old_dual = is_dual(new), is_dual(old)
        if new_dual is None or old_dual is None:
            return Verdict.REVIEW, "The audio languages of a release on the site could not be compared."
        if old_dual and has_pt_subs(old) and not new_dual:
            return Verdict.BLOCK, COMPLETE_DUAL_RULE
        if new_dual and not old_dual:
            return Verdict.ALLOW, "A DUAL release replaces one without the PT-BR dub."
        if new_dual and old_dual and has_pt_subs(new) and has_pt_subs(old) is False:
            return Verdict.ALLOW, "A DUAL release with PT-BR subtitles replaces a DUAL release without them."
        return Verdict.BLOCK, ""

    def complete_dual_check(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile], res: str) -> SlotDecision | None:
        """A complete DUAL release of any type trumps dub-only and subtitle-only releases of the title."""
        original_language = str(getattr(self.meta, "original_language", "") or "") if self.meta is not None else ""
        if original_language.lower().startswith("pt") or is_dual(upload) is not False:
            return None
        complete = [profile for profile in existing if is_dual(profile) and has_pt_subs(profile) and profile.edition == upload.edition]
        if not complete:
            return None
        same_resolution = [profile for profile in complete if profile.resolution == res]
        if same_resolution:
            return self.decision(
                Verdict.BLOCK,
                "A complete DUAL release of this title is already on the site.",
                same_resolution,
                why=COMPLETE_DUAL_RULE,
            )
        return self.decision(
            Verdict.REVIEW,
            "A complete DUAL release of this title is on the site at another resolution.",
            complete,
            why=COMPLETE_DUAL_RULE,
        )

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        res = self.require(upload.resolution, "resolution")
        same = [profile for profile in existing if profile.resolution == res and profile.edition == upload.edition]

        dual_decision = self.complete_dual_check(upload, existing, res)
        if dual_decision is not None:
            return dual_decision

        if res == "720p":
            if same:
                return self.decision(Verdict.REVIEW, "A 720p release is already on the site.", same, why="CapybaraBR keeps only one 720p release: the best quality.")
            return self.decision(Verdict.ALLOW, "No 720p release is on the site yet.")

        if res == "1080p" and upload.kind == WEBDL:
            holders = [profile for profile in same if profile.kind == WEBDL]
            if not holders:
                return self.decision(Verdict.ALLOW, "No 1080p WEB-DL is on the site yet.")
            category = str(getattr(self.meta, "category", "") or "")
            min_gap = (6 if category == "TV" else 2) * GIB
            results: list[tuple[ReleaseProfile, Verdict, str]] = []
            trumps_a_holder = False
            for holder in holders:
                verdict, reason = self.audio_trump(upload, holder)
                if verdict is Verdict.BLOCK and reason == COMPLETE_DUAL_RULE:
                    results.append((holder, verdict, reason))
                    continue
                if upload.codec and holder.codec and upload.codec != holder.codec:
                    results.append((holder, Verdict.ALLOW, "A different video codec can sit beside the existing WEB-DL."))
                elif upload.size and holder.size and abs(upload.size - holder.size) >= min_gap:
                    results.append((holder, Verdict.ALLOW, f"Two 1080p WEB-DLs can coexist when they are at least {min_gap // GIB} GB apart in size."))
                elif upload.size is None or holder.size is None:
                    results.append((holder, Verdict.REVIEW, "The size of a release on the site could not be compared."))
                else:
                    trumps_a_holder = trumps_a_holder or verdict is Verdict.ALLOW
                    results.append((holder, verdict, reason))
            verdict, reason, conflicts = _combine(results)
            replaces_one = trumps_a_holder or any(is_repack_of(upload, holder) for holder in holders)
            if verdict is Verdict.ALLOW and len(holders) >= 2 and not replaces_one:
                return self.decision(Verdict.BLOCK, "Both 1080p WEB-DL places are already taken.", holders, why="CapybaraBR keeps at most two 1080p WEB-DLs per title.")
            return self.decision(verdict, SUMMARIES[verdict], conflicts, why=reason)

        if res == "2160p" and upload.kind in (WEBDL, REMUX):
            hdr = self.require(upload.hdr, "dynamic range")
            notes = ["An HDR release from another source (e.g. AMZN) may coexist when the HBO Max 4K release is of lower quality."] if hdr else []

            def key(profile: ReleaseProfile) -> tuple[object, ...]:
                return (profile.resolution, profile.kind, "HDR" if self.require(profile.hdr, "dynamic range") else "SDR", profile.edition)

            label = f"2160p {upload.kind} {'HDR/DV' if hdr else 'SDR'}"
            return self.by_slot(upload, existing, key, label, trump=self.hdr_trump, notes=notes)

        # Other release types have no CapybaraBR slot limits; leave them to the basic dupe check.
        return None


class SamaritanoSlotRules(SlotRules):
    TRACKER = "SAMARITANO"

    def compare(self, new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
        if is_repack_of(new, old):
            return Verdict.ALLOW, "A REPACK/PROPER replaces the original release from the same group."
        if new.codec and old.codec and new.codec != old.codec:
            return Verdict.ALLOW, "A different video codec counts as a new release."
        if new.audio_languages is None or old.audio_languages is None:
            return Verdict.REVIEW, "The audio tracks of a release on the site could not be compared."
        new_pt = PORTUGUESE in new.audio_languages
        old_pt = PORTUGUESE in old.audio_languages
        if old_pt and not new_pt:
            return Verdict.BLOCK, "The release on the site has the PT-BR dub and yours doesn't; uploads with less content are dupes."
        if new_pt and not old_pt:
            return Verdict.ALLOW, "Your release adds a PT-BR dub the existing one doesn't have."
        new_channels, old_channels = channel_count(new.audio_channels), channel_count(old.audio_channels)
        if new_channels and old_channels and new_channels > old_channels:
            return Verdict.ALLOW, "Your release has more audio channels."
        new_family, old_family = audio_family(new.audio_codec), audio_family(old.audio_codec)
        if new_family and old_family and new_family != old_family:
            return Verdict.ALLOW, "Your release has a different audio format."
        if new.kind == ENCODE and new.group and old.group and new.group != old.group:
            return Verdict.REVIEW, "It is a different encode; staff decide whether the video differs enough."
        return Verdict.BLOCK, "Same source, video and audio. A different group or extra subtitles do not count as a difference."

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        res = self.require(upload.resolution, "resolution")
        kind = self.require(upload.kind, "release type")
        same = [profile for profile in existing if profile.resolution == res and profile.kind == kind and profile.edition == upload.edition]
        if not same:
            return self.decision(Verdict.ALLOW, "Your release's source or resolution is different from every release on the site.")
        verdict, reason, conflicts = _combine([(profile, *self.compare(upload, profile)) for profile in same])
        return self.decision(verdict, SUMMARIES[verdict], conflicts, why=reason)

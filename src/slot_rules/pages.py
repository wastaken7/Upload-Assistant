# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Tracker rules pages that the slot rules follow, with the last update each page showed.

To keep the rules current: when a page shows a newer update than the date here,
re-read it, change the tracker's slot rules if needed, then update the date.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class RulesPage:
    url: str
    # Last update shown on the page. Pages that only show an age ("6 days ago")
    # get the date that age pointed to when it was checked.
    updated: date


# Date shown for trackers without a listed page: when their rules were transcribed.
TRANSCRIBED = date(2026, 10, 15)

RULES_PAGES: dict[str, RulesPage] = {
    "AITHER": RulesPage("https://aither.cc/wikis/26", date(2026, 10, 17)),
    "ANTHELION": RulesPage("https://anthelion.me/wiki.php?action=article&name=dupe", date(2026, 10, 10)),
    # "Updated: 6 days ago" on 2026-11-05.
    "AVISTAZ": RulesPage("https://avistaz.to/rules/upload-rules", date(2026, 10, 30)),
    "CAPYBARABR": RulesPage("https://capybarabr.com/wikis/25", date(2026, 11, 4)),
    "CATHODERAYTUBE": RulesPage("https://www.cathode-ray.tube/articles.php?topic=upload#coexistance", date(2023, 8, 23)),
    # "Updated: 5 months ago" on 2026-11-05.
    "CINEMAZ": RulesPage("https://cinemaz.to/rules/upload-rules", date(2026, 6, 5)),
    "DREADVAULT": RulesPage("https://dreadvault.org/wikis/12", date(2026, 9, 9)),
    "GREATPOSTERWALL": RulesPage("https://greatposterwall.com/rules.php?p=slots", date(2021, 12, 31)),
    "HDTORRENTS": RulesPage("https://hd-torrents.org/rules.php#dupe", date(2026, 4, 24)),
    "HOMIEHELPDESK": RulesPage("https://homiehelpdesk.net/pages/7#trumping-and-coexistence-rules", date(2026, 10, 4)),
    "LST": RulesPage("https://lst.gg/wiki/26#slots-coexistence-trumping", date(2026, 10, 27)),
    "LUMINARR": RulesPage("https://luminarr.me/wikis/10#coexistence", date(2026, 8, 11)),
    "MTEAM": RulesPage("https://wiki.m-team.cc/", date(2026, 8, 31)),
    # The page shows no update date; this is when the rules were transcribed.
    "ORPHEUS": RulesPage("https://orpheus.network/rules.php?p=upload", date(2026, 10, 21)),
    # "Updated: 2 years ago" on 2026-11-05.
    "PRIVATEHD": RulesPage("https://privatehd.to/rules/dupe-trump-rules", date(2024, 11, 5)),
    "SAMARITANO": RulesPage("https://samaritano.cc/wikis/53", date(2026, 7, 31)),
    "SEEDPOOL": RulesPage("https://forums.seedpool.org/t/upload-guide/17437", date(2026, 6, 21)),
    "SKIPTHECOMMERCIALS": RulesPage("https://skipthecommercials.xyz/wikis/2#coex", date(2026, 9, 24)),
    "ULCX": RulesPage("https://upload.cx/pages/12", date(2026, 11, 4)),
}

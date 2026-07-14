# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import contextlib
import contextvars
import logging
import re
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text


def ansi_to_html(ansi_chunk: str, width: int = 120) -> str:
    """Convert an ANSI-containing text chunk to an HTML fragment using Rich.

    This creates a short-lived Console in record mode, renders the ANSI
    content into it (via Text.from_ansi) and exports an HTML fragment
    with inline styles so it can be embedded directly into the web UI.
    """
    try:
        c = Console(record=True, force_terminal=True, width=width)
        # Try parsing ANSI sequences first. If there are no style spans and
        # the chunk looks like Rich markup (e.g. contains [bold] tags),
        # parse as markup so styled output is preserved.
        text = Text.from_ansi(ansi_chunk)
        with contextlib.suppress(Exception):
            if (not getattr(text, "spans", None) or len(text.spans) == 0) and "[" in ansi_chunk and "]" in ansi_chunk:
                # Parse Rich markup into a Text instance
                with contextlib.suppress(Exception):
                    text = Text.from_markup(ansi_chunk)
            # If introspecting spans fails for any reason, proceed with the original text
        c.print(text, end="")
        # inline_styles keeps the fragment self-contained
        # export the recorded renderable as HTML with inline styles
        html = c.export_html(inline_styles=True)
        # Rich returns a full HTML document; extract the body contents so the
        # web UI can embed the fragment directly.
        with contextlib.suppress(Exception):
            import re

            m = re.search(r"<body[^>]*>(.*?)</body>", html, re.S | re.I)
            if m:
                return m.group(1).strip()
        return html
    except Exception:
        # Fallback: escape HTML to avoid breaking the page
        import html as _html

        return f"<div>{_html.escape(ansi_chunk)}</div>"


# Create a shared Console instance used throughout the project.
# Force terminal mode so that when other processes import `src.console.console`
# they will emit ANSI color codes to stdout even when not attached to a real TTY.
console = Console(force_terminal=True)

# Configure logger integrated with Rich console
logger = logging.getLogger("UploadAssistant")
logger.setLevel(logging.INFO)

# Load configuration settings for the RichHandler
try:
    from data.config import config

    config_default = config.get("DEFAULT", {})
except ImportError:
    config_default = {}

# ---------------------------------------------------------------------------
# Pretty tracker names in console/log output
# Keep internal code free to use any casing (usually UPPER); rewrite only for display.
# ---------------------------------------------------------------------------

# Optional per-tracker Rich markup for colored console output.
# Keys are case-insensitive (match map key or class.tracker).
# Values are Rich markup strings rendered by the logger (markup=True).
# cli_ui prompts always get the plain canonical name (no tags).
#
# Examples:
#   "CapybaraBR": "[yellow]Capybara[/yellow][green]BR[/green]",
#   "Aither": "[bold cyan]Aither[/bold cyan]",
#   "Blutopia": "[blue]Blu[/blue][white]topia[/white]",
TRACKER_DISPLAY_STYLES: dict[str, str] = {
    "Aither": "[bold #5E4FEA]A[/bold #5E4FEA][bold #5663E9]i[/bold #5663E9][bold #4D77E8]t[/bold #4D77E8][bold #458AE7]h[/bold #458AE7][bold #3C9EE6]e[/bold #3C9EE6][bold #34B2E5]r[/bold #34B2E5]",
    "AlphaRatio": "[bold #0149FE]Alpha[/bold #0149FE][bold #008AFF]Ratio[/bold #008AFF]",
    "AmigosShare": "[bold #3A72BD]AmigosShare[/bold #3A72BD]",
    "Anthelion": "[bold #A8BCC5]Anthelion[/bold #A8BCC5]",
    "AsianCinema": "[bold #FC2530]A[/bold #FC2530][bold #EA2A3D]s[/bold #EA2A3D][bold #D92F4B]i[/bold #D92F4B][bold #C73458]a[/bold #C73458][bold #B63965]n[/bold #B63965][bold #A43E72]C[/bold #A43E72][bold #924480]i[/bold #924480][bold #81498D]n[/bold #81498D][bold #6F4E9A]e[/bold #6F4E9A][bold #5E53A8]m[/bold #5E53A8][bold #4C58B5]a[/bold #4C58B5]",
    "Aura4K": "[bold #5E4FEA]A[/bold #5E4FEA][bold #5663E9]u[/bold #5663E9][bold #4D77E8]r[/bold #4D77E8][bold #458AE7]a[/bold #458AE7][bold #3C9EE6]4[/bold #3C9EE6][bold #34B2E5]K[/bold #34B2E5]",
    "AvistaZ": "[bold #FAAF02]A[/bold #FAAF02][bold #FA9802]v[/bold #FA9802][bold #FB8003]i[/bold #FB8003][bold #FB6903]s[/bold #FB6903][bold #FB5203]t[/bold #FB5203][bold #FC3A04]a[/bold #FC3A04][bold #FC2304]Z[/bold #FC2304]",
    "BeyondHD": "[bold #F7F7F7]Beyond[/bold #F7F7F7][bold #3987CC]HD[/bold #3987CC]",
    "BitHDTV": "[bold #FDA321]Bit[/bold #FDA321][bold #FFFFFF]HDTV[/bold #FFFFFF]",
    "BJShare": "[bold #C5130B]BJ[/bold #C5130B][bold #F1EFEF]Share[/bold #F1EFEF]",
    "Blutopia": "[bold #4C78F3]B[/bold #4C78F3][bold #46B1FE]l[/bold #46B1FE][bold #5AD3FB]u[/bold #5AD3FB][bold #6DEADD]t[/bold #6DEADD][bold #71F49B]o[/bold #71F49B][bold #BEC4CF]p[/bold #BEC4CF][bold #E49FE8]i[/bold #E49FE8][bold #EE7BF0]a[/bold #EE7BF0]",
    "BrasilTracker": "[bold #FFFFFF]Brasil[/bold #FFFFFF][bold #B39770]Tracker[/bold #B39770]",
    "CapybaraBR": "[bold #FEB100]Capybara[/bold #FEB100][bold #264F37]BR[/bold #264F37]",
    "Cinematik": "[bold #6E605A]Cinema[/bold #6E605A][bold #56975D]tik[/bold #56975D]",
    "DesiTorrents": "[bold #D72E2D]Desi[/bold #D72E2D][bold #F4CF70]Torrents[/bold #F4CF70]",
    "DigitalCore": "[bold #FFFFFF]Digital[/bold #FFFFFF][bold #9B9B9B]Core[/bold #9B9B9B]",
    "FileList": "[bold #FFFFFF]File[/bold #FFFFFF][bold #2E7EE2]List[/bold #2E7EE2]",
    "FunFile": "[bold #F5FAFD]F[/bold #F5FAFD][bold #D4E7F5]u[/bold #D4E7F5][bold #B3D5ED]n[/bold #B3D5ED][bold #8DC0E4]F[/bold #8DC0E4][bold #71B1DE]i[/bold #71B1DE][bold #53A1D7]l[/bold #53A1D7][bold #3C94D1]e[/bold #3C94D1]",
    "GreatPosterWall": "[bold #FFFFFF]G[/bold #FFFFFF][bold #F5FAFE]r[/bold #F5FAFE][bold #ECF5FD]e[/bold #ECF5FD][bold #E2EFFC]a[/bold #E2EFFC][bold #D8EAFB]t[/bold #D8EAFB][bold #CEE5FA]P[/bold #CEE5FA][bold #C5E0F9]o[/bold #C5E0F9][bold #BBDAF8]s[/bold #BBDAF8][bold #B1D5F8]t[/bold #B1D5F8][bold #A8D0F7]e[/bold #A8D0F7][bold #9ECBF6]r[/bold #9ECBF6][bold #94C6F5]W[/bold #94C6F5][bold #8AC0F4]a[/bold #8AC0F4][bold #81BBF3]l[/bold #81BBF3][bold #77B6F2]l[/bold #77B6F2]",
    "HawkeUno": "[bold #00B3F5]Hawke[/bold #00B3F5][bold #E2747A]Uno[/bold #E2747A]",
    "HDSpace": "[bold #2ADDFD]HDSpace[/bold #2ADDFD]",
    "HDTorrents": "[bold #E0E0E0]H[/bold #E0E0E0][bold #D7D7D7]D[/bold #D7D7D7][bold #CFCFCF]T[/bold #CFCFCF][bold #C6C6C6]o[/bold #C6C6C6][bold #BDBDBD]r[/bold #BDBDBD][bold #B5B5B5]r[/bold #B5B5B5][bold #ACACAC]e[/bold #ACACAC][bold #A3A3A3]n[/bold #A3A3A3][bold #9B9B9B]t[/bold #9B9B9B][bold #929292]s[/bold #929292]",
    "HomieHelpDesk": "[bold #ED1E79]H[/bold #ED1E79][bold #E21F7F]o[/bold #E21F7F][bold #D62084]m[/bold #D62084][bold #CB228A]i[/bold #CB228A][bold #C0238F]e[/bold #C0238F][bold #B52495]H[/bold #B52495][bold #AA269A]e[/bold #AA269A][bold #9E27A0]l[/bold #9E27A0][bold #9328A6]p[/bold #9328A6][bold #8829AB]D[/bold #8829AB][bold #7C2AB1]e[/bold #7C2AB1][bold #712CB6]s[/bold #712CB6][bold #662DBC]k[/bold #662DBC]",
    "ImmortalSeed": "[bold #F9F9F9]Immortal[/bold #F9F9F9][bold #1081D8]Seed[/bold #1081D8]",
    "InfinityHD": "[bold #5E4FEA]I[/bold #5E4FEA][bold #595AE9]n[/bold #595AE9][bold #5565E9]f[/bold #5565E9][bold #5070E8]i[/bold #5070E8][bold #4B7BE8]n[/bold #4B7BE8][bold #4786E7]i[/bold #4786E7][bold #4291E7]t[/bold #4291E7][bold #3D9CE6]y[/bold #3D9CE6][bold #39A7E6]H[/bold #39A7E6][bold #34B2E5]D[/bold #34B2E5]",
    "ItaTorrents": "[bold #008D44]I[/bold #008D44][bold #148342]t[/bold #148342][bold #287941]a[/bold #287941][bold #3C6F40]T[/bold #3C6F40][bold #50653E]o[/bold #50653E][bold #645C3C]r[/bold #645C3C][bold #78523B]r[/bold #78523B][bold #8C483A]e[/bold #8C483A][bold #A03E38]n[/bold #A03E38][bold #B43436]t[/bold #B43436][bold #C82A35]s[/bold #C82A35]",
    "LastDigitalUnderground": "[bold #41FF00]LastDigitalUnderground[/bold #41FF00]",
    "LatTeam": "[bold #FEAA00]L[/bold #FEAA00][bold #FEA000]a[/bold #FEA000][bold #FE9700]t[/bold #FE9700][bold #FE8D00]T[/bold #FE8D00][bold #FE8300]e[/bold #FE8300][bold #FE7A00]a[/bold #FE7A00][bold #FE7000]m[/bold #FE7000]",
    "Locadora": "[bold #FFA903]LOCADORA[/bold #FFA903]",
    "LongPT": "[bold #FDD6E3]L[/bold #FDD6E3][bold #ECDAE4]o[/bold #ECDAE4][bold #DBDFE6]n[/bold #DBDFE6][bold #CBE3E7]g[/bold #CBE3E7][bold #BAE8E9]P[/bold #BAE8E9][bold #A9ECEA]T[/bold #A9ECEA]",
    "LST": "[bold #04DA47]L[/bold #04DA47][bold #2483F5]S[/bold #2483F5][bold #7E49A1]T[/bold #7E49A1]",
    "Luminarr": "[bold #AAAAAA]Lumin[/bold #AAAAAA][bold #7891D1]arr[/bold #7891D1]",
    "MakingOff": "[bold #026CA0]Making[/bold #026CA0]Off",
    "MidnightScene": "[bold #A48E5B]M[/bold #A48E5B][bold #A48F5D]i[/bold #A48F5D][bold #A48F5F]d[/bold #A48F5F][bold #A39062]n[/bold #A39062][bold #A39164]i[/bold #A39164][bold #A39166]g[/bold #A39166][bold #A29268]h[/bold #A29268][bold #A2936A]t[/bold #A2936A][bold #A2936C]S[/bold #A2936C][bold #A2946E]c[/bold #A2946E][bold #A29571]e[/bold #A29571][bold #A19573]n[/bold #A19573][bold #A19675]e[/bold #A19675]",
    "MoreThanTV": "[bold #A11E22]MoreThanTV[/bold #A11E22]",
    "MTeam": "[bold #F6CA60]MTeam[/bold #F6CA60]",
    "Nebulance": "[bold #6685C1]N[/bold #6685C1][bold #5F7EBA]e[/bold #5F7EBA][bold #5877B3]b[/bold #5877B3][bold #5170AC]u[/bold #5170AC][bold #4A68A4]l[/bold #4A68A4][bold #42619D]a[/bold #42619D][bold #3B5A96]n[/bold #3B5A96][bold #34538F]c[/bold #34538F][bold #2D4C88]e[/bold #2D4C88]",
    "OldToonsWorld": "[bold #5E4FEA]O[/bold #5E4FEA][bold #5A57EA]l[/bold #5A57EA][bold #5760E9]d[/bold #5760E9][bold #5468E9]T[/bold #5468E9][bold #5070E8]o[/bold #5070E8][bold #4C78E8]o[/bold #4C78E8][bold #4980E8]n[/bold #4980E8][bold #4689E7]s[/bold #4689E7][bold #4291E7]W[/bold #4291E7][bold #3E99E6]o[/bold #3E99E6][bold #3BA2E6]r[/bold #3BA2E6][bold #38AAE5]l[/bold #38AAE5][bold #34B2E5]d[/bold #34B2E5]",
    "OnlyEncodes": "[bold #FFAC33]OnlyEncodes[/bold #FFAC33]",
    "PassThePopcorn": "[bold #F6D1D3]P[/bold #F6D1D3][bold #FDB4B0]a[/bold #FDB4B0][bold #FDD0AE]s[/bold #FDD0AE][bold #FCF6AD]s[/bold #FCF6AD][bold #EDF7C0]T[/bold #EDF7C0][bold #E0F6D1]h[/bold #E0F6D1][bold #C2F3D4]e[/bold #C2F3D4][bold #9EEBE0]P[/bold #9EEBE0][bold #9DE7F6]o[/bold #9DE7F6][bold #9CBCE3]p[/bold #9CBCE3][bold #A19AD9]c[/bold #A19AD9][bold #D4A3E5]o[/bold #D4A3E5][bold #FBBAF1]r[/bold #FBBAF1][bold #FAD7F3]n[/bold #FAD7F3]",
    "PolishTorrent": "[bold #FDFDFD]P[/bold #FDFDFD][bold #F9EDED]o[/bold #F9EDED][bold #F5DCDE]l[/bold #F5DCDE][bold #F2CCCE]i[/bold #F2CCCE][bold #EEBCBE]s[/bold #EEBCBE][bold #EAABAE]h[/bold #EAABAE][bold #E69B9E]T[/bold #E69B9E][bold #E28B8F]o[/bold #E28B8F][bold #DE7A7F]r[/bold #DE7A7F][bold #DA6A6F]r[/bold #DA6A6F][bold #D75A60]e[/bold #D75A60][bold #D34950]n[/bold #D34950][bold #CF3940]t[/bold #CF3940]",
    "Portugas": "[bold #006D24]P[/bold #006D24][bold #128D05]o[/bold #128D05][bold #51AB00]r[/bold #51AB00][bold #E6DB12]t[/bold #E6DB12][bold #FF5B00]u[/bold #FF5B00][bold #FB1601]g[/bold #FB1601][bold #E90707]a[/bold #E90707][bold #B00000]s[/bold #B00000]",
    "PrivateHD": "Private[bold #DAB62C]HD[/bold #DAB62C]",
    "PTFans": "[bold #FF5722]PT[/bold #FF5722][bold #FFFFFF]Fans[/bold #FFFFFF]",
    "Ptskit": "[bold #F9D503]P[/bold #F9D503][bold #0099FD]t[/bold #0099FD][bold #E71114]skit[/bold #E71114]",
    "Racing4Everyone": "[bold #F3F2F3]R[/bold #F3F2F3][bold #E7E6E7]a[/bold #E7E6E7][bold #DBDADB]c[/bold #DBDADB][bold #CFCECF]i[/bold #CFCECF][bold #C3C2C3]n[/bold #C3C2C3][bold #B7B6B7]g[/bold #B7B6B7][bold #ABAAAB]4[/bold #ABAAAB][bold #9F9E9F]E[/bold #9F9E9F][bold #939393]v[/bold #939393][bold #878787]e[/bold #878787][bold #7B7B7B]r[/bold #7B7B7B][bold #6F6F6F]y[/bold #6F6F6F][bold #636363]o[/bold #636363][bold #575757]n[/bold #575757][bold #4B4B4B]e[/bold #4B4B4B]",
    "RailgunPT": "[bold #FFFFFF]R[/bold #FFFFFF][bold #FEEFF4]a[/bold #FEEFF4][bold #FEDEE8]i[/bold #FEDEE8][bold #FDCEDC]l[/bold #FDCEDC][bold #FCBED1]g[/bold #FCBED1][bold #FBADC6]u[/bold #FBADC6][bold #FA9DBA]n[/bold #FA9DBA][bold #FA8CAE]P[/bold #FA8CAE][bold #F97CA3]T[/bold #F97CA3]",
    "Rastastugan": "[bold #6A92A9]Rastastugan[/bold #6A92A9]",
    "ReelFlix": "[bold #C40018]ReelFlix[/bold #C40018]",
    "RetroFlix": "[bold #5C9A8A]RetroFlix[/bold #5C9A8A]",
    "Samaritano": "[bold #FFF62E]SAMARITANO[/bold #FFF62E]",
    "Seedpool": "[bold #5E4FEA]s[/bold #5E4FEA][bold #585DE9]e[/bold #585DE9][bold #526BE9]e[/bold #526BE9][bold #4C79E8]d[/bold #4C79E8][bold #4688E7]p[/bold #4688E7][bold #4096E6]o[/bold #4096E6][bold #3AA4E6]o[/bold #3AA4E6][bold #34B2E5]l[/bold #34B2E5]",
    "ShareIsland": "[bold #7E6449]S[/bold #7E6449][bold #886E54]h[/bold #886E54][bold #92785E]a[/bold #92785E][bold #9D8269]r[/bold #9D8269][bold #A78C73]e[/bold #A78C73][bold #B1967E]I[/bold #B1967E][bold #BBA189]s[/bold #BBA189][bold #C5AB93]l[/bold #C5AB93][bold #D0B59E]a[/bold #D0B59E][bold #DABFA8]n[/bold #DABFA8][bold #E4C9B3]d[/bold #E4C9B3]",
    "SkipTheCommercials": "[bold #5E4FEA]S[/bold #5E4FEA][bold #5C55EA]k[/bold #5C55EA][bold #595BE9]i[/bold #595BE9][bold #5760E9]p[/bold #5760E9][bold #5466E9]T[/bold #5466E9][bold #526CE9]h[/bold #526CE9][bold #4F72E8]e[/bold #4F72E8][bold #4D78E8]C[/bold #4D78E8][bold #4A7EE8]o[/bold #4A7EE8][bold #4883E7]m[/bold #4883E7][bold #4589E7]m[/bold #4589E7][bold #438FE7]e[/bold #438FE7][bold #4095E6]r[/bold #4095E6][bold #3E9BE6]c[/bold #3E9BE6][bold #3BA1E6]i[/bold #3BA1E6][bold #39A6E6]a[/bold #39A6E6][bold #36ACE5]l[/bold #36ACE5][bold #34B2E5]s[/bold #34B2E5]",
    "SpeedApp": "[bold #FFC500]SpeedApp[/bold #FFC500]",
    "TheLeachZone": "[bold #5E4FEA]T[/bold #5E4FEA][bold #5A58EA]h[/bold #5A58EA][bold #5661E9]e[/bold #5661E9][bold #536AE9]L[/bold #536AE9][bold #4F73E8]e[/bold #4F73E8][bold #4B7CE8]a[/bold #4B7CE8][bold #4785E7]c[/bold #4785E7][bold #438EE7]h[/bold #438EE7][bold #3F97E6]Z[/bold #3F97E6][bold #3CA0E6]o[/bold #3CA0E6][bold #38A9E5]n[/bold #38A9E5][bold #34B2E5]e[/bold #34B2E5]",
    "TheOldSchool": "[bold #509FB2]The[/][bold #BE2A70]O[/bold #BE2A70][bold #509FB2]ldSch[/][bold #BE2A70]oo[/bold #BE2A70][bold #509FB2]l[/bold #509FB2]",
    "Torrenteros": "[bold #F8A83C]T[/bold #F8A83C][bold #F8983D]o[/bold #F8983D][bold #F9873E]r[/bold #F9873E][bold #F9763F]r[/bold #F9763F][bold #F96640]e[/bold #F96640][bold #FA5642]n[/bold #FA5642][bold #FA4543]t[/bold #FA4543][bold #FA3544]e[/bold #FA3544][bold #FA2445]r[/bold #FA2445][bold #FB1446]o[/bold #FB1446][bold #FB0347]s[/bold #FB0347]",
    "TorrentLeech": "[bold #FFFFFF]Torrent[/bold #FFFFFF][bold #016700]Leech[/bold #016700]",
    "TVChaosUK": "[bold #E84D67]T[/bold #E84D67][bold #D35871]V[/bold #D35871][bold #BE627B]C[/bold #BE627B][bold #A96D85]h[/bold #A96D85][bold #947890]a[/bold #947890][bold #7F839A]o[/bold #7F839A][bold #6A8EA4]s[/bold #6A8EA4][bold #5598AE]U[/bold #5598AE][bold #40A3B8]K[/bold #40A3B8]",
    "ULCX": "[bold #5E4FEA]U[/bold #5E4FEA][bold #5070E8]L[/bold #5070E8][bold #4291E7]C[/bold #4291E7][bold #34B2E5]X[/bold #34B2E5]",
    "YUSCENE": "[bold #FC0014]YU[/bold #FC0014][bold #0286E3]SCENE[/bold #0286E3]",
    "Zenith": "[bold #EE9F15]Z[/bold #EE9F15][bold #EA9715]e[/bold #EA9715][bold #E68F15]n[/bold #E68F15][bold #E28615]i[/bold #E28615][bold #DE7E15]t[/bold #DE7E15][bold #DA7615]h[/bold #DA7615]",
}

for style in TRACKER_DISPLAY_STYLES.values():
    console.print(style)


_tracker_name_map: dict[str, str] | None = None  # lower → plain canonical (e.g. "CapybaraBR")
_tracker_style_map: dict[str, str] | None = None  # lower → Rich markup (if customized)
_tracker_name_pattern: re.Pattern[str] | None = None


def _load_tracker_display_map() -> tuple[dict[str, str], dict[str, str], re.Pattern[str] | None]:
    """Build lowercase→canonical name map + optional style map (lazy, avoids import cycles)."""
    global _tracker_name_map, _tracker_style_map, _tracker_name_pattern
    if _tracker_name_map is not None and _tracker_style_map is not None:
        return _tracker_name_map, _tracker_style_map, _tracker_name_pattern

    mapping: dict[str, str] = {}
    try:
        from src.trackersetup import tracker_class_map

        for key, cls in tracker_class_map.items():
            canonical = str(getattr(cls, "tracker", None) or key)
            mapping[(key).lower()] = canonical
            mapping[canonical.lower()] = canonical
    except Exception:
        # trackersetup may not be importable yet during very early bootstrap
        mapping = {}

    # Apply custom styles: resolve keys case-insensitively onto canonical names
    styles: dict[str, str] = {}
    for style_key, style_value in TRACKER_DISPLAY_STYLES.items():
        if not style_key or not style_value:
            continue
        key_lower = style_key.strip().lower()
        canonical = mapping.get(key_lower, style_key.strip())
        # Prefer known canonical casing when the tracker is registered
        if key_lower in mapping:
            canonical = mapping[key_lower]
        styles[canonical.lower()] = style_value
        styles[key_lower] = style_value
        # Ensure custom-only names still match even if not in tracker_class_map
        mapping.setdefault(key_lower, canonical)
        mapping.setdefault(canonical.lower(), canonical)

    _tracker_name_map = mapping
    _tracker_style_map = styles
    if mapping:
        # Longest first so "PrivateHD" wins over shorter overlapping tokens if any
        names = sorted({re.escape(name) for name in mapping.values()}, key=len, reverse=True)
        _tracker_name_pattern = re.compile(r"\b(" + "|".join(names) + r")\b", re.IGNORECASE)
    else:
        _tracker_name_pattern = None
    return _tracker_name_map, _tracker_style_map, _tracker_name_pattern


def prettify_tracker_names(text: str, *, markup: bool = True) -> str:
    """Replace tracker name tokens with canonical casing, optionally with Rich colors.

    CAPYBARABR → CapybaraBR (plain) or styled markup if listed in TRACKER_DISPLAY_STYLES.
    Set markup=False for plain text (cli_ui prompts, etc.).
    """
    if not text:
        return text
    mapping, styles, pattern = _load_tracker_display_map()
    if not pattern or not mapping:
        return text

    def _repl(match: re.Match[str]) -> str:
        token_lower = match.group(0).lower()
        canonical = mapping.get(token_lower, match.group(0))
        if markup:
            styled = styles.get(token_lower) or styles.get(canonical.lower())
            if styled:
                return styled
        return canonical

    return pattern.sub(_repl, text)


class TrackerNamePrettyFilter(logging.Filter):
    """Rewrite tracker name tokens in log records before handlers print them."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = prettify_tracker_names(record.msg, markup=True)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: prettify_tracker_names(v, markup=True) if isinstance(v, str) else v for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(prettify_tracker_names(a, markup=True) if isinstance(a, str) else a for a in record.args)
        except Exception as e:
            logger.error(f"[bold red]Error while prettifying tracker names: {e}[/bold red]")
        return True


def _patch_cli_ui_for_pretty_trackers() -> None:
    """Also rewrite tracker names in cli_ui prompts (plain text, no Rich tags)."""
    try:
        import cli_ui
    except Exception:
        return

    def _wrap(fn):  # type: ignore[no-untyped-def]
        def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            if args and isinstance(args[0], str):
                args = (prettify_tracker_names(args[0], markup=False), *args[1:])
            return fn(*args, **kwargs)

        return wrapper

    for name in ("ask_yes_no", "ask_string", "info", "warning", "error", "info_1", "info_2", "info_3"):
        if hasattr(cli_ui, name):
            setattr(cli_ui, name, _wrap(getattr(cli_ui, name)))


_patch_cli_ui_for_pretty_trackers()

# RichHandler captures logs and outputs them using our shared console instance.
# We enable markup=True to preserve Rich color formatting like [yellow], [red], etc.
rich_handler = RichHandler(
    console=console,
    show_time=bool(config_default.get("console_show_time", False)),
    show_level=bool(config_default.get("console_show_level", False)),
    show_path=bool(config_default.get("console_show_path", False)),
    markup=bool(config_default.get("console_markup", True)),
)
rich_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(rich_handler)
logger.addFilter(TrackerNamePrettyFilter())


# Context variable to hold the path to the current release's log file (e.g. /tmp/<uuid>/upload.log)
current_release_log_path: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_release_log_path", default=None)


class LogFileFormatter(logging.Formatter):
    def __init__(self, fmt: str = "[%(asctime)s] %(levelname)s: %(message)s", datefmt: str = "%Y-%m-%d %H:%M:%S") -> None:
        super().__init__(fmt, datefmt)
        self.console = Console(color_system=None, width=150)
        self.ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    def format(self, record: logging.LogRecord) -> str:
        # Format the record normally first
        formatted = super().format(record)

        # Strip ANSI escape sequences
        formatted = self.ansi_escape.sub("", formatted)

        # Strip Rich markup using Console
        with contextlib.suppress(Exception):
            formatted = self.console.render_str(formatted).plain

        return formatted


class DynamicFileHandler(logging.Handler):
    def __init__(self, formatter=None) -> None:
        super().__init__()
        if formatter:
            self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Check if write_log is enabled in config. Use lazy lookup to support reload
            try:
                from data.config import config

                write_log = bool(config.get("DEFAULT", {}).get("write_log", False))
            except Exception:
                write_log = False

            if not write_log:
                return

            log_path = current_release_log_path.get()
            if not log_path:
                return

            # Format message
            msg = self.format(record)

            # Ensure target directory exists
            log_dir = Path(log_path).parent
            if str(log_dir) and not log_dir.exists():
                log_dir.mkdir(parents=True, exist_ok=True)

            # Append message to file
            with Path(log_path).open("a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            self.handleError(record)


# Add the dynamic file handler to UploadAssistant logger
dynamic_file_handler = DynamicFileHandler(LogFileFormatter())
logger.addHandler(dynamic_file_handler)

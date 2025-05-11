import guessit
import os
import re
from src.console import console


async def get_edition(self, video, bdinfo, filelist, manual_edition, meta):
    if video.lower().startswith('dc'):
        video = video.replace('dc', '', 1)

    guess = guessit(video)
    tag = guess.get('release_group', 'NOGROUP')
    repack = ""
    edition = ""

    if bdinfo is not None:
        try:
            edition = guessit(bdinfo['label'])['edition']
        except Exception as e:
            if meta['debug']:
                print(f"BDInfo Edition Guess Error: {e}")
            edition = ""
    else:
        try:
            edition = guess.get('edition', "")
        except Exception as e:
            if meta['debug']:
                print(f"Video Edition Guess Error: {e}")
            edition = ""

    if isinstance(edition, list):
        edition = " ".join(edition)

    if len(filelist) == 1:
        video = os.path.basename(video)

    video = video.upper().replace('.', ' ').replace(tag.upper(), '').replace('-', '')

    if "OPEN MATTE" in video:
        edition = edition + " Open Matte"

    if manual_edition:
        if isinstance(manual_edition, list):
            manual_edition = " ".join(manual_edition)
        edition = str(manual_edition)
    edition = edition.replace(",", " ")

    # print(f"Edition After Manual Edition: {edition}")

    if "REPACK" in (video or edition.upper()) or "V2" in video:
        repack = "REPACK"
    if "REPACK2" in (video or edition.upper()) or "V3" in video:
        repack = "REPACK2"
    if "REPACK3" in (video or edition.upper()) or "V4" in video:
        repack = "REPACK3"
    if "PROPER" in (video or edition.upper()):
        repack = "PROPER"
    if "PROPER2" in (video or edition.upper()):
        repack = "PROPER2"
    if "PROPER3" in (video or edition.upper()):
        repack = "PROPER3"
    if "RERIP" in (video or edition.upper()):
        repack = "RERIP"

    # print(f"Repack after Checks: {repack}")

    # Only remove REPACK, RERIP, or PROPER from edition if they're not part of manual_edition
    if not manual_edition or all(tag.lower() not in ['repack', 'repack2', 'repack3', 'proper', 'proper2', 'proper3', 'rerip'] for tag in manual_edition.strip().lower().split()):
        edition = re.sub(r"(\bREPACK\d?\b|\bRERIP\b|\bPROPER\b)", "", edition, flags=re.IGNORECASE).strip()

    if edition:
        from src.region import get_distributor
        distributors = await get_distributor(edition)

        bad = ['internal', 'limited', 'retail']

        if distributors:
            bad.append(distributors.lower())
            meta['distributor'] = distributors

        if any(term.lower() in edition.lower() for term in bad):
            edition = re.sub(r'\b(?:' + '|'.join(bad) + r')\b', '', edition, flags=re.IGNORECASE).strip()
            # Clean up extra spaces
            while '  ' in edition:
                edition = edition.replace('  ', ' ')
        if edition != "":
            console.print(f"Final Edition: {edition}")
    return edition, repack

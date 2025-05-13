import os
from src.discparse import DiscParse


async def get_disc(self, meta):
    is_disc = None
    videoloc = meta['path']
    bdinfo = None
    bd_summary = None  # noqa: F841
    discs = []
    parse = DiscParse()
    for path, directories, files in sorted(os.walk(meta['path'])):
        for each in directories:
            if each.upper() == "BDMV":  # BDMVs
                is_disc = "BDMV"
                disc = {
                    'path': f"{path}/{each}",
                    'name': os.path.basename(path),
                    'type': 'BDMV',
                    'summary': "",
                    'bdinfo': ""
                }
                discs.append(disc)
            elif each == "VIDEO_TS":  # DVDs
                is_disc = "DVD"
                disc = {
                    'path': f"{path}/{each}",
                    'name': os.path.basename(path),
                    'type': 'DVD',
                    'vob_mi': '',
                    'ifo_mi': '',
                    'main_set': [],
                    'size': ""
                }
                discs.append(disc)
            elif each == "HVDVD_TS":
                is_disc = "HDDVD"
                disc = {
                    'path': f"{path}/{each}",
                    'name': os.path.basename(path),
                    'type': 'HDDVD',
                    'evo_mi': '',
                    'largest_evo': ""
                }
                discs.append(disc)
    if is_disc == "BDMV":
        if meta.get('edit', False) is False:
            discs, bdinfo = await parse.get_bdinfo(meta, discs, meta['uuid'], meta['base_dir'], meta.get('discs', []))
        else:
            discs, bdinfo = await parse.get_bdinfo(meta, meta['discs'], meta['uuid'], meta['base_dir'], meta['discs'])
    elif is_disc == "DVD":
        discs = await parse.get_dvdinfo(discs)
        export = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt", 'w', newline="", encoding='utf-8')
        export.write(discs[0]['ifo_mi'])
        export.close()
        export_clean = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO_CLEANPATH.txt", 'w', newline="", encoding='utf-8')
        export_clean.write(discs[0]['ifo_mi'])
        export_clean.close()
    elif is_disc == "HDDVD":
        discs = await parse.get_hddvd_info(discs, meta)
        export = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt", 'w', newline="", encoding='utf-8')
        export.write(discs[0]['evo_mi'])
        export.close()
    discs = sorted(discs, key=lambda d: d['name'])
    return is_disc, videoloc, bdinfo, discs

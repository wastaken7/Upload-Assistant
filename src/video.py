async def get_uhd(type, guess, resolution, path):
    try:
        source = guess['Source']
        other = guess['Other']
    except Exception:
        source = ""
        other = ""
    uhd = ""
    if source == 'Blu-ray' and other == "Ultra HD" or source == "Ultra HD Blu-ray":
        uhd = "UHD"
    elif "UHD" in path:
        uhd = "UHD"
    elif type in ("DISC", "REMUX", "ENCODE", "WEBRIP"):
        uhd = ""

    if type in ("DISC", "REMUX", "ENCODE") and resolution == "2160p":
        uhd = "UHD"

    return uhd


async def get_hdr(mi, bdinfo):
    hdr = ""
    dv = ""
    if bdinfo is not None:  # Disks
        hdr_mi = bdinfo['video'][0]['hdr_dv']
        if "HDR10+" in hdr_mi:
            hdr = "HDR10+"
        elif hdr_mi == "HDR10":
            hdr = "HDR"
        try:
            if bdinfo['video'][1]['hdr_dv'] == "Dolby Vision":
                dv = "DV"
        except Exception:
            pass
    else:
        video_track = mi['media']['track'][1]
        try:
            hdr_mi = video_track['colour_primaries']
            if hdr_mi in ("BT.2020", "REC.2020"):
                hdr = ""
                hdr_fields = [
                    video_track.get('HDR_Format_Compatibility', ''),
                    video_track.get('HDR_Format_String', ''),
                    video_track.get('HDR_Format', '')
                ]
                hdr_format_string = next((v for v in hdr_fields if isinstance(v, str) and v.strip()), "")
                if "HDR10+" in hdr_format_string:
                    hdr = "HDR10+"
                elif "HDR10" in hdr_format_string:
                    hdr = "HDR"
                elif "SMPTE ST 2094 App 4" in hdr_format_string:
                    hdr = "HDR"
                if hdr_format_string and "HLG" in hdr_format_string:
                    hdr = f"{hdr} HLG"
                if hdr_format_string == "" and "PQ" in (video_track.get('transfer_characteristics'), video_track.get('transfer_characteristics_Original', None)):
                    hdr = "PQ10"
                transfer_characteristics = video_track.get('transfer_characteristics_Original', None)
                if "HLG" in transfer_characteristics:
                    hdr = "HLG"
                if hdr != "HLG" and "BT.2020 (10-bit)" in transfer_characteristics:
                    hdr = "WCG"
        except Exception:
            pass

        try:
            if "Dolby Vision" in video_track.get('HDR_Format', '') or "Dolby Vision" in video_track.get('HDR_Format_String', ''):
                dv = "DV"
        except Exception:
            pass

    hdr = f"{dv} {hdr}".strip()
    return hdr


async def get_video_codec(bdinfo):
    codecs = {
        "MPEG-2 Video": "MPEG-2",
        "MPEG-4 AVC Video": "AVC",
        "MPEG-H HEVC Video": "HEVC",
        "VC-1 Video": "VC-1"
    }
    codec = codecs.get(bdinfo['video'][0]['codec'], "")
    return codec


async def get_video_encode(mi, type, bdinfo):
    video_encode = ""
    codec = ""
    bit_depth = '0'
    has_encode_settings = False
    try:
        format = mi['media']['track'][1]['Format']
        format_profile = mi['media']['track'][1].get('Format_Profile', format)
        if mi['media']['track'][1].get('Encoded_Library_Settings', None):
            has_encode_settings = True
        bit_depth = mi['media']['track'][1].get('BitDepth', '0')
    except Exception:
        format = bdinfo['video'][0]['codec']
        format_profile = bdinfo['video'][0]['profile']
    if type in ("ENCODE", "WEBRIP", "DVDRIP"):  # ENCODE or WEBRIP or DVDRIP
        if format == 'AVC':
            codec = 'x264'
        elif format == 'HEVC':
            codec = 'x265'
        elif format == 'AV1':
            codec = 'AV1'
    elif type in ('WEBDL', 'HDTV'):  # WEB-DL
        if format == 'AVC':
            codec = 'H.264'
        elif format == 'HEVC':
            codec = 'H.265'
        elif format == 'AV1':
            codec = 'AV1'

        if type == 'HDTV' and has_encode_settings is True:
            codec = codec.replace('H.', 'x')
    elif format == "VP9":
        codec = "VP9"
    elif format == "VC-1":
        codec = "VC-1"
    if format_profile == 'High 10':
        profile = "Hi10P"
    else:
        profile = ""
    video_encode = f"{profile} {codec}"
    video_codec = format
    if video_codec == "MPEG Video":
        video_codec = f"MPEG-{mi['media']['track'][1].get('Format_Version')}"
    return video_encode, video_codec, has_encode_settings, bit_depth

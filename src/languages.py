import aiofiles
import os
import cli_ui
import re
from src.console import console


async def parsed_mediainfo(mediainfo_content):
    parsed_data = {
        'general': {},
        'video': [],
        'audio': [],
        'text': []
    }

    current_section = None
    current_track = {}

    lines = mediainfo_content.strip().split('\n')

    section_header_re = re.compile(r'^(General|Video|Audio|Text|Menu)(?:\s*#\d+)?$', re.IGNORECASE)

    for line in lines:
        line = line.strip()
        if not line:
            continue

        section_match = section_header_re.match(line)
        if section_match:
            if current_section and current_track:
                if current_section in ['video', 'audio', 'text']:
                    parsed_data[current_section].append(current_track)
                elif current_section == 'general':
                    parsed_data['general'] = current_track

            current_section = section_match.group(1).lower()
            current_track = {}
            continue

        if ':' in line and current_section:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()

            if current_section == 'video':
                if key in ['format', 'duration', 'bit rate', 'encoding settings', 'title']:
                    current_track[key.replace(' ', '_')] = value
            elif current_section == 'audio':
                if key in ['format', 'duration', 'bit rate', 'language', 'commercial name', 'channel', 'channel (s)', 'title']:
                    current_track[key.replace(' ', '_')] = value
            elif current_section == 'text':
                if key in ['format', 'duration', 'bit rate', 'language', 'title']:
                    current_track[key.replace(' ', '_')] = value
            elif current_section == 'general':
                current_track[key.replace(' ', '_')] = value

    if current_section and current_track:
        if current_section in ['video', 'audio', 'text']:
            parsed_data[current_section].append(current_track)
        elif current_section == 'general':
            parsed_data['general'] = current_track

    return parsed_data


async def process_desc_language(meta, desc=None, tracker=None):
    if not meta['is_disc'] == "BDMV":
        try:
            mediainfo_file = f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt"
            if os.path.exists(mediainfo_file):
                async with aiofiles.open(mediainfo_file, 'r', encoding='utf-8') as f:
                    mediainfo_content = await f.read()

                parsed_info = await parsed_mediainfo(mediainfo_content)
                audio_languages = []
                subtitle_languages = []
                meta['write_audio_languages'] = False
                meta['write_subtitle_languages'] = False
                if meta.get('audio_languages'):
                    audio_languages = meta['audio_languages']
                else:
                    meta['audio_languages'] = []
                if meta.get('subtitle_languages'):
                    subtitle_languages = meta['subtitle_languages']
                else:
                    meta['subtitle_languages'] = []
                if not audio_languages or not subtitle_languages:
                    if not audio_languages or audio_languages is None:
                        for audio_track in parsed_info.get('audio', []):
                            if 'language' not in audio_track:
                                if not meta['unattended'] or (meta['unattended'] and meta.get('unattended-confirm', False)):
                                    audio_lang = cli_ui.ask_string('No audio language/s present, you must enter (comma-separated) languages:')
                                    if audio_lang:
                                        audio_languages.extend([lang.strip() for lang in audio_lang.split(',')])
                                        meta['audio_languages'] = audio_languages
                                        meta['write_audio_languages'] = True
                                    else:
                                        audio_languages = None
                                        meta['tracker_status'][tracker]['skip_upload'] = True
                                else:
                                    meta['tracker_status'][tracker]['skip_upload'] = True
                            else:
                                if "title" in audio_track and "commentary" not in audio_track['title']:
                                    meta['audio_languages'].append(audio_track['language'])

                    if not subtitle_languages or subtitle_languages is None:
                        for text_track in parsed_info.get('text', []):
                            if 'language' not in text_track:
                                if not meta['unattended'] or (meta['unattended'] and meta.get('unattended-confirm', False)):
                                    subtitle_lang = cli_ui.ask_string('No subtitle language/s present, you must enter (comma-separated) languages:')
                                    if subtitle_lang:
                                        subtitle_languages.extend([lang.strip() for lang in subtitle_lang.split(',')])
                                        meta['subtitle_languages'] = subtitle_languages
                                        meta['write_subtitle_languages'] = True
                                    else:
                                        subtitle_languages = None
                                        meta['tracker_status'][tracker]['skip_upload'] = True
                                else:
                                    meta['tracker_status'][tracker]['skip_upload'] = True
                            else:
                                meta['subtitle_languages'].append(text_track['language'])

                if meta['audio_languages'] and meta['write_audio_languages'] and desc is not None:
                    await desc.write(f"[code]Audio Language: {', '.join(meta['audio_languages'])}[/code]\n")

                if meta['subtitle_languages'] and meta['write_subtitle_languages'] and desc is not None:
                    await desc.write(f"[code]Subtitle Language: {', '.join(meta['subtitle_languages'])}[/code]\n")

        except Exception as e:
            console.print(f"[red]Error processing mediainfo languages: {e}[/red]")

        return desc if desc is not None else None

    elif meta['is_disc'] == "BDMV":
        audio_languages = []
        if meta.get('audio_languages'):
            audio_languages = meta['audio_languages']
        else:
            meta['audio_languages'] = []
        try:
            bdinfo = meta.get('bdinfo', {})
            audio_tracks = bdinfo.get("audio", [])
            audio_languages = {track.get("language", "") for track in audio_tracks if "language" in track}
            for track in audio_tracks:
                bitrate_str = track.get("bitrate", "")
                bitrate_num = None
                if bitrate_str:
                    match = re.search(r'([\d.]+)\s*([kM]?b(?:ps|/s))', bitrate_str.replace(',', ''), re.IGNORECASE)
                    if match:
                        value = float(match.group(1))
                        unit = match.group(2).lower()
                        if unit in ['mbps', 'mb/s']:
                            bitrate_num = int(value * 1000)
                        elif unit in ['kbps', 'kb/s']:
                            bitrate_num = int(value)
                        else:
                            bitrate_num = int(value)

                    lang = track.get("language", "")
                    if meta['unattended']:
                        if bitrate_num is not None and bitrate_num < 258:
                            if lang and lang in audio_languages:
                                audio_languages.discard(lang) if isinstance(audio_languages, set) else audio_languages.remove(lang)
            meta['audio_languages'] = list(audio_languages)
        except Exception as e:
            console.print(f"[red]Error processing BDInfo languages: {e}[/red]")

        return desc if desc is not None else None

    else:
        return desc if desc is not None else None

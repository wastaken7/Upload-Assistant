# -*- coding: utf-8 -*-
import os
import requests
import cli_ui
from src.exceptions import UploadException
from bs4 import BeautifulSoup
from src.console import console
from .COMMON import COMMON
from pymediainfo import MediaInfo


class ASC(COMMON):
    def __init__(self, config):
        super().__init__(config)
        self.tracker = 'ASC'
        self.source_flag = 'ASC'
        self.banned_groups = [""]
        self.base_url = "https://cliente.amigos-share.club"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        })
        self.signature = "[center][url=https://github.com/Audionut/Upload-Assistant]Upload automatizado via Audionut's Upload Assistant[/url][/center]"

    async def _generate_description(self, meta):
        description = ""

        if meta.get('is_disc') != 'BDMV':
            video_file = meta['filelist'][0]
            mi_template = os.path.abspath(f"{meta['base_dir']}/data/templates/MEDIAINFO.txt")

            if os.path.exists(mi_template):
                try:
                    media_info = MediaInfo.parse(video_file, output="STRING", full=False, mediainfo_options={"inform": f"file://{mi_template}"})
                    description += f"[left][font=consolas]\n{media_info}\n[/font][/left]\n\n"
                except Exception as e:
                    console.print(f"[bold red]Ocorreu um erro ao processar o template do MediaInfo: {e}[/bold red]")
                    mi_file_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO_CLEANPATH.txt"
                    if os.path.exists(mi_file_path):
                        with open(mi_file_path, 'r', encoding='utf-8') as f:
                            media_info = f.read()
                        description += f"[left][font=consolas]\n{media_info}\n[/font][/left]\n\n"
            else:
                console.print("[bold yellow]Aviso: Template de MediaInfo não encontrado em 'data/templates/MEDIAINFO.txt'[/bold yellow]")
                console.print("[yellow]Usando a versão padrão do MediaInfo na descrição.[/yellow]")
                mi_file_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO_CLEANPATH.txt"
                if os.path.exists(mi_file_path):
                    with open(mi_file_path, 'r', encoding='utf-8') as f:
                        media_info = f.read()
                    description += f"[left][font=consolas]\n{media_info}\n[/font][/left]\n\n"
        else:
            bd_summary_file = f"{meta['base_dir']}/tmp/{meta['uuid']}/BD_SUMMARY_00.txt"
            if os.path.exists(bd_summary_file):
                with open(bd_summary_file, 'r', encoding='utf-8') as f:
                    bd_summary = f.read()
                description += f"[left][font=consolas]\n{bd_summary}\n[/font][/left]\n\n"

        description += self.signature

        return description.strip()

    async def _prepare_form_data(self, meta):
        try:
            data = {}

            data['takeupload'] = 'yes'

            data['descr'] = await self._generate_description(meta)

            # Nome
            nome_original = meta.get('title')
            nome_em_portugues = None

            try:
                akas_list = meta.get('imdb_info', {}).get('akas', [])
                if akas_list:
                    for aka in akas_list:
                        if aka.get('country') == 'Brazil':
                            nome_em_portugues = aka.get('title')
                            break
            except (TypeError, AttributeError):
                nome_em_portugues = None

            nome_base = nome_original
            if nome_em_portugues and nome_em_portugues.lower() != nome_original.lower():
                nome_base = f"{nome_em_portugues} ({nome_original})"

            if meta.get('category') == 'TV':
                season_episode_str = ""
                if meta.get('tv_pack') == 1 and meta.get('season'):
                    season_episode_str = f" - {meta.get('season')}"
                elif meta.get('tv_pack') == 0 and meta.get('season') and meta.get('episode'):
                    season_episode_str = f" - {meta.get('season')}{meta.get('episode')}"
                data['name'] = f"{nome_base}{season_episode_str}"
            else:
                data['name'] = nome_base

            # Categoria
            if meta.get('anime'):
                if meta.get('category') == 'MOVIE':
                    data['type'] = '116'  # Categoria Anime (Filme)
                elif meta.get('category') == 'TV':
                    data['type'] = '118'  # Categoria Anime (Série)

            # IMDB
            if meta.get('imdb_id'):
                data['imdb'] = f"tt{str(meta.get('imdb_id')).zfill(7)}"

            if meta.get('genres'):
                data['genre'] = meta.get('genres')

            if meta.get('year'):
                data['ano'] = meta.get('year')

            if meta.get('poster'):
                data['capa'] = meta.get('poster')

            data['tresd'] = 2
            data['layout'] = 2
            data['legenda'] = '1'

            # Resolução
            video_track = next((t for t in meta.get('mediainfo', {}).get('media', {}).get('track', []) if t.get('@type') == 'Video'), None)
            if meta.get('is_disc') == 'BDMV':
                res_map = {'2160p': ('3840', '2160'), '1080p': ('1920', '1080'), '1080i': ('1920', '1080'), '720p': ('1280', '720')}
                if meta.get('resolution') in res_map:
                    data['largura'], data['altura'] = res_map[meta.get('resolution')]
            elif video_track:
                data['largura'] = video_track.get('Width')
                data['altura'] = video_track.get('Height')

            # Mapeamentos
            lang_map = {"en": "1", "fr": "2", "de": "3", "it": "4", "ja": "5", "es": "6", "ru": "7", "pt": "8", "zh": "10", "da": "12", "sv": "13", "fi": "14", "bg": "15", "no": "16", "nl": "17", "pl": "19", "ko": "20", "th": "21", "hi": "23", "tr": "25"}
            codec_video_map = {"MPEG-4": "31", "AV1": "29", "AVC": "30", "DivX": "9", "H264": "17", "H265": "18", "HEVC": "27", "M4V": "20", "MPEG-1": "10", "MPEG-2": "11", "RMVB": "12", "VC-1": "21", "VP6": "22", "VP9": "23", "WMV": "13", "XviD": "15"}

            data['lang'] = lang_map.get(meta.get('original_language', '').lower(), "11")

            if meta.get('anime'):
                idioma_map = {
                    "de": "3", "zh": "9", "ko": "11", "es": "1", "en": "4",
                    "ja": "8", "pt": "5", "ru": "2"
                }
                original_lang_code = meta.get('original_language', '').lower()
                data['idioma'] = idioma_map.get(original_lang_code, "6")  # '6' é 'Outros'

            # Lógica para definir a qualidade
            if meta.get('type') == 'DISC':
                disctype = meta.get('disctype')
                qualidade_map = {"BD25": "40", "BD50": "41", "BD66": "42", "BD100": "43"}

                # Tenta usar o 'disctype' diretamente se ele for válido
                if disctype and disctype in qualidade_map:
                    data['qualidade'] = qualidade_map[disctype]
                else:
                    # Se 'disctype' for nulo ou não reconhecido, pergunta ao usuário
                    console.print("[bold yellow]Aviso: Não foi encontrado o tipo de disco.[/bold yellow]")
                    use_size_fallback = cli_ui.ask_yes_no(
                        "Deseja definir o tipo de disco pelo tamanho do arquivo?",
                        default=True
                    )

                    if use_size_fallback:
                        # Se o usuário concordar, usa a lógica de tamanho
                        size = 0
                        try:
                            size = meta['torrent_comments'][0]['size']
                        except (KeyError, IndexError, TypeError):
                            size = 0

                        if size > 66000000000:
                            data['qualidade'] = "43"  # BD100
                        elif size > 50000000000:
                            data['qualidade'] = "42"  # BD66
                        elif size > 25000000000:
                            data['qualidade'] = "41"  # BD50
                        else:
                            data['qualidade'] = "40"  # BD25
                    else:
                        # Se o usuário recusar, cancela o upload para este tracker
                        raise UploadException(f"Upload para o '{self.tracker}' cancelado pelo usuário devido à ausência do tipo de disco.", 'yellow')
            else:
                # Lógica para tipos que não são DISC (REMUX, ENCODE, etc.)
                qualidade_map = {"ENCODE": "9", "REMUX": "39", "WEBDL": "23", "WEBRIP": "38", "BDRIP": "8", "DVDR": "10"}
                data['qualidade'] = qualidade_map.get(meta.get('type'), "0")

            audio_tracks_raw = []

            # Primeiro, tenta obter do BDInfo (para discos)
            if meta.get('is_disc') == 'BDMV' and meta.get('bdinfo') and isinstance(meta.get('bdinfo', {}).get('audio'), list):
                audio_tracks_raw = meta['bdinfo']['audio']
            # Se não for um disco, tenta obter do MediaInfo (para arquivos)
            elif meta.get('mediainfo'):
                mediainfo_tracks = meta.get('mediainfo', {}).get('media', {}).get('track', [])
                audio_tracks_raw = [{'language': t.get('Language')}
                                    for t in mediainfo_tracks if t.get('@type') == 'Audio']

            pt_variants = ["pt", "portuguese", "português", "pt-br"]

            has_pt = any(
                any(variant in track.get('language', '').lower() for variant in pt_variants)
                for track in audio_tracks_raw
            )

            other_langs_count = sum(
                1 for track in audio_tracks_raw
                if not any(variant in track.get('language', '').lower() for variant in pt_variants)
            )

            is_original_pt = any(variant in meta.get('original_language', '').lower() for variant in pt_variants)

            data['audio'] = "1"  # Legendado
            if has_pt and is_original_pt:
                data['audio'] = "4"  # Nacional
            elif has_pt and other_langs_count > 0:
                data['audio'] = "2"  # Dual-Audio

            # Extensão
            if meta.get('is_disc') == "BDMV":
                data['extencao'] = "5"
            else:
                file_extension = ''
                try:
                    tracks = meta.get('mediainfo', {}).get('media', {}).get('track', [])
                    for track in tracks:
                        if track.get('@type') == 'General':
                            file_extension = track.get('FileExtension', '').lower()
                            break
                except (AttributeError, TypeError):
                    file_extension = ''

                if file_extension == 'mkv':
                    data['extencao'] = '6'
                elif file_extension == 'mp4':
                    data['extencao'] = '8'

            # Codecs
            cn = meta.get('clean_name', '').upper()
            if "ATMOS" in cn:
                data['codecaudio'] = "43"
            elif "DD+" in cn:
                data['codecaudio'] = "26"
            elif "AAC" in cn:
                data['codecaudio'] = "10"
            elif "AC-3" in cn or ("DD" in cn and "+" not in cn):
                data['codecaudio'] = "11"
            elif "FLAC" in cn:
                data['codecaudio'] = "13"
            elif "LPCM" in cn:
                data['codecaudio'] = "21"
            elif "MPEG" in cn:
                data['codecaudio'] = "17"
            elif "DTS:X" in cn:
                data['codecaudio'] = "25"
            elif "DTS-HD MA" in cn:
                data['codecaudio'] = "24"
            elif "DTS-HD" in cn:
                data['codecaudio'] = "23"
            elif "DTS" in cn:
                data['codecaudio'] = "12"
            elif "OPUS" in cn:
                data['codecaudio'] = "27"
            elif "PCM" in cn:
                data['codecaudio'] = "28"
            elif "TRUEHD" in cn:
                data['codecaudio'] = "29"

            codec_video = meta.get('video_codec')
            data['codecvideo'] = codec_video_map.get(codec_video, "16")
            if video_track and 'HDR' in video_track.get('HDR_Format_String', ''):
                if codec_video == "HEVC":
                    data['codecvideo'] = "28"
                elif codec_video == "AVC":
                    data['codecvideo'] = "32"

            # Screenshots e Trailer
            for i, img in enumerate(meta.get('image_list', [])[:4]):
                data[f'screens{i+1}'] = img.get('raw_url')
            if meta.get('youtube'):
                data['tube'] = meta.get('youtube')

            return data

        except Exception as e:
            console.print(f"[bold red]A preparação dos dados para o upload falhou. Isso geralmente ocorre devido a uma informação ausente ou inesperada no 'meta.json' deste torrent: {e}[/bold red]")
            raise

    async def _perform_search_and_parse(self, search_url, meta):
        dupes = []
        console.print(f"[cyan]Buscando duplicados em:[/cyan] {search_url}")

        try:
            cookie_file = os.path.abspath(f"{meta['base_dir']}/data/cookies/ASC.txt")
            self.session.cookies.update(await self.parseCookieFile(cookie_file))
            response = self.session.get(search_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            releases = soup.find_all('li', class_='list-group-item dark-gray')
        except Exception as e:
            console.print(f"[bold red]Falha ao acessar a página de busca do ASC: {e}[/bold red]")
            return dupes

        if not releases:
            return dupes

        console.print(f"[cyan]Encontrados {len(releases)} releases. Analisando...[/cyan]")

        for release in releases:
            try:
                badges = release.find_all('span', class_='badge')
                disc_types = ['BD25', 'BD50', 'BD66', 'BD100', 'ISO']
                is_disc = any(badge.text.strip().upper() in disc_types for badge in badges)

                if is_disc:
                    name, year, resolution, disk_type, video_codec, audio_codec = meta.get('title'), "N/A", "N/A", "Blu-ray", "N/A", "N/A"
                    video_codec_terms = ['H264', 'H265', 'HEVC', 'AVC', 'XVID', 'VC-1']
                    audio_codec_terms = ['DTS', 'AC3', 'DDP', 'E-AC-3', 'TRUEHD', 'ATMOS', 'LPCM', 'AAC', 'FLAC']

                    for badge in badges:
                        badge_text = badge.text.strip()
                        badge_text_upper = badge_text.upper()

                        if badge_text.isdigit() and len(badge_text) == 4:
                            year = badge_text
                        elif badge_text_upper in ['4K', '2160P', '1080P', '720P', 'BDRIP']:
                            resolution = "2160p" if badge_text_upper == '4K' else badge_text
                        elif any(term in badge_text_upper for term in video_codec_terms):
                            video_codec = badge_text
                        elif any(term in badge_text_upper for term in audio_codec_terms):
                            audio_codec = badge_text

                    dupe_string = f"{name} {year} {resolution} {disk_type} {video_codec} {audio_codec}"
                    dupes.append(dupe_string)
                else:
                    details_link_tag = release.find('a', href=lambda href: href and "torrents-details.php?id=" in href)
                    if not details_link_tag:
                        continue

                    torrent_id = details_link_tag['href'].split('id=')[-1]
                    file_page_url = f"https://cliente.amigos-share.club/torrents-arquivos.php?id={torrent_id}"
                    file_page_response = self.session.get(file_page_url, timeout=15)
                    file_page_response.raise_for_status()
                    file_page_soup = BeautifulSoup(file_page_response.text, 'html.parser')

                    file_li_tag = file_page_soup.find('li', class_='list-group-item')
                    if file_li_tag and file_li_tag.contents:
                        filename = file_li_tag.contents[0].strip()
                        dupes.append(filename)

            except Exception as e:
                console.print(f"[bold red]Falha ao processar um release da lista: {e}[/bold red]")
                continue
        return dupes

    async def search_existing(self, meta, disctype):
        search_url = None
        # Animes não possuem IMDb, a busca tem que ser feita por nome
        if meta.get('anime'):
            nome_base = meta.get('title')
            search_name = nome_base
            if meta.get('category') == 'TV':
                season_episode_str = ""
                if meta.get('tv_pack') == 1 and meta.get('season'):
                    season_episode_str = f" - {meta.get('season')}"
                elif meta.get('tv_pack') == 0 and meta.get('season') and meta.get('episode'):
                    season_episode_str = f" - {meta.get('season')}{meta.get('episode')}"
                search_name = f"{nome_base}{season_episode_str}"

            search_query = search_name.replace(' ', '+')
            search_url = f"https://cliente.amigos-share.club/torrents-search.php?search={search_query}&cat=0&free=2&sort=id&tipo=contenha&order=desc"

        # Lógica para Filmes/Séries (pelo IMDb)
        else:
            if not meta.get('imdb_id'):
                console.print("[yellow]IMDb ID não encontrado, não é possível buscar por duplicados no ASC.[/yellow]")
                return []
            imdb_id = f"tt{str(meta['imdb_id']).zfill(7)}"
            search_url = f"https://cliente.amigos-share.club/busca-filmes.php?search=&imdb={imdb_id}&sort=size&order=desc"

        return await self._perform_search_and_parse(search_url, meta)

    async def validate_credentials(self, meta):
        cookie_file = os.path.abspath(f"{meta['base_dir']}/data/cookies/ASC.txt")
        if not os.path.exists(cookie_file):
            console.print(f"[bold red]Arquivo de cookie para o {self.tracker} não encontrado: {cookie_file}[/bold red]")
            return False

        common = COMMON(config=self.config)
        self.session.cookies.update(await common.parseCookieFile(cookie_file))

        try:
            test_url = f"{self.base_url}/gerador.php"

            response = self.session.get(test_url, timeout=10, allow_redirects=False)

            if response.status_code == 200 and 'gerador.php' in response.url:
                return True
            else:
                console.print(f"[bold red]Falha na validação das credenciais do {self.tracker}. O cookie pode estar expirado.[/bold red]")
                return False
        except Exception as e:
            console.print(f"[bold red]Erro ao validar credenciais do {self.tracker}: {e}[/bold red]")
            return False

    async def _should_auto_approve(self, meta):
        uploader_enabled = self.config['TRACKERS'][self.tracker].get('uploader_status', False)
        if not uploader_enabled:
            return False

        send_to_mod_queue = meta.get('modq', False) or meta.get('mq', False)
        if send_to_mod_queue:
            return False, "A flag --modq ou --mq foi usada, enviando para a fila de moderação."

        return True

    async def upload(self, meta, disctype):
        common = COMMON(config=self.config)

        await common.edit_torrent(meta, self.tracker, self.source_flag)

        data = await self._prepare_form_data(meta)
        if data is None:
            raise UploadException("Falha ao preparar os dados do formulário.", 'red')

        if meta.get('anime'):
            upload_url = f"{self.base_url}/enviar-anime.php"
        elif meta.get('category') == 'MOVIE':
            upload_url = f"{self.base_url}/enviar-filme.php"
        else:  # Assume que é 'TV'
            upload_url = f"{self.base_url}/enviar-series.php"

        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"

        if not os.path.exists(torrent_path):
            console.print(f"[bold red]CRÍTICO: Arquivo torrent não encontrado em: {torrent_path}[/bold red]")
            return

        with open(torrent_path, 'rb') as torrentFile:
            files = {'torrent': (f"{data['name']}.torrent", torrentFile, "application/x-bittorrent")}

            cookie_file = os.path.abspath(f"{meta['base_dir']}/data/cookies/ASC.txt")
            self.session.cookies.update(await common.parseCookieFile(cookie_file))

            if meta.get('debug', False):
                console.print("[yellow]MODO DEBUG ATIVADO[/yellow]")
                console.print("[cyan]Upload não será realizado. Exibindo dados do formulário:[/cyan]")
                console.print(data)
                return

            response = self.session.post(upload_url, data=data, files=files, timeout=60)

            if "foi enviado com sucesso" in response.text:
                console.print("[bold green]Upload para o ASC realizado com sucesso![/bold green]")

                try:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    details_link_tag = soup.find('a', href=lambda href: href and "torrents-details.php?id=" in href)

                    if details_link_tag:
                        relative_url = details_link_tag['href']
                        torrent_url = f"{self.base_url}/{relative_url}"

                        announce_url = self.config['TRACKERS'][self.tracker].get('announce_url')

                        await common.add_tracker_torrent(meta, self.tracker, self.source_flag, announce_url, torrent_url)

                        should_approve, reason = await self._should_auto_approve(meta)

                        if should_approve:
                            console.print(f"[cyan]{reason} Tentando realizar a aprovação automática...[/cyan]")
                            try:
                                torrent_id = relative_url.split('id=')[-1]
                                approval_url = f"{self.base_url}/uploader_app.php?id={torrent_id}"

                                approval_response = self.session.get(approval_url, timeout=30)
                                approval_response.raise_for_status()

                            except Exception as e:
                                console.print(f"[bold red]Ocorreu um erro durante a tentativa de aprovação automática do torrent ID {torrent_id}: {e}[/bold red]")
                        else:
                            console.print(f"[yellow]{reason}. A aprovação automática será ignorada.[/yellow]")

                    else:
                        console.print("[bold yellow]Aviso: Não foi possível encontrar o link do torrent na página de sucesso.[/bold yellow]")

                except Exception as e:
                    console.print(f"[bold red]Ocorreu um erro no pós-processamento do upload: {e}[/bold red]")

            else:
                response_save_path = f"{meta['base_dir']}/tmp/asc_upload_fail_{meta['uuid']}.html"
                with open(response_save_path, "w", encoding="utf-8") as f:
                    f.write(response.text)
                console.print("[bold red]Falha no upload para o ASC. A resposta do servidor não indicou sucesso.[/bold red]")
                console.print(f"[yellow]A resposta do servidor foi salva em: {response_save_path}[/yellow]")
                raise UploadException("Falha no upload para o ASC: resposta inesperada do servidor.", 'red')

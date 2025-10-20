# -*- coding: utf-8 -*-
import aiofiles
import glob
import httpx
import os
import platform
import re
from bs4 import BeautifulSoup
from src.bbcode import BBCODE
from src.console import console
from src.get_desc import DescriptionBuilder
from src.trackers.COMMON import COMMON


class IPT:
    def __init__(self, config):
        self.config = config
        self.common = COMMON(config)
        self.tracker = 'IPT'
        self.source_flag = 'IPTorrents'
        self.banned_groups = ['']
        self.base_url = 'https://iptorrents.com'
        self.torrent_url = 'https://iptorrents.com/torrent.php?id='
        self.announce = self.config['TRACKERS'][self.tracker]['announce_url']
        self.session = httpx.AsyncClient(headers={
            'User-Agent': f"Upload Assistant/2.3 ({platform.system()} {platform.release()})"
        }, timeout=30)

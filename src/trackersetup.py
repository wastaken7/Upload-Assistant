from src.trackers.AR import AR
from src.trackers.HUNO import HUNO
from src.trackers.BLU import BLU
from src.trackers.BHD import BHD
from src.trackers.AITHER import AITHER
from src.trackers.STC import STC
from src.trackers.R4E import R4E
from src.trackers.THR import THR
from src.trackers.STT import STT
from src.trackers.HP import HP
from src.trackers.PTP import PTP
from src.trackers.SN import SN
from src.trackers.ACM import ACM
from src.trackers.HDB import HDB
from src.trackers.LCD import LCD
from src.trackers.TTG import TTG
from src.trackers.LST import LST
from src.trackers.FRIKI import FRIKI
from src.trackers.FL import FL
from src.trackers.LT import LT
from src.trackers.NBL import NBL
from src.trackers.ANT import ANT
from src.trackers.PTER import PTER
from src.trackers.MTV import MTV
from src.trackers.JPTV import JPTV
from src.trackers.TL import TL
from src.trackers.HDT import HDT
from src.trackers.RF import RF
from src.trackers.OE import OE
from src.trackers.BHDTV import BHDTV
from src.trackers.RTF import RTF
from src.trackers.OTW import OTW
from src.trackers.FNP import FNP
from src.trackers.CBR import CBR
from src.trackers.UTP import UTP
from src.trackers.AL import AL
from src.trackers.SHRI import SHRI
from src.trackers.TIK import TIK
from src.trackers.TVC import TVC
from src.trackers.PSS import PSS
from src.trackers.ULCX import ULCX
from src.trackers.SPD import SPD
from src.trackers.YOINK import YOINK
from src.trackers.HHD import HHD
from src.trackers.SP import SP
from src.console import console
import httpx
import aiofiles
import os
import json
from datetime import datetime, timedelta
import asyncio


class TRACKER_SETUP:
    def __init__(self, config):
        self.config = config
        # Add initialization details here
        pass

    def trackers_enabled(self, meta):
        from data.config import config
        if meta.get('trackers', None) is not None:
            trackers = meta['trackers']
        else:
            trackers = config['TRACKERS']['default_trackers']
        if "," in trackers:
            trackers = trackers.split(',')

        if isinstance(trackers, str):
            trackers = trackers.split(',')
        trackers = [s.strip().upper() for s in trackers]
        if meta.get('manual', False):
            trackers.insert(0, "MANUAL")
        return trackers

    async def get_banned_groups(self, meta, tracker):
        file_path = os.path.join(meta['base_dir'], 'data', 'banned', f'{tracker}_banned_groups.json')

        # Check if we need to update
        if not await self.should_update(file_path):
            return file_path

        url = f'https://{tracker}.cc/api/blacklists/releasegroups'
        headers = {
            'Authorization': f"Bearer {self.config['TRACKERS'][tracker]['api_key'].strip()}",
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    await self.write_banned_groups_to_file(file_path, data)
                    return file_path
                else:
                    console.print(f"Error: Received status code {response.status_code}")
                    return None
            except httpx.RequestError as e:
                console.print(f"HTTP Request failed: {e}")
                return None

    async def write_banned_groups_to_file(self, file_path, json_data):
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            names = [item['name'] for item in json_data.get('data', [])]
            names_csv = ', '.join(names)
            file_content = {
                "last_updated": datetime.now().strftime("%Y-%m-%d"),
                "banned_groups": names_csv,
                "raw_data": json_data
            }
            async with aiofiles.open(file_path, mode='w') as file:
                await file.write(json.dumps(file_content, indent=4))
            console.print(f"File '{file_path}' updated successfully with {len(names)} groups.")
        except Exception as e:
            console.print(f"An error occurred: {e}")

    async def should_update(self, file_path):
        try:
            async with aiofiles.open(file_path, mode='r') as file:
                content = await file.read()
                data = json.loads(content)
                last_updated = datetime.strptime(data['last_updated'], "%Y-%m-%d")
                return datetime.now() >= last_updated + timedelta(weeks=1)
        except FileNotFoundError:
            return True
        except Exception as e:
            console.print(f"Error reading file: {e}")
            return True

    async def check_banned_group(self, tracker, banned_group_list, meta):
        result = False
        if not meta['tag']:
            result = False

        if tracker.upper() == "AITHER":
            # Dynamically fetch banned groups for AITHER
            file_path = await self.get_banned_groups(meta, tracker)
            if not file_path:
                console.print(f"[bold red]Failed to load banned groups for '{tracker}'.")
                result = False

            # Load the banned groups from the file
            try:
                async with aiofiles.open(file_path, mode='r') as file:
                    content = await file.read()
                    data = json.loads(content)
                    banned_group_list.extend(data.get("banned_groups", "").split(", "))
            except FileNotFoundError:
                console.print(f"[bold red]Banned group file for '{tracker}' not found.")
                result = False
            except json.JSONDecodeError:
                console.print(f"[bold red]Failed to parse banned group file for '{tracker}'.")
                result = False

        for tag in banned_group_list:
            if isinstance(tag, list):
                if meta['tag'][1:].lower() == tag[0].lower():
                    console.print(f"[bold yellow]{meta['tag'][1:]}[/bold yellow][bold red] was found on [bold yellow]{tracker}'s[/bold yellow] list of banned groups.")
                    console.print(f"[bold red]NOTE: [bold yellow]{tag[1]}")
                    await asyncio.sleep(5)
                    result = True
            else:
                if meta['tag'][1:].lower() == tag.lower():
                    console.print(f"[bold yellow]{meta['tag'][1:]}[/bold yellow][bold red] was found on [bold yellow]{tracker}'s[/bold yellow] list of banned groups.")
                    await asyncio.sleep(5)
                    result = True

        return result


tracker_class_map = {
    'ACM': ACM, 'AITHER': AITHER, 'AL': AL, 'ANT': ANT, 'AR': AR, 'BHD': BHD, 'BHDTV': BHDTV, 'BLU': BLU, 'CBR': CBR,
    'FNP': FNP, 'FL': FL, 'FRIKI': FRIKI, 'HDB': HDB, 'HDT': HDT, 'HHD': HHD, 'HP': HP, 'HUNO': HUNO, 'JPTV': JPTV, 'LCD': LCD,
    'LST': LST, 'LT': LT, 'MTV': MTV, 'NBL': NBL, 'OE': OE, 'OTW': OTW, 'PSS': PSS, 'PTP': PTP, 'PTER': PTER,
    'R4E': R4E, 'RF': RF, 'RTF': RTF, 'SHRI': SHRI, 'SN': SN, 'SP': SP, 'SPD': SPD, 'STC': STC, 'STT': STT, 'THR': THR,
    'TIK': TIK, 'TL': TL, 'TVC': TVC, 'TTG': TTG, 'ULCX': ULCX, 'UTP': UTP, 'YOINK': YOINK,
}

api_trackers = {
    'ACM', 'AITHER', 'AL', 'BHD', 'BLU', 'CBR', 'FNP', 'FRIKI', 'HHD', 'HUNO', 'JPTV', 'LCD', 'LST', 'LT',
    'OE', 'OTW', 'PSS', 'RF', 'R4E', 'SHRI', 'SP', 'STC', 'STT', 'TIK', 'ULCX', 'UTP', 'YOINK'
}

other_api_trackers = {
    'ANT', 'BHDTV', 'NBL', 'RTF', 'SN', 'SPD', 'TL', 'TVC'
}

http_trackers = {
    'AR', 'FL', 'HDB', 'HDT', 'MTV', 'PTER', 'TTG'
}

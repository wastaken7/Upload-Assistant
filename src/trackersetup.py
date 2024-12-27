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
import cli_ui
from src.console import console


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

    def check_banned_group(self, tracker, banned_group_list, meta):
        if meta['tag'] == "":
            return False
        else:
            q = False
            for tag in banned_group_list:
                if isinstance(tag, list):
                    if meta['tag'][1:].lower() == tag[0].lower():
                        console.print(f"[bold yellow]{meta['tag'][1:]}[/bold yellow][bold red] was found on [bold yellow]{tracker}'s[/bold yellow] list of banned groups.")
                        console.print(f"[bold red]NOTE: [bold yellow]{tag[1]}")
                        q = True
                else:
                    if meta['tag'][1:].lower() == tag.lower():
                        console.print(f"[bold yellow]{meta['tag'][1:]}[/bold yellow][bold red] was found on [bold yellow]{tracker}'s[/bold yellow] list of banned groups.")
                        q = True
            if q:
                if not meta['unattended'] or (meta['unattended'] and meta.get('unattended-confirm', False)):
                    if not cli_ui.ask_yes_no(cli_ui.red, "Upload Anyways?", default=False):
                        return True
                else:
                    return True
        return False


tracker_class_map = {
    'ACM': ACM, 'AITHER': AITHER, 'AL': AL, 'ANT': ANT, 'BHD': BHD, 'BHDTV': BHDTV, 'BLU': BLU, 'CBR': CBR,
    'FNP': FNP, 'FL': FL, 'HDB': HDB, 'HDT': HDT, 'HHD': HHD, 'HP': HP, 'HUNO': HUNO, 'JPTV': JPTV, 'LCD': LCD,
    'LST': LST, 'LT': LT, 'MTV': MTV, 'NBL': NBL, 'OE': OE, 'OTW': OTW, 'PSS': PSS, 'PTP': PTP, 'PTER': PTER,
    'R4E': R4E, 'RF': RF, 'RTF': RTF, 'SHRI': SHRI, 'SN': SN, 'SPD': SPD, 'STC': STC, 'STT': STT, 'THR': THR,
    'TIK': TIK, 'TL': TL, 'TVC': TVC, 'TTG': TTG, 'ULCX': ULCX, 'UTP': UTP, 'YOINK': YOINK,
}

api_trackers = {
    'ACM', 'AITHER', 'AL', 'BHD', 'BLU', 'CBR', 'FNP', 'HHD', 'HUNO', 'JPTV', 'LCD', 'LST', 'LT',
    'OE', 'OTW', 'PSS', 'RF', 'R4E', 'SHRI', 'STC', 'STT', 'TIK', 'ULCX', 'UTP', 'YOINK'
}

other_api_trackers = {
    'ANT', 'BHDTV', 'NBL', 'RTF', 'SN', 'SPD', 'TL', 'TVC'
}

http_trackers = {
    'FL', 'HDB', 'HDT', 'MTV', 'PTER', 'TTG'
}

# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path so we can import src modules
base_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(base_dir))

from bin.get_7z import SevenZipBinaryManager  # noqa: E402
from bin.get_bdinfo import BDInfoBinaryManager  # noqa: E402
from bin.get_mkbrr import MkbrrBinaryManager  # noqa: E402
from bin.get_nyuu import NyuuBinaryManager  # noqa: E402
from bin.get_par2 import Par2BinaryManager  # noqa: E402
from bin.get_pesto import PestoBinaryManager  # noqa: E402


async def main() -> None:
    print("Pre-downloading all utility binaries for release build...")

    print("1/6 Downloading 7-Zip...")
    p7z = await SevenZipBinaryManager.ensure_7z_binary(base_dir)
    print(f"Downloaded 7-Zip to {p7z}")

    print("2/6 Downloading BDInfo CLI...")
    bd = await BDInfoBinaryManager.ensure_bdinfo_binary(base_dir)
    print(f"Downloaded BDInfo to {bd}")

    print("3/6 Downloading mkbrr...")
    mk = await MkbrrBinaryManager.ensure_mkbrr_binary(base_dir, "v1.18.0")
    print(f"Downloaded mkbrr to {mk}")

    print("4/6 Downloading Nyuu...")
    ny = await NyuuBinaryManager.ensure_nyuu_binary(base_dir, path_7z=p7z)
    print(f"Downloaded Nyuu to {ny}")

    print("5/6 Downloading PAR2...")
    pa = await Par2BinaryManager.ensure_par2_binary(base_dir)
    print(f"Downloaded PAR2 to {pa}")

    print("6/6 Downloading Pesto...")
    pe = await PestoBinaryManager.ensure_pesto_binary(base_dir)
    print(f"Downloaded Pesto to {pe}")

    print("All internal utility binaries downloaded successfully!")


if __name__ == "__main__":
    asyncio.run(main())

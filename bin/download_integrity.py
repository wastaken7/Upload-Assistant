"""Pinned SHA-256 verification for third-party executable downloads."""

import hashlib
from pathlib import Path

SHA256_BY_ASSET = {
    "ffmpeg-9.0.1-essentials_build.zip": "fec81ae03971d9dd4be3ebe02e263bd2ec1d789483f931bdba5f5715e65da2e9",
    "MediaInfo_CLI_23.04_Windows_x64.zip": "b1beafae0a15168ca37db8a3061d55eba55c1a120d6a6423ac1d3f30ed869270",
    "MediaInfo_CLI_26.05_Lambda_arm64.zip": "57268dcfc044cdcbe4641e26432392f002b7fa4bcb06e9d738be04cd047a2c1e",
    "MediaInfo_CLI_26.05_Lambda_x86_64.zip": "1ae3744a78c93492b69f0b38bb2d1de1433c3eae04030ff1ea82ee1f60ac9a99",
    "MediaInfo_CLI_26.05_Mac.dmg": "507605a7c8f1054a6996d99a4ef5b5a0711cfbf2f8ca2ef5161d6ee701ea8015",
    "MediaInfo_CLI_26.05_Windows_ARM64.zip": "6b403fa1411730672adefa8d49d97cbf7163eed7fc5c1256c9a6e9f915fde1a8",
    "MediaInfo_CLI_26.05_Windows_x64.zip": "f7f80620ce6d14f4995f0de6f98e3ef18ad29496db01899571152ee3311229f9",
    "mkbrr_1.25.1_darwin_arm64.tar.gz": "42f1c32bd86c3d7b1e1c900ab6d29a43eec74fe3b7f3374fb8da5da19f09f013",
    "mkbrr_1.25.1_darwin_x86_64.tar.gz": "410525eb87a3372346072c43bab000de3efdbe31e569cf4e477508dc6a514b40",
    "mkbrr_1.25.1_freebsd_x86_64.tar.gz": "dd1a8e265263359f51605085423ba1e8214ae852fdb49c4de6c0b2f9b6543788",
    "mkbrr_1.25.1_linux_arm.tar.gz": "3d59ba8b78cf60471f092e3bdc2eb3b53387259873a935dab66af88f78707e40",
    "mkbrr_1.25.1_linux_arm64.tar.gz": "6cd2347406c7b2f03a12d240022c9f2d23684c336a3802e5706a6ea3e360552d",
    "mkbrr_1.25.1_linux_x86_64.tar.gz": "a48a3032fad09c033918a6e7a712eb45069b2a2f02546f8672768b19991bbb3b",
    "mkbrr_1.25.1_windows_x86_64.zip": "2a1ca85148d558b680d16d37e3c83b03883494b3445f82f3fd5fd97a4cbe928f",
    "mkbrr_1.18.0_linux_x86_64.tar.gz": "a796bd97dfb093e18a1a509c8986580498e65253582983a462b977b359f987b9",
    "mkbrr_1.18.0_linux_arm64.tar.gz": "1c187ab2b860e637296d6f0deb4c2e7754a4c1e249b0226f0be671170689de24",
    "mkbrr_1.18.0_linux_arm.tar.gz": "f622595f6afee302c72c89abdd9f31ad3197bd85d45a8b482f97ebd21930ac51",
    "bdinfo_0.4.2_darwin_amd64.tar.gz": "f4679bd06077f1f9080b58559b235f1f4d8fb8ddbb49b872956904d28b33e65c",
    "bdinfo_0.4.2_darwin_arm64.tar.gz": "98dffc9dbd6f81f6b691271ecf5462b8164ec07a4f7ea357b9f03eefba06969a",
    "bdinfo_0.4.2_linux_amd64.tar.gz": "8794988af6e154bc34ceccd8c327e4eb2b6386e10f248a20e21e190d472fe9b1",
    "bdinfo_0.4.2_linux_arm.tar.gz": "c6a49181961836fde75e15f9dfd19284a12bc3037f164de72bd9470211461053",
    "bdinfo_0.4.2_linux_arm64.tar.gz": "f9f791534b48ad6c507bef3284be8a8395edc2f7193ac18f7bcde2a5e22467dd",
    "bdinfo_0.4.2_windows_amd64.zip": "e68d48912b1ca7dba73c872a67c36abaabb7c46b73ac5dad32998025246bc462",
    "7zr.exe": "abcf64ae1cbafddb5395e4cdd3bdc7e3e0561d54a0c6380e3dd43bdbffe519a2",
    "7z2601-mac.tar.xz": "0b6b930dbf82742e3f1014c35072a6b8b3aab183fece348e7f723675f1c5bea2",
    "7z2601-linux-x64.tar.xz": "8ea0fc8a135e7b848e80a4116fe22dff56c8c4518dde1f43cce67f4e340b437a",
    "7z2601-linux-arm64.tar.xz": "39f8c9070c300a63c7484d9a983119ef3edf841e1ddf69f1affae29fdec5f612",
    "7z2601-linux-arm.tar.xz": "72c19911abb6964fcf85ebe213dfcee57bad892345e03bb940c5a27a1050b3bf",
    "pesto-linux-x86_64": "4eff75ade11b1f8e67c1347be3ed3a1b2e2c7ddc54ff65a3f8f1e1e9604b80b7",
    "pesto-windows-x86_64.exe": "f3dfa8d91dbbbb7147ed76aef2a68c890160f809c113f08c18cdb3bd2337bdce",
    "par2cmdline-turbo-1.4.0-win-x64.zip": "7905d1d6aced2b2ca30d824b4954e6bf740dc9d6cfec718b0ab146b5fc0d6327",
    "par2cmdline-turbo-1.4.0-win-arm64.zip": "89870943c142b1360ab79bb287e47d5bffc686e159581750917207bbad2f6dcb",
    "par2cmdline-turbo-1.4.0-macos-arm64.zip": "926139d3cf18f6c4e4aeb25d6fc12b758cdf4936788fb46acd18caf21ffa9a15",
    "par2cmdline-turbo-1.4.0-macos-amd64.zip": "29ebb3629911a5b3ce4cdd8723a551a2877771b633630f443d99637559ef76be",
    "par2cmdline-turbo-1.4.0-linux-amd64.zip": "0be495172b4b8aeabda39c493e47de652813fab88ae745c8633e901c05494281",
    "par2cmdline-turbo-1.4.0-linux-arm64.zip": "1bb2acb2c549bb3a2e91be3ac6291b00d4b657a56ab23f763f2161ffe7df0fcd",
    "nyuu-v0.4.2-win32.7z": "b14eb105e064ec2bd8f6d872c1c652a9943ea54d767c80554617f4eff6c801b8",
    "nyuu-v0.4.2-linux-aarch64.tar.xz": "8a94f3f775996e4469736494074ac7663ff463748b0e302c2bc13d0ff4a88c0b",
    "nyuu-v0.4.2-linux-amd64.tar.xz": "bbea69ffaf1d8ed3465935157e3842fe7a38bade2703504879eb8bc7c0a83dff",
    "nyuu-v0.4.2-macos-x64.tar.xz": "040c56a486bc4ac7e3b0eed7a482ffce1bbf747ff731ad45ffd99d7230fcb2a0",
    "dovi_tool-2.3.3-aarch64-pc-windows-msvc.zip": "559ed634ef0b956ab89ed965b4920371bb228983f105d99fafeb372a8190c872",
    "dovi_tool-2.3.3-aarch64-unknown-linux-musl.tar.gz": "daf538c275f4e702219ce8eb61db28382193ac9d0126e1ef4185a88303af4485",
    "dovi_tool-2.3.3-universal-macOS.zip": "b113c83fed2d8d7ed9e43f0428d02fa0d0030e20965fc24a3cd4d48597d88685",
    "dovi_tool-2.3.3-x86_64-pc-windows-msvc.zip": "37ae198f2a535c910befad39fc09c21cded76bf3ef2d5459d542e58c2c158311",
    "dovi_tool-2.3.3-x86_64-unknown-linux-musl.tar.gz": "5dae82cb2becd3b9fd726127f936a8d32635e60746d16238fdfded12aa05988c",
    "hdr10plus_tool-1.7.2-aarch64-pc-windows-msvc.zip": "0cc1cd6ae9fb1115e5dc3d1f6daed47c486410ad5731f60a298e5d78fe995d6b",
    "hdr10plus_tool-1.7.2-aarch64-unknown-linux-musl.tar.gz": "5fb90607cd94296640f1fc2355207b8107b67baac96d37481423d08a9fce437d",
    "hdr10plus_tool-1.7.2-universal-macOS.zip": "d76977ed2ea90f8d6bce9035e37ea9dbffcead4725ceb1acf455c25d8658ff28",
    "hdr10plus_tool-1.7.2-x86_64-pc-windows-msvc.zip": "82b2d560073941b14c6511a431f429e33e134e5caefb60d7e8f6f6e6da8e16ba",
    "hdr10plus_tool-1.7.2-x86_64-unknown-linux-musl.tar.gz": "06385f37a639d61ba21d4be3150c863846933bc3b58110e094d8fc8f1c2249f2",
}


def verify_downloaded_asset(path: Path, asset: str) -> None:
    """Fail closed unless a downloaded executable archive matches its pinned hash."""
    expected = SHA256_BY_ASSET.get(asset)
    if expected is None:
        raise RuntimeError(f"No SHA-256 checksum is pinned for {asset}")
    with path.open("rb") as asset_file:
        actual = hashlib.file_digest(asset_file, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError(f"SHA-256 checksum mismatch for {asset}")


def verify_downloaded_content(content: bytes, asset: str) -> None:
    """Fail closed unless downloaded content matches its pinned hash."""
    expected = SHA256_BY_ASSET.get(asset)
    if expected is None:
        raise RuntimeError(f"No SHA-256 checksum is pinned for {asset}")
    if hashlib.sha256(content).hexdigest() != expected:
        raise RuntimeError(f"SHA-256 checksum mismatch for {asset}")

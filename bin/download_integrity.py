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
    "mkbrr_1.24.0_windows_x86_64.zip": "23b923a26d50e3afabcd99938ea70a510904a98365f698bbeaae057ec1a51711",
    "mkbrr_1.24.0_darwin_arm64.tar.gz": "99c939d1b3e7329d1cf82c90adceb93291eefc34f72ca263577b9c4826172c1e",
    "mkbrr_1.24.0_darwin_x86_64.tar.gz": "26092fa6b59ec79ede4be8d09f9f6f3135af1ccf0f4df312215b2ed92691e7dd",
    "mkbrr_1.24.0_linux_x86_64.tar.gz": "bd23b2e2aa62a943eb5cfea23fa250e60b9ba2169a36e27aaeec980d82dc47a5",
    "mkbrr_1.24.0_linux_arm64.tar.gz": "dada7d9aab0bd0854cdf3b5473b77d7f04b7dcf99ef519b45b522959f9db78e7",
    "mkbrr_1.24.0_linux_arm.tar.gz": "7480a96b9dafd458be1769d8c743bc85c53034a9673252b831b3130e8c1b758d",
    "mkbrr_1.24.0_freebsd_x86_64.tar.gz": "d3c2fe3bc9bad2467faa38124f7f1ebf3e70b8b32300486ee21f0667bd7fc6c7",
    "mkbrr_1.18.0_linux_x86_64.tar.gz": "a796bd97dfb093e18a1a509c8986580498e65253582983a462b977b359f987b9",
    "mkbrr_1.18.0_linux_arm64.tar.gz": "1c187ab2b860e637296d6f0deb4c2e7754a4c1e249b0226f0be671170689de24",
    "mkbrr_1.18.0_linux_arm.tar.gz": "f622595f6afee302c72c89abdd9f31ad3197bd85d45a8b482f97ebd21930ac51",
    "bdinfo_0.4.0_windows_amd64.zip": "2291df819388739287b042694adc5bc8e9b90583968802ff3a4ab1ace3f658f9",
    "bdinfo_0.4.0_darwin_amd64.tar.gz": "ecb47628798aa1bde3188b4d47f135e9baeee628345921b2f993590b42e22b61",
    "bdinfo_0.4.0_darwin_arm64.tar.gz": "27bb0f0dcc252850075bf6e30b65c0ce42a07c5afa9c52f42c69422df36c6428",
    "bdinfo_0.4.0_linux_amd64.tar.gz": "78fd90627c5d9a2bddd3126875d036e73bb4178192fe786c29b0d6c6ccc3b3eb",
    "bdinfo_0.4.0_linux_arm64.tar.gz": "b98a58f903984b86622387db45be9142485c6171dcd5de41c951c7a3de34d6bf",
    "bdinfo_0.4.0_linux_arm.tar.gz": "94bd7a32d90ce6118695ab50940b048d91d42f9e48f3d9e879ac3d0721c83463",
    "7zr.exe": "abcf64ae1cbafddb5395e4cdd3bdc7e3e0561d54a0c6380e3dd43bdbffe519a2",
    "7z2601-mac.tar.xz": "0b6b930dbf82742e3f1014c35072a6b8b3aab183fece348e7f723675f1c5bea2",
    "7z2601-linux-x64.tar.xz": "8ea0fc8a135e7b848e80a4116fe22dff56c8c4518dde1f43cce67f4e340b437a",
    "7z2601-linux-arm64.tar.xz": "39f8c9070c300a63c7484d9a983119ef3edf841e1ddf69f1affae29fdec5f612",
    "7z2601-linux-arm.tar.xz": "72c19911abb6964fcf85ebe213dfcee57bad892345e03bb940c5a27a1050b3bf",
    "pesto-windows-x86_64.exe": "25306273eb6ed91abfb465d9a3e60adceb868883f7c456926d2de4eee1e57236",
    "pesto-linux-x86_64": "4a357e37c5f867694fa95d025a7aba836d43f6cfa410f1ab78e86f817f4c656c",
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

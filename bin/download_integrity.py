"""Pinned SHA-256 verification for third-party executable downloads."""

import hashlib
from pathlib import Path

SHA256_BY_ASSET = {
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
    "bdinfo_0.3.1_windows_amd64.zip": "53258982e0aee24f87a95d6869552512028217f5ce3c77ac0036cf0eed1f3073",
    "bdinfo_0.3.1_darwin_amd64.tar.gz": "8d63e3fd4cff3d3438c40bcf8c006114388820bb3f118c67b25bd1b18b73ed1f",
    "bdinfo_0.3.1_darwin_arm64.tar.gz": "31b414300a5745acaacbd99a4ebc5ce2623aa7614986f41be51570c712f692ba",
    "bdinfo_0.3.1_linux_amd64.tar.gz": "75cffac8adf3c1c971aaffb7843edd053a2d275814439bfd4868ba7774080feb",
    "bdinfo_0.3.1_linux_arm64.tar.gz": "37d389107894589a54e37e0d9f503c8f8c53960614714ee8095f06bdb9ec9437",
    "bdinfo_0.3.1_linux_arm.tar.gz": "21e382e063cf81d9c3b97adfa92ae841e9d23caac7045c63beec0a9e0b1fe82e",
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

"""Build a per-user Setup with a pinned, portable, free NSIS compiler."""
import argparse
import html
from pathlib import Path
import re
import subprocess
import urllib.request
import zipfile

from common import ROOT, sha256, version, safe_member

NSIS_VERSION = "3.13"
NSIS_SHA256 = "ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8"
NSIS_URL = f"https://downloads.sourceforge.net/project/nsis/NSIS%203/{NSIS_VERSION}/nsis-{NSIS_VERSION}.zip"


def compiler():
    cache = ROOT / ".build/nsis"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"nsis-{NSIS_VERSION}.zip"
    if not archive.is_file() or sha256(archive) != NSIS_SHA256:
        url = NSIS_URL
        for _ in range(4):
            with urllib.request.urlopen(url, timeout=60) as response:
                body = response.read(10 * 1024 * 1024 + 1)
            if len(body) > 10 * 1024 * 1024:
                raise ValueError("NSIS archive exceeds expected size")
            if body.startswith(b"PK"):
                archive.write_bytes(body)
                break
            match = re.search(r'http-equiv="refresh" content="[0-9]+; url=([^"]+)', body.decode("utf-8", errors="replace"))
            if not match:
                raise ValueError("SourceForge did not return the pinned NSIS ZIP")
            url = html.unescape(match[1])
            if not url.startswith("https://downloads.sourceforge.net/"):
                raise ValueError("Unexpected NSIS download redirect")
        if not archive.is_file() or sha256(archive) != NSIS_SHA256:
            raise ValueError("Pinned NSIS SHA256 mismatch")
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            name = safe_member(entry.filename.rstrip("/"))
            if name.parts[0] != f"nsis-{NSIS_VERSION}":
                raise ValueError("Unexpected NSIS archive entry")
        package.extractall(cache)
    return cache / f"nsis-{NSIS_VERSION}/makensis.exe"


def build(makensis=None):
    payload = ROOT / ".build/payload/KurtLauncher"
    if not (payload / "KurtLauncher.exe").is_file():
        raise ValueError("Build the clean Windows payload first")
    output = ROOT / "artifacts" / f"KurtLauncher-v{version()}-Setup.exe"
    subprocess.run([str(makensis or compiler()), "/V2", f"/DVERSION={version()}",
                    f"/DPAYLOAD={payload}", f"/DOUTPUT={output}",
                    str(ROOT / "installer/KurtLauncher.nsi")], check=True)
    print("Windows Setup:", output.name, "SHA256:", sha256(output), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--makensis", type=Path)
    build(parser.parse_args().makensis)

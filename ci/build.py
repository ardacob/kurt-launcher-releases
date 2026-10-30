"""Prepare pinned assets, then assemble a clean portable Windows ZIP."""
import argparse
import importlib.metadata
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from common import ROOT, constant, sha256, version


def assets():
    from PySide6.QtCore import QByteArray, QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    svg = QSvgRenderer(QByteArray((ROOT / "assets/icon.svg").read_bytes()))
    if not svg.isValid():
        raise ValueError("Invalid icon SVG")
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    svg.render(painter, QRectF(0, 0, 256, 256))
    painter.end()
    if not image.save(str(ROOT / "assets/icon.ico"), "ICO"):
        raise RuntimeError("Icon generation failed")
    agent_version = constant(ROOT / "src/invites.py", "AGENT_VERSION")
    expected = constant(ROOT / "src/invites.py", "AGENT_SHA256")
    target = ROOT / "assets/playit/playitd.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/playit-cloud/playit-agent/releases/download/v{agent_version}/playitd-windows-x86_64-signed.exe"
    if not target.exists() or sha256(target) != expected:
        urllib.request.urlretrieve(url, target)
    if sha256(target) != expected:
        target.unlink()
        raise ValueError("Pinned Playit SHA256 does not match")
    subprocess.run([str(target), "--help"], check=True, timeout=30, stdout=subprocess.DEVNULL)
    print("Icon and pinned Playit helper verified")


def package():
    current = version()
    folder = ROOT / ".build/payload/KurtLauncher"
    folder.mkdir(parents=True, exist_ok=False)
    for name in ("src", "assets", "third-party", "tests"):
        shutil.copytree(ROOT / name, folder / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    notices = folder / "third-party/CI-BUILD-NOTICES.txt"
    distributions = sorted(importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower())
    notices.write_text("Python " + sys.version + "\n\n" + "\n".join(
        f"{dist.metadata['Name']} {dist.version}" for dist in distributions), encoding="utf-8")
    # Include licenses from the actual build environment as dependencies evolve.
    for dist in distributions:
        for entry in dist.files or []:
            if "licenses" in entry.parts or entry.name.upper().startswith(("LICENSE", "COPYING")):
                origin = Path(dist.locate_file(entry))
                if origin.is_file() and origin.suffix not in (".py", ".pyc"):
                    target = folder / "third-party/ci" / dist.metadata["Name"] / str(entry).replace("..", "_")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(origin, target)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, folder / "third-party/Python-LICENSE.txt")
    for name in ("README.md", "DOGRULAMA.txt", "requirements.txt", "build.ps1", "KurtLauncher.spec",
                 "Baslat.cmd", "sign_release.py", "GUNCELLEME-YAYINLAMA.md"):
        shutil.copy2(ROOT / name, folder / name)
    shutil.copy2(ROOT / "dist/KurtLauncher.exe", folder / "KurtLauncher.exe")
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    target = output / f"KurtLauncher-v{current}-Windows.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_symlink():
                raise ValueError("Links cannot be distributed")
            if path.is_file():
                archive.write(path, "KurtLauncher/" + path.relative_to(folder).as_posix())
    print("Clean Windows ZIP:", target.name, "SHA256:", sha256(target))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=("assets", "package"))
    args = parser.parse_args()
    assets() if args.step == "assets" else package()

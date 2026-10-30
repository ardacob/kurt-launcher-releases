"""Install the launcher once per Windows user; game data lives beside, never inside, app."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile

from core import APP_VERSION, LauncherError, atomic_json
from data_paths import location_file
from snapshots import digest, regular_files
from updater import TOP_LEVEL, version_tuple


def app_folder():
    return (location_file().parent / "app").resolve()


def installed_state():
    path = location_file().parent / "installation.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        executable = app_folder() / "KurtLauncher.exe"
        if state.get("format") == 1 and state.get("product") == "KurtLauncher" and executable.is_file():
            version_tuple(state["version"])
            if digest(executable) == state["sha512"]:
                return state
    except (OSError, ValueError, KeyError, TypeError, LauncherError):
        pass
    return None


def prepare_managed_install(updater, *, progress=lambda *args: None):
    """Return False if already installed; otherwise start a helper and let this process exit."""
    if not getattr(sys, "frozen", False):
        return False
    executable = Path(sys.executable).resolve()
    destination = app_folder()
    if executable.parent == destination:
        return False
    updates = updater.store.root / "updates"
    updates.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="verified-install-", dir=updates))
    state = installed_state()
    redirect = state is not None and version_tuple(state["version"]) >= version_tuple(APP_VERSION)
    try:
        records = {}
        if not redirect:
            files = []
            for child in executable.parent.iterdir():
                if child.name not in TOP_LEVEL:
                    continue
                if child.is_symlink():
                    raise LauncherError("Kurulum kaynağı bağlantı içeremez.")
                if child.is_dir():
                    files.extend(regular_files(child))
                elif child.is_file():
                    files.append(child)
            files = [p for p in files if "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo")]
            for index, origin in enumerate(files, 1):
                name = origin.relative_to(executable.parent).as_posix()
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                expected = digest(origin)
                shutil.copy2(origin, target)
                if digest(target) != expected:
                    raise LauncherError("Launcher kurulum dosyası doğrulanamadı.")
                records[name] = {"size": target.stat().st_size, "sha512": expected}
                progress("Launcher ortak uygulama klasörüne kuruluyor…", index, len(files))
            if "KurtLauncher.exe" not in records:
                raise LauncherError("Launcher çalıştırıcısı bulunamadı.")
        info = {"format": 1, "product": "KurtLauncher", "platform": "windows-x64",
                "version": state["version"] if redirect else APP_VERSION, "files": records}
        atomic_json(stage / "verified.json", info)
        updater.launch_helper(stage, installation=destination, obsolete=executable,
                              redirect_hash=state["sha512"] if redirect else None)
        return True
    except Exception:
        if stage.is_dir() and stage.parent == updates and stage.name.startswith("verified-install-"):
            shutil.rmtree(stage)
        raise

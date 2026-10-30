"""One remembered game archive across launcher versions; never move game files."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


class DataLocationError(Exception):
    pass


class DataChoiceRequired(DataLocationError):
    def __init__(self, candidates):
        super().__init__("Birden fazla eski oyun klasörü bulundu. Kullanacağınız klasörü seçin.")
        self.candidates = candidates


class DataFolderMissing(DataLocationError):
    def __init__(self, folder):
        super().__init__("Önceki oyun klasörüne ulaşılamıyor. Diskin bağlı olduğunu kontrol edin veya eski oyun klasörünüzü seçin.")
        self.folder = folder


def location_file():
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData/Local"
    return base / "KurtLauncher/data-location.json"


def has_game_data(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return False
    if any((folder / name).is_file() for name in ("profiles.json", "servers.json", "account.json", "settings.json")):
        return True
    for name in ("instances", "servers", "minecraft"):
        directory = folder / name
        if directory.is_dir() and next(directory.iterdir(), None) is not None:
            return True
    return False


def selected_data_folder(folder):
    """Accept either the old launcher's folder or its data subfolder."""
    folder = Path(folder).resolve()
    if has_game_data(folder / "data"):
        return folder / "data"
    if has_game_data(folder):
        return folder
    raise DataLocationError("Bu klasörde eski Kurt Launcher oyun verileri bulunamadı. Eski launcher klasörünü veya içindeki data klasörünü seçin.")


def remember_data_folder(folder):
    folder = Path(folder).resolve()
    if not folder.is_dir() or folder.parent == folder:
        raise DataLocationError("Oyun klasörü bulunamadı.")
    target = location_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"format": 1, "data_directory": str(folder)}, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def remembered_data_folder():
    target = location_file()
    if not target.exists():
        return None
    try:
        if target.stat().st_size > 65536:
            raise ValueError("oversize")
        value = json.loads(target.read_text(encoding="utf-8"))
        folder = Path(value["data_directory"])
        if value.get("format") != 1 or not folder.is_absolute() or folder.parent == folder:
            raise ValueError("path")
    except (OSError, ValueError, TypeError, KeyError):
        raise DataLocationError("Kayıtlı oyun klasörü bilgisi okunamadı. Ayarlardan eski oyun klasörünü yeniden seçin.") from None
    if not folder.is_dir():
        raise DataFolderMissing(folder)
    return folder.resolve()


def legacy_candidates(base):
    """Only nearby Kurt Launcher folders; no drive-wide or home-directory scan."""
    base = Path(base).resolve()
    found = set()
    for parent in (base.parent, base.parent.parent):
        if parent == parent.parent:
            continue
        try:
            children = sorted(parent.iterdir(), key=lambda p: p.name.casefold())[:256]
        except OSError:
            continue
        for child in children:
            if not child.name.casefold().startswith(("kurtlauncher", "kurt-launcher")) or not child.is_dir():
                continue
            for folder in (child / "data", child / "KurtLauncher/data"):
                try:
                    if has_game_data(folder):
                        found.add(folder.resolve())
                except OSError:
                    continue
    return sorted(found, key=lambda p: str(p).casefold())


def resolve_data_folder(base):
    override = os.environ.get("KURT_DATA_DIR")
    if override:
        return Path(override).resolve()
    remembered = remembered_data_folder()
    if remembered is not None:
        return remembered
    adjacent = Path(base).resolve() / "data"
    if has_game_data(adjacent):
        return adjacent
    candidates = legacy_candidates(base)
    if len(candidates) > 1:
        raise DataChoiceRequired(candidates)
    if candidates:
        return candidates[0]
    return location_file().parent / "data"

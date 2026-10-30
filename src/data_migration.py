"""Verified, atomic copy of legacy game data into the user's shared archive."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

from data_paths import DataLocationError, common_data_folder, has_game_data

RECEIPT = ".migration-receipt.json"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha512").hexdigest()


def files_in(folder):
    files = {}
    for parent, directories, names in os.walk(folder, followlinks=False):
        parent = Path(parent)
        if parent == folder:
            directories[:] = [n for n in directories if n != "updates"]
        for name in directories + names:
            path = parent / name
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
            if path.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
                raise DataLocationError("Bağlantı/junction içeren oyun klasörü otomatik aktarılamaz: " + name)
        for name in names:
            if name in ("launcher.lock", "session.lock", RECEIPT):
                continue
            path = parent / name
            if not path.is_file():
                raise DataLocationError("Oyun klasöründe normal olmayan dosya bulundu.")
            files[path.relative_to(folder).as_posix()] = path
    return files


@contextmanager
def archive_locks(source, destination, *, own_launcher_lock=False):
    from PySide6.QtCore import QLockFile
    destination.parent.mkdir(parents=True, exist_ok=True)
    transfer_lock = QLockFile(str(destination.parent / "data-migration.lock"))
    if not transfer_lock.tryLock(0):
        raise DataLocationError("Başka bir veri aktarımı sürüyor. Tamamlanmasını bekleyin.")
    launcher_lock = None
    try:
        if own_launcher_lock:
            try:
                owner = int((source / "launcher.lock").read_text(encoding="utf-8").splitlines()[0])
            except (OSError, ValueError, IndexError):
                owner = None
            if owner != os.getpid():
                raise DataLocationError("Oyun klasörünün kullanım durumu doğrulanamadı.")
        else:
            launcher_lock = QLockFile(str(source / "launcher.lock"))
            if not launcher_lock.tryLock(0):
                raise DataLocationError("Aktarım için önce eski launcher'ı, Minecraft'ı ve sunucuyu kapatın.")
        with ExitStack() as stack:
            for path in source.rglob("session.lock"):
                if not path.is_file():
                    continue
                try:
                    stream = stack.enter_context(path.open("r+b"))
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.lockf(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise DataLocationError("Minecraft veya sunucu dünyayı kullanıyor. Kaydedilip kapanmasını bekleyin.") from None
            yield
    finally:
        if launcher_lock is not None:
            launcher_lock.unlock()
        transfer_lock.unlock()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def reuse_verified_copy(source, destination, files, progress):
    """Recover a completed copy if the previous process stopped before saving its location."""
    receipt = destination / RECEIPT
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
        if data["format"] != 1 or Path(data["source"]).resolve() != source:
            return False
        if set(data["files"]) != set(files) or set(files_in(destination)) != set(files):
            return False
        for index, (name, path) in enumerate(files.items(), 1):
            expected = data["files"][name]
            if digest(path) != data.get("source_files", data["files"])[name] or digest(destination / name) != expected:
                return False
            progress("Önceki aktarım doğrulanıyor…", index, len(files))
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def ensure_shared_data(source, *, progress=lambda *args: None, own_launcher_lock=False):
    source = Path(source).resolve()
    destination = common_data_folder()
    if source == destination:
        destination.mkdir(parents=True, exist_ok=True)
        return destination
    if not source.is_dir():
        raise DataLocationError("Eski oyun klasörü bulunamadı. Boş bir arşiv oluşturulmadı; eski klasörü veya bağlı diski kontrol edin.")
    if (source.parent == source or destination.is_relative_to(source)
            or source.is_relative_to(destination)):
        raise DataLocationError("Eski ve ortak oyun klasörleri iç içe olamaz.")
    files_in(source)  # Reject links before looking for world locks.
    with archive_locks(source, destination, own_launcher_lock=own_launcher_lock):
        files = files_in(source)
        if has_game_data(destination):
            if reuse_verified_copy(source, destination, files, progress):
                return destination
            raise DataLocationError("Ortak oyun klasöründe farklı bir arşiv var. İki arşiv de korundu; ortak klasörü seçin veya önce mevcut arşivi yedekleyin.")
        total = sum(path.stat().st_size for path in files.values())
        if shutil.disk_usage(destination.parent).free < total + 128 * 1024 * 1024:
            raise DataLocationError("Ortak oyun klasörüne aktarım için yeterli boş disk alanı yok. Eski veriler korunuyor.")
        stage = Path(tempfile.mkdtemp(prefix=".data-migration-", dir=destination.parent))
        committed = False
        try:
            hashes, signatures = {}, {}
            copied = 0
            for name, origin in sorted(files.items()):
                before = origin.stat()
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                hasher = hashlib.sha512()
                with origin.open("rb") as inp, target.open("wb") as out:
                    while block := inp.read(1024 * 1024):
                        out.write(block)
                        hasher.update(block)
                        copied += len(block)
                        progress("Oyunlar, modlar ve dünyalar ortak klasöre kopyalanıyor…", copied, max(total * 2, 1))
                after = origin.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise DataLocationError("Aktarım sırasında oyun dosyaları değişti. Eski veriler korundu; oyunu kapatıp tekrar deneyin.")
                shutil.copystat(origin, target)
                hashes[name] = hasher.hexdigest()
                signatures[name] = (after.st_size, after.st_mtime_ns)
            if set(files_in(source)) != set(files):
                raise DataLocationError("Aktarım sırasında oyun klasörü değişti. Eski veriler korunuyor.")
            checked = 0
            for name, origin in files.items():
                current = origin.stat()
                if (current.st_size, current.st_mtime_ns) != signatures[name] or digest(origin) != hashes[name] or digest(stage / name) != hashes[name]:
                    raise DataLocationError("Kopyalanan dosya doğrulanamadı. Eski oyun arşivi kullanılmaya devam edecek.")
                checked += current.st_size
                progress("Kopyalanan oyun dosyaları doğrulanıyor…", total + checked, max(total * 2, 1))
            # A custom Java executable inside the old archive must follow the copied runtime.
            source_hashes = dict(hashes)
            settings_path = stage / "settings.json"
            if settings_path.is_file():
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
                custom = settings.get("java", "")
                if custom and Path(custom).is_absolute() and Path(custom).resolve().is_relative_to(source):
                    settings["java"] = str(destination / Path(custom).resolve().relative_to(source))
                    write_json(settings_path, settings)
                    hashes["settings.json"] = digest(settings_path)
            write_json(stage / RECEIPT, {"format": 1, "source": str(source), "files": hashes,
                                       "source_files": source_hashes, "bytes": total})
            if destination.exists():
                # Only empty directories may be replaced here; never remove a second archive.
                if any(path.is_file() for path in destination.rglob("*")):
                    raise DataLocationError("Ortak klasör aktarım sırasında değişti. Arşivler korunuyor.")
                for path in sorted(destination.rglob("*"), reverse=True):
                    path.rmdir()
                destination.rmdir()
            stage.replace(destination)
            committed = True
            progress("Oyunların ortak klasöre aktarımı tamamlandı.", 1, 1)
            return destination
        finally:
            if not committed and stage.is_dir() and stage.parent == destination.parent and stage.name.startswith(".data-migration-"):
                shutil.rmtree(stage)

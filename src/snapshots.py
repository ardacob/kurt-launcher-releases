"""Local, verified profile snapshots. Never snapshot a running game/server."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from core import LauncherError, Task, atomic_json, safe_file


def digest(path, algorithm="sha512"):
    result = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or len(value) > 600:
        raise LauncherError("Arşivde geçersiz dosya yolu var.")
    parts = PurePosixPath(value)
    if parts.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise LauncherError("Arşiv profil klasörünün dışına çıkamaz.")
    for part in parts.parts:
        safe_file(part)
    return parts


def regular_files(directory):
    directory = Path(directory).resolve()
    for parent, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs + files:
            path = Path(parent) / name
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
            if path.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
                raise LauncherError("Bağlantı/junction içeren klasör işlenemez: " + name)
            if not path.resolve().is_relative_to(directory):
                raise LauncherError("Profil dışına yönelen dosya bulundu.")
        for name in files:
            yield Path(parent) / name


class Snapshots:
    def __init__(self, store, guard=lambda profile: None):
        self.store, self.guard = store, guard

    def folder(self, profile):
        self.store.directory(profile)  # validates ID
        folder = self.store.root / "backups" / profile["id"]
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def list(self, profile):
        results = []
        for path in self.folder(profile).glob("*.zip"):
            try:
                with zipfile.ZipFile(path) as archive:
                    info = archive.getinfo("snapshot.json")
                    if info.file_size > 2 * 1024 * 1024:
                        continue
                    meta = json.loads(archive.read(info))
                    if meta.get("profile", {}).get("id") == profile["id"]:
                        results.append({**meta, "path": str(path), "size": path.stat().st_size})
            except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                continue
        return sorted(results, key=lambda x: x.get("created", ""), reverse=True)

    def create(self, profile, task=None, reason="Elle yedekleme", automatic=False):
        task = task or Task()
        self.guard(profile)
        directory = self.store.directory(profile)
        files = [p for p in regular_files(directory) if p.name != "session.lock"]
        if automatic and not files:
            return None
        total = sum(p.stat().st_size for p in files)
        folder = self.folder(profile)
        if shutil.disk_usage(folder).free < total + 64 * 1024 * 1024:
            raise LauncherError("Yedekleme için yeterli boş disk alanı yok. Değişiklik yapılmadı.")
        meta = {"format": 1, "created": datetime.now(timezone.utc).isoformat(),
                "reason": reason, "automatic": automatic, "profile": dict(profile), "files": {}}
        target = folder / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8] + ".zip")
        temporary = target.with_suffix(".tmp")
        try:
            task.status("Yedek alınıyor: " + profile["name"])
            task.set_max(len(files))
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
                for i, path in enumerate(files, 1):
                    task.check()
                    name = path.relative_to(directory).as_posix()
                    relative_path(name)
                    meta["files"][name] = digest(path)
                    archive.write(path, "files/" + name)
                    task.progress(i)
                archive.writestr("snapshot.json", json.dumps(meta, ensure_ascii=False))
            task.check()
            os.replace(temporary, target)
            if automatic:
                keep = max(1, min(20, int(self.store.settings.get("backup_keep", 5))))
                for old in [v for v in self.list(profile) if v.get("automatic")][keep:]:
                    Path(old["path"]).unlink(missing_ok=True)
            return str(target)
        finally:
            temporary.unlink(missing_ok=True)

    def before_change(self, profile, task=None, reason="Değişiklik öncesi"):
        self.guard(profile)
        if self.store.settings.get("auto_backup", True):
            return self.create(profile, task, reason, automatic=True)

    def restore(self, profile, source, task):
        self.guard(profile)
        source = Path(source).resolve()
        if not source.is_relative_to(self.folder(profile).resolve()) or source.suffix != ".zip":
            raise LauncherError("Bu profile ait bir yedek seçin.")
        directory = self.store.directory(profile)
        stage = Path(tempfile.mkdtemp(prefix=".restore-", dir=directory.parent))
        old_directory = directory.with_name(".previous-" + uuid.uuid4().hex)
        old_profile = dict(profile)
        moved = False
        try:
            with zipfile.ZipFile(source) as archive:
                if archive.getinfo("snapshot.json").file_size > 2 * 1024 * 1024:
                    raise LauncherError("Yedek kaydı çok büyük.")
                meta = json.loads(archive.read("snapshot.json"))
                if meta.get("format") != 1 or meta.get("profile", {}).get("id") != profile["id"]:
                    raise LauncherError("Yedek farklı bir profile ait.")
                entries = meta.get("files", {})
                if len(entries) > 100000 or sum(i.file_size for i in archive.infolist()) > shutil.disk_usage(stage).free - 64 * 1024 * 1024:
                    raise LauncherError("Yedeği açmak için yeterli disk alanı yok veya yedek çok büyük.")
                seen = set()
                task.status("Yedek doğrulanıyor ve hazırlanıyor…")
                task.set_max(len(entries))
                for i, (name, expected) in enumerate(entries.items(), 1):
                    task.check()
                    relative_path(name)
                    if name.casefold() in seen:
                        raise LauncherError("Yedekte yinelenen dosya yolu var.")
                    seen.add(name.casefold())
                    dest = stage.joinpath(*PurePosixPath(name).parts)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open("files/" + name) as inp, dest.open("wb") as out:
                        shutil.copyfileobj(inp, out, 1024 * 1024)
                    if digest(dest) != expected:
                        raise LauncherError("Yedek dosyası doğrulanamadı: " + name)
                    task.progress(i)
            # Always preserve the current state, even when automatic backups are off.
            self.create(profile, task, "Geri yükleme öncesi güvenlik yedeği")
            task.check()
            directory.rename(old_directory)
            moved = True
            try:
                stage.rename(directory)
                for key in ("version", "loader", "loader_version", "installed", "launch_jar", "java_component"):
                    if key in meta["profile"]:
                        profile[key] = meta["profile"][key]
                self.store.save()
            except Exception:
                if directory.exists():
                    shutil.rmtree(directory)
                old_directory.rename(directory)
                moved = False
                profile.clear()
                profile.update(old_profile)
                raise
            shutil.rmtree(old_directory)
            moved = False
            return "Yedek geri yüklendi. Önceki durum ayrıca yedeklendi."
        except (zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise LauncherError("Yedek okunamadı; mevcut profil korunuyor.") from exc
        finally:
            shutil.rmtree(stage, ignore_errors=True)
            # Never delete the only surviving original if a filesystem rollback fails.
            if moved and old_directory.exists() and not directory.exists():
                old_directory.rename(directory)

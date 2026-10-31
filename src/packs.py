"""Validated mrpack import/export and consent-based mod synchronisation."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
import requests
from core import LauncherError, Task, MODRINTH, atomic_json, safe_file, validate_jar
from snapshots import digest, relative_path, regular_files

PACK_LIMIT = 20 * 1024**3
HOSTS = {"cdn.modrinth.com", "github.com", "raw.githubusercontent.com", "gitlab.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
LOADER_KEYS = {"fabric-loader": "fabric", "forge": "forge", "neoforge": "neoforge", "quilt-loader": "quilt"}


def allowed_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise LauncherError("Paket indirme adresi izin verilen HTTPS kaynaklarından değil.")
    return url


def pack_path(path):
    parts = relative_path(path)
    if parts.parts[0] not in ("mods", "config", "resourcepacks", "shaderpacks", "defaultconfigs", "kubejs", "scripts") and path != "options.txt":
        raise LauncherError("Paket bu dosya yolunu kullanamaz: " + path)
    if Path(path).suffix.lower() in (".exe", ".dll", ".bat", ".cmd", ".ps1", ".lnk", ".com", ".scr", ".vbs"):
        raise LauncherError("Pakette desteklenmeyen çalıştırılabilir dosya var: " + path)
    return parts


def download_file(api, record, target, task):
    urls = record.get("downloads", [])
    expected = record.get("hashes", {}).get("sha512", "")
    if not re.fullmatch(r"[a-fA-F0-9]{128}", expected) or not urls or len(urls) > 10:
        raise LauncherError("Dosyanın SHA-512 kaydı veya indirme adresi eksik.")
    for url in urls:
        allowed_url(url)
    from downloads import download
    cache = getattr(api, 'download_cache', None)
    if not isinstance(cache, (str, os.PathLike)):
        cache = target.parent / '.kurt-downloads'
    last = None
    for url in urls:
        task.check()
        try:
            return download(api.session, url, target, task,
                cache=cache,
                expected=expected, size=record.get('fileSize', 0),
                validator=validate_jar if target.suffix.lower() == '.jar' else None,
                allow_url=allowed_url, limit=PACK_LIMIT)
        except LauncherError as exc:
            last = exc
    raise last


def lock_entry(version, file):
    return {"name": version.get("name", file), "file": file, "version_id": version["id"],
            "version_number": version.get("version_number", ""), "game_versions": version.get("game_versions", []),
            "loaders": version.get("loaders", []),
            "requires": [d for d in version.get("dependencies", []) if d.get("dependency_type") == "required"],
            "incompatible": [d for d in version.get("dependencies", []) if d.get("dependency_type") == "incompatible"]}


class Packs:
    def __init__(self, launcher):
        self.launcher, self.store, self.api = launcher, launcher.store, launcher.api

    def inspect(self, source):
        try:
            with zipfile.ZipFile(source) as archive:
                all_files = archive.infolist()
                if len(all_files) > 50000 or sum(i.file_size for i in all_files) > PACK_LIMIT:
                    raise LauncherError("Paket dosya/boyut sınırını aşıyor.")
                if len({i.filename.casefold() for i in all_files}) != len(all_files):
                    raise LauncherError("Pakette yinelenen arşiv yolu var.")
                for info in all_files:
                    if info.is_dir():
                        relative_path(info.filename.rstrip("/"))
                        continue
                    relative_path(info.filename)
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise LauncherError("Paket sembolik bağlantı içeremez.")
                entry = archive.getinfo("modrinth.index.json")
                if entry.file_size > 4 * 1024 * 1024:
                    raise LauncherError("Paket kaydı çok büyük.")
                index = json.loads(archive.read(entry))
                if index.get("formatVersion") != 1 or index.get("game") != "minecraft":
                    raise LauncherError("Bu mrpack sürümü desteklenmiyor.")
                deps = index.get("dependencies", {})
                if not deps.get("minecraft") or any(k not in {"minecraft", *LOADER_KEYS} for k in deps):
                    raise LauncherError("Paketin oyun/yükleyici bağımlılıkları desteklenmiyor.")
                if len([k for k in LOADER_KEYS if k in deps]) > 1:
                    raise LauncherError("Pakette birden fazla mod yükleyicisi var.")
                for value in deps.values():
                    safe_file(value)
                files = index.get("files", [])
                if not isinstance(files, list) or len(files) > 10000:
                    raise LauncherError("Paket dosya listesi geçersiz.")
                seen = set()
                total = 0
                for record in files:
                    path = str(record["path"])
                    pack_path(path)
                    if path.casefold() in seen:
                        raise LauncherError("Pakette aynı hedef dosya iki kez var.")
                    seen.add(path.casefold())
                    size = record.get("fileSize", 0)
                    if type(size) is not int or size < 0:
                        raise LauncherError("Paket dosya boyutu geçersiz.")
                    total += size
                    for key, length in (("sha512", 128), ("sha1", 40)):
                        if not re.fullmatch(r"[a-fA-F0-9]{" + str(length) + "}", record.get("hashes", {}).get(key, "")):
                            raise LauncherError("Pakette dosya doğrulama bilgisi eksik.")
                    if not record.get("downloads"):
                        raise LauncherError("Paket indirme adresi eksik.")
                    for url in record["downloads"]:
                        allowed_url(url)
                    if any(v not in ("required", "optional", "unsupported") for v in record.get("env", {}).values()):
                        raise LauncherError("Paket ortam tanımı geçersiz.")
                if total > PACK_LIMIT:
                    raise LauncherError("Paket indirme boyutu çok büyük.")
                for info in all_files:
                    if not info.is_dir() and info.filename.startswith(("overrides/", "client-overrides/", "server-overrides/")):
                        pack_path(info.filename.split("/", 1)[1])
                loader_key = next((k for k in LOADER_KEYS if k in deps), None)
                return {"index": index, "version": deps["minecraft"], "loader": LOADER_KEYS.get(loader_key, "vanilla"),
                        "loader_version": deps.get(loader_key), "size": total, "count": len(files),
                        "unpacked_size": total + sum(i.file_size for i in all_files),
                        "source_hash": digest(source), "name": str(index.get("name", "Mod paketi"))[:64]}
        except (KeyError, ValueError, TypeError, zipfile.BadZipFile) as exc:
            raise LauncherError("Mod paketi okunamadı veya biçimi geçersiz.") from exc

    def import_pack(self, source, task, preview=None, optional=False):
        self.launcher.ensure_idle()
        info = self.inspect(source)
        if preview and info["source_hash"] != preview["source_hash"]:
            raise LauncherError("Paket önizlemeden sonra değişmiş. Tekrar seçin.")
        manifest, _ = self.launcher.versions()
        if info["version"] not in {v["id"] for v in manifest["versions"]}:
            raise LauncherError("Paketin Minecraft sürümü resmî listede yok.")
        parent = self.store.root / "instances"
        parent.mkdir(exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".pack-", dir=parent))
        profile = {"id": uuid.uuid4().hex, "name": info["name"] or "Mod paketi", "version": info["version"],
                   "loader": info["loader"], "loader_version": info["loader_version"], "installed": None}
        profile['modpack'] = {'name':info['name'], 'source_sha512':info['source_hash']}
        lock = {}
        destination = parent / profile["id"]
        try:
            if shutil.disk_usage(stage).free < info["unpacked_size"] + 256 * 1024 * 1024:
                raise LauncherError("Paket kurulumu için boş disk alanı yetersiz.")
            records = [r for r in info["index"]["files"] if r.get("env", {}).get("client") != "unsupported"
                       and (optional or r.get("env", {}).get("client") != "optional")]
            task.transfer.pending = [r["path"] for r in records]
            for i, record in enumerate(records, 1):
                task.transfer.queue = f"Dosya {i}/{len(records)}"
                download_file(self.api, record, stage / record["path"], task)
                task.transfer.pending.pop(0)
            with zipfile.ZipFile(source) as archive:
                for layer in ("overrides/", "client-overrides/"):
                    for entry in archive.infolist():
                        if entry.filename.startswith(layer) and not entry.is_dir():
                            task.check()
                            name = entry.filename[len(layer):]
                            pack_path(name)
                            if any(name.casefold() == r["path"].casefold() for r in records):
                                raise LauncherError("Paket doğrulanmış indirmeyi override ile değiştiremez: " + name)
                            dest = stage / name
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with archive.open(entry) as inp, dest.open("wb") as out:
                                shutil.copyfileobj(inp, out)
            for path in (stage / "mods").glob("*.jar") if (stage / "mods").exists() else []:
                validate_jar(path)
                task.status("Mod kaydı tanınıyor: " + path.name)
                try:
                    version = self.api.get(MODRINTH + "/version_file/" + digest(path), algorithm="sha512")
                except LauncherError:
                    # Valid third-party/override JARs remain local, explicitly unverified mods.
                    pass
                else:
                    if profile['loader'] not in version.get('loaders', []):
                        raise LauncherError("Pakette profile uyumsuz bir mod var: " + path.name)
                    entry = lock_entry(version, path.name)
                    entry['pinned'] = True
                    entry['pack_managed'] = True
                    if (profile['version'] not in version.get('game_versions', [])
                            or version.get('client_side') == 'unsupported'
                            or version.get('environment') in ('server_only','dedicated_server_only')):
                        entry['pack_compatibility_note'] = 'Paket yapımcısının sabit seçimi; tekil modun oyun/ortam etiketi paket tanımından farklı.'
                    lock[version["project_id"]] = entry
            task.check()
            atomic_json(stage / "mods.lock.json", lock)
            stage.rename(destination)
            self.store.profiles.append(profile)
            try:
                self.store.save()
            except Exception:
                self.store.profiles.remove(profile)
                shutil.rmtree(destination, ignore_errors=True)
                raise
            return profile
        finally:
            task.transfer.queue = ""
            task.transfer.pending = []
            shutil.rmtree(stage, ignore_errors=True)

    def describe_mods(self, profile, task):
        """No JAR redistribution: only public hashes/download metadata are shared."""
        result = []
        paths = sorted(self.store.mods(profile).glob("*.jar"))
        lock = {v["file"]: v for v in self.store.mod_lock(profile).values()}
        for i, path in enumerate(paths, 1):
            task.status(f"Mod listesi hazırlanıyor: {i}/{len(paths)} · {path.name}")
            h512, h1 = digest(path), digest(path, "sha1")
            env = {"client": "required", "server": "required"}
            with zipfile.ZipFile(path) as jar:
                if "fabric.mod.json" in jar.namelist():
                    side = json.loads(jar.read("fabric.mod.json")).get("environment")
                    if side == "client": env["server"] = "unsupported"
                    if side == "server": env["client"] = "unsupported"
            record = {"path": "mods/" + path.name, "hashes": {"sha512": h512, "sha1": h1},
                      "fileSize": path.stat().st_size, "env": env, "downloads": []}
            try:
                entry = lock.get(path.name)
                version = self.api.get(MODRINTH + "/version/" + entry["version_id"]) if entry else self.api.get(MODRINTH + "/version_file/" + h512, algorithm="sha512")
                file = next((f for f in version["files"] if f.get("hashes", {}).get("sha512") == h512), None)
                if file:
                    record["downloads"] = [allowed_url(file["url"])]
            except LauncherError:
                pass
            result.append(record)
        return {"format": 1, "version": profile["version"], "loader": profile["loader"],
                "loader_version": profile.get("loader_version"), "files": result}

    def export(self, profile, target, task, config=False):
        self.launcher.ensure_profile_idle(profile)
        metadata = self.describe_mods(profile, task)
        missing = [r["path"] for r in metadata["files"] if not r["downloads"]]
        if missing:
            raise LauncherError("Paylaşılabilir kaynağı bulunmayan yerel/değiştirilmiş modlar var. Bunları kapatın veya izinli kaynaklarını kullanın: " + ", ".join(missing[:8]))
        deps = {"minecraft": profile["version"]}
        if profile["loader"] != "vanilla":
            key = next(k for k, v in LOADER_KEYS.items() if v == profile["loader"])
            if not profile.get("loader_version"):
                raise LauncherError("Önce Kur / onar ile yükleyici sürümünü sabitleyin.")
            deps[key] = profile["loader_version"]
        index = {"formatVersion": 1, "game": "minecraft", "versionId": uuid.uuid4().hex,
                 "name": profile["name"], "summary": "Kurt Launcher ile paylaşılan profil", "dependencies": deps, "files": metadata["files"]}
        target = Path(target)
        if target.resolve().is_relative_to(self.store.directory(profile)):
            raise LauncherError("Paket dosyasını profil klasörü dışında kaydedin.")
        temporary = target.with_suffix(".tmp")
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("modrinth.index.json", json.dumps(index, ensure_ascii=False))
                if config:
                    directory = self.store.directory(profile) / "config"
                    if directory.exists():
                        for path in regular_files(directory):
                            task.check()
                            name = "config/" + path.relative_to(directory).as_posix()
                            pack_path(name)
                            archive.write(path, "overrides/" + name)
            task.check()
            os.replace(temporary, target)
            return "Mod paketi kaydedildi: " + str(target)
        finally:
            temporary.unlink(missing_ok=True)

    def compare(self, profile, description):
        if description.get("format") != 1 or not isinstance(description.get("files"), list) or len(description["files"]) > 1000:
            raise LauncherError("Sunucu mod listesi geçersiz.")
        rows, expected_names = [], set()
        same_profile = profile["version"] == description.get("version") and profile["loader"] == description.get("loader") and (
            not description.get("loader_version") or profile.get("loader_version") == description.get("loader_version"))
        local = {digest(p): p.name for p in self.store.mods(profile).glob("*.jar")}
        for record in description["files"]:
            if record.get("env", {}).get("client") == "unsupported":
                continue
            path = str(record.get("path", ""))
            parts = pack_path(path)
            if len(parts.parts) != 2 or parts.parts[0] != "mods" or not path.endswith(".jar"):
                raise LauncherError("Sunucu listesinde geçersiz mod yolu var.")
            h512 = record.get("hashes", {}).get("sha512", "")
            if not re.fullmatch(r"[a-fA-F0-9]{128}", h512) or path.casefold() in expected_names:
                raise LauncherError("Sunucu mod listesi doğrulanamadı.")
            expected_names.add(path.casefold())
            for url in record.get("downloads", []): allowed_url(url)
            rows.append({"file": parts.name, "state": "Eşleşiyor" if h512 in local else "Eksik / farklı sürüm",
                         "record": record, "installable": bool(record.get("downloads"))})
        expected_hashes = {r["record"]["hashes"]["sha512"] for r in rows}
        extras = [name for key, name in local.items() if key not in expected_hashes]
        return {"profile_matches": same_profile, "rows": rows, "extras": extras}

    def sync(self, profile, description, task):
        self.launcher.ensure_profile_idle(profile)
        comparison = self.compare(profile, description)
        if not comparison["profile_matches"]:
            raise LauncherError("Önce sunucuyla aynı Minecraft/yükleyici sürümünde profil oluşturun.")
        missing = [r for r in comparison["rows"] if r["state"] != "Eşleşiyor"]
        if any(not r["installable"] for r in missing):
            raise LauncherError("Bazı yerel sunucu modları otomatik indirilemiyor. İzinli kaynaklarını sunucu sahibinden isteyin.")
        directory = self.store.mods(profile)
        stage = Path(tempfile.mkdtemp(prefix=".sync-", dir=directory.parent))
        try:
            original_lock = self.store.mod_lock(profile)
            new_lock = copy.deepcopy(original_lock)
            replacements = {}
            task.transfer.pending = [r["file"] for r in missing]
            for i, row in enumerate(missing, 1):
                task.transfer.queue = f"Mod {i}/{len(missing)}"
                download_file(self.api, row["record"], stage / row["file"], task)
                task.transfer.pending.pop(0)
                try:
                    version = self.api.get(MODRINTH + "/version_file/" + row["record"]["hashes"]["sha512"], algorithm="sha512")
                except LauncherError:
                    version = None
                if version:
                    if not self.launcher.mods.compatible(version, profile):
                        raise LauncherError("Sunucu listesindeki mod bu profile uygun değil: " + row["file"])
                    pid = version["project_id"]
                    old_entry = original_lock.get(pid)
                    if old_entry: replacements[old_entry["file"]] = row["file"]
                    new_lock[pid] = lock_entry(version, row["file"])
            self.launcher.snapshots.before_change(profile, task, "Sunucuyla mod eşleştirme öncesi")
            # Transaction includes unchanged files; rollback is directory-based.
            replacement = stage / "replacement"
            shutil.copytree(directory, replacement)
            for old_name, new_name in replacements.items():
                safe_file(old_name)
                if old_name != new_name: (replacement / old_name).unlink(missing_ok=True)
            for row in missing:
                dest = replacement / row["file"]
                # Never guess which differently named JAR is the old version.
                shutil.copy2(stage / row["file"], dest)
            task.check()
            old = directory.with_name(".sync-old-" + uuid.uuid4().hex)
            directory.rename(old)
            try:
                replacement.rename(directory)
                atomic_json(directory.parent / "mods.lock.json", new_lock)
            except Exception:
                shutil.rmtree(directory, ignore_errors=True)
                old.rename(directory)
                atomic_json(directory.parent / "mods.lock.json", original_lock)
                raise
            shutil.rmtree(old)
            return f"{len(missing)} mod kuruldu. Fazladan/farklı adlı eski modları uyumluluk ekranından kontrol edin."
        finally:
            task.transfer.queue = ""
            task.transfer.pending = []
            shutil.rmtree(stage, ignore_errors=True)


class ModUpdates:
    def __init__(self, launcher):
        self.launcher, self.store = launcher, launcher.store

    def scan(self, profile, task):
        rows = []
        for pid, entry in self.store.mod_lock(profile).items():
            task.status("Güncelleme kontrolü: " + entry["name"])
            version = self.launcher.mods.choose(pid, profile)
            if version["id"] != entry["version_id"]:
                installed = self.launcher.api.get(MODRINTH + "/version/" + entry["version_id"])
                if version.get("date_published", "") <= installed.get("date_published", ""):
                    continue
                rows.append({"project_id": pid, "old": copy.deepcopy(entry), "new": version,
                             "pinned": bool(entry.get("pinned")), "profile_id": profile["id"]})
        return rows

    def pin(self, profile, filename):
        lock = self.store.mod_lock(profile)
        entry = next((v for v in lock.values() if v["file"] == filename.removesuffix(".disabled")), None)
        if not entry:
            raise LauncherError("Bu yerel modun Modrinth kaydı yok.")
        entry["pinned"] = not entry.get("pinned", False)
        atomic_json(self.store.directory(profile) / "mods.lock.json", lock)
        return entry["pinned"]

    def apply(self, profile, rows, task):
        self.launcher.ensure_profile_idle(profile)
        current = self.store.mod_lock(profile)
        chosen = [r for r in rows if not r["pinned"]]
        if not chosen:
            return "Güncellenecek seçili mod yok."
        for row in chosen:
            pid = row["project_id"]
            if row["profile_id"] != profile["id"] or current.get(pid) != row["old"]:
                raise LauncherError("Mod listesi değişmiş. Güncellemeleri yeniden kontrol edin.")
            if not (self.store.mods(profile) / row["old"]["file"]).is_file():
                raise LauncherError("Kapalı/eksik modu güncellemeden önce etkinleştirin.")
        self.launcher.snapshots.before_change(profile, task, "Mod güncelleme öncesi")
        # Resolve changes against a temporary isolated profile, including all other mods.
        shadow = {**profile, "id": uuid.uuid4().hex}
        shadow_dir = self.store.directory(shadow)
        try:
            shutil.copytree(self.store.mods(profile), self.store.mods(shadow), dirs_exist_ok=True)
            lock = copy.deepcopy(current)
            for row in chosen:
                (self.store.mods(shadow) / row["old"]["file"]).unlink()
                lock.pop(row["project_id"])
            atomic_json(shadow_dir / "mods.lock.json", lock)
            # Selected old roots are removed together, then their new dependencies are
            # resolved against the entire remaining profile. Any conflict aborts the batch.
            manager = self.launcher.mods
            original_backup = manager.before_change
            manager.before_change = lambda *args, **kwargs: None
            try:
                for row in chosen:
                    task.check()
                    manager.install(row["project_id"], shadow, task, row["new"]["id"])
                manager.validate_enabled(shadow)
                final_lock = self.store.mod_lock(shadow)
                for pid, old in current.items():
                    if pid in final_lock:
                        final_lock[pid]["pinned"] = old.get("pinned", False)
                atomic_json(shadow_dir / "mods.lock.json", final_lock)
            finally:
                manager.before_change = original_backup
            task.check()
            directory = self.store.directory(profile)
            rollback = directory / (".mods-old-" + uuid.uuid4().hex)
            original_lock = self.store.mod_lock(profile)
            (directory / "mods").rename(rollback)
            try:
                (shadow_dir / "mods").rename(directory / "mods")
                atomic_json(directory / "mods.lock.json", final_lock)
            except Exception:
                shutil.rmtree(directory / "mods", ignore_errors=True)
                rollback.rename(directory / "mods")
                atomic_json(directory / "mods.lock.json", original_lock)
                raise
            shutil.rmtree(rollback)
            return f"{len(chosen)} mod güncellendi. Önceki duruma Yedekler bölümünden dönebilirsiniz."
        finally:
            shutil.rmtree(shadow_dir, ignore_errors=True)

"""Kurt Launcher: isolated instances, official installs, verified mod downloads."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import requests
import minecraft_launcher_lib as mc

APP_VERSION = "0.4.1"
MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
MODRINTH = "https://api.modrinth.com/v2"
LOADERS = ("vanilla", "fabric", "forge", "neoforge", "quilt")


class LauncherError(Exception):
    pass


class Cancelled(LauncherError):
    pass


def offline_account(username: str):
    name = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", name):
        raise LauncherError("Kullanıcı adı 3–16 karakter olmalı; İngilizce harf, rakam ve _ kullanabilirsiniz.")
    # Java UUID.nameUUIDFromBytes: raw MD5 with UUID v3 and RFC 4122 variant bits.
    # uuid.uuid3(namespace, name) would produce a different, incompatible identity.
    player_id = uuid.UUID(bytes=hashlib.md5(("OfflinePlayer:" + name).encode("utf-8"), usedforsecurity=False).digest(), version=3)
    return {"name": name, "id": player_id.hex, "access_token": "0", "mode": "offline"}


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise LauncherError(f"Dosya okunamadı: {path.name}. Yedeğini alıp kontrol edin.") from exc


def safe_file(name: str) -> str:
    if (not name or name in (".", "..") or len(name) > 200
            or re.search(r'[\\/:*?"<>|\x00-\x1f]', name)
            or name.endswith((".", " "))
            or name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}):
        raise LauncherError("Geçersiz dosya adı: " + repr(name))
    return name


def validate_jar(path: Path):
    if not zipfile.is_zipfile(path):
        raise LauncherError(f"Geçerli bir JAR dosyası değil: {path.name}")
    with zipfile.ZipFile(path) as jar:
        if not any(n in jar.namelist() for n in (
                "fabric.mod.json", "quilt.mod.json", "META-INF/mods.toml",
                "META-INF/neoforge.mods.toml", "mcmod.info", "META-INF/MANIFEST.MF")):
            raise LauncherError("Dosyada bir mod/JAR tanımı bulunamadı.")


class Task:
    def __init__(self, notify=lambda message, value, maximum: None):
        self.cancel = threading.Event()
        self.notify = notify
        self.maximum = 0
        self.value = 0
        self._progress_lock = threading.RLock()
        self.message = "Hazırlanıyor…"
        from insights import TransferStats
        self.transfer = TransferStats()

    def check(self):
        if self.cancel.is_set():
            raise Cancelled("İşlem iptal edildi.")

    def status(self, text):
        self.check()
        with self._progress_lock:
            self.message = str(text)
            self.maximum, self.value = 0, 0
            self.transfer.begin(0, "items")
            self.notify(self.message, self.value, self.maximum)

    def library_status(self, text):
        self.check()
        phases = {"Download Libraries": "Kütüphaneler indiriliyor…",
                  "Download Assets": "Oyun varlıkları indiriliyor…",
                  "Install java runtime": "Java hazırlanıyor…",
                  "Installation complete": "Dosya doğrulaması tamamlandı.",
                  "Running installer": "Mod yükleyicisi kuruluyor…",
                  "Running fabric installer": "Fabric kuruluyor…",
                  "Running quilt installer": "Quilt kuruluyor…"}
        if text in phases:
            self.status(phases[text])
            return
        with self._progress_lock:
            if text.startswith("Download "):
                text = "İndiriliyor: " + text[len("Download "):]
            elif text.startswith("Running processor "):
                text = "Yükleyici bileşeni işleniyor: " + text[len("Running processor "):]
            self.message = str(text)
            # File-name callbacks must not reset the current batch percentage.
            # A standalone download after a completed batch has no known total.
            if self.maximum > 0 and self.value >= self.maximum:
                self.maximum, self.value = 0, 0
            self.notify(self.message, self.value, self.maximum)

    def progress(self, value):
        self.check()
        with self._progress_lock:
            self.value = max(0, int(value))
            self.transfer.current = self.value
            self.notify(self.message, self.value, self.maximum)

    def set_max(self, maximum):
        self.check()
        with self._progress_lock:
            self.maximum = max(0, int(maximum))
            self.value = 0
            self.transfer.begin(self.maximum, "items")
            self.notify(self.message, self.value, self.maximum)

    def begin_bytes(self, maximum=0):
        self.set_max(maximum)
        self.transfer.begin(self.maximum, "bytes")

    @property
    def callbacks(self):
        return {"setStatus": self.library_status, "setMax": self.set_max, "setProgress": self.progress}


class Api:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"KurtLauncher/{APP_VERSION} (desktop Minecraft launcher)"

    def get(self, url, **params):
        try:
            response = self.session.get(url, params=params, timeout=(15, 45))
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise LauncherError(f"Bağlantı kurulamadı ({urlparse(url).hostname}). İnterneti kontrol edin.") from exc

    def icon(self, url, directory: Path, task: Task):
        if not url or urlparse(url).scheme != "https" or urlparse(url).hostname != "cdn.modrinth.com":
            return None
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (hashlib.sha256(url.encode()).hexdigest() + ".img")
        if target.is_file() and 0 < target.stat().st_size <= 2 * 1024 * 1024:
            return str(target)
        temporary = None
        try:
            task.check()
            with self.session.get(url, stream=True, timeout=(10, 20)) as response:
                response.raise_for_status()
                if not response.headers.get("Content-Type", "").lower().startswith("image/"):
                    return None
                if int(response.headers.get("Content-Length", 0)) > 2 * 1024 * 1024:
                    return None
                fd, name = tempfile.mkstemp(dir=directory, suffix=".tmp")
                temporary = Path(name)
                size = 0
                with os.fdopen(fd, "wb") as stream:
                    for chunk in response.iter_content(65536):
                        task.check()
                        size += len(chunk)
                        if size > 2 * 1024 * 1024:
                            return None
                        stream.write(chunk)
                if size:
                    os.replace(temporary, target)
                    return str(target)
        except (requests.RequestException, OSError, ValueError):
            return None
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        return None

    def download(self, file, target: Path, task: Task):
        url = file["url"]
        if urlparse(url).scheme != "https" or urlparse(url).hostname != "cdn.modrinth.com":
            raise LauncherError("Mod indirme adresi Modrinth CDN adresi değil.")
        expected = file.get("hashes", {}).get("sha512")
        if not expected:
            raise LauncherError("Mod dosyası için SHA-512 doğrulaması bulunamadı.")
        digest = hashlib.sha512()
        size = 0
        task.status("İndiriliyor: " + file["filename"])
        task.begin_bytes(file.get("size", 0))
        try:
            with self.session.get(url, stream=True, timeout=(15, 45)) as response:
                response.raise_for_status()
                with target.open("wb") as output:
                    for chunk in response.iter_content(128 * 1024):
                        task.check()
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                        task.progress(size)
            if digest.hexdigest().lower() != expected.lower():
                raise LauncherError("Mod doğrulaması başarısız. Dosya kurulmadı.")
            validate_jar(target)
        except Exception:
            target.unlink(missing_ok=True)
            raise


class Store:
    def __init__(self, root: Path | None = None):
        base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        self.root = (root or Path(os.environ.get("KURT_DATA_DIR", str(base / "data")))).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.minecraft = self.root / "minecraft"
        self.minecraft.mkdir(exist_ok=True)
        self.settings = read_json(self.root / "settings.json", {"ram": 4096, "java": "", "client_id": ""})
        self.profiles = read_json(self.root / "profiles.json", [])
        self.account = read_json(self.root / "account.json", {})
        self.servers = read_json(self.root / "servers.json", [])
        self.settings.setdefault("login_mode", "microsoft" if self.account else "offline")
        self.settings.setdefault("offline_username", "")

    def save(self):
        atomic_json(self.root / "profiles.json", self.profiles)
        atomic_json(self.root / "settings.json", self.settings)
        atomic_json(self.root / "servers.json", self.servers)

    def directory(self, profile):
        if not re.fullmatch(r"[0-9a-f]{32}", profile["id"]):
            raise LauncherError("Geçersiz profil kimliği.")
        directory = self.root / ("servers" if profile.get("kind") == "server" else "instances") / profile["id"]
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def create(self, name, version, loader):
        if not name.strip() or len(name.strip()) > 64:
            raise LauncherError("Profil adı 1–64 karakter olmalı.")
        if loader not in LOADERS:
            raise LauncherError("Geçersiz mod yükleyici.")
        safe_file(version)
        profile = {"id": uuid.uuid4().hex, "name": name.strip(), "version": version,
                   "loader": loader, "loader_version": None, "installed": None}
        self.directory(profile)
        self.profiles.append(profile)
        self.save()
        return profile

    def mods(self, profile):
        directory = self.directory(profile) / "mods"
        directory.mkdir(exist_ok=True)
        return directory

    def mod_lock(self, profile):
        return read_json(self.directory(profile) / "mods.lock.json", {})

    @property
    def icon_cache(self):
        return self.root / "cache" / "mod-icons"

    def cached_icon(self, url):
        if not url:
            return None
        path = self.icon_cache / (hashlib.sha256(url.encode()).hexdigest() + ".img")
        return str(path) if path.is_file() else None


class ModManager:
    def __init__(self, store: Store, api: Api):
        self.store, self.api = store, api
        self.before_change = lambda profile, task=None, reason="": None

    def search(self, profile, query="", offset=0, sort=None):
        if profile["loader"] == "vanilla":
            raise LauncherError("Modlar için Fabric, Forge, NeoForge veya Quilt profili seçin.")
        if sort is not None and sort not in ("downloads", "relevance", "newest", "updated"):
            raise LauncherError("Geçersiz mod sıralaması.")
        facets = [["project_type:mod"], ["versions:" + profile["version"]], ["categories:" + profile["loader"]]]
        return self.api.get(MODRINTH + "/search", query=query, facets=json.dumps(facets),
                            index=sort or ("relevance" if query else "downloads"), limit=20, offset=offset)

    def catalog(self, profile, query="", offset=0, task=None, sort=None):
        """Search facets are project-wide; verify an actual matching mod version."""
        task = task or Task()
        task.status("Modlar aranıyor…")
        result = self.search(profile, query, offset, sort=sort)
        def details(hit):
            task.check()
            # Each task owns its requests session; shared Session state is avoided.
            api = Api()
            icon_path = None
            try:
                icon_path = api.icon(hit.get("icon_url"), self.store.icon_cache, task)
                version = ModManager(self.store, api).choose(hit["project_id"], profile)
                return {**hit, "icon_path": icon_path, "version_info": version, "compatibility": "compatible"}
            except Cancelled:
                raise
            except LauncherError as exc:
                return {**hit, "icon_path": icon_path, "version_info": None, "compatibility": "unverified", "version_error": str(exc)}
            finally:
                api.session.close()
        hits = result["hits"]
        enriched = [None] * len(hits)
        task.status("Mod sürümleri ve uyumlulukları kontrol ediliyor…")
        task.set_max(len(hits))
        with ThreadPoolExecutor(max_workers=4) as executor:
            pending = {executor.submit(details, hit): index for index, hit in enumerate(hits)}
            for complete, future in enumerate(as_completed(pending), start=1):
                task.check()
                enriched[pending[future]] = future.result()
                task.progress(complete)
        return {**result, "hits": enriched}

    def project_details(self, project):
        return self.api.get(MODRINTH + "/project/" + project)

    def compatible(self, version, profile):
        return (profile["version"] in version.get("game_versions", [])
                and profile["loader"] in version.get("loaders", [])
                and (version.get("server_side") != "unsupported" if profile.get("kind") == "server" else
                     version.get("client_side") != "unsupported" and version.get("environment") not in ("server_only", "dedicated_server_only")))

    def choose(self, project, profile):
        versions = self.api.get(MODRINTH + f"/project/{project}/version",
                                loaders=json.dumps([profile["loader"]]),
                                game_versions=json.dumps([profile["version"]]))
        choices = [v for v in versions if self.compatible(v, profile)]
        if not choices:
            raise LauncherError(f"{project}: {profile['version']} / {profile['loader']} için uyumlu sürüm yok.")
        choices.sort(key=lambda v: (v.get("version_type") == "release", v.get("date_published", "")), reverse=True)
        return choices[0]

    def plan(self, project, profile, version_id=None):
        """Resolve entire required dependency graph before writing any mod files."""
        installed = self.store.mod_lock(profile)
        chosen, visiting = {}, set()
        def visit(version):
            project_id = version["project_id"]
            if not self.compatible(version, profile):
                raise LauncherError("Gerekli bağımlılıklardan biri bu profil ile uyumlu değil.")
            if project_id in chosen:
                if chosen[project_id]["id"] != version["id"]:
                    raise LauncherError("Modların istediği bağımlılık sürümleri çakışıyor.")
                return
            old = installed.get(project_id)
            if old and old["version_id"] != version["id"]:
                raise LauncherError(f"{old['name']} farklı bir sürümle kurulu. Önce mevcut sürümü kaldırın.")
            if old and not (self.store.mods(profile) / old["file"]).exists():
                raise LauncherError(f"{old['name']} kapalı veya dosyası eksik. Önce etkinleştirin ya da kaldırın.")
            chosen[project_id] = version
            if project_id in visiting:
                return
            visiting.add(project_id)
            for dep in version.get("dependencies", []):
                if dep["dependency_type"] != "required":
                    continue
                if dep.get("version_id"):
                    child = self.api.get(MODRINTH + "/version/" + dep["version_id"])
                elif dep.get("project_id"):
                    existing = installed.get(dep["project_id"])
                    selected = chosen.get(dep["project_id"])
                    child = selected or (self.api.get(MODRINTH + "/version/" + existing["version_id"]) if existing
                                         else self.choose(dep["project_id"], profile))
                else:
                    raise LauncherError("Otomatik çözülemeyen harici bağımlılık: " + str(dep.get("file_name")))
                visit(child)
            visiting.discard(project_id)
        root = self.api.get(MODRINTH + "/version/" + version_id) if version_id else self.choose(project, profile)
        if version_id and root["project_id"] != project:
            raise LauncherError("Seçilen sürüm bu moda ait değil.")
        visit(root)
        full_ids = set(installed) | set(chosen)
        full_versions = {v["version_id"] for v in installed.values()} | {v["id"] for v in chosen.values()}
        def incompatible(dep, ids, versions):
            return dep["version_id"] in versions if dep.get("version_id") else dep.get("project_id") in ids
        for entry in installed.values():
            for dep in entry.get("incompatible", []):
                if incompatible(dep, set(chosen), {v["id"] for v in chosen.values()}):
                    raise LauncherError("Kurulu mod yeni modla çakışıyor: " + entry["name"])
        for version in chosen.values():
            for dep in version.get("dependencies", []):
                if dep["dependency_type"] == "incompatible":
                    if incompatible(dep, full_ids, full_versions):
                        raise LauncherError("Modlar arasında bildirilen bir uyumsuzluk var.")
        return [v for pid, v in chosen.items() if pid not in installed]

    def install(self, project, profile, task: Task, version_id=None):
        task.status("Mod ve gerekli bağımlılıkları kontrol ediliyor…")
        plan = self.plan(project, profile, version_id)
        if plan:
            self.before_change(profile, task, "Mod kurulumu öncesi")
        projects = {}
        if plan:
            try:
                projects = {p["id"]: p for p in self.api.get(MODRINTH + "/projects", ids=json.dumps([v["project_id"] for v in plan]))}
            except LauncherError:
                pass
        lock = self.store.mod_lock(profile)
        directory = self.store.mods(profile)
        stage = Path(tempfile.mkdtemp(prefix=".kurt-", dir=directory.parent))
        committed = []
        try:
            files = []
            names = set()
            task.transfer.pending = [next((f["filename"] for f in v["files"] if f.get("primary")), v["files"][0]["filename"]) for v in plan]
            for index, version in enumerate(plan, 1):
                task.check()
                task.transfer.queue = f"Mod {index}/{len(plan)}"
                candidates = [f for f in version["files"] if f["filename"].lower().endswith(".jar")]
                if not candidates:
                    raise LauncherError("Bu sürümde kurulabilir JAR bulunamadı.")
                file = next((f for f in candidates if f.get("primary")), candidates[0])
                name = safe_file(file["filename"])
                if name.casefold() in names or (directory / name).exists() or (directory / (name + ".disabled")).exists():
                    raise LauncherError("Aynı adlı mod dosyası zaten var: " + name)
                names.add(name.casefold())
                self.api.download(file, stage / name, task)
                if task.transfer.pending: task.transfer.pending.pop(0)
                files.append((version, name))
            task.check()
            for version, name in files:
                target = directory / name
                os.replace(stage / name, target)
                committed.append(target)
                project = projects.get(version["project_id"], {})
                lock[version["project_id"]] = {
                    "name": project.get("title") or version.get("name", name), "version_id": version["id"], "file": name,
                    "icon_url": project.get("icon_url"),
                    "version_number": version.get("version_number", ""),
                    "game_versions": version.get("game_versions", []), "loaders": version.get("loaders", []),
                    "requires": [d for d in version.get("dependencies", []) if d["dependency_type"] == "required"],
                    "incompatible": [d for d in version.get("dependencies", []) if d["dependency_type"] == "incompatible"]}
            atomic_json(self.store.directory(profile) / "mods.lock.json", lock)
            return f"{len(files)} mod/bağımlılık kuruldu." if files else "Bu mod zaten kurulu."
        except Exception:
            for file in committed:
                file.unlink(missing_ok=True)
            raise
        finally:
            task.transfer.queue = ""
            task.transfer.pending = []
            shutil.rmtree(stage, ignore_errors=True)

    def refresh_metadata(self, profile, task):
        lock = self.store.mod_lock(profile)
        if not lock:
            return "Güncellenecek Modrinth mod kaydı yok."
        task.status("Kurulu modların sürüm bilgileri alınıyor…")
        versions = []
        ids = [item["version_id"] for item in lock.values()]
        for start in range(0, len(ids), 100):
            task.check()
            versions.extend(self.api.get(MODRINTH + "/versions", ids=json.dumps(ids[start:start + 100])))
        lookup = {version["id"]: version for version in versions}
        projects = {p["id"]: p for p in self.api.get(MODRINTH + "/projects", ids=json.dumps(list(lock)))}
        for project_id, entry in lock.items():
            version = lookup.get(entry["version_id"])
            if version:
                entry.update(version_number=version.get("version_number", ""),
                             game_versions=version.get("game_versions", []), loaders=version.get("loaders", []))
            project = projects.get(project_id, {})
            if project:
                entry["name"] = project["title"]
                entry["icon_url"] = project.get("icon_url")
                self.api.icon(entry["icon_url"], self.store.icon_cache, task)
        task.check()
        atomic_json(self.store.directory(profile) / "mods.lock.json", lock)
        return "Kurulu modların sürüm ve uyumluluk bilgileri güncellendi."

    def import_local(self, profile, paths, task=None):
        if profile["loader"] == "vanilla":
            raise LauncherError("Önce mod yükleyicili bir profil seçin.")
        directory = self.store.mods(profile)
        result = []
        stage = Path(tempfile.mkdtemp(prefix=".local-", dir=directory.parent))
        committed = []
        try:
            names = set()
            for source in paths:
                source = Path(source)
                name = safe_file(source.name)
                if source.suffix.lower() != ".jar":
                    raise LauncherError("Yalnızca .jar dosyaları eklenebilir.")
                if name.casefold() in names or (directory / name).exists() or (directory / (name + ".disabled")).exists():
                    raise LauncherError("Dosya zaten var: " + name)
                names.add(name.casefold())
                validate_jar(source)
                with zipfile.ZipFile(source) as jar:
                    entries = set(jar.namelist())
                    if profile.get("kind") == "server" and "fabric.mod.json" in entries:
                        metadata = json.loads(jar.read("fabric.mod.json"))
                        if metadata.get("environment") == "client":
                            raise LauncherError(name + ": bu mod yalnızca istemcide çalışır; sunucuya eklenemez.")
                    loader = profile["loader"]
                    if loader == "fabric" and "fabric.mod.json" not in entries:
                        raise LauncherError(name + ": Fabric mod tanımı yok.")
                    if loader == "quilt" and not entries.intersection({"quilt.mod.json", "fabric.mod.json"}):
                        raise LauncherError(name + ": Quilt/Fabric mod tanımı yok.")
                    if loader in ("forge", "neoforge") and not entries.intersection({"META-INF/mods.toml", "META-INF/neoforge.mods.toml", "mcmod.info"}):
                        raise LauncherError(name + ": Forge/NeoForge mod tanımı yok.")
                shutil.copy2(source, stage / name)
                result.append(name)
            self.before_change(profile, task, "Yerel mod ekleme öncesi")
            for name in result:
                target = directory / name
                os.replace(stage / name, target)
                committed.append(target)
            return f"{len(result)} yerel mod eklendi. Oyun sürümü ve bağımlılıklarını kontrol edin."
        except Exception:
            for file in committed:
                file.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def guard_dependents(self, profile, filename):
        lock = self.store.mod_lock(profile)
        target = next((pid for pid, v in lock.items() if v["file"] == filename.removesuffix(".disabled")), None)
        if not target:
            return
        version_id = lock[target]["version_id"]
        for pid, v in lock.items():
            if pid == target or not (self.store.mods(profile) / v["file"]).exists():
                continue
            if any(d.get("project_id") == target or d.get("version_id") == version_id for d in v.get("requires", [])):
                raise LauncherError("Bu mod şu mod için gerekli: " + v["name"] + ". Önce onu kapatın/kaldırın.")

    def toggle(self, profile, name, task=None):
        safe_file(name)
        directory = self.store.mods(profile)
        source = directory / name
        if name.endswith(".disabled"):
            dest = directory / name.removesuffix(".disabled")
            lock = self.store.mod_lock(profile)
            entry = next((v for v in lock.values() if v["file"] == dest.name), None)
            if entry:
                for dep in entry.get("requires", []):
                    found = next((v for pid, v in lock.items() if pid == dep.get("project_id") or v["version_id"] == dep.get("version_id")), None)
                    if not found or not (directory / found["file"]).exists():
                        raise LauncherError("Gerekli bağımlılık kapalı veya eksik. Önce onu etkinleştirin.")
        else:
            self.guard_dependents(profile, name)
            dest = directory / (name + ".disabled")
        if dest.exists():
            raise LauncherError("Hedef dosya zaten var.")
        self.before_change(profile, task, "Mod etkinlik değişikliği öncesi")
        source.rename(dest)

    def remove(self, profile, name, task=None):
        safe_file(name)
        self.guard_dependents(profile, name)
        self.before_change(profile, task, "Mod kaldırma öncesi")
        source = self.store.mods(profile) / name
        trash = self.store.directory(profile) / "removed-mods"
        trash.mkdir(exist_ok=True)
        destination = trash / (uuid.uuid4().hex[:8] + "-" + name)
        lock = self.store.mod_lock(profile)
        lock = {pid: v for pid, v in lock.items() if v["file"] != name.removesuffix(".disabled")}
        source.rename(destination)
        try:
            atomic_json(self.store.directory(profile) / "mods.lock.json", lock)
        except Exception:
            destination.rename(source)
            raise

    def validate_enabled(self, profile):
        lock = self.store.mod_lock(profile)
        directory = self.store.mods(profile)
        for entry in lock.values():
            if not (directory / entry["file"]).exists():
                continue
            for dep in entry.get("requires", []):
                found = next((v for pid, v in lock.items() if pid == dep.get("project_id") or v["version_id"] == dep.get("version_id")), None)
                if not found or not (directory / found["file"]).exists():
                    raise LauncherError("Eksik/kapalı bağımlılık: " + entry["name"])


class Account:
    def __init__(self, store):
        self.store = store

    @property
    def vault(self):
        # Explicit OS vault: never fall back to a plaintext keyring backend.
        if sys.platform != "win32":
            raise LauncherError("Bu derlemede hesap kasası yalnızca Windows için destekleniyor.")
        from keyring.backends.Windows import WinVaultKeyring
        return WinVaultKeyring()

    @property
    def key(self):
        return "KurtLauncher-" + hashlib.sha256(str(self.store.root).encode()).hexdigest()[:20]

    def remember(self, result):
        self.vault.set_password(self.key, self.store.settings["client_id"], result["refresh_token"])
        self.store.account = {"name": result["name"], "id": result["id"], "client_id": self.store.settings["client_id"]}
        atomic_json(self.store.root / "account.json", self.store.account)
        return result

    def login(self, task):
        client = self.store.settings.get("client_id", "").strip()
        try:
            uuid.UUID(client)
        except ValueError as exc:
            raise LauncherError("Ayarlar bölümüne Microsoft uygulamanızın Client ID değerini girin.") from exc
        result = {}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                if urlparse(self.path).path != "/callback":
                    self.send_error(404)
                    return
                try:
                    result["code"] = mc.microsoft_account.parse_auth_code_url(redirect + self.path[self.path.index("?"):], state)
                    message = "Giris alindi. Bu pencereyi kapatip Kurt Launcher'a donebilirsiniz."
                except Exception:
                    result["error"] = True
                    message = "Giris dogrulanamadi. Launcher uzerinden tekrar deneyin."
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(message.encode("utf-8"))
        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            server.timeout = 0.5
            redirect = f"http://localhost:{server.server_port}/callback"
            url, state, verifier = mc.microsoft_account.get_secure_login_data(client, redirect)
            task.status("Microsoft girişi tarayıcıda bekleniyor…")
            webbrowser.open(url)
            deadline = time.monotonic() + 240
            while not result and time.monotonic() < deadline:
                task.check()
                server.handle_request()
        if result.get("error") or not result.get("code"):
            raise LauncherError("Giriş tamamlanmadı. Uygulama kimliği ve dönüş adresini kontrol edin.")
        task.status("Minecraft hesabı doğrulanıyor…")
        return self.remember(mc.microsoft_account.complete_login(client, None, redirect, result["code"], verifier))

    def refresh(self):
        client = self.store.settings.get("client_id", "")
        token = self.vault.get_password(self.key, client) if client else None
        if not token:
            raise LauncherError("Önce Microsoft hesabınızla giriş yapın.")
        return self.remember(mc.microsoft_account.complete_refresh(client, None, None, token))

    def logout(self):
        client = self.store.account.get("client_id", self.store.settings.get("client_id", ""))
        if client and self.vault.get_password(self.key, client):
            self.vault.delete_password(self.key, client)
        self.store.account = {}
        atomic_json(self.store.root / "account.json", {})


class Launcher:
    def __init__(self, store):
        self.store, self.api = store, Api()
        self.mods = ModManager(store, self.api)
        self.account = Account(store)
        self.process = None
        self.server_manager = None
        self.active_profile_id = None
        from snapshots import Snapshots
        self.snapshots = Snapshots(store, self.ensure_profile_idle)
        self.mods.before_change = self.snapshots.before_change

    def ensure_profile_idle(self, profile):
        if profile.get("kind") != "server":
            self.ensure_idle()
        if self.server_manager and self.server_manager.running and self.server_manager.active_id == profile["id"]:
            raise LauncherError("Önce sunucuyu durdurun; dünyası kaydedildikten sonra değişiklik yapın.")

    def ensure_idle(self):
        if self.process and self.process.poll() is None:
            raise LauncherError("Oyun çalışırken kurulum veya mod değişikliği yapılamaz. Önce Minecraft'ı kapatın.")

    def versions(self):
        cache = self.store.root / "versions-cache.json"
        try:
            result = self.api.get(MANIFEST)
            atomic_json(cache, result)
            return result, False
        except LauncherError:
            if cache.exists():
                return read_json(cache, {}), True
            raise

    def java(self, profile, task, allow_download=True):
        custom = self.store.settings.get("java", "").strip()
        if custom:
            if not Path(custom).is_file():
                raise LauncherError("Seçilen Java dosyası bulunamadı.")
            return custom
        information = mc.runtime.get_version_runtime_information(profile["version"], self.store.minecraft)
        runtime = information["name"] if information else "jre-legacy"
        executable = mc.runtime.get_executable_path(runtime, self.store.minecraft)
        if not executable:
            if not allow_download:
                raise LauncherError("Bu profilin Java kurulumu eksik. İnternete bağlanıp Kur / onar işlemini çalıştırın.")
            task.status("Uygun Java hazırlanıyor…")
            from transfers import library_downloads
            with library_downloads(task):
                mc.runtime.install_jvm_runtime(runtime, self.store.minecraft, callback=task.callbacks)
            executable = mc.runtime.get_executable_path(runtime, self.store.minecraft)
        if not executable:
            raise LauncherError("Uygun Java bulunamadı. Ayarlardan Java yolunu seçin.")
        return executable

    def install(self, profile, task):
        self.ensure_idle()
        if profile.get("installed"):
            self.snapshots.before_change(profile, task, "Oyun/yükleyici onarımı öncesi")
        loader = None
        if profile["loader"] != "vanilla":
            loader = mc.mod_loader.get_mod_loader(profile["loader"])
            if not loader.is_minecraft_version_supported(profile["version"]):
                raise LauncherError(f"{profile['loader']} yükleyicisi {profile['version']} sürümünü desteklemiyor.")
        task.status("Minecraft dosyaları doğrulanıyor…")
        directory = self.store.minecraft
        from transfers import library_downloads
        with library_downloads(task):
            mc.install.install_minecraft_version(profile["version"], directory, task.callbacks)
        java = self.java(profile, task)
        task.check()
        version = profile["version"]
        if loader:
            selected = profile.get("loader_version") or loader.get_latest_loader_version(version)
            task.status(profile["loader"].title() + " kuruluyor…")
            with library_downloads(task):
                version = loader.install(version, directory, loader_version=selected, callback=task.callbacks, java=java)
            profile["loader_version"] = selected
        task.check()
        profile["installed"] = version
        self.store.save()
        return f"{profile['name']} hazır."

    def play(self, profile, task, join_address=None):
        if self.process and self.process.poll() is None:
            raise LauncherError("Minecraft zaten çalışıyor.")
        self.mods.validate_enabled(profile)
        mode = self.store.settings.get("login_mode", "microsoft")
        if mode == "offline":
            account = offline_account(self.store.settings.get("offline_username", ""))
            task.status("Kullanıcı adıyla başlatılıyor: " + account["name"])
        elif mode == "microsoft":
            task.status("Hesap oturumu yenileniyor…")
            account = self.account.refresh()
        else:
            raise LauncherError("Geçersiz giriş yöntemi. Oyun merkezinden bir giriş yöntemi seçin.")
        installed = profile.get("installed")
        if installed:
            safe_file(installed)
        cached = bool(mode == "offline" and installed
                      and (self.store.minecraft / "versions" / installed / (installed + ".json")).is_file()
                      and (self.store.minecraft / "versions" / profile["version"] / (profile["version"] + ".jar")).is_file())
        if cached:
            task.status("Kurulu oyun kullanılıyor; hesap servisine bağlanılmıyor…")
        else:
            task.status("İlk kurulum hazırlanıyor; dosyaları indirmek için internet gerekir…")
            self.install(profile, task)
        task.status("Minecraft başlatılıyor…")
        game = self.store.directory(profile)
        options = {"username": account["name"], "uuid": account["id"], "token": account["access_token"],
                   "executablePath": self.java(profile, task, allow_download=not cached), "gameDirectory": str(game),
                   "launcherName": "KurtLauncher", "launcherVersion": APP_VERSION,
                   "jvmArguments": [f"-Xmx{int(self.store.settings.get('ram', 4096))}M", "-Xms512M"],
                   "enableLoggingConfig": True}
        if join_address:
            from invites import split_endpoint
            host, port = split_endpoint(join_address)
            vanilla_json = read_json(self.store.minecraft / "versions" / profile["version"] / (profile["version"] + ".json"), {})
            if "quickPlayMultiplayer" in json.dumps(vanilla_json.get("arguments", {})):
                options["quickPlayMultiplayer"] = f"{host}:{port}"
                options["quickPlayPath"] = str(game / "quickplay.json")
            else:
                options.update(server=host, port=str(port))
        command = mc.command.get_minecraft_command(profile["installed"], self.store.minecraft, options)
        if mode == "offline":
            for index, argument in enumerate(command[:-1]):
                if argument == "--userType":
                    command[index + 1] = "legacy"
        task.check()
        # Never log the launch command: it contains the Minecraft access token.
        with (game / "launcher-game.log").open("w", encoding="utf-8") as output:
            self.process = subprocess.Popen(command, cwd=game, stdout=output, stderr=subprocess.STDOUT,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.active_profile_id = profile["id"]
        profile["last_played"] = time.time()
        self.store.save()
        return "Minecraft başlatıldı: " + account["name"] + (" (kullanıcı adıyla)." if mode == "offline" else ".")

    def join_invite(self, code, task):
        from invites import decode_invite
        info = decode_invite(code)
        if self.store.settings["login_mode"] == "offline":
            offline_account(self.store.settings.get("offline_username", ""))
        profile = self.invite_profile(info)
        if info.get("mod_manifest"):
            from packs import Packs
            comparison = Packs(self).compare(profile, info["mod_manifest"])
            if not comparison["profile_matches"] or any(r["state"] != "Eşleşiyor" for r in comparison["rows"]):
                raise LauncherError("Davetin modları henüz eşleşmiyor. Önce mod uyumluluğu ekranını tamamlayın.")
        message = self.play(profile, task, join_address=info["address"])
        return message, profile["id"]

    def invite_profile(self, info):
        manifest, _ = self.versions()
        if info["version"] not in {entry["id"] for entry in manifest["versions"]}:
            raise LauncherError("Davet kodundaki Minecraft sürümü resmî listede bulunamadı.")
        if info["loader"] != "vanilla" and info["loader_version"]:
            supported = mc.mod_loader.get_mod_loader(info["loader"]).get_loader_versions(info["version"], False)
            if info["loader_version"] not in supported:
                raise LauncherError("Davet kodundaki Fabric yükleyicisi bu oyun sürümüyle uyumlu değil.")
        profile = next((p for p in self.store.profiles if p["version"] == info["version"] and p["loader"] == info["loader"]
                        and (not info["loader_version"] or p.get("loader_version") == info["loader_version"])), None)
        if profile is None:
            profile = self.store.create("Arkadaş sunucusu · " + info["version"] + " " + info["loader"].title(), info["version"], info["loader"])
            profile["loader_version"] = info["loader_version"]
            self.store.save()
        return profile

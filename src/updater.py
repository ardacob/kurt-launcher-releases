"""Ed25519-authenticated updates; game data is never part of an update."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from core import APP_VERSION, LauncherError, atomic_json
from snapshots import digest, relative_path

TOP_LEVEL = {"KurtLauncher.exe", "src", "assets", "third-party", "README.md", "DOGRULAMA.txt", "requirements.txt", "build.ps1", "KurtLauncher.spec", "Baslat.cmd", "_internal", "tests", "sign_release.py", "GUNCELLEME-YAYINLAMA.md"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,4}\.\d{1,4}\.\d{1,4}", value):
        raise LauncherError("Güncelleme sürüm numarası geçersiz.")
    return tuple(map(int, value.split(".")))


class Updater:
    def __init__(self, store, public_key=None):
        self.store = store
        self.assets = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets"
        self.public_key = public_key or (self.assets / "update-public-key.bin").read_bytes()

    def verify(self, envelope):
        try:
            data = envelope["manifest"]
            signature = base64.b64decode(envelope["signature"], validate=True)
            Ed25519PublicKey.from_public_bytes(self.public_key).verify(signature, canonical(data))
            if data.get("product") != "KurtLauncher" or data.get("platform") != "windows-x64" or data.get("format") != 1:
                raise ValueError("product")
            version_tuple(data["version"])
            return data
        except (InvalidSignature, ValueError, KeyError, TypeError) as exc:
            raise LauncherError("Güncellemenin yayıncı imzası doğrulanamadı. Kurulum yapılmadı.") from exc

    def inspect(self, package, allow_current=False):
        try:
            with zipfile.ZipFile(package) as archive:
                info = archive.getinfo("update.json")
                if info.file_size > 4 * 1024 * 1024:
                    raise LauncherError("Güncelleme kaydı çok büyük.")
                manifest = self.verify(json.loads(archive.read(info)))
                if not allow_current and version_tuple(manifest["version"]) <= version_tuple(APP_VERSION):
                    raise LauncherError("Bu paket kurulu sürümden yeni değil.")
                files = manifest.get("files", {})
                if not isinstance(files, dict) or not files or len(files) > 20000 or "KurtLauncher.exe" not in files:
                    raise LauncherError("Güncellemenin dosya listesi geçersiz.")
                seen, total = set(), 0
                for name, record in files.items():
                    parts = relative_path(name)
                    if parts.parts[0] not in TOP_LEVEL or name.casefold() in seen:
                        raise LauncherError("Güncelleme veri klasörüne veya tanınmayan yola yazamaz.")
                    seen.add(name.casefold())
                    if not re.fullmatch(r"[a-f0-9]{128}", record["sha512"]) or type(record["size"]) is not int or record["size"] < 0:
                        raise LauncherError("Güncelleme dosya kaydı geçersiz.")
                    entry = archive.getinfo("payload/" + name)
                    if entry.file_size != record["size"]:
                        raise LauncherError("Güncelleme dosya boyutu uyuşmuyor.")
                    total += record["size"]
                if total > 2 * 1024**3:
                    raise LauncherError("Güncelleme paketi çok büyük.")
                names = [i.filename for i in archive.infolist() if not i.is_dir()]
                if len(set(n.casefold() for n in names)) != len(names) or set(names) != {"update.json", *("payload/" + n for n in files)}:
                    raise LauncherError("Güncellemede beklenmeyen veya yinelenen dosyalar var.")
                return {**manifest, "package_hash": digest(package)}
        except (zipfile.BadZipFile, KeyError, ValueError, TypeError) as exc:
            raise LauncherError("Güncelleme paketi okunamadı.") from exc

    def stage(self, package, task, preview=None, allow_current=False):
        info = self.inspect(package, allow_current=allow_current)
        if preview and info["package_hash"] != preview["package_hash"]:
            raise LauncherError("Güncelleme paketi önizlemeden sonra değişti.")
        folder = self.store.root / "updates"
        folder.mkdir(exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix="verified-", dir=folder))
        try:
            if shutil.disk_usage(stage).free < sum(r["size"] for r in info["files"].values()) * 2 + 64 * 1024 * 1024:
                raise LauncherError("Güncelleme ve geri dönüş kopyası için disk alanı yetersiz.")
            task.status("Yayıncı imzalı güncelleme hazırlanıyor…")
            task.set_max(len(info["files"]))
            with zipfile.ZipFile(package) as archive:
                for i, (name, record) in enumerate(info["files"].items(), 1):
                    task.check()
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open("payload/" + name) as inp, target.open("wb") as out:
                        shutil.copyfileobj(inp, out)
                    if digest(target) != record["sha512"]:
                        raise LauncherError("Güncelleme dosyası doğrulanamadı: " + name)
                    task.progress(i)
            atomic_json(stage / "verified.json", info)
            return str(stage)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def launch_helper(self, stage, *, installation=None, obsolete=None, redirect_hash=None):
        if not getattr(sys, "frozen", False) or os.name != "nt":
            raise LauncherError("Uygulama içi güncelleme paketlenmiş Windows EXE'sinde uygulanır.")
        stage = Path(stage).resolve()
        if not stage.is_relative_to((self.store.root / "updates").resolve()):
            raise LauncherError("Güncelleme hazırlık klasörü geçersiz.")
        current_executable = Path(sys.executable).resolve()
        installation = Path(installation).resolve() if installation is not None else current_executable.parent
        if installation == Path(installation.anchor) or len(installation.parts) < 3:
            raise LauncherError("Launcher'ı kendine ait bir klasöre taşıyın.")
        task_id = uuid.uuid4().hex
        plan = {"installation": str(installation), "stage": str(stage), "pid": os.getpid(),
                "health": str(self.store.root / "updates" / (task_id + ".ok")), "data": str(self.store.root)}
        from installation import app_folder
        if installation == app_folder():
            plan["managed"] = True
            plan["create_shortcut"] = os.environ.get("KURT_SKIP_SHORTCUT") != "1" and os.environ.get("KURT_SKIP_INTEGRATION") != "1"
        if obsolete is not None:
            obsolete = Path(obsolete).resolve()
            if obsolete != current_executable or obsolete.name.lower() != "kurtlauncher.exe":
                raise LauncherError("Eski launcher yolu geçersiz.")
            plan["obsolete_executable"] = str(obsolete)
            plan["obsolete_sha512"] = digest(obsolete)
        if redirect_hash:
            plan["redirect_sha512"] = redirect_hash
        path = self.store.root / "updates" / (task_id + ".json")
        atomic_json(path, plan)
        helper = self.store.root / "updates" / (task_id + ".ps1")
        shutil.copy2(self.assets / "update-worker.ps1", helper)
        powershell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        subprocess.Popen([str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(helper), "-Plan", str(path)],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True,
                         env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
        return Path(str(path) + ".result")

    def check_feed(self, task):
        """Feed URL and publisher key are shipped by the publisher, never user content."""
        config = self.assets / "release-channel.json"
        settings = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
        url = settings.get("manifest_url", "")
        if not url:
            return {"available": False, "message": "Çevrimiçi yayın kanalı henüz yapılandırılmadı. Yayıncı imzalı .kurtupdate dosyasını seçerek güncelleyebilirsiniz."}
        if urlparse(url).scheme != "https":
            raise LauncherError("Güncelleme kanalı HTTPS kullanmalı.")
        import requests
        task.status("Güncelleme kanalı kontrol ediliyor…")
        with requests.get(url, stream=True, timeout=(5, 10), headers={"User-Agent": f"KurtLauncher/{APP_VERSION}", "Cache-Control": "no-cache"}) as response:
            if response.status_code == 404:
                return {"available": False, "pending": True, "message": "Güncelleme kanalı ilk yayını bekliyor. Yerel imzalı paket seçebilirsiniz."}
            response.raise_for_status()
            body = b""
            for chunk in response.iter_content(65536):
                task.check()
                body += chunk
                if len(body) > 4 * 1024 * 1024: raise LauncherError("Güncelleme kaydı çok büyük.")
        data = self.verify(json.loads(body))
        return {"available": version_tuple(data["version"]) > version_tuple(APP_VERSION), "manifest": data,
                "message": "Yeni sürüm: " + data["version"] if version_tuple(data["version"]) > version_tuple(APP_VERSION) else "Launcher güncel."}

    def download_release(self, manifest, task):
        url = manifest.get("package_url", "")
        expected = manifest.get("package_sha512", "")
        if urlparse(url).scheme != "https" or not re.fullmatch(r"[a-f0-9]{128}", expected):
            raise LauncherError("İmzalı güncelleme indirme bilgileri geçersiz.")
        import requests
        directory = self.store.root / "updates"
        directory.mkdir(exist_ok=True)
        target = directory / ("release-" + uuid.uuid4().hex + ".kurtupdate")
        from downloads import download
        def allowed(value):
            if urlparse(value).scheme != 'https':
                raise LauncherError('Güncelleme yalnız HTTPS üzerinden indirilebilir.')
        return download(requests, url, target, task, cache=self.store.root / 'cache/downloads',
                        expected=expected, allow_url=allowed, limit=1024**3)

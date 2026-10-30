"""Local Vanilla/Fabric server lifecycle. No firewall/router changes are made."""
from __future__ import annotations
import hashlib
import os
import queue
import re
import socket
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from core import LauncherError, Task, atomic_json, mc, safe_file, validate_jar


class ServerManager:
    def __init__(self, launcher):
        self.launcher = launcher
        self.store = launcher.store
        self.api = launcher.api
        self.process = None
        self.active_id = None
        self.ready = threading.Event()
        self.stopping = False
        self.output = queue.Queue(maxsize=2000)
        self.reader = None
        self.players = []
        launcher.server_manager = self

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def create(self, name, version, loader="vanilla", port=25565, ram=2048, username_players=True, slots=8):
        if not name.strip() or len(name.strip()) > 64:
            raise LauncherError("Sunucu adı 1–64 karakter olmalı.")
        safe_file(version)
        if loader not in ("vanilla", "fabric"):
            raise LauncherError("Sunucu için Vanilla veya Fabric seçin.")
        if not 1024 <= int(port) <= 65535 or not 1024 <= int(ram) <= 65536 or not 1 <= int(slots) <= 100:
            raise LauncherError("Sunucu portu, belleği veya oyuncu sınırı geçersiz.")
        server = {"id": uuid.uuid4().hex, "kind": "server", "name": name.strip(), "version": version,
                  "loader": loader, "port": int(port), "ram": int(ram), "slots": int(slots),
                  "username_players": bool(username_players), "eula_accepted": False,
                  "loader_version": None, "installed": False}
        self.store.directory(server)
        self.store.servers.append(server)
        self.store.save()
        return server

    def metadata(self, version):
        manifest, _ = self.launcher.versions()
        item = next((entry for entry in manifest["versions"] if entry["id"] == version), None)
        if not item:
            raise LauncherError("Bu Minecraft sürümü resmî listede bulunamadı.")
        data = self.api.get(item["url"])
        if not data.get("downloads", {}).get("server"):
            raise LauncherError("Bu arşiv sürümünün resmî sunucu indirmesi yok. Başka bir sürüm seçin.")
        return data

    def download(self, url, target, task, sha1=None):
        allowed = {"piston-data.mojang.com", "launcher.mojang.com", "meta.fabricmc.net"}
        if urlparse(url).scheme != "https" or urlparse(url).hostname not in allowed:
            raise LauncherError("Sunucu dosyası resmî bir indirme adresinden gelmiyor.")
        if target.is_file() and sha1 and hashlib.sha1(target.read_bytes()).hexdigest() == sha1:
            return
        fd, name = tempfile.mkstemp(dir=target.parent, suffix=".download")
        temporary = Path(name)
        try:
            digest = hashlib.sha1()
            with os.fdopen(fd, "wb") as stream:
                task.status("Sunucu indiriliyor: " + target.name)
                with self.api.session.get(url, stream=True, timeout=(15, 60)) as response:
                    response.raise_for_status()
                    task.begin_bytes(int(response.headers.get("Content-Length", 0)))
                    size = 0
                    for chunk in response.iter_content(128*1024):
                        task.check()
                        stream.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                        task.progress(size)
            if sha1 and digest.hexdigest() != sha1:
                raise LauncherError("Sunucu dosyası doğrulanamadı; kurulum yapılmadı.")
            validate_jar(temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def prepare(self, server, task, accept_eula=False):
        if self.running:
            raise LauncherError("Önce çalışan sunucuyu durdurun.")
        if not server.get("eula_accepted") and not accept_eula:
            raise LauncherError("Sunucuyu kurmadan önce Minecraft EULA onay kutusunu işaretleyin.")
        if server.get("installed"):
            self.launcher.snapshots.before_change(server, task, "Sunucu onarımı öncesi")
        data = self.metadata(server["version"])
        directory = self.store.directory(server)
        artifact = data["downloads"]["server"]
        self.download(artifact["url"], directory / "server.jar", task, artifact["sha1"])
        component = data.get("javaVersion", {}).get("component", "jre-legacy")
        custom = self.store.settings.get("java", "").strip()
        if custom and not Path(custom).is_file():
            raise LauncherError("Ayarlardaki Java çalıştırıcısı bulunamadı.")
        if not custom and not mc.runtime.get_executable_path(component, self.store.minecraft):
            task.status("Sunucu için uygun Java hazırlanıyor…")
            from transfers import library_downloads
            with library_downloads(task):
                mc.runtime.install_jvm_runtime(component, self.store.minecraft, callback=task.callbacks)
        java = custom or mc.runtime.get_executable_path(component, self.store.minecraft)
        if not java:
            raise LauncherError("Sunucu için Java bulunamadı.")
        jar = "server.jar"
        if server["loader"] == "fabric":
            loaders = self.api.get("https://meta.fabricmc.net/v2/versions/loader/" + server["version"])
            if not loaders:
                raise LauncherError("Fabric bu sunucu sürümünü desteklemiyor.")
            selected = server.get("loader_version") or next((v["loader"]["version"] for v in loaders if v["loader"].get("stable")), loaders[0]["loader"]["version"])
            installers = self.api.get("https://meta.fabricmc.net/v2/versions/installer")
            installer = next((v["version"] for v in installers if v.get("stable")), installers[0]["version"])
            safe_file(selected)
            safe_file(installer)
            jar = "fabric-server.jar"
            if not (directory / jar).exists():
                url = f"https://meta.fabricmc.net/v2/versions/loader/{server['version']}/{selected}/{installer}/server/jar"
                self.download(url, directory / jar, task)
            server["loader_version"] = selected
            self.store.mods(server)
        task.check()
        properties = {}
        path = directory / "server.properties"
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    properties[key] = value
        properties.update({"server-port": str(server["port"]), "server-ip": "",
                           "max-players": str(server["slots"]),
                           "online-mode": str(not server["username_players"]).lower(),
                           "enforce-secure-profile": str(not server["username_players"]).lower(),
                           "enable-rcon": "false"})
        for key, value in {"motd": "Kurt Launcher - Arkadas dunyasi", "gamemode": "survival",
                           "difficulty": "normal", "view-distance": "8", "simulation-distance": "6"}.items():
            properties.setdefault(key, value)
        path.write_text("\n".join(key + "=" + value for key, value in properties.items()) + "\n", encoding="utf-8")
        (directory / "eula.txt").write_text("# Accepted by user in Kurt Launcher\neula=true\n", encoding="utf-8")
        server.update(eula_accepted=True, eula_accepted_at=server.get("eula_accepted_at") or datetime.now(timezone.utc).isoformat(),
                      installed=True, launch_jar=jar, java_component=component)
        self.store.save()
        return java

    def start(self, server, task, accept_eula=False):
        if self.running:
            raise LauncherError("Zaten çalışan bir sunucu var. Önce onu durdurun.")
        if server.get("installed"):
            self.launcher.snapshots.before_change(server, task, "Sunucu açılışı öncesi")
        if not server.get("installed"):
            java = self.prepare(server, task, accept_eula)
        else:
            if not server.get("eula_accepted"):
                raise LauncherError("Sunucu EULA onayı eksik.")
            java = self.store.settings.get("java", "").strip() or mc.runtime.get_executable_path(server["java_component"], self.store.minecraft)
            if not java:
                raise LauncherError("Sunucunun Java kurulumu eksik; Kur / onar düğmesini kullanın.")
        directory = self.store.directory(server)
        if not (directory / server["launch_jar"]).is_file():
            raise LauncherError("Sunucu JAR dosyası eksik; Kur / onar düğmesini kullanın.")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test:
            if os.name == "nt":
                test.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                test.bind(("", server["port"]))
            except OSError as exc:
                raise LauncherError("Sunucu portu başka bir uygulama tarafından kullanılıyor.") from exc
        task.check()
        command = [str(java), "-Xms512M", f"-Xmx{server['ram']}M", "-jar", server["launch_jar"], "nogui"]
        self.ready.clear()
        self.stopping = False
        self.drain()
        self.active_id = server["id"]
        self.players = []
        self.process = subprocess.Popen(command, cwd=directory, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        process = self.process
        def read_output():
            with (directory / "launcher-server.log").open("a", encoding="utf-8") as log:
                for line in process.stdout:
                    line = re.sub(r"\x1b\[[0-9;]*m", "", line).rstrip()
                    log.write(line + "\n")
                    log.flush()
                    if "Done (" in line:
                        self.ready.set()
                    listed = re.search(r"There are \d+ of a max of \d+ players online:\s*(.*)", line)
                    if listed:
                        self.players = [v.strip() for v in listed.group(1).split(",") if v.strip()]
                    joined = re.search(r"\b([A-Za-z0-9_]{3,16}) joined the game", line)
                    left = re.search(r"\b([A-Za-z0-9_]{3,16}) left the game", line)
                    if joined and joined.group(1) not in self.players:
                        self.players.append(joined.group(1))
                    if left and left.group(1) in self.players:
                        self.players.remove(left.group(1))
                    try:
                        self.output.put_nowait(line)
                    except queue.Full:
                        try: self.output.get_nowait()
                        except queue.Empty: pass
                        try: self.output.put_nowait(line)
                        except queue.Full: pass
        self.reader = threading.Thread(target=read_output, daemon=True)
        self.reader.start()
        return "Sunucu başlatılıyor. Konsolda Done mesajı göründüğünde katılabilirsiniz."

    def command(self, text):
        if not self.running or not self.process.stdin:
            raise LauncherError("Çalışan bir sunucu yok.")
        text = text.strip()
        if not text or len(text) > 512 or "\n" in text or "\r" in text:
            raise LauncherError("Tek satırlık bir Minecraft konsol komutu yazın.")
        try:
            self.process.stdin.write(text + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise LauncherError("Sunucu konsoluna komut gönderilemedi.") from exc

    def stop(self):
        self.command("stop")
        self.stopping = True

    def configuration(self, server):
        path = self.store.directory(server) / "server.properties"
        result = {"difficulty": "normal", "gamemode": "survival", "white-list": "false", "view-distance": "8", "simulation-distance": "6"}
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    result[key.strip()] = value.strip()
        return result

    def configure(self, server, values, ram, slots, task):
        self.launcher.ensure_profile_idle(server)
        valid = {"difficulty": {"peaceful", "easy", "normal", "hard"}, "gamemode": {"survival", "creative", "adventure", "spectator"},
                 "white-list": {"true", "false"}}
        for key, value in values.items():
            if key in valid and value in valid[key]: continue
            if key in ("view-distance", "simulation-distance") and str(value).isdigit() and 2 <= int(value) <= 32: continue
            raise LauncherError("Geçersiz sunucu ayarı.")
        if not 1024 <= ram <= 65536 or not 1 <= slots <= 100:
            raise LauncherError("Sunucu belleği veya oyuncu sınırı geçersiz.")
        self.launcher.snapshots.before_change(server, task, "Sunucu ayarları öncesi")
        configuration = self.configuration(server)
        configuration.update(values)
        configuration["max-players"] = str(slots)
        path = self.store.directory(server) / "server.properties"
        temporary = path.with_suffix(".tmp")
        temporary.write_text("\n".join(k + "=" + v for k, v in configuration.items()) + "\n", encoding="utf-8")
        temporary.replace(path)
        server.update(ram=ram, slots=slots)
        self.store.save()
        return "Sunucu ayarları kaydedildi. Bir sonraki açılışta uygulanır."

    def whitelist(self, server, name, add=True):
        from core import offline_account, read_json
        offline = offline_account(name)
        if self.running:
            if self.active_id != server["id"] or not self.ready.is_set():
                raise LauncherError("Seçilen sunucu hazır değil.")
            self.command("whitelist " + ("add " if add else "remove ") + name)
            return "İstek sunucuya gönderildi; sonucu konsoldan kontrol edin."
        if not server.get("username_players"):
            raise LauncherError("Microsoft doğrulamalı sunucuda oyuncuyu sunucu çalışırken ekleyin; kimliği sunucu doğrulasın.")
        path = self.store.directory(server) / "whitelist.json"
        entries = [v for v in read_json(path, []) if v.get("name", "").casefold() != name.casefold()]
        if add:
            import uuid
            entries.append({"name": name, "uuid": str(uuid.UUID(offline["id"]))})
        atomic_json(path, entries)
        return "İzin verilen oyuncu listesi güncellendi."

    def drain(self):
        lines = []
        for _ in range(250):
            try: lines.append(self.output.get_nowait())
            except queue.Empty: break
        return lines

    @staticmethod
    def lan_addresses(port):
        try:
            ips = sorted({record[4][0] for record in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                          if not record[4][0].startswith(("127.", "169.254."))})
            return [f"{ip}:{port}" for ip in ips]
        except OSError:
            return []

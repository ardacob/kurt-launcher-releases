"""Free Minecraft Java relay and self-contained, credential-free invitations."""
from __future__ import annotations
import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import struct
import subprocess
import sys
import time
import uuid
import webbrowser
import zlib
from pathlib import Path

import requests
from PySide6.QtCore import QIODevice
from PySide6.QtNetwork import QLocalSocket
from core import APP_VERSION, LOADERS, LauncherError, Task, safe_file

AGENT_VERSION = "1.2.0"
AGENT_SHA256 = "e8dff30a9269a10d2c6786c95a0618567772e441d07dd7ebe3c1a37d3f35534d"
API = "https://api.playit.gg"


def split_endpoint(address):
    if not isinstance(address, str) or len(address) > 260 or not re.fullmatch(r"[a-zA-Z0-9.-]+(?::[0-9]{1,5})?", address):
        raise LauncherError("Geçersiz tünel adresi.")
    host, separator, port = address.rpartition(":")
    if not separator:
        host, port = address, "25565"
    host = host.lower().rstrip(".")
    port = int(port)
    if not 1 <= port <= 65535:
        raise LauncherError("Geçersiz bağlantı portu.")
    try:
        public = ipaddress.ip_address(host).is_global
    except ValueError:
        labels_valid = all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split("."))
        public = labels_valid and any(host.endswith("." + domain) for domain in ("ply.gg", "joinmc.link", "playit.gg"))
    if not public or ".." in host or host.startswith("-"):
        raise LauncherError("Davet adresi desteklenen genel Playit adresi değil.")
    return host, port


def encode_invite(address, server):
    host, port = split_endpoint(address)
    version = safe_file(server["version"])
    loader = server["loader"]
    if loader not in ("vanilla", "fabric"):
        raise LauncherError("Bu sunucu yükleyicisi davet için desteklenmiyor.")
    pinned = server.get("loader_version")
    if pinned:
        safe_file(pinned)
    raw = json.dumps([host, port, version, loader, pinned], separators=(",", ":"), ensure_ascii=True).encode()
    prefix = "KURT1-"
    if server.get("mod_manifest"):
        raw = json.dumps([host, port, version, loader, pinned, server["mod_manifest"]], separators=(",", ":"), ensure_ascii=True).encode()
        if len(raw) > 128000:
            raise LauncherError("Mod listesi davet kodu için çok büyük. Mod listesini dosya olarak paylaşın.")
        raw = zlib.compress(raw)
        prefix = "KURT2-"
    packet = raw + struct.pack(">I", zlib.crc32(raw))
    return prefix + base64.urlsafe_b64encode(packet).decode().rstrip("=")


def decode_invite(code):
    if not isinstance(code, str) or len(code) > 180000:
        raise LauncherError("Geçersiz davet kodu.")
    code = code.strip()
    if not re.fullmatch(r"KURT[12]-[A-Za-z0-9_-]+", code):
        raise LauncherError("Kurt Launcher davet kodunu eksiksiz yapıştırın.")
    try:
        value = code[6:]
        packet = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        raw, checksum = packet[:-4], packet[-4:]
        if len(checksum) != 4 or struct.pack(">I", zlib.crc32(raw)) != checksum:
            raise ValueError("checksum")
        if code.startswith("KURT2-"):
            decompress = zlib.decompressobj()
            raw = decompress.decompress(raw, 128001)
            if len(raw) > 128000 or not decompress.eof or decompress.unused_data:
                raise ValueError("size")
        data = json.loads(raw)
        expected = 6 if code.startswith("KURT2-") else 5
        if not isinstance(data, list) or len(data) != expected:
            raise ValueError("shape")
        host, port, version, loader, pinned = data[:5]
        if type(port) is not int or not isinstance(version, str) or not (pinned is None or isinstance(pinned, str)):
            raise ValueError("types")
        host, port = split_endpoint(f"{host}:{port}")
        safe_file(version)
        if loader not in ("vanilla", "fabric") or (pinned and not safe_file(pinned)):
            raise ValueError("loader")
        result = {"address": f"{host}:{port}", "version": version, "loader": loader, "loader_version": pinned}
        if expected == 6:
            metadata = data[5]
            if not isinstance(metadata, dict) or metadata.get("version") != version or metadata.get("loader") != loader or metadata.get("loader_version") != pinned:
                raise ValueError("mods")
            result["mod_manifest"] = metadata
        return result
    except (ValueError, TypeError, UnicodeError, KeyError, zlib.error) as exc:
        raise LauncherError("Davet kodu eksik veya değiştirilmiş. Arkadaşınızdan tekrar kopyalayın.") from exc


class RelayError(LauncherError):
    pass


class PlayitManager:
    def __init__(self, launcher):
        self.launcher, self.store = launcher, launcher.store
        self.process = None
        self.pipe = r"\\.\pipe\kurt-playit-" + uuid.uuid4().hex
        self.private = self.store.root / "network" / "private"
        self.secret_file = self.private / "session.toml"
        self.sharing_server_id = None
        self.address = None
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"KurtLauncher/{APP_VERSION}"

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    @property
    def vault_key(self):
        return "KurtLauncher-Playit-" + hashlib.sha256(str(self.store.root).encode()).hexdigest()[:20]

    def secret(self):
        return self.launcher.account.vault.get_password(self.vault_key, "agent")

    def protect_directory(self):
        if sys.platform != "win32":
            raise RelayError("Bu tünel derlemesi Windows x64 içindir.")
        self.private.mkdir(parents=True, exist_ok=True)
        system = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        identity = subprocess.run([str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
                                  capture_output=True, text=True, timeout=5, creationflags=flags)
        sid = re.search(r"S-1-[0-9-]+", identity.stdout)
        if identity.returncode or not sid:
            raise RelayError("Tünel anahtarı için özel klasör izinleri hazırlanamadı.")
        result = subprocess.run([str(system / "icacls.exe"), str(self.private), "/inheritance:r", "/grant:r",
                                 "*" + sid.group() + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                                capture_output=True, timeout=5, creationflags=flags)
        if result.returncode:
            raise RelayError("Tünel klasörünün erişim izinleri ayarlanamadı.")

    def ipc(self, command, **fields):
        connection = QLocalSocket()
        try:
            connection.connectToServer(self.pipe, QIODevice.ReadWrite)
            if connection.state() != QLocalSocket.ConnectedState and not connection.waitForConnected(1500):
                raise RelayError("Ücretsiz bağlantı yardımcısına ulaşılamadı.")
            request_id = secrets.randbelow(2**31)
            request = {"ipc_version": 2, "request_id": request_id, "request": {"type": command, **fields}}
            connection.write(json.dumps(request).encode() + b"\n")
            if connection.bytesToWrite() and not connection.waitForBytesWritten(1500):
                raise RelayError("Tünel komutu iletilemedi.")
            buffer = b""
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if not connection.bytesAvailable():
                    connection.waitForReadyRead(250)
                buffer += bytes(connection.readAll())
                if len(buffer) > 1024*1024:
                    raise RelayError("Tünel yanıtı beklenen boyutu aşıyor.")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    item = json.loads(line)
                    if item.get("message_kind") != "response":
                        continue
                    envelope = item["data"]
                    if envelope.get("request_id") != request_id:
                        continue
                    if envelope.get("ipc_version") != 2:
                        raise RelayError("Tünel yardımcısının sürümü uyumsuz.")
                    response = envelope["response"]
                    if response.get("type") == "error":
                        raise RelayError("Tünel yardımcısı işlemi tamamlayamadı. Bağlantıyı yeniden başlatın.")
                    return response.get("data")
            raise RelayError("Tünel yardımcısı yanıt vermedi.")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RelayError("Tünel yardımcısının yanıtı okunamadı.") from exc
        finally:
            connection.abort()

    def cloud(self, path, payload, secret=None):
        # Deliberately no billing, subscription or purchase endpoints.
        allowed = {"/claim/setup", "/claim/exchange", "/tunnels/list", "/tunnels/create"}
        if path not in allowed:
            raise RelayError("Desteklenmeyen tünel işlemi.")
        headers = {"Authorization": "Agent-Key " + secret} if secret else {}
        try:
            response = self.session.post(API + path, json=payload, headers=headers, timeout=(10, 25))
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as exc:
            raise RelayError("Ücretsiz tünel servisine ulaşılamadı. İnterneti kontrol edin.") from exc
        if result.get("status") != "success":
            reason = json.dumps(result.get("data", ""))
            if "Premium" in reason or "Limit" in reason or "limit" in reason:
                raise RelayError("Ücretsiz tünel kotası kullanılamıyor. Ücretli işlem yapılmadı; Playit panelinden kullanılmayan tünelleri kaldırın.")
            if "Verified" in reason:
                raise RelayError("Ücretsiz Playit hesabınızın e-posta doğrulamasını tamamlayıp yeniden deneyin.")
            raise RelayError("Playit işlemi reddetti. Ücretsiz panelde Minecraft Java tünelini kontrol edin; hiçbir satın alma yapılmadı.")
        return result.get("data")

    def start_agent(self, task):
        if self.running:
            status = self.ipc("get_status")
            key = self.secret()
            if key and not status.get("has_secret"):
                answer = self.ipc("set_secret", secret=key)
                self.secret_file.unlink(missing_ok=True)
                if not answer.get("accepted"):
                    raise RelayError("Kaydedilen ücretsiz bağlantı yardımcısına aktarılamadı.")
            return
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        executable = base / "assets/playit/playitd.exe"
        if not executable.is_file() or hashlib.sha256(executable.read_bytes()).hexdigest() != AGENT_SHA256:
            raise RelayError("İmzalı tünel yardımcısı eksik veya değiştirilmiş. Launcher paketini yeniden çıkarın.")
        self.protect_directory()
        self.secret_file.unlink(missing_ok=True)
        self.process = subprocess.Popen([str(executable), "--socket-path", self.pipe, "--secret-path", str(self.secret_file)],
                                        cwd=self.private, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 8
        try:
            while time.monotonic() < deadline:
                task.check()
                try:
                    self.ipc("get_status")
                    key = self.secret()
                    if key:
                        response = self.ipc("set_secret", secret=key)
                        if not response.get("accepted"):
                            raise RelayError("Tünel anahtarı kabul edilmedi.")
                        self.secret_file.unlink(missing_ok=True)
                    return
                except RelayError:
                    if not self.running:
                        break
                    task.cancel.wait(.2)
            raise RelayError("Ücretsiz bağlantı yardımcısı başlatılamadı.")
        except Exception:
            self.stop()
            raise

    def setup(self, task):
        self.start_agent(task)
        if self.secret():
            return "Ücretsiz hesap bağlantısı zaten hazır. Sunucuyu başlatıp Davet oluştur düğmesini kullanın."
        code = secrets.token_hex(5)
        request = {"code": code, "agent_type": "assignable", "version": "Kurt Launcher " + APP_VERSION}
        self.cloud("/claim/setup", request)
        url = "https://playit.gg/claim/" + code
        # Browser authorization is done by the user; no automatic signup/terms consent.
        webbrowser.open(url)
        task.status("Tarayıcıda ücretsiz Playit bağlantısını onaylayın; satın alma gerekmez…")
        deadline = time.monotonic() + 300
        try:
            while time.monotonic() < deadline:
                task.check()
                status = self.cloud("/claim/setup", request)
                if status == "UserRejected":
                    raise RelayError("Ücretsiz bağlantı tarayıcıda onaylanmadı.")
                if status == "UserAccepted":
                    task.check()
                    result = self.cloud("/claim/exchange", {"code": code})
                    task.check()
                    key = result.get("secret_key", "")
                    if not re.fullmatch(r"[0-9a-fA-F]{32,512}", key):
                        raise RelayError("Tünel anahtarı doğrulanamadı.")
                    self.launcher.account.vault.set_password(self.vault_key, "agent", key)
                    answer = self.ipc("set_secret", secret=key)
                    self.secret_file.unlink(missing_ok=True)
                    if not answer.get("accepted"):
                        raise RelayError("Tünel anahtarı yardımcısına aktarılamadı.")
                    return "Ücretsiz bağlantı onaylandı. Sunucuyu başlatıp Davet oluştur düğmesini kullanın."
                task.cancel.wait(2)
            raise RelayError("Tarayıcı onayı zaman aşımına uğradı. Ücretsiz kurulumu yeniden açın.")
        finally:
            self.secret_file.unlink(missing_ok=True)

    @staticmethod
    def matching_tunnel(tunnels, agent_id, port):
        for tunnel in tunnels:
            origin = tunnel.get("origin") or {}
            local = origin.get("data") or {}
            if (tunnel.get("tunnel_type") == "minecraft-java" and tunnel.get("port_type") == "tcp"
                    and origin.get("type") == "agent" and local.get("agent_id") == agent_id
                    and local.get("local_port") == port and local.get("local_ip") in ("127.0.0.1", "::1")):
                return tunnel
        return None

    @staticmethod
    def live_address(state, port):
        if state.get("state") != "running":
            return None
        for item in state.get("data", {}).get("tunnels", []):
            if item.get("is_disabled") or item.get("destination") not in (f"127.0.0.1:{port}", f"[::1]:{port}"):
                continue
            try:
                host, public_port = split_endpoint(item.get("display_address", ""))
                return f"{host}:{public_port}"
            except LauncherError:
                continue
        return None

    def publish(self, server, task):
        self.address = None
        self.sharing_server_id = None
        self.start_agent(task)
        key = self.secret()
        if not key:
            raise RelayError("Önce Ücretsiz bağlantıyı kur düğmesiyle tarayıcı onayını tamamlayın.")
        task.status("Ücretsiz Minecraft Java tüneli hazırlanıyor…")
        deadline = time.monotonic() + 45
        agent_id = None
        while time.monotonic() < deadline:
            task.check()
            state = self.ipc("get_state")
            if state.get("state") == "running":
                agent_id = state["data"]["agent_id"]
                existing = self.live_address(state, server["port"])
                if existing:
                    self.address, self.sharing_server_id = existing, server["id"]
                    return encode_invite(existing, server)
                break
            task.cancel.wait(1)
        if not agent_id:
            raise RelayError("Tünel servisine henüz bağlanılamadı. Biraz sonra tekrar deneyin.")
        listing = self.cloud("/tunnels/list", {"agent_id": agent_id, "tunnel_id": None}, key)
        tunnel = self.matching_tunnel(listing.get("tunnels", []), agent_id, server["port"])
        if not tunnel:
            quota = listing.get("tcp_alloc", {})
            if isinstance(quota.get("allowed"), int) and quota.get("claimed", 0) >= quota["allowed"]:
                raise RelayError("Ücretsiz tünel kotası dolu. Playit panelinden kullanılmayan bir tüneli kaldırın; satın alma yapılmaz.")
            self.cloud("/tunnels/create", {"name": "Kurt - " + server["name"][:40], "tunnel_type": "minecraft-java",
                       "port_type": "tcp", "port_count": 1, "origin": {"type": "agent", "data": {
                           "agent_id": agent_id, "local_ip": "127.0.0.1", "local_port": server["port"]}},
                       "enabled": True, "alloc": {"type": "region", "details": {"region": "global"}},
                       "firewall_id": None, "proxy_protocol": None}, key)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            task.check()
            listing = self.cloud("/tunnels/list", {"agent_id": agent_id, "tunnel_id": None}, key)
            tunnel = self.matching_tunnel(listing.get("tunnels", []), agent_id, server["port"])
            allocation = (tunnel or {}).get("alloc") or {}
            if allocation.get("status") == "disabled":
                raise RelayError("Ücretsiz tünel etkin değil. Playit panelinde ücretsiz kotayı kontrol edin; ücretli pakete geçiş yapılmaz.")
            if allocation.get("status") == "allocated":
                info = allocation["data"]
                address = f"{info['assigned_domain']}:{info['port_start']}"
                split_endpoint(address)
                # Require the daemon to have actually loaded this origin, not just a cloud allocation.
                live = self.ipc("get_state")
                if live.get("state") == "running" and any(
                        not item.get("is_disabled") and item.get("destination") in (f"127.0.0.1:{server['port']}", f"[::1]:{server['port']}")
                        for item in live.get("data", {}).get("tunnels", [])):
                    self.address, self.sharing_server_id = address, server["id"]
                    return encode_invite(address, server)
            task.cancel.wait(2)
        raise RelayError("Tünel henüz hazır değil. Biraz sonra Davet oluştur düğmesine tekrar basın.")

    def stop(self):
        self.address = None
        self.sharing_server_id = None
        if self.running:
            try: self.ipc("stop")
            except LauncherError: pass
            try: self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try: self.process.wait(timeout=2)
                except subprocess.TimeoutExpired: self.process.kill()
        self.secret_file.unlink(missing_ok=True)

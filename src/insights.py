"""Offline diagnostics, hardware recommendations and local collections."""
from __future__ import annotations
import ctypes
import json
import re
import shutil
import time
from pathlib import Path
from core import LauncherError, atomic_json


def redact(text):
    text = re.sub(r"(?i)(--(?:accessToken|clientToken|uuid|username)\s+)(\S+)", r"\1[GİZLENDİ]", text)
    text = re.sub(r'(?i)((?:access_token|refresh_token|authorization|client_secret|password|secret_key)[\s\"\x27:=]+)([^\s\",}]+)', r'\1[GİZLENDİ]', text)
    text = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[TOKEN GİZLENDİ]", text)
    text = re.sub(r"(?i)[A-Z]:[\\/]Users[\\/][^\\/\r\n]+", r"C:/Users/[KULLANICI]", text)
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?\b", "[IP GİZLENDİ]", text)
    return text


def diagnose(text):
    rules = [
        (r"UnsupportedClassVersionError|class file version", "Java sürümü uygun görünmüyor", "Ayarlar'daki özel Java yolunu kaldırıp Kur / onar işlemini çalıştırın. Modun istediği Java sürümünü kontrol edin."),
        (r"OutOfMemoryError|Could not reserve enough space|insufficient memory|Native memory allocation", "Bellek sorunu olabilir", "RAM önerisini kontrol edin. Arka plandaki uygulamaları kapatın; bilgisayardaki belleğin tamamını Minecraft'a ayırmayın."),
        (r"requires .*(?:missing|not installed)|Missing.*dependenc|depends on.*missing|ModResolutionException|Incompatible mods found", "Mod sürümü veya bağımlılık sorunu olabilir", "Kurulu modların Minecraft ve yükleyici sürümlerini kontrol edin. Eksik bağımlılığı kurun; gerekirse son değişiklik öncesi yedeğe dönün."),
        (r"DuplicateModsFoundException|Duplicate mod|duplicate.*mod id", "Aynı modun birden fazla kopyası olabilir", "Kurulu modlar ve mods klasöründe aynı modun eski/yeni kopyalarını kontrol edin. Bir kopyayı kapatın."),
        (r"GLFW error 65542|does not support OpenGL|Failed to create window|Pixel format not accelerated", "Grafik sürücüsü veya OpenGL sorunu olabilir", "Ekran kartı üreticisinin resmî sürücüsünü kontrol edin. Bu Minecraft sürümünün donanım gereksinimleriyle bilgisayarınızı karşılaştırın."),
        (r"Failed to bind to port|Address already in use|BindException", "Sunucu portu kullanımda olabilir", "Açık diğer sunucuyu kapatın veya farklı port seçin."),
        (r"Invalid session|Failed to verify username|Not authenticated with Minecraft", "Sunucunun hesap doğrulamasıyla giriş yöntemi uyuşmuyor", "Hesap doğrulaması isteyen sunucu için oyuna sahip Microsoft hesabıyla giriş yapın. Sunucu yöneticisinin ayarlarını kontrol edin."),
        (r"MixinApplyError|MixinTransformerError|InjectionError|NoSuchMethodError", "Modlar arasında çalışma zamanı uyuşmazlığı olabilir", "Son eklenen modları ve güncelleme geçmişini kontrol edin. Önceki profil yedeğiyle karşılaştırın; bu kayıt tek başına sorumlu modu kesin olarak belirlemez."),
        (r"Connection refused|Connection timed out|UnknownHostException", "Sunucu bağlantısı kurulamadı", "Sunucunun ve paylaşım bağlantısının açık olduğunu kontrol edin. Yeni davet isteyin; adresi ve ağ bağlantısını kontrol edin."),
    ]
    found = [{"title": title, "advice": advice} for pattern, title, advice in rules if re.search(pattern, text, re.I)]
    return found or [{"title": "Bilinen bir hata kalıbı bulunamadı", "advice": "En yeni çökme raporunu ve son mod değişikliklerini inceleyin. Hata yardımcısı tüm sorunları kesin olarak teşhis edemez."}]


def read_logs(directory):
    directory = Path(directory)
    paths = [directory / "launcher-game.log", directory / "launcher-server.log", directory / "logs/latest.log"]
    crash = directory / "crash-reports"
    if crash.exists():
        paths.extend(sorted(crash.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:1])
    chunks = []
    for path in paths:
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 512 * 1024))
                chunks.append(f"--- {path.name} ---\n" + stream.read().decode("utf-8", errors="replace"))
    return "\n\n".join(chunks)


def hardware(root):
    total = available = 0
    try:
        class Memory(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in ("total", "available", "page", "freepage", "virtual", "freevirtual", "extended")]
        info = Memory()
        info.length = ctypes.sizeof(info)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
            total, available = info.total // 1048576, info.available // 1048576
    except (AttributeError, OSError):
        pass
    recommended = max(1024, min(6144, (total // 2 // 512) * 512, ((available - 1024) // 512) * 512)) if total else 2048
    return {"total": total, "available": available, "recommended": recommended,
            "disk_free": shutil.disk_usage(root).free}


PRESETS = {
    "low": {"renderDistance": "6", "simulationDistance": "4", "graphicsMode": "0", "particles": "2", "maxFps": "60"},
    "balanced": {"renderDistance": "10", "simulationDistance": "6", "graphicsMode": "1", "particles": "1", "maxFps": "120"},
    "high": {"renderDistance": "16", "simulationDistance": "10", "graphicsMode": "1", "particles": "0", "maxFps": "120"},
}


def apply_preset(store, profile, preset):
    if preset not in PRESETS:
        raise LauncherError("Geçersiz görüntü ayarı.")
    path = store.directory(profile) / "options.txt"
    values = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    settings = dict(PRESETS[preset])
    # Classic versions use fancyGraphics; keep the rest of options.txt untouched.
    settings["fancyGraphics"] = "false" if preset == "low" else "true"
    output = []
    for line in values:
        key = line.split(":", 1)[0]
        if key in settings:
            output.append(key + ":" + settings.pop(key))
        else:
            output.append(line)
    output.extend(k + ":" + v for k, v in settings.items())
    temporary = path.with_suffix(".kurt-tmp")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    temporary.replace(path)
    profile["graphics_preset"] = preset
    store.save()


class Collections:
    def __init__(self, store):
        self.store = store
        from core import read_json
        self.data = read_json(store.root / "collections.json", {"Favoriler": {}})

    def add(self, collection, hit):
        name = collection.strip()
        if not name or len(name) > 64:
            raise LauncherError("Koleksiyon adı 1–64 karakter olmalı.")
        pid = str(hit.get("project_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", pid):
            raise LauncherError("Geçersiz mod kimliği.")
        self.data.setdefault(name, {})[pid] = {key: hit.get(key, "") for key in ("project_id", "title", "description", "icon_url")}
        atomic_json(self.store.root / "collections.json", self.data)

    def remove(self, collection, pid):
        self.data.get(collection, {}).pop(pid, None)
        atomic_json(self.store.root / "collections.json", self.data)


class TransferStats:
    def __init__(self):
        self.started = time.monotonic()
        self.current = self.total = 0
        self.unit = "items"
        self.queue = ""
        self.pending = []

    def begin(self, total=0, unit="bytes"):
        self.started, self.current, self.total, self.unit = time.monotonic(), 0, total, unit
        self.base = 0

    def text(self):
        if self.unit != "bytes":
            return self.queue
        elapsed = time.monotonic() - self.started
        speed = max(0,self.current-getattr(self,'base',0)) / elapsed if elapsed > .2 else 0
        size = lambda n: f"{n / 1048576:.1f} MB"
        text = size(self.current) + (" / " + size(self.total) if self.total else " / boyut bilinmiyor")
        if speed > 0:
            text += "  •  " + size(speed) + "/sn"
            text += f"  •  ~{max(0, int((self.total-self.current)/speed))} sn" if self.total else "  •  süre hesaplanamıyor"
        return text + ("  •  " + self.queue if self.queue else "")

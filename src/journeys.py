"""Local session history, external game imports and bounded Java server status."""
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import tempfile
import time
import uuid

from core import LauncherError, Task, atomic_json, read_json, safe_file, LOADERS
from profile_data import session_locks, verified_copy


class Sessions:
    def __init__(self, store):
        self.path = store.root / 'sessions.json'
        self.rows = read_json(self.path, [])
        self.active = None
        for row in self.rows:
            if row.get('state') == 'running':
                row['state'] = 'interrupted'
        self.clock = time.monotonic

    def start(self, profile):
        self.active = {'id': uuid.uuid4().hex, 'profile': profile['id'], 'name': profile['name'],
                       'version': profile['version'], 'started': time.time(), 'seconds': 0, 'state': 'running'}
        self.tick = self.clock()
        self.rows.append(self.active)
        self.save()

    def save(self):
        atomic_json(self.path, self.rows)

    def update(self, process=None, closing=False):
        if self.active is None:
            return
        self.active['seconds'] = max(0, int(self.clock() - self.tick))
        if closing or process is None or process.poll() is not None:
            self.active['state'] = 'launcher_closed' if closing else 'completed'
            self.active['ended'] = time.time()
            if not closing and process is not None:
                self.active['exit_code'] = process.returncode
            self.active = None
        self.save()

    def summary(self):
        totals = {}
        for row in self.rows:
            entry = totals.setdefault(row['profile'], {'name': row['name'], 'seconds': 0, 'sessions': 0})
            entry['seconds'] += max(0, int(row.get('seconds', 0)))
            entry['sessions'] += 1
        return sorted(totals.values(), key=lambda r: r['seconds'], reverse=True)


def server_endpoint(value):
    value = value.strip()
    if len(value) > 260 or any(c.isspace() for c in value):
        raise LauncherError('Geçerli bir sunucu adresi yazın.')
    match = re.fullmatch(r'(?:\[([0-9a-fA-F:]+)\]|([a-zA-Z0-9._-]+))(?::([0-9]{1,5}))?', value)
    if not match:
        raise LauncherError('Adres biçimi: sunucu.example:25565 veya [IPv6]:25565')
    host, port = match[1] or match[2], int(match[3] or 25565)
    if not 1 <= port <= 65535 or host.startswith('-'):
        raise LauncherError('Sunucu portu 1–65535 arasında olmalı.')
    return host, port


def varint(n):
    n &= 0xffffffff
    out = bytearray()
    while True:
        part = n & 127
        n >>= 7
        out.append(part | (128 if n else 0))
        if not n: return bytes(out)


def packet(payload):
    return varint(len(payload)) + payload


def server_status(address, task=None):
    task = task or Task()
    host, port = server_endpoint(address)
    deadline = time.monotonic() + 7
    with socket.create_connection((host, port), timeout=3) as stream:
        def read(n):
            data = bytearray()
            while len(data) < n:
                task.check()
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise TimeoutError('Sunucu yanıt süresi doldu.')
                stream.settimeout(min(3, remaining))
                value = stream.recv(n - len(data))
                if not value: raise ValueError('Eksik sunucu yanıtı.')
                data.extend(value)
            return bytes(data)
        def integer():
            n = 0
            for shift in range(0, 35, 7):
                b = read(1)[0]; n |= (b & 127) << shift
                if not b & 128: return n
            raise ValueError('Geçersiz sunucu paketi.')
        hostname = host.encode('utf-8')
        stream.sendall(packet(b'\x00' + varint(-1) + varint(len(hostname)) + hostname + struct.pack('>H', port) + b'\x01') + b'\x01\x00')
        length = integer()
        if not 3 <= length <= 1024 * 1024: raise ValueError('Sunucu yanıtı çok büyük.')
        raw = read(length)
        if raw[0] != 0: raise ValueError('Geçersiz durum yanıtı.')
        size = 0; offset = 1
        for shift in range(0, 35, 7):
            if offset >= len(raw): raise ValueError('Eksik durum yanıtı.')
            b = raw[offset]; offset += 1; size |= (b & 127) << shift
            if not b & 128: break
        else: raise ValueError('Geçersiz JSON uzunluğu.')
        if size != len(raw) - offset: raise ValueError('Geçersiz durum uzunluğu.')
        info = json.loads(raw[offset:])
        if not isinstance(info, dict): raise ValueError('Geçersiz durum verisi.')
        def chat(value, depth=0):
            if depth > 8: return ''
            if isinstance(value, str): return value[:2000]
            if isinstance(value, list): return ''.join(chat(v, depth+1) for v in value[:30])[:2000]
            if isinstance(value, dict): return (str(value.get('text', ''))[:2000] + chat(value.get('extra', []), depth+1))[:2000]
            return ''
        ping = None
        stamp = struct.pack('>q', int(time.time()*1000))
        started = time.monotonic()
        try:
            stream.sendall(packet(b'\x01' + stamp))
            if integer() == 9 and read(9) == b'\x01' + stamp:
                ping = round((time.monotonic() - started)*1000)
        except (OSError, ValueError): pass
        version, players = info.get('version', {}), info.get('players', {})
        return {'version': str(version.get('name', '?'))[:100], 'protocol': version.get('protocol'),
                'online': int(players.get('online', 0)), 'max': int(players.get('max', 0)),
                'description': re.sub('§.', '', chat(info.get('description', ''))), 'ping': ping}


class FavoriteServers:
    def __init__(self, store):
        self.store, self.path = store, store.root / 'favorite-servers.json'

    def list(self): return read_json(self.path, [])

    def add(self, name, address, profile):
        server_endpoint(address)
        if not name.strip() or len(name.strip()) > 64 or profile not in {p['id'] for p in self.store.profiles}:
            raise LauncherError('Sunucu adı ve oyuncu profili seçin.')
        rows = self.list()
        entry = {'id': uuid.uuid4().hex, 'name': name.strip(), 'address': address.strip(), 'profile': profile}
        rows.append(entry); atomic_json(self.path, rows)
        return entry

    def remove(self, identity):
        atomic_json(self.path, [r for r in self.list() if r['id'] != identity])


class ExternalImports:
    """Copy only game content. Accounts, tokens, launch arguments and binaries stay outside."""
    CONTENT = {'mods', 'config', 'defaultconfigs', 'saves', 'resourcepacks', 'shaderpacks', 'screenshots',
               'options.txt', 'optionsof.txt', 'optionsshaders.txt', 'servers.dat', 'servers.dat_old'}

    def __init__(self, launcher):
        self.launcher, self.store = launcher, launcher.store

    def discover(self, selected, task):
        root = Path(selected).resolve()
        if not root.is_dir(): raise LauncherError('Oyun veya launcher klasörünü seçin.')
        candidates = [root]
        for base in (root, root / 'instances'):
            if base.is_dir():
                candidates.extend(p for p in list(base.iterdir())[:200] if p.is_dir() and not p.is_symlink())
        rows = []; seen = set()
        for instance in candidates:
            task.check()
            if not instance.resolve().is_relative_to(root): continue
            game = next((p for p in (instance / '.minecraft', instance / 'minecraft', instance)
                         if p.is_dir() and any((p / n).exists() for n in ('saves','mods','options.txt','versions'))), None)
            if not game or game.resolve() in seen: continue
            # Reject every reparse point before following paths for a preview or a copy.
            for part in (instance, game):
                if part.is_symlink() or getattr(part.lstat(), 'st_file_attributes', 0) & 1024:
                    raise LauncherError('Aktarım kaynağı bağlantı/junction olamaz.')
            seen.add(game.resolve())
            versions = []
            components = read_json(instance / 'mmc-pack.json', {}).get('components', [])
            if components:
                minecraft = next((c.get('version') for c in components if c.get('uid') == 'net.minecraft'), '')
                loader, pinned = 'vanilla', None
                for component in components:
                    identity = component.get('uid', '')
                    for token, value in (('fabric-loader','fabric'),('quilt-loader','quilt'),('forge','forge'),('neoforge','neoforge')):
                        if token in identity:
                            loader, pinned = value, component.get('version')
                if minecraft: versions.append((minecraft, loader, pinned))
            official = read_json(game / 'launcher_profiles.json', {}).get('profiles', {})
            for p in official.values():
                if p.get('gameDir') and Path(os.path.expandvars(p['gameDir'])).resolve() != game.resolve(): continue
                version = p.get('lastVersionId', '')
                if version and not version.startswith('latest-'): versions.append((version, 'vanilla', None))
            if not versions and (game / 'versions').is_dir():
                versions = [(p.name, 'vanilla', None) for p in list((game / 'versions').iterdir())[:100]
                            if p.is_dir() and (p / (p.name+'.json')).is_file()]
            if not versions: versions = [('', 'vanilla', None)]
            for version, loader, pinned in dict.fromkeys(versions):
                if version: safe_file(version)
                metadata = read_json(game / 'versions' / version / (version+'.json'), {}) if version else {}
                if metadata.get('inheritsFrom'):
                    version = metadata['inheritsFrom']
                    safe_file(version)
                    for lib in metadata.get('libraries', []):
                        parts = lib.get('name', '').split(':')
                        if len(parts) >= 3 and parts[1] in ('fabric-loader','quilt-loader','forge','neoforge'):
                            loader = {'fabric-loader':'fabric','quilt-loader':'quilt'}.get(parts[1],parts[1])
                            pinned = parts[2]
                            if loader == 'forge' and pinned.startswith(version+'-'): pinned = pinned[len(version)+1:]
                rows.append({'source': str(game), 'name': instance.name, 'version': version, 'loader': loader,
                             'loader_version': pinned, 'worlds': (game/'saves').is_dir(), 'mods':(game/'mods').is_dir()})
        return rows

    def install(self, info, name, version, loader, worlds, task):
        self.launcher.ensure_idle()
        safe_file(version)
        if loader not in LOADERS or not name.strip() or len(name.strip()) > 64:
            raise LauncherError('Profil adı, Minecraft sürümü ve yükleyiciyi kontrol edin.')
        source = Path(info['source']).resolve()
        if source.is_relative_to(self.store.root) or self.store.root.is_relative_to(source):
            raise LauncherError('Bu klasör zaten Kurt Launcher arşivine ait.')
        parent = self.store.root / 'instances'; parent.mkdir(exist_ok=True)
        profile = {'id':uuid.uuid4().hex, 'name':name.strip(), 'version':version, 'loader':loader,
                   'loader_version':info.get('loader_version') if loader==info.get('loader') and version==info.get('version') else None,
                   'installed':None}
        destination = parent / profile['id']
        def include(path):
            first = path.split('/')[0].casefold()
            return first in self.CONTENT and (worlds or first != 'saves')
        with session_locks(source), tempfile.TemporaryDirectory(prefix='.external-import-', dir=parent) as temp:
            stage = Path(temp) / 'game'
            verified_copy(source, stage, task, include)
            task.check(); stage.rename(destination)
            try: atomic_json(self.store.root / 'profiles.json', self.store.profiles + [profile])
            except Exception:
                import shutil
                assert destination.resolve().parent == parent.resolve()
                shutil.rmtree(destination); raise
            self.store.profiles.append(profile)
        return profile


def detect_gpu():
    if os.name != 'nt': return []
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
        '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion | ConvertTo-Json -Compress'],
        capture_output=True, timeout=20, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        data = json.loads(result.stdout.decode('utf-8-sig'))
        return [str(r.get('Name',''))[:200] for r in (data if isinstance(data,list) else [data]) if r.get('Name')]
    except (ValueError, UnicodeError, AttributeError): return []


def gpu_tier(names, ram_mb):
    """Conservative starting preset, never an FPS or VRAM estimate."""
    names = ' '.join(names).casefold()
    if not names or ram_mb and ram_mb < 8000: return 'low'
    if any(t in names for t in ('rtx 40','rtx 50','rtx 60','rx 7','rx 9','rx 8')): return 'high'
    if any(t in names for t in ('geforce','radeon rx','arc a','arc b')): return 'medium'
    return 'low'

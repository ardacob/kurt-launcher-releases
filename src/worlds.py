"""Read-only bounded Java NBT metadata and verified per-world operations."""
from datetime import datetime, timezone
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import uuid
import zipfile

from core import LauncherError, Task, safe_file
from profile_data import session_locks, verified_copy
from snapshots import digest, regular_files, relative_path


def level_metadata(path):
    """Only read NBT; never convert or rewrite a world's game data."""
    try:
        with gzip.open(path, 'rb') as stream:
            raw = stream.read(16 * 1024**2 + 1)
        if len(raw) > 16 * 1024**2:
            raise ValueError('NBT size')
        stream, nodes = io.BytesIO(raw), [0]
        def take(n):
            value = stream.read(n)
            if len(value) != n: raise ValueError('truncated NBT')
            return value
        def number(fmt): return struct.unpack('>' + fmt, take(struct.calcsize('>' + fmt)))[0]
        def string(): return take(number('H')).decode('utf-8', errors='replace')
        def tag(kind, depth=0):
            nodes[0] += 1
            if depth > 32 or nodes[0] > 250000: raise ValueError('NBT limits')
            if kind in (1, 2, 3, 4, 5, 6): return number({1:'b',2:'h',3:'i',4:'q',5:'f',6:'d'}[kind])
            if kind == 8: return string()
            if kind in (7, 11, 12):
                n = number('i')
                if n < 0 or n > 4000000: raise ValueError('NBT array')
                take(n * {7:1,11:4,12:8}[kind]); return None
            if kind == 9:
                child, n = number('B'), number('i')
                if n < 0 or n > 250000 or child == 0 and n: raise ValueError('NBT list')
                for _ in range(n): tag(child, depth+1)
                return None
            if kind == 10:
                result = {}
                while True:
                    child = number('B')
                    if child == 0: return result
                    name = string()
                    result[name] = tag(child, depth+1)
            raise ValueError('NBT type')
        if number('B') != 10: raise ValueError('NBT root')
        string()
        data = tag(10).get('Data', {})
        version = data.get('Version', {})
        return {'title':str(data.get('LevelName', '')), 'version':str(version.get('Name', 'Eski / bilinmiyor')),
                'data_version':data.get('DataVersion'), 'last_played':data.get('LastPlayed', 0),
                'seed':data.get('WorldGenSettings', {}).get('seed', data.get('RandomSeed')), 'hardcore':bool(data.get('hardcore'))}
    except (OSError, ValueError, EOFError, struct.error, AttributeError, TypeError):
        return {'version':'Okunamadı', 'title':'', 'last_played':0, 'seed':None}


class Worlds:
    def __init__(self, launcher):
        self.launcher, self.store = launcher, launcher.store

    def folder(self, profile):
        if profile.get('kind') == 'server':
            raise LauncherError('Dünya yönetimi için oyuncu profili seçin.')
        path = self.store.directory(profile) / 'saves'
        if path.is_symlink() or path.exists() and path.resolve().parent != self.store.directory(profile).resolve():
            raise LauncherError('Dünya klasörü bağlantı olamaz.')
        path.mkdir(exist_ok=True)
        return path

    def world(self, profile, name):
        path = self.folder(profile) / safe_file(name)
        if path.is_symlink() or path.resolve().parent != self.folder(profile).resolve() or not (path / 'level.dat').is_file():
            raise LauncherError('Geçerli bir dünya seçin.')
        return path

    def list(self, profile, task):
        result = []
        for path in self.folder(profile).iterdir():
            task.check()
            if path.is_dir() and not path.is_symlink() and (path / 'level.dat').is_file():
                self.world(profile, path.name)
                meta = level_metadata(path / 'level.dat')
                result.append({**meta, 'name':path.name, 'title':meta.get('title') or path.name,
                    'icon':str(path / 'icon.png') if (path / 'icon.png').is_file() else None,
                    'size':sum(p.stat().st_size for p in regular_files(path))})
        return sorted(result, key=lambda p:p.get('last_played', 0), reverse=True)

    def backups(self, profile, name):
        folder = self.store.root / 'world-backups' / profile['id']
        result = []
        if not folder.is_dir(): return []
        for path in folder.glob('*.zip'):
            try:
                with zipfile.ZipFile(path) as archive:
                    info = archive.getinfo('kurt-world.json')
                    if info.file_size > 4 * 1024**2: continue
                    meta = json.loads(archive.read(info))
                if meta.get('profile') == profile['id'] and meta.get('world') == name:
                    result.append({**meta, 'path':str(path), 'size':path.stat().st_size})
            except (OSError, ValueError, KeyError, zipfile.BadZipFile): pass
        return sorted(result, key=lambda p:p['created'], reverse=True)

    def export(self, profile, name, target, task, backup=False):
        self.launcher.ensure_profile_idle(profile)
        world, target = self.world(profile, name), Path(target).resolve()
        if target.is_relative_to(world.resolve()):
            raise LauncherError('Dünya ZIP dosyası dünyanın içine kaydedilemez.')
        target.parent.mkdir(parents=True, exist_ok=True)
        with session_locks(world), tempfile.TemporaryDirectory(prefix='.world-export-', dir=target.parent) as temporary:
            path = Path(temporary) / 'world.zip'
            files = [p for p in regular_files(world) if p.name != 'session.lock']
            meta = {'format':1, 'profile':profile['id'], 'world':name,
                    'created':datetime.now(timezone.utc).isoformat(), 'files':{}}
            task.status('Dünya ZIP olarak doğrulanıyor…')
            task.set_max(len(files))
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
                for i, source in enumerate(files, 1):
                    task.check()
                    relative = source.relative_to(world).as_posix()
                    before = digest(source)
                    archive.write(source, name + '/' + relative)
                    if digest(source) != before: raise LauncherError('Dünya işlem sırasında değişti.')
                    meta['files'][relative] = before
                    task.progress(i)
                archive.writestr('kurt-world.json', json.dumps(meta))
            task.check()
            os.replace(path, target)
        return str(target)

    def backup(self, profile, name, task):
        folder = self.store.root / 'world-backups' / profile['id']
        folder.mkdir(parents=True, exist_ok=True)
        return self.export(profile, name, folder / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8] + '.zip'), task, True)

    def copy(self, profile, name, new_name, task):
        self.launcher.ensure_profile_idle(profile)
        source, folder = self.world(profile, name), self.folder(profile)
        target = folder / safe_file(new_name)
        if any(p.name.casefold() == new_name.casefold() for p in folder.iterdir()):
            raise LauncherError('Bu adla bir dünya zaten var.')
        with session_locks(source), tempfile.TemporaryDirectory(prefix='.world-copy-', dir=folder.parent) as temporary:
            stage = Path(temporary) / 'world'
            verified_copy(source, stage, task)
            task.check()
            stage.rename(target)
        return 'Dünya kopyalandı: ' + new_name

    def restore(self, profile, name, source, task):
        self.launcher.ensure_profile_idle(profile)
        world, source = self.world(profile, name), Path(source).resolve()
        known = self.store.root / 'world-backups' / profile['id']
        if not source.is_relative_to(known.resolve()) or source.suffix != '.zip':
            raise LauncherError('Bu dünyaya ait yerel bir yedek seçin.')
        # Always keep a fresh world-specific backup before replacing anything.
        self.backup(profile, name, task)
        with tempfile.TemporaryDirectory(prefix='.world-restore-', dir=world.parent.parent) as temporary:
            stage, old = Path(temporary) / 'new', Path(temporary) / 'previous'
            stage.mkdir()
            with zipfile.ZipFile(source) as archive:
                info = archive.getinfo('kurt-world.json')
                if info.file_size > 4 * 1024**2: raise LauncherError('Yedek kaydı çok büyük.')
                meta = json.loads(archive.read(info))
                if meta.get('format') != 1 or meta.get('profile') != profile['id'] or meta.get('world') != name:
                    raise LauncherError('Yedek farklı bir dünyaya ait.')
                entries = meta.get('files', {})
                if len(entries) > 100000 or sum(i.file_size for i in archive.infolist()) > shutil.disk_usage(stage).free - 64 * 1024**2:
                    raise LauncherError('Yedeği açmak için yeterli disk alanı yok.')
                seen = set()
                task.status('Dünya yedeği doğrulanıyor…'); task.set_max(len(entries))
                for i, (relative, expected) in enumerate(entries.items(), 1):
                    task.check(); relative_path(relative)
                    if relative.casefold() in seen: raise LauncherError('Yedekte yinelenen yol var.')
                    seen.add(relative.casefold())
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name + '/' + relative) as inp, target.open('wb') as out:
                        shutil.copyfileobj(inp, out, 1024 * 1024)
                    if digest(target) != expected: raise LauncherError('Dünya yedeği doğrulanamadı.')
                    task.progress(i)
            if not (stage / 'level.dat').is_file(): raise LauncherError('Yedekte level.dat yok.')
            # Check again immediately before the directory swap. Windows must
            # release our session.lock handle before its parent can be renamed.
            with session_locks(world):
                self.launcher.ensure_profile_idle(profile)
                task.check()
            world.rename(old)
            try: stage.rename(world)
            except Exception:
                old.rename(world)
                raise
        return 'Dünya geri yüklendi; önceki hali de yedeklerde korundu.'

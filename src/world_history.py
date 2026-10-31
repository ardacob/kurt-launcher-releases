"""Content-addressed, verified local world restore points. No retention deletion."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import zipfile

from core import LauncherError, atomic_json, read_json
from profile_data import session_locks
from snapshots import digest, regular_files, relative_path


class WorldHistory:
    def __init__(self, launcher):
        self.launcher, self.store = launcher, launcher.store
        self.root = self.store.root / 'world-history'

    def directory(self, *parts):
        path = self.root
        for part in ('', *parts):
            path = path / part
            if path.is_symlink() or path.exists() and getattr(path.lstat(),'st_file_attributes',0)&1024:
                raise LauncherError('Dünya geçmişi klasörü bağlantı/junction olamaz.')
            path.mkdir(parents=True, exist_ok=True)
        return path

    def object(self, value):
        if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{128}',value):
            raise LauncherError('Geçersiz yedek dosyası kimliği.')
        path = self.directory('objects', value[:2]) / value
        if path.is_symlink() or path.exists() and getattr(path.lstat(),'st_file_attributes',0)&1024:
            raise LauncherError('Yedek dosyası bağlantı olamaz.')
        return path

    def points(self, profile, name):
        self.launcher.worlds.world(profile,name)
        rows = []
        for path in self.directory('points',profile['id']).glob('*.json'):
            if path.is_symlink() or path.stat().st_size > 16*1024**2: continue
            value = read_json(path,{})
            if value.get('format')==1 and value.get('profile')==profile['id'] and value.get('world')==name:
                rows.append({**value,'path':str(path)})
        return sorted(rows,key=lambda row:row['created'],reverse=True)

    def create(self, profile, name, task, automatic=False):
        self.launcher.ensure_profile_idle(profile)
        world = self.launcher.worlds.world(profile,name)
        meta = {'format':1,'profile':profile['id'],'world':name,'created':datetime.now(timezone.utc).isoformat(),
                'files':{},'bytes':0,'new_bytes':0,'automatic':automatic}
        with session_locks(world):
            files = [p for p in regular_files(world) if p.name.casefold()!='session.lock']
            if len(files)>20000:raise LauncherError('Bu dünya dosya sınırını aşıyor; ZIP yedeğini kullanın.')
            task.status('Değişen dünya dosyaları yedekleniyor…'); task.set_max(len(files))
            for index,source in enumerate(files,1):
                task.check(); before=source.stat(); expected=digest(source); target=self.object(expected)
                relative=source.relative_to(world).as_posix(); relative_path(relative)
                if not target.exists():
                    if shutil.disk_usage(target.parent).free < before.st_size+64*1024**2:
                        raise LauncherError('Dünya geçmişi için yeterli boş alan yok.')
                    with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as temporary:
                        temporary_path=Path(temporary.name)
                    try:
                        shutil.copyfile(source,temporary_path)
                        if digest(temporary_path)!=expected: raise LauncherError('Dünya kopyası doğrulanamadı.')
                        os.replace(temporary_path,target)
                    finally: temporary_path.unlink(missing_ok=True)
                    meta['new_bytes']+=before.st_size
                elif digest(target)!=expected:
                    raise LauncherError('Dünya geçmişindeki dosya bozuk; mevcut dünya korundu.')
                after=source.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or digest(source)!=expected:
                    raise LauncherError('Dünya yedeklenirken değişti; tekrar deneyin.')
                meta['files'][relative]=expected; meta['bytes']+=before.st_size; task.progress(index)
            # Detect added/removed files, not just changes to the files seen initially.
            if {p.relative_to(world).as_posix() for p in regular_files(world) if p.name.casefold()!='session.lock'}!=set(meta['files']):
                raise LauncherError('Dünya yedeklenirken değişti; tekrar deneyin.')
            task.check()
            if len(json.dumps(meta).encode())>4*1024**2:
                raise LauncherError('Bu dünyanın yedek kaydı çok büyük; ZIP yedeğini kullanın.')
            path=self.directory('points',profile['id'])/(uuid.uuid4().hex+'.json')
            atomic_json(path,meta)
        return meta

    def restore(self,profile,name,point,task):
        self.launcher.ensure_profile_idle(profile)
        allowed={r['path'] for r in self.points(profile,name)}
        if str(Path(point)) not in allowed: raise LauncherError('Bu dünyaya ait bir geri dönüş noktası seçin.')
        path=Path(point)
        if path.is_symlink() or path.stat().st_size>16*1024**2: raise LauncherError('Geçersiz geri dönüş noktası.')
        meta=read_json(path,{})
        if meta.get('profile')!=profile['id'] or meta.get('world')!=name or meta.get('format')!=1:
            raise LauncherError('Geri dönüş noktası farklı bir dünyaya ait.')
        entries=meta.get('files',{})
        if not isinstance(entries,dict) or not entries or len(entries)>100000:
            raise LauncherError('Geçersiz geri dönüş noktası.')
        folder=self.store.root/'world-backups'/profile['id']; folder.mkdir(parents=True,exist_ok=True)
        # Build the established ZIP restore format, then reuse its verified swap/rollback.
        with tempfile.TemporaryDirectory(prefix='.history-restore-',dir=folder) as temporary:
            target=Path(temporary)/'point.zip'; seen=set()
            with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
                task.status('Geri dönüş noktası doğrulanıyor…'); task.set_max(len(entries))
                for index,(relative,expected) in enumerate(entries.items(),1):
                    task.check(); relative_path(relative)
                    if relative.casefold() in seen: raise LauncherError('Yedekte yinelenen dosya var.')
                    seen.add(relative.casefold()); source=self.object(expected)
                    if not source.is_file() or digest(source)!=expected: raise LauncherError('Geri dönüş noktası eksik veya bozuk; dünya değiştirilmedi.')
                    archive.write(source,name+'/'+relative)
                    if digest(source)!=expected: raise LauncherError('Yedek dosyası değişti.')
                    task.progress(index)
                archive.writestr('kurt-world.json',json.dumps(meta))
            task.check()
            return self.launcher.worlds.restore(profile,name,target,task)

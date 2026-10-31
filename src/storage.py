"""Disk inventory and explicit, change-checked cleanup of reproducible cache files."""
from pathlib import Path
import os
import stat

from core import LauncherError
from snapshots import regular_files, relative_path

CACHE_ROOTS = ('cache/downloads', 'cache/mod-icons', 'cache/modpacks')


class Storage:
    def __init__(self, launcher):
        self.launcher, self.store = launcher, launcher.store

    def scan(self, task):
        groups = {name:0 for name in ('Dünyalar', 'Modlar', 'Shaderpack’ler', 'Doku paketleri',
            'Minecraft sürümleri', 'Java', 'Oyun kütüphaneleri ve varlıklar', 'Yedekler', 'Önbellek', 'Diğer')}
        cleanup = []
        task.status('Disk kullanımı hesaplanıyor…')
        for index, path in enumerate(regular_files(self.store.root), 1):
            task.check()
            name = path.relative_to(self.store.root).as_posix()
            parts = Path(name).parts
            if 'saves' in parts or parts[0] == 'servers' and 'world' in parts: group = 'Dünyalar'
            elif 'mods' in parts: group = 'Modlar'
            elif 'shaderpacks' in parts: group = 'Shaderpack’ler'
            elif 'resourcepacks' in parts: group = 'Doku paketleri'
            elif name.startswith('minecraft/versions/'): group = 'Minecraft sürümleri'
            elif name.startswith('minecraft/runtime/'): group = 'Java'
            elif name.startswith(('minecraft/libraries/', 'minecraft/assets/')): group = 'Oyun kütüphaneleri ve varlıklar'
            elif parts[0] in ('backups', 'world-backups', 'world-history'): group = 'Yedekler'
            elif parts[0] == 'cache': group = 'Önbellek'
            else: group = 'Diğer'
            info = path.stat()
            groups[group] += info.st_size
            if any(name.startswith(prefix + '/') for prefix in CACHE_ROOTS):
                cleanup.append({'path':name, 'size':info.st_size, 'mtime_ns':info.st_mtime_ns})
            if index % 100 == 0: task.progress(index)
        return {'groups':groups, 'cleanup':cleanup, 'total':sum(groups.values()),
                'reclaimable':sum(v['size'] for v in cleanup)}

    def clean(self, selected, task):
        self.launcher.ensure_idle()
        if self.launcher.server_manager and self.launcher.server_manager.running:
            raise LauncherError('Temizlemeden önce sunucuyu durdurun.')
        root = self.store.root.resolve()
        removed, freed, skipped = 0, 0, 0
        validated = []
        for record in selected:
            task.check()
            name = record['path']
            relative_path(name)
            if not any(name.startswith(prefix + '/') for prefix in CACHE_ROOTS):
                raise LauncherError('Bu klasör önbellek temizliğine dahil değil.')
            path = root / name
            if not path.resolve().is_relative_to(root):
                raise LauncherError('Temizleme yolu oyun arşivinin dışına çıkamaz.')
            for parent in (path, *path.parents):
                if parent == root: break
                if parent.exists() and (parent.is_symlink() or getattr(parent.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024)):
                    raise LauncherError('Temizleme bağlantı/junction üzerinden yapılamaz.')
            validated.append((record,path))
        task.status('Seçilen önbellek dosyaları temizleniyor…'); task.set_max(len(validated))
        for index,(record,path) in enumerate(validated,1):
            task.check()
            if path.is_file():
                now = path.stat()
                if (now.st_size, now.st_mtime_ns) != (record['size'], record['mtime_ns']):
                    skipped += 1
                else:
                    path.unlink()
                    removed += 1; freed += now.st_size
            task.progress(index)
        return f'{removed} önbellek dosyası temizlendi • {freed / 1048576:.1f} MB • değiştiği için atlanan: {skipped}'

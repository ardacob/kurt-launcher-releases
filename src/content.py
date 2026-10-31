"""Resource-pack and modpack catalogs using public Modrinth metadata."""
import json
import os
from pathlib import Path
import tempfile
import zipfile

from core import LauncherError, MODRINTH, Task, atomic_json, safe_file
from shaders import ShaderManager
from snapshots import relative_path


def validate_resourcepack(path):
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 50000 or sum(i.file_size for i in entries) > 2 * 1024**3:
                raise LauncherError('Doku paketi boyut sınırını aşıyor.')
            seen = set()
            for entry in entries:
                name = entry.filename.rstrip('/')
                relative_path(name)
                if name.casefold() in seen or entry.flag_bits & 1 or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise LauncherError('Doku paketi arşivinde geçersiz dosya var.')
                seen.add(name.casefold())
            info = archive.getinfo('pack.mcmeta')
            if info.file_size > 1024 * 1024:
                raise LauncherError('Doku paketi tanımı çok büyük.')
            meta = json.loads(archive.read(info))
            pack = meta.get('pack', {})
            if not isinstance(pack, dict) or not any(k in pack for k in ('pack_format', 'min_format', 'max_format', 'supported_formats')):
                raise LauncherError('Doku paketinin biçim tanımı eksik.')
            if archive.testzip():
                raise LauncherError('Doku paketi ZIP dosyası bozuk.')
    except (KeyError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        raise LauncherError('ZIP kökünde geçerli pack.mcmeta bulunmalı.') from exc


class ResourcePacks(ShaderManager):
    project_type, folder_name, title = 'resourcepack', 'resourcepacks', 'Doku paketi'
    validate = staticmethod(validate_resourcepack)
    install_message = 'Doku paketi indirildi. İndirilenler sekmesinden seçip sırasını oyuna uygulayabilirsiniz.'

    def compatible(self, version, profile, engine=''):
        return profile.get('kind') != 'server' and profile['version'] in version.get('game_versions', [])

    def search(self, profile, query='', offset=0, sort='downloads', engine=''):
        if sort not in ('downloads', 'newest', 'updated', 'relevance'):
            raise LauncherError('Geçersiz sıralama.')
        return self.api.get(MODRINTH + '/search', query=query,
            facets=json.dumps([['project_type:resourcepack'], ['versions:' + profile['version']]]),
            index=sort, offset=max(0, int(offset)), limit=20)

    def choose(self, project, profile, engine=''):
        versions = self.api.get(MODRINTH + f'/project/{project}/version', game_versions=json.dumps([profile['version']]))
        choices = [v for v in versions if self.compatible(v, profile)
                   and any(f['filename'].lower().endswith('.zip') for f in v.get('files', []))]
        if not choices:
            raise LauncherError('Bu Minecraft sürümü için doku paketi sürümü yok.')
        return max(choices, key=lambda v:(v.get('version_type') == 'release', v.get('date_published', '')))

    def order(self, profile):
        path = self.store.directory(profile) / 'options.txt'
        for line in path.read_text(encoding='utf-8').splitlines() if path.is_file() else []:
            if line.startswith('resourcePacks:'):
                try:
                    values = json.loads(line.split(':', 1)[1])
                    return [v[5:] for v in values if isinstance(v, str) and v.startswith('file/')] if isinstance(values, list) else []
                except ValueError:
                    return []
        return []

    def apply_order(self, profile, names, task):
        folder = self.folder(profile)
        if len(set(n.casefold() for n in names)) != len(names):
            raise LauncherError('Aynı doku paketi iki kez seçilemez.')
        for name in names:
            path = folder / safe_file(name)
            if not path.is_file() or path.is_symlink():
                raise LauncherError('Seçilen doku paketi bulunamadı.')
            self.validate(path)
        self.before_change(profile, task, 'Doku paketi sırası öncesi')
        target = self.store.directory(profile) / 'options.txt'
        lines = target.read_text(encoding='utf-8').splitlines() if target.exists() else []
        preserved = ['vanilla']
        for line in lines:
            if line.startswith('resourcePacks:'):
                try:
                    current = json.loads(line.split(':', 1)[1])
                    if isinstance(current, list):
                        preserved = [v for v in current if isinstance(v, str) and not v.startswith('file/')]
                except ValueError:
                    pass
        setting = 'resourcePacks:' + json.dumps(preserved + ['file/' + n for n in names], ensure_ascii=False)
        result = [line for line in lines if not line.startswith('resourcePacks:')] + [setting]
        with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, encoding='utf-8', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write('\n'.join(result) + '\n')
        try:
            task.check()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return 'Doku paketi sırası kaydedildi. Listedeki son paket daha yüksek önceliklidir.'


class ModpackCatalog:
    def __init__(self, launcher):
        from packs import Packs
        self.launcher, self.store, self.api = launcher, launcher.store, launcher.api
        self.packs = Packs(launcher)

    def search(self, query='', offset=0, sort='downloads', game='', loader=''):
        if sort not in ('downloads', 'newest', 'updated', 'relevance') or loader not in ('', 'vanilla', 'fabric', 'forge', 'neoforge', 'quilt'):
            raise LauncherError('Geçersiz modpack filtresi.')
        facets = [['project_type:modpack']]
        if game: facets.append(['versions:' + game])
        if loader: facets.append(['categories:' + loader])
        return self.api.get(MODRINTH + '/search', query=query, facets=json.dumps(facets),
                            index=sort, offset=max(0, int(offset)), limit=20)

    def versions(self, project, game='', loader=''):
        params = {}
        if game: params['game_versions'] = json.dumps([game])
        if loader: params['loaders'] = json.dumps([loader])
        values = self.api.get(MODRINTH + f'/project/{project}/version', **params)
        return sorted([v for v in values if (not game or game in v.get('game_versions', []))
            and (not loader or loader in v.get('loaders', []))
            and any(f['filename'].lower().endswith('.mrpack') for f in v.get('files', []))],
            key=lambda v:(v.get('version_type') == 'release', v.get('date_published', '')), reverse=True)

    def download(self, project, version_id, task):
        details = self.api.get(MODRINTH + '/project/' + project)
        version = self.api.get(MODRINTH + '/version/' + version_id)
        if details.get('project_type') != 'modpack' or version.get('project_id') != details.get('id'):
            raise LauncherError('Paket türü veya sürümü eşleşmiyor.')
        files = [f for f in version.get('files', []) if f['filename'].lower().endswith('.mrpack')]
        if not files:
            raise LauncherError('Bu sürümde mrpack dosyası yok.')
        file = next((f for f in files if f.get('primary')), files[0])
        folder = self.store.root / 'cache/modpacks'
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (safe_file(details['id']) + '-' + safe_file(version['id']) + '.mrpack')
        self.api.download(file, target, task, validator=self.packs.inspect)
        info = self.packs.inspect(target)
        return {'source':str(target), 'info':info}

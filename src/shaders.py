"""Verified Iris/OptiFine shader ZIPs, isolated per Minecraft profile."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile

from core import Api, Cancelled, LauncherError, MODRINTH, Task, atomic_json, read_json, safe_file
from snapshots import digest, relative_path

ENGINES = {"iris": "Iris", "optifine": "OptiFine"}


def validate_shaderpack(path):
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 20000 or sum(i.file_size for i in entries) > 512 * 1024 * 1024:
                raise LauncherError("Shaderpack arşivi çok büyük.")
            found = False
            seen = set()
            for entry in entries:
                name = entry.filename.rstrip('/')
                relative_path(name)
                if name.casefold() in seen or entry.flag_bits & 1 or stat.S_ISLNK(entry.external_attr >> 16):
                    raise LauncherError("Shaderpack arşivinde geçersiz dosya var.")
                seen.add(name.casefold())
                if name.startswith('shaders/') and name.endswith(('.vsh', '.fsh', '.glsl', '.csh')):
                    found = True
            if not found:
                raise LauncherError("ZIP kökünde shaders klasörü ve shader dosyaları bulunmalı.")
            if archive.testzip():
                raise LauncherError("Shaderpack ZIP dosyası bozuk.")
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise LauncherError("Geçerli bir shaderpack ZIP dosyası değil.") from exc


class ShaderManager:
    def __init__(self, store, api):
        self.store, self.api = store, api
        self.before_change = lambda profile, task=None, reason='': None

    def folder(self, profile):
        if profile.get('kind') == 'server':
            raise LauncherError("Shaderpack'ler oyuncu profiline kurulur; sunucuya kurulmaz.")
        directory = self.store.directory(profile) / 'shaderpacks'
        attributes = getattr(directory.lstat(), 'st_file_attributes', 0) if directory.exists() else 0
        if directory.is_symlink() or attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
            raise LauncherError("Shaderpack klasörü bağlantı/junction olamaz.")
        directory.mkdir(exist_ok=True)
        return directory

    def lock_path(self, profile):
        return self.store.directory(profile) / 'shaderpacks.lock.json'

    def records(self, profile):
        return read_json(self.lock_path(profile), {})

    def compatible(self, version, profile, engine=''):
        return (profile.get('kind') != 'server' and profile['version'] in version.get('game_versions', [])
                and bool(set(version.get('loaders', [])) & set(ENGINES))
                and (not engine or engine in version.get('loaders', [])))

    def search(self, profile, query='', offset=0, sort='downloads', engine=''):
        if profile.get('kind') == 'server':
            raise LauncherError("Shaderpack aramak için oyuncu profili seçin.")
        if sort not in ('downloads', 'relevance', 'newest', 'updated') or engine not in ('', *ENGINES):
            raise LauncherError("Geçersiz shaderpack filtresi.")
        facets = [['project_type:shader'], ['versions:' + profile['version']],
                  ['categories:' + engine] if engine else ['categories:iris', 'categories:optifine']]
        return self.api.get(MODRINTH + '/search', query=query, facets=json.dumps(facets),
                            index=sort, limit=20, offset=max(0, int(offset)))

    def choose(self, project, profile, engine=''):
        versions = self.api.get(MODRINTH + f'/project/{project}/version',
                                game_versions=json.dumps([profile['version']]),
                                loaders=json.dumps([engine] if engine else list(ENGINES)))
        choices = [v for v in versions if self.compatible(v, profile, engine)
                   and any(f.get('filename', '').lower().endswith('.zip') for f in v.get('files', []))]
        if not choices:
            raise LauncherError(f"Minecraft {profile['version']} için uyumlu Iris/OptiFine shaderpack sürümü yok.")
        return max(choices, key=lambda v: (v.get('version_type') == 'release', v.get('date_published', '')))

    def catalog(self, profile, query='', offset=0, task=None, sort='downloads', engine=''):
        task = task or Task()
        task.status('Shaderpack’ler aranıyor…')
        result = self.search(profile, query, offset, sort, engine)
        def enrich(hit):
            api = Api()
            paths = {'icon_path': None, 'preview_path': None}
            try:
                task.check()
                paths['icon_path'] = api.icon(hit.get('icon_url'), self.store.icon_cache, task)
                preview = hit.get('featured_gallery') or next(iter(hit.get('gallery', [])), None)
                paths['preview_path'] = api.icon(preview, self.store.icon_cache, task)
                info = ShaderManager(self.store, api).choose(hit['project_id'], profile, engine)
                return {**hit, **paths, 'version_info': info}
            except Cancelled:
                raise
            except LauncherError as exc:
                return {**hit, **paths, 'version_info': None, 'version_error': str(exc)}
            finally:
                api.session.close()
        hits = result.get('hits', [])
        enriched = [None] * len(hits)
        task.status('Shaderpack sürümleri ve görselleri kontrol ediliyor…')
        task.set_max(len(hits))
        with ThreadPoolExecutor(max_workers=4) as executor:
            pending = {executor.submit(enrich, h): i for i, h in enumerate(hits)}
            for number, future in enumerate(as_completed(pending), 1):
                task.check()
                enriched[pending[future]] = future.result()
                task.progress(number)
        return {**result, 'hits': enriched}

    def _check_name(self, folder, filename):
        name = safe_file(filename)
        if not name.lower().endswith('.zip'):
            raise LauncherError("Shaderpack dosyası .zip olmalı.")
        if any(p.name.casefold() == name.casefold() for p in folder.iterdir()):
            raise LauncherError('Aynı adlı shaderpack zaten var: ' + name)
        return name

    def _commit(self, profile, staged, records, task):
        directory = self.folder(profile)
        task.check()
        self.before_change(profile, task, 'Shaderpack kurulumu öncesi')
        committed = []
        try:
            for source, name in staged:
                self._check_name(directory, name)
                task.check()
                os.replace(source, directory / name)
                committed.append(directory / name)
            task.check()
            atomic_json(self.lock_path(profile), records)
        except Exception:
            for path in committed:
                path.unlink(missing_ok=True)
            raise

    def install(self, project, profile, task, version_id=None, engine=''):
        folder = self.folder(profile)
        details = self.api.get(MODRINTH + '/project/' + project)
        if details.get('project_type') != 'shader':
            raise LauncherError('Seçilen proje bir shaderpack değil.')
        version = self.api.get(MODRINTH + '/version/' + version_id) if version_id else self.choose(project, profile, engine)
        if version.get('project_id') != details['id'] or not self.compatible(version, profile, engine):
            raise LauncherError('Seçilen shaderpack sürümü bu profil ile uyumlu değil.')
        records = self.records(profile)
        if details['id'] in records:
            raise LauncherError('Bu shaderpack kayıtlı. Farklı sürüm için önce indirilen paketi kaldırın.')
        candidates = [f for f in version['files'] if f['filename'].lower().endswith('.zip')]
        if not candidates:
            raise LauncherError('Bu sürümde shaderpack ZIP dosyası yok.')
        file = next((f for f in candidates if f.get('primary')), candidates[0])
        name = self._check_name(folder, file['filename'])
        with tempfile.TemporaryDirectory(prefix='.shader-', dir=folder.parent) as temporary:
            target = Path(temporary) / name
            self.api.download(file, target, task, validator=validate_shaderpack)
            records[details['id']] = {'name': details.get('title', name), 'file': name,
                'project_id': details['id'], 'version_id': version['id'],
                'version_number': version.get('version_number', ''), 'game_versions': version.get('game_versions', []),
                'loaders': version.get('loaders', []), 'icon_url': details.get('icon_url'), 'sha512': digest(target)}
            self._commit(profile, [(target, name)], records, task)
        return 'Shaderpack indirildi. Minecraft → Video ayarları → Shader Packs bölümünden seçin.'

    def import_local(self, profile, files, task):
        folder = self.folder(profile)
        records = self.records(profile)
        with tempfile.TemporaryDirectory(prefix='.shader-', dir=folder.parent) as temporary:
            staged, seen = [], set()
            task.status('Yerel shaderpack’ler doğrulanıyor…')
            task.set_max(len(files))
            for i, source in enumerate(files, 1):
                task.check()
                source = Path(source)
                name = self._check_name(folder, source.name)
                if name.casefold() in seen:
                    raise LauncherError('Aynı adlı shaderpack seçildi.')
                seen.add(name.casefold())
                target = Path(temporary) / name
                shutil.copy2(source, target)
                validate_shaderpack(target)
                value = digest(target)
                if digest(source) != value:
                    raise LauncherError('Yerel shaderpack kopyası doğrulanamadı.')
                staged.append((target, name))
                records['local:' + name] = {'name': source.stem, 'file': name, 'sha512': value}
                task.progress(i)
            self._commit(profile, staged, records, task)
        return f'{len(files)} yerel shaderpack eklendi. Kullanmak için oyun içinden seçin.'

    def remove(self, profile, name, task):
        folder = self.folder(profile)
        target = folder / safe_file(name)
        if not name.lower().endswith('.zip') or not target.is_file() or target.is_symlink():
            raise LauncherError('Listeden bir shaderpack ZIP dosyası seçin.')
        self.before_change(profile, task, 'Shaderpack kaldırma öncesi')
        records = {key: value for key, value in self.records(profile).items() if value.get('file') != name}
        with tempfile.TemporaryDirectory(prefix='.shader-', dir=folder.parent) as temporary:
            saved = Path(temporary) / name
            task.check()
            os.replace(target, saved)
            try:
                atomic_json(self.lock_path(profile), records)
            except Exception:
                os.replace(saved, target)
                raise
        return 'Shaderpack kaldırıldı.'

"""Guided dependency-aware bisection in a world-free copy of the user's profile."""
import json
from pathlib import Path
import re
import time
import uuid
import zipfile

from core import LauncherError, atomic_json, read_json, safe_file
from profile_data import ProfileCopies
from snapshots import digest


class ModDiagnostics:
    def __init__(self, launcher):
        self.launcher, self.store = launcher, launcher.store

    def folder(self):
        path = self.store.root / 'diagnostics'
        path.mkdir(exist_ok=True)
        return path

    def get(self, session_id):
        if not isinstance(session_id,str) or not re.fullmatch('[a-f0-9]{32}', session_id):
            raise LauncherError('Geçersiz mod testi kaydı.')
        session = read_json(self.folder() / (session_id + '.json'), {})
        profile = next((p for p in self.store.profiles if p['id'] == session.get('test_profile')), None)
        if not profile or profile.get('diagnostic_session') != session_id:
            raise LauncherError('Test profili bulunamadı.')
        return session, profile

    def sessions(self):
        values = []
        for path in self.folder().glob('*.json'):
            try:
                session, _ = self.get(path.stem)
                values.append(session)
            except LauncherError: pass
        return sorted(values, key=lambda s:s.get('created', 0), reverse=True)

    def start(self, profile, task):
        self.launcher.ensure_profile_idle(profile)
        self.launcher.mods.validate_enabled(profile)
        files = sorted(p.name for p in self.store.mods(profile).glob('*.jar') if p.is_file())
        if len(files) < 2:
            raise LauncherError('Gruplu test için en az iki etkin mod olmalı.')
        records = self.store.mod_lock(profile)
        ids = {pid:v['file'] for pid,v in records.items() if v['file'] in files}
        versions = {v.get('version_id'):v['file'] for v in records.values() if v['file'] in files}
        graph = {name:[] for name in files}
        for pid, record in records.items():
            if pid not in ids: continue
            graph[ids[pid]] = list({ids.get(d.get('project_id')) or versions.get(d.get('version_id'))
                for d in record.get('requires', [])} - {None})
        # Local Fabric/Quilt-compatible JAR metadata supplements the online lock.
        fabric_ids, dependencies = {}, {}
        for name in files:
            try:
                with zipfile.ZipFile(self.store.mods(profile) / name) as archive:
                    info = archive.getinfo('fabric.mod.json')
                    if info.file_size > 1024**2: continue
                    meta = json.loads(archive.read(info))
                fabric_ids[meta['id']] = name
                dependencies[name] = list(meta.get('depends', {}))
            except (KeyError, ValueError, OSError, zipfile.BadZipFile): pass
        for name, dependencies_ids in dependencies.items():
            graph[name] = sorted(set(graph[name]) | {fabric_ids[d] for d in dependencies_ids if d in fabric_ids})
        clone = ProfileCopies(self.launcher).clone(profile, (profile['name'][:45] + ' · Mod testi'), False, task, True)
        session_id = uuid.uuid4().hex
        clone['diagnostic_session'] = session_id
        atomic_json(self.store.root / 'profiles.json', self.store.profiles)
        session = {'format':1, 'id':session_id, 'created':time.time(), 'source_profile':profile['id'],
            'test_profile':clone['id'], 'source_name':profile['name'], 'all':files, 'candidates':files,
            'hashes':{name:digest(self.store.mods(clone) / name) for name in files},
            'dependencies':graph, 'history':[], 'round':0, 'complete':False}
        self.prepare(session, clone, task)
        return session

    def closure(self, session, seeds):
        found, pending = set(), list(seeds)
        while pending:
            name = pending.pop()
            if name in found: continue
            found.add(name)
            pending.extend(session['dependencies'].get(name, []))
        return found

    def prepare(self, session, profile, task):
        self.launcher.ensure_profile_idle(profile)
        directory = self.store.mods(profile)
        candidates = session['candidates']
        complete = len(candidates) <= 1
        active = self.closure(session, candidates[:max(1, (len(candidates) + 1)//2)])
        if not complete and set(candidates).issubset(active):
            other = self.closure(session, candidates[(len(candidates) + 1)//2:])
            if set(candidates).issubset(other):
                complete = True  # inseparable dependency group; never accuse one mod.
                active = self.closure(session, candidates)
            else:
                active = other
        changes = []
        try:
            for name in session['all']:
                safe_file(name)
                current = directory / name
                disabled = directory / (name + '.disabled')
                source = current if current.is_file() else disabled
                if not source.is_file() or source.is_symlink() or digest(source) != session['hashes'][name]:
                    raise LauncherError('Test profili değiştirilmiş. Yeni bir test başlatın.')
                destination = current if name in active else disabled
                if source != destination:
                    if destination.exists(): raise LauncherError('Test dosyası adı çakışıyor.')
                    task.check()
                    source.rename(destination)
                    changes.append((source, destination))
            session.update(active=sorted(active), tested=sorted(set(candidates) & active),
                           complete=complete, round=session['round']+1)
            atomic_json(self.folder() / (session['id'] + '.json'), session)
        except Exception:
            for source, destination in reversed(changes): destination.rename(source)
            raise

    def result(self, session_id, crashed, task):
        session, profile = self.get(session_id)
        if session['complete']: raise LauncherError('Bu test tamamlanmış; yeni bir test başlatabilirsiniz.')
        self.launcher.ensure_profile_idle(profile)
        session['history'].append({'round':session['round'], 'active':session['active'], 'crashed':bool(crashed)})
        session['candidates'] = session['tested'] if crashed else [n for n in session['candidates'] if n not in session['tested']]
        self.prepare(session, profile, task)
        return session

"""Verified local copies and locks shared by worlds, profile cloning and diagnostics."""
from contextlib import contextmanager, ExitStack
import copy
import os
from pathlib import Path
import shutil
import tempfile
import uuid

from core import LauncherError, Task, atomic_json
from snapshots import digest, regular_files


@contextmanager
def session_locks(directory):
    with ExitStack() as stack:
        for path in regular_files(directory):
            if path.name != 'session.lock':
                continue
            try:
                stream = stack.enter_context(path.open('r+b'))
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.lockf(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise LauncherError('Minecraft bu dünyayı kullanıyor. Kaydedilip kapanmasını bekleyin.') from None
        yield


def verified_copy(source, destination, task, include=lambda name: True):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise LauncherError('Kopya kaynak klasörünün içinde olamaz.')
    files = [(p, p.relative_to(source)) for p in regular_files(source)
             if p.name.casefold() not in ('session.lock', 'launcher.lock') and include(p.relative_to(source).as_posix())]
    destination.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination).free < sum(p.stat().st_size for p, _ in files) + 64 * 1024**2:
        raise LauncherError('Kopyalama için yeterli boş disk alanı yok.')
    task.status('Dosyalar doğrulanarak kopyalanıyor…')
    task.set_max(len(files))
    records = {}
    for index, (path, relative) in enumerate(files, 1):
        task.check()
        before = path.stat()
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = digest(path)
        shutil.copy2(path, target)
        after = path.stat()
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size) or digest(target) != expected or digest(path) != expected:
            raise LauncherError('Kaynak işlem sırasında değişti veya kopya doğrulanamadı.')
        records[relative.as_posix()] = expected
        task.progress(index)
    task.check()
    return records


class ProfileCopies:
    def __init__(self, launcher):
        self.launcher, self.store = launcher, launcher.store

    def clone(self, profile, name, worlds=False, task=None, diagnostic=False):
        task = task or Task()
        self.launcher.ensure_profile_idle(profile)
        if profile.get('kind') == 'server' or not name.strip() or len(name.strip()) > 64:
            raise LauncherError('Geçerli bir oyuncu profili ve 1–64 karakterlik ad seçin.')
        source = self.store.directory(profile)
        parent = self.store.root / 'instances'
        clone = copy.deepcopy(profile)
        clone.update(id=uuid.uuid4().hex, name=name.strip())
        for key in ('last_played', 'diagnostic_session', 'diagnostic'):
            clone.pop(key, None)
        if diagnostic:
            clone['diagnostic'] = True
        destination = parent / clone['id']
        def include(value):
            first = value.split('/')[0].casefold()
            if first in ('logs', 'crash-reports', 'screenshots', 'removed-mods') or value.casefold() in ('launcher-game.log', 'quickplay.json'):
                return False
            return worlds or first != 'saves'
        with session_locks(source), tempfile.TemporaryDirectory(prefix='.profile-copy-', dir=parent) as temporary:
            stage = Path(temporary) / 'profile'
            verified_copy(source, stage, task, include)
            task.check()
            stage.rename(destination)
            try:
                atomic_json(self.store.root / 'profiles.json', self.store.profiles + [clone])
            except Exception:
                assert destination.resolve().parent == parent.resolve()
                shutil.rmtree(destination)
                raise
            self.store.profiles.append(clone)
        return clone

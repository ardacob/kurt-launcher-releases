"""Streaming adapter for the pinned minecraft-launcher-lib 8.0 downloader."""
from contextlib import contextmanager
import hashlib
import lzma
import os
from pathlib import Path
import sys
import tempfile
import threading
import requests
from core import LauncherError
from snapshots import digest

_lock = threading.RLock()


def stream_library_file(task, url, path, callback=None, sha1=None, lzma_compressed=False,
                        session=None, minecraft_directory=None, overwrite=False):
    path = Path(path)
    if minecraft_directory is not None and not path.resolve().is_relative_to(Path(minecraft_directory).resolve()):
        raise LauncherError("Oyun indirmesi kurulum klasörünün dışına yazamaz.")
    task.check()
    if path.is_file() and not overwrite and (sha1 is None or digest(path, "sha1") == sha1):
        return False
    from downloads import download
    cache = getattr(task, 'download_cache', (Path(minecraft_directory).parent / 'cache/downloads')
                    if minecraft_directory else path.parent / '.kurt-downloads')
    batch, queued = (task.maximum, task.value), task.transfer.queue
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not lzma_compressed:
            download(session or requests, url, path, task, cache=cache,
                     expected=sha1, algorithm='sha1', limit=2 * 1024**3)
        else:
            with tempfile.TemporaryDirectory(prefix='.transfer-', dir=path.parent) as temporary:
                compressed, expanded = Path(temporary) / 'input.xz', Path(temporary) / path.name
                download(session or requests, url, compressed, task, cache=cache, limit=2 * 1024**3)
                size, actual = 0, hashlib.sha1()
                with lzma.open(compressed, 'rb') as inp, expanded.open('wb') as out:
                    for block in iter(lambda: inp.read(1024 * 1024), b''):
                        task.check()
                        size += len(block)
                        if size > 2 * 1024**3:
                            raise LauncherError('Oyun dosyası boyut sınırını aşıyor.')
                        out.write(block)
                        actual.update(block)
                if sha1 and actual.hexdigest() != sha1:
                    raise LauncherError('Oyun dosyası doğrulanamadı: ' + path.name)
                task.check()
                os.replace(expanded, path)
        return True
    finally:
        task.maximum, task.value = batch
        task.transfer.begin(batch[0], 'items')
        task.transfer.queue = queued


@contextmanager
def library_downloads(task):
    # The app has one installer worker. Restore every reference on success/failure;
    # no installed third-party source files are modified.
    import minecraft_launcher_lib._helper as helper
    with _lock:
        original = helper.download_file
        replaced = []
        def download(*args, **kwargs):
            return stream_library_file(task, *args, **kwargs)
        for name, module in list(sys.modules.items()):
            if name.startswith("minecraft_launcher_lib") and getattr(module, "download_file", None) is original:
                replaced.append((module, original))
                module.download_file = download
        try:
            yield
        finally:
            for module, previous in replaced:
                module.download_file = previous

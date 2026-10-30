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
    path.parent.mkdir(parents=True, exist_ok=True)
    batch = task.maximum, task.value
    queued = task.transfer.queue
    if batch[0] > 0:
        task.transfer.queue = f"Dosya {min(batch[1]+1,batch[0]+1)}/{batch[0]+1}"
    task.status("İndiriliyor: " + path.name)
    fd, name = tempfile.mkstemp(prefix=".transfer-", dir=path.parent)
    temporary = Path(name)
    try:
        transport = session or requests
        with transport.get(url, stream=True, timeout=(15, 60)) as response, os.fdopen(fd, "wb") as out:
            fd = None
            response.raise_for_status()
            task.begin_bytes(int(response.headers.get("Content-Length", 0)))
            decompress = lzma.LZMADecompressor() if lzma_compressed else None
            actual = hashlib.sha1()
            size = written = 0
            for chunk in response.iter_content(128 * 1024):
                task.check()
                size += len(chunk)
                output = decompress.decompress(chunk) if decompress else chunk
                written += len(output)
                if written > 2 * 1024**3: raise LauncherError("Oyun dosyası boyut sınırını aşıyor.")
                out.write(output)
                actual.update(output)
                task.progress(size)
            if decompress and not decompress.eof:
                raise LauncherError("Sıkıştırılmış oyun dosyası eksik.")
            if sha1 and actual.hexdigest() != sha1:
                raise LauncherError("Oyun dosyası doğrulanamadı: " + path.name)
        task.check()
        os.replace(temporary, path)
        return True
    finally:
        if fd is not None: os.close(fd)
        temporary.unlink(missing_ok=True)
        task.maximum, task.value = batch
        task.transfer.begin(batch[0], "items")
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

"""Content-verified resumable downloads. HTTP Range is only trusted after validation."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from urllib.parse import urljoin, urlparse

import requests
from core import LauncherError, atomic_json

_locks = {}
_registry_lock = threading.Lock()


def download(session, url, target, task, *, cache, expected=None, algorithm='sha512', size=0,
             validator=None, allow_url=None, limit=20 * 1024**3):
    """Keep incomplete bytes in cache; publish the target only after all checks pass."""
    target, cache = Path(target), Path(cache)
    if expected and not re.fullmatch('[a-fA-F0-9]{%d}' % (hashlib.new(algorithm).digest_size * 2), expected):
        raise LauncherError('İndirme doğrulama kaydı geçersiz.')
    def allowed(value):
        parsed=urlparse(value)
        if parsed.scheme not in ('http','https') or parsed.username or parsed.password:
            raise LauncherError('İndirme adresi geçersiz.')
        if allow_url:
            allow_url(value)
        return value
    allowed(url)
    for ancestor in (cache, *cache.parents):
        if ancestor.is_symlink() or ancestor.exists() and getattr(ancestor.lstat(), 'st_file_attributes', 0) & 1024:
            raise LauncherError('İndirme önbelleği bağlantı/junction olamaz.')
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((url + '\0' + algorithm + '\0' + (expected or '')).encode()).hexdigest()
    with _registry_lock:
        lock = _locks.setdefault(str(cache.resolve() / key), threading.RLock())
    with lock:
        part, metadata = cache / (key + '.part'), cache / (key + '.json')
        blob = cache / (key + '.blob')
        if part.is_symlink() or metadata.is_symlink() or blob.is_symlink():
            raise LauncherError('İndirme önbelleği dosyası bağlantı olamaz.')
        try:
            info = json.loads(metadata.read_text(encoding='utf-8')) if metadata.exists() else {}
        except (OSError, ValueError):
            info = {}
        if not isinstance(info,dict): info={}
        cached = bool(expected and blob.is_file())
        payload = blob if cached else part
        offset = payload.stat().st_size if payload.is_file() else 0
        # Without an expected digest we need an origin validator to resume safely.
        if offset and (offset > limit or size and offset > size or not expected and not info.get('validator')):
            payload.unlink(missing_ok=True)
            offset = 0
            cached = False
            payload = part
        task.status('İndiriliyor: ' + target.name)
        task.wait_transfer()
        complete = cached or bool(expected and size and offset == size)
        try:
            if not complete:
                headers = {'Accept-Encoding': 'identity'}
                if offset:
                    headers['Range'] = f'bytes={offset}-'
                    if info.get('validator'):
                        headers['If-Range'] = info['validator']
                current = url
                for _ in range(6):
                    response = session.get(allowed(current), stream=True, headers=headers,
                                           timeout=(15, 45), allow_redirects=False)
                    if getattr(response, 'is_redirect', False) is True:
                        next_url = urljoin(current, response.headers['Location'])
                        response.close()
                        current = allowed(next_url)
                        continue
                    break
                else:
                    raise LauncherError('Çok fazla indirme yönlendirmesi var.')
                with response:
                    status = getattr(response, 'status_code', 200)
                    if status == 416:
                        part.unlink(missing_ok=True)
                        metadata.unlink(missing_ok=True)
                        raise LauncherError('Devam kaydı sunucuyla eşleşmedi. Tekrar dene ile yeniden indirin.')
                    response.raise_for_status()
                    response_headers = getattr(response, 'headers', {})
                    if response_headers.get('Content-Encoding', 'identity').lower() not in ('identity', ''):
                        raise LauncherError('Sunucu devam ettirilebilir ham dosya göndermedi.')
                    total = size or 0
                    if status == 206:
                        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response_headers.get('Content-Range', ''))
                        if not match or int(match[1]) != offset or int(match[2]) < offset or int(match[2]) >= int(match[3]):
                            raise LauncherError('Sunucunun devam aralığı geçersiz.')
                        total = int(match[3])
                        if size and total != size:
                            raise LauncherError('Sunucudaki dosya boyutu değişmiş.')
                    else:
                        # Range can legally be ignored; replacing the partial avoids duplicate bytes.
                        offset = 0
                        total = size or int(response_headers.get('Content-Length', 0))
                    if total > limit:
                        raise LauncherError('İndirme boyut sınırını aşıyor.')
                    etag = response_headers.get('ETag', '')
                    origin_validator = etag if etag and not etag.startswith('W/') else response_headers.get('Last-Modified', '')
                    atomic_json(metadata, {'validator': origin_validator, 'size': total})
                    task.begin_bytes(total)
                    task.transfer.base = offset
                    task.progress(offset)
                    received, started = 0, time.monotonic()
                    with part.open('ab' if offset else 'wb') as output:
                        for chunk in response.iter_content(128 * 1024):
                            task.wait_transfer()
                            if not chunk:
                                continue
                            offset += len(chunk)
                            received += len(chunk)
                            if offset > limit or total and offset > total:
                                raise LauncherError('İndirilen dosya beklenen boyutu aşıyor.')
                            output.write(chunk)
                            task.progress(offset)
                            while True:
                                rate = task.rate_limit
                                delay = received / rate - (time.monotonic() - started) if rate else 0
                                if delay <= 0:
                                    break
                                task.wait_transfer()
                                task.cancel.wait(min(.1, delay))
                    if total and offset != total:
                        raise requests.ConnectionError('Incomplete download')
            else:
                task.begin_bytes(size)
                task.progress(offset)
            task.check()
            if expected:
                actual = hashlib.new(algorithm)
                with payload.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        task.check()
                        actual.update(block)
                if actual.hexdigest().lower() != expected.lower():
                    payload.unlink(missing_ok=True)
                    metadata.unlink(missing_ok=True)
                    raise LauncherError('Dosya doğrulaması başarısız. Dosya kurulmadı.')
            if validator:
                try:
                    validator(payload)
                except Exception:
                    payload.unlink(missing_ok=True)
                    metadata.unlink(missing_ok=True)
                    raise
            if expected and payload != blob:
                os.replace(payload, blob)
                payload = blob
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.verified-download-', dir=target.parent)
            try:
                with os.fdopen(fd, 'wb') as out, payload.open('rb') as inp:
                    shutil.copyfileobj(inp, out, 1024 * 1024)
                task.check()
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
            if not expected: part.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
            return str(target)
        except requests.RequestException as exc:
            raise LauncherError('İndirme kesildi. Tekrar dene ile destekleyen sunucularda kaldığı yerden sürdürülür.') from exc

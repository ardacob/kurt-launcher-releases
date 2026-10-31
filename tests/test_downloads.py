import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import Task, LauncherError, Cancelled
from downloads import download


class Response:
    def __init__(self,chunks,status=200,headers=None):
        self.chunks,self.status_code,self.headers=chunks,status,headers or {}
        self.is_redirect=status in (301,302,307,308)
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def close(self):pass
    def raise_for_status(self):
        if self.status_code>=400:raise requests.HTTPError('HTTP error')
    def iter_content(self,*args):
        for item in self.chunks:
            if isinstance(item,Exception):raise item
            yield item


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.cache=self.root/'cache';self.target=self.root/'target.bin'
        self.raw=b'abcdef';self.expected=hashlib.sha512(self.raw).hexdigest();self.url='https://cdn.example.org/file'
        self.session=Mock()

    def run_download(self,task=None,**kwargs):
        return download(self.session,self.url,self.target,task or Task(),cache=self.cache,
                        expected=self.expected,size=len(self.raw),**kwargs)

    def interrupt(self):
        self.session.get.return_value=Response([b'ab',requests.ConnectionError('cut')],headers={'ETag':'"v1"','Content-Length':'6'})
        with self.assertRaises(LauncherError):self.run_download()
        self.assertEqual(next(self.cache.glob('*.part')).read_bytes(),b'ab')
        self.assertFalse(self.target.exists())

    def test_interrupted_download_resumes_with_range_and_if_range(self):
        self.interrupt()
        self.session.get.return_value=Response([b'cdef'],206,{'Content-Range':'bytes 2-5/6','ETag':'"v1"'})
        self.run_download()
        self.assertEqual(self.target.read_bytes(),self.raw)
        self.assertEqual(self.session.get.call_args.kwargs['headers']['Range'],'bytes=2-')
        self.assertEqual(self.session.get.call_args.kwargs['headers']['If-Range'],'"v1"')
        self.assertFalse(list(self.cache.glob('*.part')))

    def test_server_ignoring_range_restarts_without_duplicate_bytes(self):
        self.interrupt();self.session.get.return_value=Response([self.raw],headers={'Content-Length':'6'})
        self.run_download();self.assertEqual(self.target.read_bytes(),self.raw)

    def test_wrong_range_cannot_replace_an_existing_target(self):
        self.interrupt();self.target.write_bytes(b'precious-original')
        self.session.get.return_value=Response([b'def'],206,{'Content-Range':'bytes 3-5/6'})
        with self.assertRaises(LauncherError):self.run_download()
        self.assertEqual(self.target.read_bytes(),b'precious-original')
        self.assertEqual(next(self.cache.glob('*.part')).read_bytes(),b'ab')

    def test_bad_digest_removes_partial_and_preserves_existing_target(self):
        self.target.write_bytes(b'original');self.session.get.return_value=Response([b'xxxxxx'])
        with self.assertRaises(LauncherError):self.run_download()
        self.assertEqual(self.target.read_bytes(),b'original');self.assertFalse(list(self.cache.glob('*.part')))

    def test_cached_complete_file_still_requires_digest_verification(self):
        self.interrupt();next(self.cache.glob('*.part')).write_bytes(b'wrong!')
        before=self.session.get.call_count
        with self.assertRaises(LauncherError):self.run_download()
        self.assertEqual(self.session.get.call_count,before);self.assertFalse(self.target.exists())

    def test_cancelled_download_keeps_verified_resume_prefix(self):
        task=Task();task.notify=lambda message,value,maximum:task.cancel.set() if value==2 else None
        self.session.get.return_value=Response([b'ab',b'cdef'],headers={'Content-Length':'6'})
        with self.assertRaises(Cancelled):self.run_download(task)
        self.assertEqual(next(self.cache.glob('*.part')).read_bytes(),b'ab')
        self.session.get.return_value=Response([b'cdef'],206,{'Content-Range':'bytes 2-5/6'})
        self.run_download();self.assertEqual(self.target.read_bytes(),self.raw)

    def test_pause_blocks_completion_until_resume(self):
        reached=threading.Event();finished=threading.Event();errors=[]
        task=Task()
        def notify(message,value,maximum):
            if value==2:task.paused.set();reached.set()
        task.notify=notify;self.session.get.return_value=Response([b'ab',b'cdef'])
        def work():
            try:self.run_download(task)
            except Exception as exc:errors.append(exc)
            finally:finished.set()
        thread=threading.Thread(target=work);thread.start()
        try:
            self.assertTrue(reached.wait(2));self.assertFalse(finished.wait(.15))
            task.paused.clear();self.assertTrue(finished.wait(2))
        finally:task.cancel.set();task.paused.clear();thread.join(3)
        self.assertEqual(errors,[]);self.assertEqual(self.target.read_bytes(),self.raw)

    def test_cancelling_a_paused_request_does_not_wait_for_resume(self):
        task=Task();task.paused.set();finished=threading.Event();errors=[]
        def work():
            try:self.run_download(task)
            except Exception as exc:errors.append(exc)
            finally:finished.set()
        thread=threading.Thread(target=work);thread.start();task.cancel.set()
        self.assertTrue(finished.wait(2));thread.join(2)
        self.assertIsInstance(errors[0],Cancelled);self.session.get.assert_not_called()

    def test_speed_limit_is_enforced_for_received_bytes(self):
        self.raw=b'x'*32768;self.expected=hashlib.sha512(self.raw).hexdigest()
        self.session.get.return_value=Response([self.raw]);task=Task();task.rate_limit=65536
        start=time.monotonic();self.run_download(task)
        self.assertGreaterEqual(time.monotonic()-start,.4)

    def test_redirect_policy_is_checked_at_every_hop(self):
        self.session.get.return_value=Response([],302,{'Location':'http://untrusted.example/file'})
        def allow(url):
            if not url.startswith('https://cdn.example.org/'):raise LauncherError('unsafe')
        with self.assertRaises(LauncherError):self.run_download(allow_url=allow)
        self.assertFalse(self.target.exists());self.assertEqual(self.session.get.call_count,1)

    def test_invalid_payload_after_valid_hash_does_not_publish(self):
        self.session.get.return_value=Response([self.raw])
        def invalid(path):raise LauncherError('not a pack')
        with self.assertRaises(LauncherError):self.run_download(validator=invalid)
        self.assertFalse(self.target.exists());self.assertFalse(list(self.cache.glob('*.part')))

    def test_completed_verified_file_is_reused_after_a_batch_retry(self):
        self.session.get.return_value=Response([self.raw]);self.run_download()
        self.target.unlink();calls=self.session.get.call_count
        self.run_download()
        self.assertEqual(self.target.read_bytes(),self.raw)
        self.assertEqual(self.session.get.call_count,calls)


if __name__=='__main__':unittest.main()

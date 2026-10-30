import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ci"))
from ci.common import canonical, release_state, safe_member, version
from ci.sign_ci import extract_payload
from ci import publish
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class ReleaseTests(unittest.TestCase):
    def test_release_gate_preserves_existing_versions_and_blocks_downgrades(self):
        item = {"tag_name": "v1.2.3", "draft": False, "prerelease": False}
        self.assertIs(release_state("1.2.3", [item]), item)
        self.assertIsNone(release_state("1.2.4", [item]))
        with self.assertRaises(ValueError):
            release_state("1.2.2", [item])
        draft = {**item, "draft": True}
        self.assertIs(release_state("1.2.3", [draft]), draft)

    def test_archive_rejects_traversal_windows_drives_and_backslashes(self):
        for name in ("../key", "/abs", "a/../b", "C:/key", "a\\b", "a//b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_member(name)

    def test_signer_accepts_only_clean_application_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("KurtLauncher/data/account.json", "KurtLauncher/ci/key.bin", "KurtLauncher/../key.bin"):
                archive = root / "bad.zip"
                with zipfile.ZipFile(archive, "w") as stream:
                    stream.writestr(name, "private")
                with self.subTest(name=name), self.assertRaises(ValueError):
                    extract_payload(archive, root / "out")

    def test_archive_rejects_case_insensitive_duplicate_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("KurtLauncher/src/test.py", "a")
                stream.writestr("KurtLauncher/src/TEST.py", "b")
            with self.assertRaises(ValueError):
                extract_payload(archive, root / "out")

    def test_standalone_signer_remains_compatible_with_installed_updater(self):
        from core import Store, Task
        from updater import Updater
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "payload"
            (source / "src").mkdir(parents=True)
            (source / "assets").mkdir()
            for name in ("core.py", "updater.py"):
                (source / "src" / name).write_bytes((ROOT / "src" / name).read_bytes())
            (source / "KurtLauncher.exe").write_bytes(b"test-executable")
            (source / "data").mkdir()
            (source / "data/account.json").write_text("never publish")
            key = Ed25519PrivateKey.generate()
            public = key.public_key().public_bytes_raw()
            (source / "assets/update-public-key.bin").write_bytes(public)
            private = root / "private.bin"
            private.write_bytes(key.private_bytes_raw())
            package, feed = root / "app.kurtupdate", root / "latest.json"
            subprocess.run([sys.executable, str(ROOT / "sign_release.py"), "--source", str(source),
                            "--key", str(private), "--output", str(package),
                            "--package-url", "https://example.com/app.kurtupdate", "--feed-output", str(feed)],
                           check=True, capture_output=True)
            updater = Updater(Store(root / "data"), public)
            manifest = updater.inspect(package, allow_current=True)
            self.assertEqual(manifest["version"], version())
            self.assertNotIn("data/account.json", manifest["files"])
            envelope = json.loads(feed.read_text())
            key.public_key().verify(base64.b64decode(envelope["signature"]), canonical(envelope["manifest"]))
            self.assertEqual(envelope["manifest"]["package_sha512"], hashlib.sha512(package.read_bytes()).hexdigest())

    def test_signer_refuses_key_stored_inside_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "src").mkdir()
            for name in ("core.py", "updater.py"):
                (root / "src" / name).write_bytes((ROOT / "src" / name).read_bytes())
            private = root / "key.bin"
            private.write_bytes(Ed25519PrivateKey.generate().private_bytes_raw())
            result = subprocess.run([sys.executable, str(ROOT / "sign_release.py"), "--source", str(root),
                                     "--key", str(private), "--output", str(root / "out.kurtupdate")], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"outside the release folder", result.stderr)

    def test_publication_rejects_pull_requests_and_other_repositories(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "fork/repo", "GITHUB_REF": "refs/heads/main",
                                     "GITHUB_EVENT_NAME": "pull_request"}), patch.object(publish, "request") as api:
            with self.assertRaises(ValueError):
                publish.main()
            api.assert_not_called()

    def test_published_release_is_never_replaced(self):
        current = version()
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "ardacob/kurt-launcher-releases",
                                     "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": "abc"}), \
                patch.object(publish, "releases", return_value=[{"tag_name": "v" + current, "draft": False}]), \
                patch.object(publish, "request") as api:
            publish.main()
            api.assert_not_called()

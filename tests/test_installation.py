import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core import APP_VERSION, LauncherError, Store, atomic_json
from updater import Updater
import installation


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "download/KurtLauncher"
        self.source.mkdir(parents=True)
        self.exe = self.source / "KurtLauncher.exe"
        self.exe.write_bytes(b"publisher-executable")
        (self.source / "README.md").write_text("launcher docs")
        self.store = Store(self.root / "shared/data")
        self.updater = Updater(self.store)
        patcher = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "LocalAppData")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_installer_uses_fixed_app_folder_and_never_packages_game_data_or_keys(self):
        (self.source / "data").mkdir()
        (self.source / "data/world.dat").write_bytes(b"private-world")
        (self.source / "private-key.bin").write_bytes(b"private-key")
        with patch("sys.frozen", True, create=True), patch("sys.executable", str(self.exe)), \
                patch.object(self.updater, "launch_helper") as launch:
            self.assertTrue(installation.prepare_managed_install(self.updater))
        stage = launch.call_args.args[0]
        records = json.loads((stage / "verified.json").read_text())["files"]
        self.assertEqual(set(records), {"KurtLauncher.exe", "README.md"})
        self.assertEqual(launch.call_args.kwargs["installation"], self.root / "LocalAppData/KurtLauncher/app")
        self.assertEqual(launch.call_args.kwargs["obsolete"], self.exe)
        self.assertTrue(self.exe.is_file())  # Removal waits until the installed app starts.
        self.assertEqual((self.source / "data/world.dat").read_bytes(), b"private-world")

    def test_already_managed_launcher_does_not_reinstall_itself(self):
        managed = installation.app_folder() / "KurtLauncher.exe"
        with patch("sys.frozen", True, create=True), patch("sys.executable", str(managed)), \
                patch.object(self.updater, "launch_helper") as launch:
            self.assertFalse(installation.prepare_managed_install(self.updater))
            launch.assert_not_called()

    def test_old_download_cannot_downgrade_a_newer_managed_installation(self):
        managed = installation.app_folder() / "KurtLauncher.exe"
        managed.parent.mkdir(parents=True)
        managed.write_bytes(b"newer-publisher-executable")
        newer = ".".join(APP_VERSION.split(".")[:2] + [str(int(APP_VERSION.split(".")[2]) + 1)])
        digest = hashlib.sha512(managed.read_bytes()).hexdigest()
        atomic_json(managed.parent.parent / "installation.json", {"format": 1, "product": "KurtLauncher", "version": newer, "sha512": digest})
        with patch("sys.frozen", True, create=True), patch("sys.executable", str(self.exe)), \
                patch.object(self.updater, "launch_helper") as launch:
            installation.prepare_managed_install(self.updater)
        stage = launch.call_args.args[0]
        info = json.loads((stage / "verified.json").read_text())
        self.assertEqual(info["files"], {})
        self.assertEqual(info["version"], newer)
        self.assertEqual(launch.call_args.kwargs["redirect_hash"], digest)
        self.assertEqual(managed.read_bytes(), b"newer-publisher-executable")

    def test_copy_hash_failure_never_starts_installer_or_deletes_source(self):
        def bad_copy(source, destination):
            Path(destination).write_bytes(b"corrupted")
        with patch("sys.frozen", True, create=True), patch("sys.executable", str(self.exe)), \
                patch("installation.shutil.copy2", side_effect=bad_copy), \
                patch.object(self.updater, "launch_helper") as launch:
            with self.assertRaises(LauncherError):
                installation.prepare_managed_install(self.updater)
            launch.assert_not_called()
        self.assertEqual(self.exe.read_bytes(), b"publisher-executable")
        self.assertFalse(list((self.store.root / "updates").glob("verified-install-*")))

    def test_installer_cannot_mark_an_unrelated_executable_for_deletion(self):
        stage = self.store.root / "updates/verified-test"
        stage.mkdir(parents=True)
        with patch("sys.frozen", True, create=True), patch("sys.executable", str(self.exe)), \
                patch("updater.subprocess.Popen") as start:
            with self.assertRaises(LauncherError):
                self.updater.launch_helper(stage, obsolete=self.root / "someone-else/KurtLauncher.exe")
            start.assert_not_called()

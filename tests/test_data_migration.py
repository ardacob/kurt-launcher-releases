import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6.QtCore import QLockFile
from core import Store, atomic_json
from data_paths import DataLocationError
import data_migration as migration


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.target = self.root / "LocalAppData/KurtLauncher/data"
        patcher = patch("data_migration.common_data_folder", return_value=self.target)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.old = Store(self.root / "old-launcher/data")
        self.profile = self.old.create("Dünyam", "1.20.1", "fabric")
        world = self.old.directory(self.profile) / "saves/Dunya/level.dat"
        world.parent.mkdir(parents=True)
        world.write_bytes(b"world-before-migration")
        (self.old.mods(self.profile) / "mod.jar").write_bytes(b"original-mod")

    def test_copy_is_verified_and_source_files_remain_intact(self):
        before = {n: migration.digest(p) for n, p in migration.files_in(self.old.root).items()}
        positions = []
        actual = migration.ensure_shared_data(self.old.root, progress=lambda m, v, maximum: positions.append((v, maximum)))
        self.assertEqual(actual, self.target)
        for name, expected in before.items():
            self.assertEqual(migration.digest(actual / name), expected)
            self.assertEqual(migration.digest(self.old.root / name), expected)
        self.assertEqual(positions[-1], (1, 1))
        self.assertTrue((self.target / migration.RECEIPT).is_file())

    def test_retry_reuses_a_completed_identical_copy(self):
        migration.ensure_shared_data(self.old.root)
        receipt = (self.target / migration.RECEIPT).read_bytes()
        self.assertEqual(migration.ensure_shared_data(self.old.root), self.target)
        self.assertEqual((self.target / migration.RECEIPT).read_bytes(), receipt)

    def test_other_common_archive_is_never_overwritten_or_merged(self):
        common = Store(self.target)
        common.create("Başka arşiv", "1.8.9", "vanilla")
        before = (common.root / "profiles.json").read_bytes()
        with self.assertRaises(DataLocationError):
            migration.ensure_shared_data(self.old.root)
        self.assertEqual((common.root / "profiles.json").read_bytes(), before)
        self.assertEqual(len(self.old.profiles), 1)

    def test_disk_full_leaves_old_archive_and_location_untouched(self):
        with patch("data_migration.shutil.disk_usage", return_value=SimpleNamespace(free=0)), self.assertRaises(DataLocationError):
            migration.ensure_shared_data(self.old.root)
        self.assertFalse(self.target.exists())
        self.assertTrue((self.old.root / "profiles.json").is_file())

    def test_missing_source_does_not_create_an_empty_shared_archive(self):
        with self.assertRaises(DataLocationError):
            migration.ensure_shared_data(self.root / "missing-old-data")
        self.assertFalse(self.target.exists())

    def test_copy_error_removes_only_its_temporary_stage(self):
        with patch("data_migration.shutil.copystat", side_effect=OSError("disk write failed")), self.assertRaises(OSError):
            migration.ensure_shared_data(self.old.root)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.target.parent.glob(".data-migration-*")))
        self.assertTrue((self.old.root / "profiles.json").is_file())

    def test_corrupted_copy_is_not_committed(self):
        real_digest = migration.digest
        def corrupt(path):
            if any(part.startswith(".data-migration-") for part in path.parts):
                return "0" * 128
            return real_digest(path)
        with patch("data_migration.digest", side_effect=corrupt), self.assertRaises(DataLocationError):
            migration.ensure_shared_data(self.old.root)
        self.assertFalse(self.target.exists())

    def test_source_change_during_copy_is_detected(self):
        source_file = self.old.root / "a.bin"
        source_file.write_bytes(b"old")
        changed = False
        def progress(message, value, maximum):
            nonlocal changed
            if not changed:
                source_file.write_bytes(b"new")
                changed = True
        with self.assertRaises(DataLocationError):
            migration.ensure_shared_data(self.old.root, progress=progress)
        self.assertEqual(source_file.read_bytes(), b"new")
        self.assertFalse(self.target.exists())

    def test_running_old_launcher_blocks_migration(self):
        lock = QLockFile(str(self.old.root / "launcher.lock"))
        self.assertTrue(lock.tryLock(0))
        try:
            with self.assertRaises(DataLocationError):
                migration.ensure_shared_data(self.old.root)
            self.assertFalse(self.target.exists())
        finally:
            lock.unlock()

    def test_current_launcher_can_migrate_while_holding_its_own_lock(self):
        lock = QLockFile(str(self.old.root / "launcher.lock"))
        self.assertTrue(lock.tryLock(0))
        try:
            self.assertEqual(migration.ensure_shared_data(self.old.root, own_launcher_lock=True), self.target)
            self.assertTrue(lock.isLocked())
        finally:
            lock.unlock()

    def test_running_minecraft_world_lock_blocks_the_copy(self):
        session = self.old.directory(self.profile) / "saves/Dunya/session.lock"
        session.write_bytes(b"12345678")
        code = "import os,sys; f=open(sys.argv[1],'r+b'); "
        if os.name == "nt":
            code += "import msvcrt; msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1); "
        else:
            code += "import fcntl; fcntl.lockf(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB); "
        code += "print('READY',flush=True); sys.stdin.buffer.read(1)"
        process = subprocess.Popen([sys.executable, "-c", code, str(session)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(process.stdout.readline().strip(), b"READY")
            with self.assertRaises(DataLocationError):
                migration.ensure_shared_data(self.old.root)
            self.assertFalse(self.target.exists())
        finally:
            process.communicate(b"x", timeout=5)
        self.assertEqual(migration.ensure_shared_data(self.old.root), self.target)
        self.assertFalse((self.target / session.relative_to(self.old.root)).exists())

    def test_custom_java_path_follows_the_copied_runtime(self):
        executable = self.old.minecraft / "runtime/java.exe"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"java")
        self.old.settings["java"] = str(executable)
        self.old.save()
        migration.ensure_shared_data(self.old.root)
        settings = json.loads((self.target / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["java"], str(self.target / "minecraft/runtime/java.exe"))
        self.assertEqual(self.old.settings["java"], str(executable))
        self.assertEqual(migration.ensure_shared_data(self.old.root), self.target)

    def test_update_downloads_and_session_files_are_not_migrated(self):
        updates = self.old.root / "updates"
        updates.mkdir()
        (updates / "old.kurtupdate").write_bytes(b"temporary-download")
        migration.ensure_shared_data(self.old.root)
        self.assertFalse((self.target / "updates").exists())
        self.assertFalse((self.target / "launcher.lock").exists())

    def test_link_to_another_folder_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.old.root / "linked").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("This Windows user cannot create symbolic links")
        with self.assertRaises(DataLocationError):
            migration.ensure_shared_data(self.old.root)
        self.assertFalse(self.target.exists())

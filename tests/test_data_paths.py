"""Real legacy catalogs and world bytes survive launches from another version folder."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import core
from core import Store, atomic_json
from data_paths import (DataChoiceRequired, DataFolderMissing, DataLocationError,
                        remembered_data_folder, remember_data_folder, resolve_data_folder,
                        selected_data_folder)


class DataPathsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / "LocalAppData/KurtLauncher/data-location.json"
        self.addCleanup(patch.stopall)
        patch("data_paths.location_file", return_value=self.config).start()
        patch.dict(os.environ, {"KURT_DATA_DIR": ""}).start()

    def legacy(self, name="KurtLauncher-v0.4.1-Windows"):
        base = self.root / name / "KurtLauncher"
        store = Store(base / "data")
        profile = store.create("Eski dünyam", "1.20.1", "fabric")
        profile["installed"] = "fabric-loader-0.16.0-1.20.1"
        store.settings.update(last_profile=profile["id"], offline_username="WolfPlayer", login_mode="offline")
        store.save()
        game = store.directory(profile)
        (game / "saves/Dunyam").mkdir(parents=True)
        (game / "saves/Dunyam/level.dat").write_bytes(b"original-world-041")
        (game / "mods").mkdir()
        (game / "mods/sodium.jar").write_bytes(b"original-mod")
        atomic_json(game / "mods.lock.json", {"sodium": {"file": "sodium.jar", "version_id": "old-version"}})
        installed = store.minecraft / "versions" / profile["installed"]
        installed.mkdir(parents=True)
        (installed / (profile["installed"] + ".json")).write_text("{}")
        return base, store, profile

    def start_at(self, base):
        base.mkdir(parents=True, exist_ok=True)
        with patch.object(core, "__file__", str(base / "src/core.py")):
            return Store()

    def test_041_world_mods_install_and_selected_profile_reappear_in_another_launcher(self):
        base, old, profile = self.legacy()
        self.start_at(base)  # The first updated launch remembers its old data.
        another = self.start_at(self.root / "Elsewhere/KurtLauncher-0.4.4")
        self.assertEqual(another.root, old.root)
        self.assertEqual(another.profiles, old.profiles)
        self.assertEqual(another.settings["last_profile"], profile["id"])
        self.assertEqual(another.settings["offline_username"], "WolfPlayer")
        self.assertEqual(another.profiles[0]["version"], "1.20.1")
        self.assertEqual(another.profiles[0]["installed"], profile["installed"])
        self.assertEqual((another.directory(profile) / "saves/Dunyam/level.dat").read_bytes(), b"original-world-041")
        self.assertEqual((another.mods(profile) / "sodium.jar").read_bytes(), b"original-mod")
        self.assertEqual(another.mod_lock(profile)["sodium"]["version_id"], "old-version")
        self.assertEqual(another.minecraft, old.minecraft)

    def test_fresh_zip_finds_one_nearby_old_archive_without_a_previous_registration(self):
        _, old, _ = self.legacy()
        new = self.start_at(self.root / "KurtLauncher-v0.4.4-Windows/KurtLauncher")
        self.assertEqual(new.root, old.root)
        self.assertEqual(remembered_data_folder(), old.root)

    def test_an_empty_043_catalog_does_not_hide_the_remembered_041_world(self):
        _, old, _ = self.legacy()
        remember_data_folder(old.root)
        new_base = self.root / "KurtLauncher-0.4.3"
        empty = Store(new_base / "data")
        empty.save()
        actual = self.start_at(new_base)
        self.assertEqual(actual.root, old.root)
        self.assertEqual(len(actual.profiles), 1)
        self.assertEqual(json.loads((empty.root / "profiles.json").read_text()), [])

    def test_old_update_worker_with_empty_043_data_finds_the_real_041_archive(self):
        _, old, _ = self.legacy()
        new_base = self.root / "KurtLauncher-0.4.3"
        empty = Store(new_base / "data")
        empty.save()
        with patch.dict(os.environ, {"KURT_DATA_DIR": str(empty.root)}), \
                patch.object(core, "__file__", str(new_base / "src/core.py")):
            updated = Store(update_from=empty.root)
        self.assertEqual(updated.root, old.root)
        self.assertEqual(remembered_data_folder(), old.root)
        self.assertEqual(json.loads((empty.root / "profiles.json").read_text()), [])

    def test_old_update_worker_cannot_replace_remembered_world_with_empty_data(self):
        _, old, _ = self.legacy()
        remember_data_folder(old.root)
        empty = Store(self.root / "fresh-043/data")
        empty.save()
        with patch.dict(os.environ, {"KURT_DATA_DIR": str(empty.root)}):
            updated = Store(update_from=empty.root)
        self.assertEqual(updated.root, old.root)
        self.assertEqual(remembered_data_folder(), old.root)

    def test_old_update_worker_preserves_custom_populated_data_directory(self):
        _, old, _ = self.legacy("KurtLauncher-private-games")
        self.legacy("KurtLauncher-other-games")
        with patch.dict(os.environ, {"KURT_DATA_DIR": str(old.root)}):
            updated = Store(update_from=old.root)
        self.assertEqual(updated.root, old.root)
        self.assertEqual(remembered_data_folder(), old.root)

    def test_new_install_uses_one_user_archive_independent_of_exe_folder(self):
        first = self.start_at(self.root / "first")
        second = self.start_at(self.root / "second")
        self.assertEqual(first.root, self.config.parent / "data")
        self.assertEqual(second.root, first.root)
        self.assertFalse((self.root / "second/data").exists())

    def test_two_legacy_archives_require_a_choice_and_are_not_merged(self):
        _, first, _ = self.legacy("KurtLauncher-old-one")
        _, second, _ = self.legacy("KurtLauncher-old-two")
        with self.assertRaises(DataChoiceRequired) as caught:
            self.start_at(self.root / "KurtLauncher-new")
        self.assertEqual(set(caught.exception.candidates), {first.root, second.root})
        self.assertFalse(self.config.exists())
        self.assertFalse((self.root / "KurtLauncher-new/data").exists())

    def test_missing_old_disk_does_not_silently_create_an_empty_profile_catalog(self):
        missing = self.root / "disconnected/data"
        atomic_json(self.config, {"format": 1, "data_directory": str(missing)})
        with self.assertRaises(DataFolderMissing):
            self.start_at(self.root / "KurtLauncher-new")
        self.assertFalse((self.config.parent / "data").exists())

    def test_corrupt_or_relative_location_is_rejected(self):
        for value in ({"format": 1, "data_directory": "relative/data"}, {"format": 42, "data_directory": str(self.root)}):
            atomic_json(self.config, value)
            with self.subTest(value=value), self.assertRaises(DataLocationError):
                resolve_data_folder(self.root / "app")

    def test_explicit_and_environment_test_directories_never_change_user_location(self):
        _, old, _ = self.legacy()
        remember_data_folder(old.root)
        before = self.config.read_bytes()
        explicit = self.root / "explicit"
        self.assertEqual(Store(explicit).root, explicit)
        with patch.dict(os.environ, {"KURT_DATA_DIR": str(self.root / "smoke")}):
            self.assertEqual(self.start_at(self.root / "app").root, self.root / "smoke")
        self.assertEqual(self.config.read_bytes(), before)

    def test_picker_accepts_old_app_or_data_folder_and_rejects_empty_folder(self):
        base, old, _ = self.legacy()
        self.assertEqual(selected_data_folder(base), old.root)
        self.assertEqual(selected_data_folder(old.root), old.root)
        with self.assertRaises(DataLocationError):
            selected_data_folder(self.root / "empty")

    def test_unrelated_nearby_app_data_is_not_adopted(self):
        unrelated = Store(self.root / "OtherApplication/data")
        unrelated.create("Not Kurt", "1.20.1", "vanilla")
        actual = self.start_at(self.root / "KurtLauncher-new")
        self.assertNotEqual(actual.root, unrelated.root)
        self.assertEqual(actual.profiles, [])

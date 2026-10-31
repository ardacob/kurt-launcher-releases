import base64
import copy
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from core import APP_VERSION, Launcher, Store, Task, LauncherError, Cancelled, atomic_json
from packs import Packs, ModUpdates, pack_path, download_file
from snapshots import Snapshots, digest, relative_path
from insights import diagnose, redact, apply_preset, Collections, TransferStats
from updater import Updater, canonical
from invites import encode_invite, decode_invite
from servers import ServerManager
from transfers import stream_library_file, library_downloads
from test_core import FakeApi, version, jar_bytes, dep

NEXT_VERSION = ".".join(APP_VERSION.split(".")[:2] + [str(int(APP_VERSION.split(".")[2]) + 1)])


class Features(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data")
        self.launcher = Launcher(self.store)
        self.profile = self.store.create("Arkadaşlar", "1.20.1", "fabric")
        self.profile["loader_version"] = "0.16.0"
        self.directory = self.store.directory(self.profile)
        self.world = self.directory / "saves/test/level.dat"
        self.world.parent.mkdir(parents=True)
        self.world.write_bytes(b"my world")
        self.packs = Packs(self.launcher)

    def test_snapshot_restore_world_mods_and_profile_metadata(self):
        (self.store.mods(self.profile) / "test.jar").write_bytes(jar_bytes())
        source = self.launcher.snapshots.create(self.profile, Task())
        self.world.write_bytes(b"changed")
        self.profile["version"] = "1.21"
        (self.directory / "new-file.txt").write_text("new")
        self.launcher.snapshots.restore(self.profile, source, Task())
        self.assertEqual(self.world.read_bytes(), b"my world")
        self.assertEqual(self.profile["version"], "1.20.1")
        self.assertFalse((self.directory / "new-file.txt").exists())
        self.assertEqual(len(self.launcher.snapshots.list(self.profile)), 2)

    def test_snapshot_corrupt_hash_preserves_current_world(self):
        source = Path(self.launcher.snapshots.create(self.profile, Task()))
        with zipfile.ZipFile(source) as arc:
            entries = {n: arc.read(n) for n in arc.namelist()}
        entries["files/saves/test/level.dat"] = b"corrupted"
        with zipfile.ZipFile(source, "w") as arc:
            for n, raw in entries.items(): arc.writestr(n, raw)
        with self.assertRaises(LauncherError): self.launcher.snapshots.restore(self.profile, source, Task())
        self.assertEqual(self.world.read_bytes(), b"my world")

    def test_snapshot_restore_rejects_path_traversal_and_other_profile(self):
        source = Path(self.launcher.snapshots.create(self.profile, Task()))
        with zipfile.ZipFile(source) as arc: meta = json.loads(arc.read("snapshot.json"))
        meta["files"] = {"../escape": "0"*128}
        with zipfile.ZipFile(source, "w") as arc: arc.writestr("snapshot.json", json.dumps(meta))
        with self.assertRaises(LauncherError): self.launcher.snapshots.restore(self.profile, source, Task())
        other = self.store.create("Other", "1.20.1", "fabric")
        with self.assertRaises(LauncherError): self.launcher.snapshots.restore(other, source, Task())
        self.assertEqual(self.world.read_bytes(), b"my world")

    def test_backup_retention_keeps_manual_snapshots(self):
        self.store.settings["backup_keep"] = 2
        manager = self.launcher.snapshots
        manager.create(self.profile)
        for _ in range(4): manager.before_change(self.profile)
        items = manager.list(self.profile)
        self.assertEqual(len(items), 3)
        self.assertEqual(sum(v["automatic"] for v in items), 2)

    def test_backup_blocks_running_game_or_active_server(self):
        self.launcher.process = Mock()
        self.launcher.process.poll.return_value = None
        with self.assertRaises(LauncherError): self.launcher.snapshots.create(self.profile)
        self.launcher.process = None
        manager = ServerManager(self.launcher)
        server = manager.create("Friends", "1.20.1")
        manager.process = Mock()
        manager.process.poll.return_value = None
        manager.active_id = server["id"]
        with self.assertRaises(LauncherError): self.launcher.snapshots.create(server)

    def test_backup_cancel_leaves_no_partial_zip(self):
        task = Task()
        task.cancel.set()
        with self.assertRaises(Cancelled): self.launcher.snapshots.create(self.profile, task)
        self.assertEqual(list(self.launcher.snapshots.folder(self.profile).iterdir()), [])

    def pack(self, records=None, overrides=None):
        raw = jar_bytes()
        records = records if records is not None else [{"path": "mods/test.jar", "hashes": {"sha512": hashlib.sha512(raw).hexdigest(), "sha1": hashlib.sha1(raw).hexdigest()},
            "fileSize": len(raw), "downloads": ["https://cdn.modrinth.com/data/test.jar"]}]
        index = {"formatVersion": 1, "game": "minecraft", "name": "Shared pack", "versionId": "1", "dependencies": {"minecraft": "1.20.1", "fabric-loader": "0.16.0"}, "files": records}
        target = self.root / "test.mrpack"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("modrinth.index.json", json.dumps(index))
            for name, content in (overrides or {}).items(): archive.writestr(name, content)
        return target

    def test_pack_path_rejects_windows_escape_and_program_files(self):
        for name in ("../evil", "C:/evil", "mods/../bad.jar", "mods\\bad.jar", "mods/CON.jar", "data/account.json", "mods/x.jar:stream", "config/evil.ps1"):
            with self.subTest(name=name), self.assertRaises(LauncherError): pack_path(name)

    def test_pack_duplicate_and_override_validation(self):
        target = self.pack(overrides={"overrides/../../escape": "bad"})
        with self.assertRaises(LauncherError): self.packs.inspect(target)
        target = self.pack(overrides={"overrides/config/good.json": "{}"})
        with zipfile.ZipFile(target, "a") as archive: archive.writestr("../escape", "bad")
        with self.assertRaises(LauncherError): self.packs.inspect(target)

    def test_pack_import_isolated_and_optional_and_override_layers(self):
        records = json.loads(zipfile.ZipFile(self.pack()).read("modrinth.index.json"))["files"]
        optional = copy.deepcopy(records[0])
        optional["path"] = "mods/optional.jar"
        optional["env"] = {"client": "optional"}
        records.append(optional)
        source = self.pack(records, {"overrides/config/settings.json": "common", "client-overrides/config/settings.json": "client"})
        self.launcher.versions = lambda: ({"versions": [{"id": "1.20.1"}]}, False)
        self.packs.api.get = Mock(side_effect=LauncherError("Unknown hash"))
        def download(api, record, target, task):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(jar_bytes())
        with patch("packs.download_file", side_effect=download):
            p = self.packs.import_pack(source, Task())
        target = self.store.directory(p)
        self.assertNotEqual(p["id"], self.profile["id"])
        self.assertEqual(self.world.read_bytes(), b"my world")
        self.assertTrue((target / "mods/test.jar").is_file())
        self.assertFalse((target / "mods/optional.jar").exists())
        self.assertEqual((target / "config/settings.json").read_text(), "client")

    def test_pack_failed_download_leaves_no_new_profile(self):
        source = self.pack()
        self.launcher.versions = lambda: ({"versions": [{"id": "1.20.1"}]}, False)
        with patch("packs.download_file", side_effect=LauncherError("connection failed")):
            with self.assertRaises(LauncherError): self.packs.import_pack(source, Task())
        self.assertEqual(len(self.store.profiles), 1)
        self.assertFalse(list((self.store.root / "instances").glob(".pack-*")))

    def test_pack_preview_change_not_imported(self):
        source = self.pack()
        preview = self.packs.inspect(source)
        with zipfile.ZipFile(source, "a") as archive: archive.writestr("note.txt", "changed")
        with self.assertRaises(LauncherError): self.packs.import_pack(source, Task(), preview)

    def test_known_incompatible_pack_mod_not_committed(self):
        source = self.pack()
        self.launcher.versions = lambda: ({"versions": [{"id": "1.20.1"}]}, False)
        incompatible = version("test")
        incompatible["loaders"] = ["forge"]
        self.packs.api.get = Mock(return_value=incompatible)
        def download(api, record, target, task):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(jar_bytes())
        with patch("packs.download_file", side_effect=download), self.assertRaises(LauncherError): self.packs.import_pack(source, Task())
        self.assertEqual(len(self.store.profiles), 1)

    def test_curated_pack_keeps_pinned_versions_and_reports_cross_loader_metadata(self):
        source=self.pack()
        self.launcher.versions=lambda:({'versions':[{'id':'1.20.1'}]},False)
        selected=version('test');selected['environment']='server_only'
        selected['dependencies']=[dep('missing-other-loader')]
        self.packs.api.get=Mock(return_value=selected)
        def download(api,record,target,task):
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(jar_bytes())
        with patch('packs.download_file',side_effect=download):profile=self.packs.import_pack(source,Task())
        entry=next(iter(self.store.mod_lock(profile).values()))
        self.assertTrue(entry['pinned']);self.assertTrue(entry['pack_managed'])
        self.assertIn('pack_compatibility_note',entry)
        self.launcher.mods.validate_enabled(profile)

    def test_export_contains_metadata_not_mod_binaries_or_world(self):
        v = version("test")
        self.launcher.api = FakeApi([v])
        self.launcher.mods.api = self.launcher.api
        self.launcher.mods.install("test", self.profile, Task())
        packs = Packs(self.launcher)
        target = self.root / "shared.mrpack"
        packs.export(self.profile, target, Task())
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(archive.namelist(), ["modrinth.index.json"])
            index = json.loads(archive.read("modrinth.index.json"))
            self.assertEqual(index["dependencies"]["fabric-loader"], "0.16.0")
            self.assertEqual(len(index["files"]), 1)

    def test_hash_failure_not_written_and_unsafe_redirect_rejected(self):
        api = Mock()
        response = Mock()
        response.is_redirect = False
        response.headers = {}
        response.iter_content.return_value = iter([b"wrong"])
        response.__enter__ = lambda v: response
        response.__exit__ = lambda *v: None
        api.session.get.return_value = response
        record = {"hashes": {"sha512": "0"*128}, "downloads": ["https://cdn.modrinth.com/test.jar"]}
        target = self.root / "mod.jar"
        with self.assertRaises(LauncherError): download_file(api, record, target, Task())
        self.assertFalse(target.exists())
        response.is_redirect = True
        response.headers = {"Location": "http://127.0.0.1/private"}
        with self.assertRaises(LauncherError): download_file(api, record, target, Task())
        self.assertEqual(api.session.get.call_count, 2)

    def test_comparison_uses_hash_not_filename_and_ignores_server_only(self):
        raw = jar_bytes()
        (self.store.mods(self.profile) / "renamed.jar").write_bytes(raw)
        record = {"path": "mods/test.jar", "hashes": {"sha512": hashlib.sha512(raw).hexdigest()}, "downloads": []}
        description = {"format": 1, "version": "1.20.1", "loader": "fabric", "loader_version": "0.16.0", "files": [record]}
        result = self.packs.compare(self.profile, description)
        self.assertTrue(result["profile_matches"])
        self.assertEqual(result["rows"][0]["state"], "Eşleşiyor")
        record["env"] = {"client": "unsupported"}
        self.assertEqual(self.packs.compare(self.profile, description)["rows"], [])

    def test_mod_update_transaction_and_pin(self):
        old = version("test", "v1")
        old["date_published"] = "2025-01-01"
        api = FakeApi([old])
        self.launcher.api = self.launcher.mods.api = api
        self.launcher.mods.install("test", self.profile, Task())
        newer = version("test", "v2")
        updater = ModUpdates(self.launcher)
        row = {"project_id": "test", "old": self.store.mod_lock(self.profile)["test"], "new": newer, "pinned": False, "profile_id": self.profile["id"]}
        api.versions["test"] = newer
        updater.apply(self.profile, [row], Task())
        self.assertEqual(self.store.mod_lock(self.profile)["test"]["version_id"], "v2")
        self.assertTrue(updater.pin(self.profile, "test.jar"))
        self.assertTrue(self.store.mod_lock(self.profile)["test"]["pinned"])
        self.assertGreaterEqual(len(self.launcher.snapshots.list(self.profile)), 2)

    def test_mod_update_failure_preserves_original(self):
        old = version("test", "v1")
        api = FakeApi([old])
        self.launcher.api = self.launcher.mods.api = api
        self.launcher.mods.install("test", self.profile, Task())
        newer = version("test", "v2")
        row = {"project_id": "test", "old": self.store.mod_lock(self.profile)["test"], "new": newer, "pinned": False, "profile_id": self.profile["id"]}
        api.versions["test"] = newer
        api.fail_on = "test.jar"
        with self.assertRaises(LauncherError): ModUpdates(self.launcher).apply(self.profile, [row], Task())
        self.assertEqual(self.store.mod_lock(self.profile)["test"]["version_id"], "v1")
        self.assertEqual((self.store.mods(self.profile) / "test.jar").read_bytes(), jar_bytes())
        self.assertEqual(len(list((self.store.root / "instances").iterdir())), 1)

    def test_mod_sync_recognises_replacement_and_commits_lock(self):
        old = version("test", "v1")
        api = FakeApi([old])
        self.launcher.api = self.launcher.mods.api = api
        self.launcher.mods.install("test", self.profile, Task())
        oldfile = self.store.mods(self.profile) / "test.jar"
        oldfile.rename(oldfile.with_name("test-old.jar"))
        lock = self.store.mod_lock(self.profile)
        lock["test"]["file"] = "test-old.jar"
        atomic_json(self.directory / "mods.lock.json", lock)
        # Different bytes, but still a valid JAR.
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as jar: jar.writestr("fabric.mod.json", '{"id":"test","version":"2"}')
        raw = data.getvalue()
        record = {"path": "mods/test-new.jar", "hashes": {"sha512": hashlib.sha512(raw).hexdigest()}, "downloads": ["https://cdn.modrinth.com/new.jar"]}
        description = {"format": 1, "version": "1.20.1", "loader": "fabric", "files": [record]}
        api.get = Mock(return_value=version("test", "v2"))
        def download(api, record, target, task): target.write_bytes(raw)
        with patch("packs.download_file", side_effect=download): Packs(self.launcher).sync(self.profile, description, Task())
        self.assertFalse((self.store.mods(self.profile) / "test-old.jar").exists())
        self.assertTrue((self.store.mods(self.profile) / "test-new.jar").exists())
        self.assertEqual(self.store.mod_lock(self.profile)["test"]["version_id"], "v2")

    def test_diagnosis_and_private_report_redaction(self):
        log = 'UnsupportedClassVersionError --accessToken SECRET access_token="TOKEN" C:\\Users\\Arda\\game 192.168.1.42'
        self.assertIn("Java", diagnose(log)[0]["title"])
        safe = redact(log)
        for secret in ("SECRET", "TOKEN\"", "Arda", "192.168.1.42"): self.assertNotIn(secret, safe)

    def test_preset_preserves_other_options(self):
        path = self.directory / "options.txt"
        path.write_text("music:0.5\nrenderDistance:32\nfancyGraphics:true\n", encoding="utf-8")
        apply_preset(self.store, self.profile, "low")
        self.assertIn("music:0.5", path.read_text())
        self.assertIn("renderDistance:6", path.read_text())
        self.assertEqual(path.read_text().count("renderDistance:"), 1)

    def test_collections_are_local_and_persistent(self):
        collections = Collections(self.store)
        collections.add("Performans", {"project_id": "sodium", "title": "Sodium"})
        self.assertIn("sodium", Collections(self.store).data["Performans"])
        collections.remove("Performans", "sodium")
        self.assertFalse(Collections(self.store).data["Performans"])

    def test_v2_invite_preserves_mod_manifest_and_old_invite_still_works(self):
        metadata = {"format": 1, "version": "1.20.1", "loader": "fabric", "loader_version": "0.16.0", "files": []}
        server = {**self.profile, "mod_manifest": metadata}
        code = encode_invite("friends.joinmc.link:1234", server)
        self.assertTrue(code.startswith("KURT2-"))
        self.assertEqual(decode_invite(code)["mod_manifest"], metadata)
        self.assertNotIn("mod_manifest", decode_invite(encode_invite("friends.joinmc.link:1234", self.profile)))

    def test_invite_decompression_bomb_rejected(self):
        raw = zlib.compress(b"x" * 1000000)
        code = "KURT2-" + base64.urlsafe_b64encode(raw + struct.pack(">I", zlib.crc32(raw))).decode().rstrip("=")
        with self.assertRaises(LauncherError): decode_invite(code)

    def test_server_configuration_and_whitelist(self):
        manager = ServerManager(self.launcher)
        server = manager.create("Friends", "1.20.1")
        folder = self.store.directory(server)
        (folder / "server.properties").write_text("level-name=precious-world\n", encoding="utf-8")
        manager.configure(server, {"difficulty": "hard", "gamemode": "survival", "white-list": "true", "view-distance": "8"}, 3072, 12, Task())
        self.assertEqual(manager.configuration(server)["level-name"], "precious-world")
        self.assertEqual(manager.configuration(server)["difficulty"], "hard")
        manager.whitelist(server, "Arda_1")
        entries = json.loads((folder / "whitelist.json").read_text())
        self.assertEqual(entries[0]["name"], "Arda_1")
        manager.whitelist(server, "Arda_1", add=False)
        self.assertEqual(json.loads((folder / "whitelist.json").read_text()), [])

    def test_library_stream_has_bytes_progress_and_preserves_batch(self):
        raw = b"official-file"
        session = Mock()
        response = Mock()
        response.headers = {"Content-Length": str(len(raw))}
        response.iter_content.return_value = iter([raw[:3], raw[3:]])
        response.__enter__ = lambda value: response
        response.__exit__ = lambda *args: None
        session.get.return_value = response
        progress = []
        task = Task(lambda *v: progress.append(v))
        task.set_max(100)
        task.progress(5)
        path = self.root / "library.jar"
        stream_library_file(task, "https://example.org/file", path, sha1=hashlib.sha1(raw).hexdigest(), session=session)
        self.assertEqual(path.read_bytes(), raw)
        self.assertTrue(any(v[1:] == (len(raw), len(raw)) for v in progress))
        self.assertEqual((task.value, task.maximum), (5, 100))

    def test_library_stream_bad_hash_preserves_existing_file(self):
        response = Mock()
        response.headers = {}
        response.iter_content.return_value = iter([b"bad"])
        response.__enter__ = lambda value: response
        response.__exit__ = lambda *args: None
        session = Mock()
        session.get.return_value = response
        path = self.root / "library.jar"
        path.write_bytes(b"old")
        with self.assertRaises(LauncherError): stream_library_file(Task(), "https://example.org/file", path, sha1="0"*40, session=session)
        self.assertEqual(path.read_bytes(), b"old")

    def test_library_adapter_references_restored_on_failure(self):
        import minecraft_launcher_lib._helper as helper
        import minecraft_launcher_lib.install as install
        original = helper.download_file
        with self.assertRaises(ValueError):
            with library_downloads(Task()):
                self.assertIsNot(helper.download_file, original)
                self.assertIs(install.download_file, helper.download_file)
                raise ValueError("test")
        self.assertIs(helper.download_file, original)
        self.assertIs(install.download_file, original)


class Updates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data")
        self.key = Ed25519PrivateKey.generate()
        self.updater = Updater(self.store, self.key.public_key().public_bytes_raw())

    def package(self, version=NEXT_VERSION, name="KurtLauncher.exe", raw=b"test-executable", recorded_hash=None):
        manifest = {"format": 1, "product": "KurtLauncher", "platform": "windows-x64", "version": version,
                    "files": {name: {"size": len(raw), "sha512": recorded_hash or hashlib.sha512(raw).hexdigest()}}}
        envelope = {"manifest": manifest, "signature": base64.b64encode(self.key.sign(canonical(manifest))).decode()}
        path = self.root / "new.kurtupdate"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("update.json", json.dumps(envelope))
            archive.writestr("payload/" + name, raw)
        return path

    def test_valid_signed_package_staged_without_touching_data(self):
        (self.store.root / "world.dat").write_bytes(b"world")
        stage = Path(self.updater.stage(self.package(), Task()))
        self.assertEqual((stage / "KurtLauncher.exe").read_bytes(), b"test-executable")
        self.assertEqual((self.store.root / "world.dat").read_bytes(), b"world")

    def test_untrusted_publisher_rejected(self):
        path = self.package()
        stranger = Updater(self.store, Ed25519PrivateKey.generate().public_key().public_bytes_raw())
        with self.assertRaises(LauncherError): stranger.inspect(path)

    def test_tampered_executable_rejected_before_commit(self):
        path = self.package(recorded_hash="0"*128)
        with self.assertRaises(LauncherError): self.updater.stage(path, Task())
        self.assertFalse(list((self.store.root / "updates").iterdir()))

    def test_downgrade_and_data_paths_rejected(self):
        for ver in ("0.3.1", "0.4.0"):
            with self.assertRaises(LauncherError): self.updater.inspect(self.package(version=ver))
        for name in ("../escape", "data/account.json", "src/../../data/settings.json"):
            with self.assertRaises(LauncherError): self.updater.inspect(self.package(name=name))

    def test_feed_unconfigured_is_honest_and_offline(self):
        self.updater.assets = self.root
        result = self.updater.check_feed(Task())
        self.assertFalse(result["available"])
        self.assertIn("yapılandırılmadı", result["message"])

    def response(self, content, status=200):
        response = Mock()
        response.status_code = status
        response.iter_content.return_value = iter([content])
        response.__enter__ = lambda value: response
        response.__exit__ = lambda *args: None
        return response

    def test_online_signed_feed_and_download_hash(self):
        raw = b"signed-update-package"
        data = {"format": 1, "product": "KurtLauncher", "platform": "windows-x64", "version": NEXT_VERSION,
                "package_url": f"https://github.com/ardacob/kurt-launcher-releases/releases/download/v{NEXT_VERSION}/release.kurtupdate",
                "package_sha512": hashlib.sha512(raw).hexdigest()}
        envelope = {"manifest": data, "signature": base64.b64encode(self.key.sign(canonical(data))).decode()}
        with patch("requests.get", return_value=self.response(json.dumps(envelope).encode())):
            info = self.updater.check_feed(Task())
        self.assertTrue(info["available"])
        response = self.response(raw)
        response.headers = {"Content-Length": str(len(raw))}
        with patch("requests.get", return_value=response):
            path = self.updater.download_release(info["manifest"], Task())
        self.assertEqual(Path(path).read_bytes(), raw)

    def test_unpublished_github_channel_is_pending_not_current(self):
        with patch("requests.get", return_value=self.response(b"not found", 404)):
            info = self.updater.check_feed(Task())
        self.assertFalse(info["available"])
        self.assertTrue(info["pending"])
        self.assertNotIn("güncel.", info["message"])

    def test_tampered_feed_rejected_before_download(self):
        data = {"format": 1, "product": "KurtLauncher", "platform": "windows-x64", "version": NEXT_VERSION}
        envelope = {"manifest": data, "signature": base64.b64encode(self.key.sign(canonical(data))).decode()}
        envelope["manifest"]["version"] = "9.9.9"
        with patch("requests.get", return_value=self.response(json.dumps(envelope).encode())), self.assertRaises(LauncherError):
            self.updater.check_feed(Task())


if __name__ == "__main__": unittest.main()

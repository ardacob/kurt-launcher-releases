"""Offline regression tests. No Minecraft account or game launch required."""
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core import Api, Cancelled, Launcher, LauncherError, ModManager, Store, Task, safe_file, offline_account


def jar_bytes():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as jar:
        jar.writestr("fabric.mod.json", '{"id":"test","version":"1"}')
    return stream.getvalue()


def version(project, vid=None, dependencies=None):
    raw = jar_bytes()
    return {"id": vid or project + "-v1", "project_id": project, "name": project,
            "game_versions": ["1.20.1"], "loaders": ["fabric"], "version_type": "release",
            "date_published": "2026-01-01", "dependencies": dependencies or [],
            "files": [{"filename": project+".jar", "url": "https://cdn.modrinth.com/data/"+project+".jar",
                       "hashes": {"sha512": hashlib.sha512(raw).hexdigest()}, "primary": True, "size": len(raw)}]}


def dep(project, vid=None, kind="required"):
    return {"project_id":project, "version_id":vid, "dependency_type":kind}


class FakeApi:
    def __init__(self, versions):
        self.versions = {v["project_id"]:v for v in versions}
        self.downloaded = []
        self.fail_on = None

    def get(self, url, **kwargs):
        if url.endswith("/projects"):
            return [{"id": v["project_id"], "title": v["name"], "icon_url": None} for v in self.versions.values()]
        if "/project/" in url:
            project = url.split("/project/")[1].split("/")[0]
            return [copy.deepcopy(self.versions[project])]
        vid = url.split("/version/")[1]
        return copy.deepcopy(next(v for v in self.versions.values() if v["id"]==vid))

    def download(self, file, target, task):
        if self.fail_on == file["filename"]:
            raise LauncherError("Test: failed download")
        self.downloaded.append(file["filename"])
        target.write_bytes(jar_bytes())

    def icon(self, url, directory, task):
        return None


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.p = self.store.create("Fabric test", "1.20.1", "fabric")

    def manager(self, versions):
        return ModManager(self.store, FakeApi(versions))

    def test_profiles_are_persistent_and_isolated(self):
        second = self.store.create("Other", "1.8.9", "forge")
        self.assertNotEqual(self.store.directory(self.p), self.store.directory(second))
        self.assertEqual(Store(self.store.root).profiles[0]["name"], "Fabric test")

    def test_unsafe_filenames_rejected(self):
        for name in ["../evil.jar", "..\\evil.jar", "C:evil.jar", "x.jar:stream", "CON.jar", "x.jar.", "x.jar ", "x\x00.jar", ""]:
            with self.subTest(name=name), self.assertRaises(LauncherError):
                safe_file(name)

    def test_instance_path_escape_rejected(self):
        with self.assertRaises(LauncherError):
            self.store.directory({"id":"../../escape"})

    def test_required_dependencies_installed_once(self):
        manager = self.manager([version("main",dependencies=[dep("api"),dep("lib")]),
                                version("lib",dependencies=[dep("api")]), version("api")])
        manager.install("main", self.p, Task())
        self.assertEqual(set(manager.api.downloaded), {"main.jar","lib.jar","api.jar"})
        self.assertEqual(len(manager.api.downloaded), 3)
        self.assertEqual(len(self.store.mod_lock(self.p)), 3)

    def test_dependency_cycle_terminates(self):
        manager = self.manager([version("a",dependencies=[dep("b")]),version("b",dependencies=[dep("a")])])
        self.assertEqual(len(manager.plan("a",self.p)),2)

    def test_incompatible_loader_rejected_before_download(self):
        child=version("api")
        child["loaders"]=["forge"]
        manager=self.manager([version("main",dependencies=[dep("api")]),child])
        with self.assertRaises(LauncherError):
            manager.install("main",self.p,Task())
        self.assertFalse(list(self.store.mods(self.p).iterdir()))

    def test_failed_download_rolls_back_whole_plan(self):
        manager=self.manager([version("main",dependencies=[dep("api")]),version("api")])
        manager.api.fail_on="api.jar"
        with self.assertRaises(LauncherError):
            manager.install("main",self.p,Task())
        self.assertEqual(list(self.store.mods(self.p).iterdir()),[])
        self.assertEqual(self.store.mod_lock(self.p),{})
        self.assertFalse(list(self.store.directory(self.p).glob(".kurt-*")))

    def test_failed_lock_write_rolls_back_files(self):
        manager=self.manager([version("main")])
        with patch("core.atomic_json",side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                manager.install("main",self.p,Task())
        self.assertFalse(list(self.store.mods(self.p).iterdir()))

    def test_existing_local_file_not_overwritten(self):
        manager=self.manager([version("main")])
        target=self.store.mods(self.p)/"main.jar"
        target.write_bytes(b"mine")
        with self.assertRaises(LauncherError):
            manager.install("main",self.p,Task())
        self.assertEqual(target.read_bytes(),b"mine")

    def test_dependent_blocks_disabling_and_removal(self):
        manager=self.manager([version("main",dependencies=[dep("api")]),version("api")])
        manager.install("main",self.p,Task())
        with self.assertRaises(LauncherError): manager.toggle(self.p,"api.jar")
        with self.assertRaises(LauncherError): manager.remove(self.p,"api.jar")
        manager.toggle(self.p,"main.jar")
        manager.toggle(self.p,"api.jar")
        with self.assertRaises(LauncherError): manager.toggle(self.p,"main.jar.disabled")
        manager.toggle(self.p,"api.jar.disabled")
        manager.toggle(self.p,"main.jar.disabled")
        manager.validate_enabled(self.p)

    def test_removed_mod_preserved_for_recovery(self):
        manager=self.manager([version("main")])
        manager.install("main",self.p,Task())
        manager.remove(self.p,"main.jar")
        self.assertFalse((self.store.mods(self.p)/"main.jar").exists())
        self.assertEqual(len(list((self.store.directory(self.p)/"removed-mods").iterdir())),1)
        self.assertFalse(self.store.mod_lock(self.p))

    def test_new_install_rejects_disabled_dependency(self):
        manager=self.manager([version("main",dependencies=[dep("api")]),version("api")])
        manager.install("api",self.p,Task())
        manager.toggle(self.p,"api.jar")
        with self.assertRaises(LauncherError): manager.plan("main",self.p)

    def test_declared_incompatibility_rejected(self):
        manager=self.manager([version("a",dependencies=[dep("b",kind="incompatible")]),version("b")])
        manager.install("b",self.p,Task())
        with self.assertRaises(LauncherError): manager.plan("a",self.p)

    def test_specific_incompatibility_does_not_reject_other_version(self):
        manager=self.manager([version("a",dependencies=[dep("b","b-old",kind="incompatible")]),version("b")])
        manager.install("b",self.p,Task())
        self.assertEqual(len(manager.plan("a",self.p)),1)

    def test_reverse_incompatibility_rejected(self):
        manager=self.manager([version("a",dependencies=[dep("b",kind="incompatible")]),version("b")])
        manager.install("a",self.p,Task())
        with self.assertRaises(LauncherError): manager.plan("b",self.p)

    def test_local_import_validates_loader_and_is_transactional(self):
        good=Path(self.temp.name)/"good.jar"
        good.write_bytes(jar_bytes())
        invalid=Path(self.temp.name)/"invalid.jar"
        invalid.write_bytes(b"not a jar")
        manager=self.manager([])
        with self.assertRaises(LauncherError): manager.import_local(self.p,[good,invalid])
        self.assertFalse(list(self.store.mods(self.p).iterdir()))
        forge=self.store.create("forge","1.20.1","forge")
        with self.assertRaises(LauncherError): manager.import_local(forge,[good])
        manager.import_local(self.p,[good])
        self.assertTrue((self.store.mods(self.p)/"good.jar").exists())

    def test_bad_hash_not_committed(self):
        raw=jar_bytes()
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def raise_for_status(self): pass
            def iter_content(self,*args): return iter([raw])
        api=Api()
        file=version("a")["files"][0]
        file["hashes"]["sha512"]="0"*128
        target=Path(self.temp.name)/"a.jar"
        with patch.object(api.session,"get",return_value=Response()):
            with self.assertRaises(LauncherError): api.download(file,target,Task())
        self.assertFalse(target.exists())

    def test_cancel_prevents_mod_install(self):
        manager=self.manager([version("a")])
        task=Task()
        task.cancel.set()
        with self.assertRaises(Cancelled): manager.install("a",self.p,task)
        self.assertFalse(list(self.store.mods(self.p).iterdir()))

    def test_game_running_blocks_repair(self):
        launcher=Launcher(self.store)
        class Running:
            def poll(self): return None
        launcher.process=Running()
        with self.assertRaises(LauncherError): launcher.install(self.p,Task())

    def test_cached_versions_available_on_network_failure(self):
        launcher=Launcher(self.store)
        (self.store.root/"versions-cache.json").write_text('{"versions": [{"id":"1.20.1"}]}')
        with patch.object(launcher.api,"get",side_effect=LauncherError("offline")):
            data,cached=launcher.versions()
        self.assertTrue(cached)
        self.assertEqual(data["versions"][0]["id"],"1.20.1")

    def test_offline_uuid_matches_java_and_is_stable(self):
        account = offline_account("Notch")
        self.assertEqual(account["id"], "b50ad385829d3141a2167e7d7539ba7f")
        self.assertEqual(account, offline_account(" Notch "))
        self.assertNotEqual(account["id"], offline_account("notch")["id"])
        self.assertEqual(account["access_token"], "0")

    def test_invalid_offline_usernames_rejected(self):
        for name in ("", "ab", "player name", "a"*17, "../player", "OyuncuŞ", "name;cmd"):
            with self.subTest(name=name), self.assertRaises(LauncherError):
                offline_account(name)

    def test_offline_cached_launch_never_uses_account_or_installer(self):
        launcher = Launcher(self.store)
        self.store.settings.update(login_mode="offline", offline_username="ArdaTest")
        self.p["installed"] = "fabric-test"
        installed = self.store.minecraft / "versions/fabric-test"
        installed.mkdir(parents=True)
        (installed / "fabric-test.json").write_text("{}")
        vanilla = self.store.minecraft / "versions/1.20.1"
        vanilla.mkdir()
        (vanilla / "1.20.1.jar").write_bytes(b"cache")
        command = ["java", "--username", "ArdaTest", "--userType", "msa", "--accessToken", "0"]
        with patch.object(launcher.account, "refresh") as refresh, patch.object(launcher, "install") as install, \
                patch.object(launcher, "java", return_value="java.exe") as java, \
                patch("core.mc.command.get_minecraft_command", return_value=command) as build, \
                patch("core.subprocess.Popen") as launch:
            result = launcher.play(self.p, Task())
        refresh.assert_not_called()
        install.assert_not_called()
        java.assert_called_once_with(self.p, unittest.mock.ANY, allow_download=False)
        options = build.call_args.args[2]
        self.assertEqual(options["username"], "ArdaTest")
        self.assertEqual(options["uuid"], offline_account("ArdaTest")["id"])
        self.assertEqual(launch.call_args.args[0][4], "legacy")
        self.assertIn("ArdaTest", result)

    def test_offline_first_launch_installs_missing_game(self):
        launcher = Launcher(self.store)
        self.store.settings.update(login_mode="offline", offline_username="Player_1")
        def install(profile, task): profile["installed"] = profile["version"]
        with patch.object(launcher.account, "refresh") as refresh, patch.object(launcher, "install", side_effect=install) as setup, \
                patch.object(launcher, "java", return_value="java.exe"), \
                patch("core.mc.command.get_minecraft_command", return_value=["java"]), patch("core.subprocess.Popen"):
            launcher.play(self.p, Task())
        setup.assert_called_once()
        refresh.assert_not_called()

    def test_microsoft_mode_still_refreshes_real_account(self):
        launcher = Launcher(self.store)
        self.store.settings["login_mode"] = "microsoft"
        account = {"name": "RealPlayer", "id": "account-uuid", "access_token": "real-test-token"}
        def install(profile, task): profile["installed"] = profile["version"]
        with patch.object(launcher.account, "refresh", return_value=account) as refresh, \
                patch.object(launcher, "install", side_effect=install), patch.object(launcher, "java", return_value="java.exe"), \
                patch("core.mc.command.get_minecraft_command", return_value=["java", "--userType", "msa"]) as build, \
                patch("core.subprocess.Popen") as launch:
            launcher.play(self.p, Task())
        refresh.assert_called_once()
        self.assertEqual(build.call_args.args[2]["token"], "real-test-token")
        self.assertEqual(launch.call_args.args[0][-1], "msa")

    def test_invalid_username_rejected_before_install(self):
        launcher = Launcher(self.store)
        self.store.settings.update(login_mode="offline", offline_username="bad name")
        with patch.object(launcher, "install") as install:
            with self.assertRaises(LauncherError): launcher.play(self.p, Task())
        install.assert_not_called()

    def test_installed_mod_retains_version_metadata(self):
        mod = version("main")
        mod["version_number"] = "2.3.4"
        manager = self.manager([mod])
        manager.install("main", self.p, Task())
        record = self.store.mod_lock(self.p)["main"]
        self.assertEqual(record["version_number"], "2.3.4")
        self.assertEqual(record["game_versions"], ["1.20.1"])
        self.assertEqual(record["loaders"], ["fabric"])

    def test_pinned_catalog_version_is_the_one_installed(self):
        manager = self.manager([version("main", "selected-version")])
        with patch.object(manager, "choose", side_effect=AssertionError("Do not choose latest")):
            manager.install("main", self.p, Task(), "selected-version")
        self.assertEqual(self.store.mod_lock(self.p)["main"]["version_id"], "selected-version")

    def test_pinned_version_must_belong_to_selected_project(self):
        manager = self.manager([version("other", "wrong-version")])
        with self.assertRaises(LauncherError): manager.plan("main", self.p, "wrong-version")

    def test_catalog_attaches_exact_compatible_version(self):
        manager = self.manager([])
        mod = version("main")
        mod["version_number"] = "1.2.3"
        hits = [{"project_id": "main", "title": "Main"}, {"project_id": "other", "title": "Other"}]
        with patch.object(manager, "search", return_value={"hits": hits, "total_hits": 2}), patch("core.Api") as factory:
            factory.return_value.get.side_effect = lambda url, **params: [mod] if "/main/" in url else [version("other")]
            result = manager.catalog(self.p, task=Task())
        self.assertEqual(result["hits"][0]["version_info"]["version_number"], "1.2.3")
        self.assertEqual(result["hits"][0]["compatibility"], "compatible")
        self.assertEqual([hit["title"] for hit in result["hits"]], ["Main", "Other"])

    def test_catalog_does_not_claim_unverified_compatibility(self):
        manager = self.manager([])
        hits = [{"project_id": "main", "title": "Main"}]
        with patch.object(manager, "search", return_value={"hits": hits, "total_hits": 1}), patch("core.Api") as factory:
            factory.return_value.get.side_effect = LauncherError("network failure")
            result = manager.catalog(self.p, task=Task())
        self.assertIsNone(result["hits"][0]["version_info"])
        self.assertEqual(result["hits"][0]["compatibility"], "unverified")

    def test_older_mod_lock_metadata_can_be_refreshed(self):
        from core import atomic_json
        atomic_json(self.store.directory(self.p)/"mods.lock.json", {"main": {
            "name": "Main", "file": "main.jar", "version_id": "main-v1"}})
        manager = self.manager([])
        mod = version("main")
        mod["version_number"] = "2.0.1"
        with patch.object(manager.api, "get", return_value=[mod]):
            manager.refresh_metadata(self.p, Task())
        record = self.store.mod_lock(self.p)["main"]
        self.assertEqual(record["version_number"], "2.0.1")
        self.assertEqual(record["loaders"], ["fabric"])


if __name__=="__main__":
    unittest.main()

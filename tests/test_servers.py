import hashlib
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core import Api, Launcher, LauncherError, Store, Task
from servers import ServerManager


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.launcher = Launcher(self.store)
        self.manager = ServerManager(self.launcher)
        self.server = self.manager.create("Friends", "1.20.1", "vanilla")
        java = Path(self.temp.name) / "java.exe"
        java.write_bytes(b"test executable, never run")
        self.store.settings["java"] = str(java)
        self.metadata = {"javaVersion": {"component": "java-runtime-gamma"},
                         "downloads": {"server": {"url": "https://piston-data.mojang.com/server.jar", "sha1": "test"}}}

    def fake_download(self, url, target, task, sha1=None):
        with zipfile.ZipFile(target, "w") as jar:
            jar.writestr("META-INF/MANIFEST.MF", "Main-Class: Server")

    def prepare(self):
        with patch.object(self.manager, "metadata", return_value=self.metadata), \
                patch.object(self.manager, "download", side_effect=self.fake_download):
            self.manager.prepare(self.server, Task(), accept_eula=True)

    def test_server_profile_isolated_and_persisted_without_eula(self):
        self.assertEqual(self.store.directory(self.server).parent.name, "servers")
        self.assertFalse(self.server["eula_accepted"])
        self.assertFalse((self.store.directory(self.server) / "eula.txt").exists())
        self.assertEqual(Store(self.store.root).servers[0]["id"], self.server["id"])

    def test_eula_gate_prevents_network_and_start(self):
        with patch.object(self.manager, "metadata") as request:
            with self.assertRaises(LauncherError): self.manager.start(self.server, Task())
        request.assert_not_called()

    def test_prepare_writes_configuration_only_after_explicit_consent(self):
        directory = self.store.directory(self.server)
        (directory / "server.properties").write_text("level-name=my-existing-world\ndifficulty=hard\n")
        self.prepare()
        text = (directory / "server.properties").read_text()
        self.assertIn("online-mode=false", text)
        self.assertIn("server-port=25565", text)
        self.assertIn("level-name=my-existing-world", text)
        self.assertIn("difficulty=hard", text)
        self.assertIn("eula=true", (directory / "eula.txt").read_text())
        self.assertTrue(self.server["installed"])

    def test_online_server_keeps_microsoft_authentication(self):
        self.server["username_players"] = False
        self.prepare()
        self.assertIn("online-mode=true", (self.store.directory(self.server) / "server.properties").read_text())

    def test_start_captures_logs_and_stops_gracefully(self):
        self.prepare()
        fake = SimpleNamespace(stdin=io.StringIO(), stdout=iter(["[Server thread/INFO]: Done (1.2s)! For help, type help\n"]),
                               poll=lambda: None, returncode=None)
        with patch("servers.subprocess.Popen", return_value=fake) as spawn, patch("servers.socket.socket"):
            self.manager.start(self.server, Task())
        self.manager.reader.join(2)
        self.assertTrue(self.manager.ready.is_set())
        self.assertIn("Done (", "\n".join(self.manager.drain()))
        self.assertEqual(spawn.call_args.args[0][-1], "nogui")
        self.manager.stop()
        self.assertEqual(fake.stdin.getvalue(), "stop\n")
        self.assertTrue(self.manager.stopping)

    def test_console_rejects_multiline_command(self):
        fake = SimpleNamespace(stdin=io.StringIO(), poll=lambda: None)
        self.manager.process = fake
        with self.assertRaises(LauncherError): self.manager.command("say hello\nstop")
        self.assertEqual(fake.stdin.getvalue(), "")

    def test_second_server_start_is_blocked(self):
        self.manager.process = SimpleNamespace(poll=lambda: None)
        with self.assertRaises(LauncherError): self.manager.start(self.server, Task(), True)

    def test_invalid_ports_and_loaders_rejected(self):
        for port in (0, 1023, 65536):
            with self.assertRaises(LauncherError): self.manager.create("x", "1.20.1", port=port)
        with self.assertRaises(LauncherError): self.manager.create("x", "1.20.1", "unknown")

    def test_client_only_mod_not_added_to_server(self):
        import json
        self.server["loader"] = "fabric"
        source = Path(self.temp.name) / "client.jar"
        with zipfile.ZipFile(source, "w") as jar:
            jar.writestr("fabric.mod.json", json.dumps({"id": "test", "version": "1", "environment": "client"}))
        with self.assertRaises(LauncherError): self.launcher.mods.import_local(self.server, [source])
        self.assertFalse(list(self.store.mods(self.server).iterdir()))

    def test_server_download_hash_failure_not_committed(self):
        class Response:
            headers = {"Content-Length": "3"}
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def raise_for_status(self): pass
            def iter_content(self,*args): return iter([b"bad"])
        target = self.store.directory(self.server)/"server.jar"
        with patch.object(self.manager.api.session, "get", return_value=Response()):
            with self.assertRaises(LauncherError):
                self.manager.download("https://piston-data.mojang.com/server.jar", target, Task(), "0"*40)
        self.assertFalse(target.exists())
        self.assertFalse(list(target.parent.glob("*.download")))

    def test_logos_are_cached_and_external_hosts_rejected(self):
        class Response:
            headers = {"Content-Length": "3", "Content-Type": "image/png"}
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def raise_for_status(self): pass
            def iter_content(self,*args): return iter([b"png"])
        api = Api()
        with patch.object(api.session, "get", return_value=Response()) as get:
            first = api.icon("https://cdn.modrinth.com/icon.png", self.store.icon_cache, Task())
            second = api.icon("https://cdn.modrinth.com/icon.png", self.store.icon_cache, Task())
            self.assertIsNone(api.icon("https://example.com/icon.png", self.store.icon_cache, Task()))
        self.assertEqual(first, second)
        self.assertEqual(Path(first).read_bytes(), b"png")
        get.assert_called_once()


if __name__ == "__main__": unittest.main()

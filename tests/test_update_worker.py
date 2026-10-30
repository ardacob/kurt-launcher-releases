"""Run the actual Windows replacement/rollback worker with tiny compiled fixtures."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from core import APP_VERSION

CSC = Path("C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe")


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "Windows .NET fixture compiler required")
class WindowsUpdateWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name).resolve()
        cls.flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cls.fixtures = {}
        for name, body in (("old", "return 0;"), ("good", 'if(args.Length == 2 && args[0] == "--update-health") { File.WriteAllText(args[1] + ".cwd", Directory.GetCurrentDirectory()); File.WriteAllText(args[1], "OK"); } return 0;'), ("bad", "return 2;")):
            source = cls.root / (name + ".cs")
            target = cls.root / (name + ".exe")
            source.write_text("using System; using System.IO; class App { static int Main(string[] args) { " + body + " } }")
            result = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/out:" + str(target), str(source)], capture_output=True, creationflags=cls.flags)
            if result.returncode:
                raise RuntimeError(result.stdout.decode(errors="replace"))
            cls.fixtures[name] = target

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.temp_case = tempfile.TemporaryDirectory(dir=self.root)
        def cleanup_fixture():
            deadline = time.monotonic() + 5
            while True:
                try:
                    self.temp_case.cleanup()
                    return
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.1)
        self.addCleanup(cleanup_fixture)
        self.case = Path(self.temp_case.name)
        self.local = self.case / "LocalAppData"
        self.app = self.local / "KurtLauncher/app"
        self.data = self.local / "KurtLauncher/data"
        self.stage = self.data / "updates/verified-test"
        self.stage.mkdir(parents=True)
        self.app.mkdir(parents=True)
        shutil.copy2(self.fixtures["old"], self.app / "KurtLauncher.exe")
        self.obsolete = self.case / "old-download/KurtLauncher.exe"
        self.obsolete.parent.mkdir()
        shutil.copy2(self.fixtures["old"], self.obsolete)
        (self.data / "world.dat").write_bytes(b"precious-world")
        self.health = self.data / "updates/startup.ok"
        self.health.write_text("stale health from an earlier attempt")

    def run_worker(self, fixture="good", changed_old=False, unsafe=False, redirect=False):
        shutil.copy2(self.fixtures[fixture], self.stage / "KurtLauncher.exe")
        (self.stage / "README.md").write_bytes(b"new launcher")
        records = {path.name: {"size": path.stat().st_size, "sha512": hashlib.sha512(path.read_bytes()).hexdigest()}
                   for path in self.stage.iterdir() if path.is_file()}
        if unsafe:
            records["../world.dat"] = records.pop("README.md")
        version = APP_VERSION
        if redirect:
            shutil.copy2(self.fixtures["good"], self.app / "KurtLauncher.exe")
            version = ".".join(APP_VERSION.split(".")[:2] + [str(int(APP_VERSION.split(".")[2]) + 1)])
            records = {}
        (self.stage / "verified.json").write_text(json.dumps({"version": version, "files": records}))
        plan = {"installation": str(self.app), "stage": str(self.stage), "data": str(self.data), "health": str(self.health),
                "pid": 2147483647, "managed": True, "create_shortcut": False,
                "obsolete_executable": str(self.obsolete),
                "obsolete_sha512": "0" * 128 if changed_old else hashlib.sha512(self.obsolete.read_bytes()).hexdigest()}
        if redirect:
            plan["redirect_sha512"] = hashlib.sha512(self.fixtures["good"].read_bytes()).hexdigest()
        path = self.data / "updates/plan.json"
        path.write_text(json.dumps(plan))
        shell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                                 str(ROOT / "assets/update-worker.ps1"), "-Plan", str(path)],
                                env=dict(os.environ, LOCALAPPDATA=str(self.local)), capture_output=True,
                                creationflags=self.flags, timeout=35)
        self.assertEqual((self.data / "world.dat").read_bytes(), b"precious-world")
        return result, Path(str(path) + ".result").read_text()

    def test_success_removes_old_app_backup_and_stage_only_after_health(self):
        result, status = self.run_worker()
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace") + status)
        self.assertEqual(self.health.read_text(), "OK")
        self.assertEqual(Path(Path(str(self.health) + ".cwd").read_text()).resolve(), self.app.resolve())
        self.assertEqual((self.app / "KurtLauncher.exe").read_bytes(), self.fixtures["good"].read_bytes())
        self.assertFalse(self.obsolete.exists(), status)
        self.assertFalse(self.stage.exists(), status)
        self.assertFalse(list(self.app.glob(".kurt-rollback-*")), status)
        state = json.loads((self.app.parent / "installation.json").read_text(encoding="utf-8"))
        self.assertEqual(state["version"], APP_VERSION)
        self.assertEqual(state["sha512"], hashlib.sha512(self.fixtures["good"].read_bytes()).hexdigest())

    def test_failed_startup_restores_old_app_and_ignores_stale_health(self):
        result, status = self.run_worker("bad")
        self.assertEqual(result.returncode, 1, result.stderr.decode(errors="replace") + status)
        self.assertEqual((self.app / "KurtLauncher.exe").read_bytes(), self.fixtures["old"].read_bytes())
        self.assertTrue(self.obsolete.is_file())
        self.assertFalse((self.app / "README.md").exists())
        self.assertFalse(self.health.exists())
        failed = json.loads((self.data / "updates/last-failure.json").read_text(encoding="utf-8"))
        self.assertEqual(failed["version"], APP_VERSION)

    def test_cleanup_does_not_delete_a_changed_executable(self):
        result, status = self.run_worker(changed_old=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace") + status)
        self.assertTrue(self.obsolete.is_file())

    def test_unsafe_verified_path_cannot_change_game_data(self):
        result, status = self.run_worker(unsafe=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Unsafe update path", status)
        self.assertEqual((self.app / "KurtLauncher.exe").read_bytes(), self.fixtures["old"].read_bytes())

    def test_opening_an_old_download_redirects_to_the_newer_installed_exe(self):
        result, status = self.run_worker(redirect=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace") + status)
        self.assertEqual((self.app / "KurtLauncher.exe").read_bytes(), self.fixtures["good"].read_bytes())
        self.assertFalse(self.obsolete.exists(), status)
        state = json.loads((self.app.parent / "installation.json").read_text(encoding="utf-8"))
        self.assertGreater(tuple(map(int, state["version"].split("."))), tuple(map(int, APP_VERSION.split("."))))

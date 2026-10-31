"""Exercise the actual Setup.exe without touching the user's app, desktop or data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from common import ROOT, version


def wait_for(check, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.15)
    raise AssertionError("Setup completion timed out")


def verify(setup, executable, current):
    with tempfile.TemporaryDirectory(prefix="kurt-setup-ç-test-") as temporary:
        base = Path(temporary).resolve()
        local = base / "LocalAppData"
        data = local / "KurtLauncher/data"
        target = local / "KurtLauncher/app/KurtLauncher.exe"
        data.mkdir(parents=True)
        scratch = base / "temp"
        scratch.mkdir()
        profile = {"id":"1" * 32, "name":"Kurulum testi", "version":"1.21.1", "loader":"vanilla",
                   "loader_version":None, "installed":None}
        (data / "profiles.json").write_text(json.dumps([profile]), encoding="utf-8")
        (data / "settings.json").write_text(json.dumps({"auto_update_check":False, "auto_install_updates":False}), encoding="utf-8")
        sentinels = {"instances/" + profile["id"] + "/saves/Arkadaşlar/level.dat":b"preserved-world",
                     "instances/" + profile["id"] + "/mods/example.jar":b"preserved-mod",
                     "minecraft/versions/test/test.jar":b"preserved-game"}
        for name, content in sentinels.items():
            path = data / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        env = dict(os.environ, LOCALAPPDATA=str(local), KURT_DATA_DIR=str(data), TEMP=str(scratch), TMP=str(scratch),
                   KURT_SETUP_LOG=str(base / "setup-debug.txt"),
                   KURT_SKIP_INTEGRATION="1", KURT_SKIP_SHORTCUT="1", KURT_DISABLE_AUTOSTART="1", QT_QPA_PLATFORM="offscreen",
                   _PYI_ARCHIVE_FILE=str(target), _PYI_APPLICATION_HOME_DIR=str(base / "deleted-runtime"), _PYI_PARENT_PROCESS_LEVEL="1")
        env.pop("PYINSTALLER_RESET_ENVIRONMENT", None)
        pid = None
        try:
            subprocess.run([str(setup.resolve()), "/S"], env=env, check=True, timeout=180)
            state = local / "KurtLauncher/installation.json"
            wait_for(state.is_file)
            info = json.loads(state.read_text(encoding="utf-8"))
            assert info["version"] == current, info
            expected = hashlib.sha512(executable.read_bytes()).hexdigest()
            assert info["sha512"] == expected == hashlib.sha512(target.read_bytes()).hexdigest()
            healths = list((data / "updates").glob("*.ok"))
            assert len(healths) == 1
            health = json.loads(healths[0].read_text(encoding="utf-8"))
            pid = health["pid"]
            assert Path(health["executable"]).resolve() == target.resolve()
            assert Path(health["data"]).resolve() == data.resolve()
            results = list((data / "updates").glob("*.result"))
            assert len(results) == 1 and results[0].read_text(encoding="utf-8-sig").startswith("Update OK")
            assert not list((data / "updates").glob("verified-install-*"))
            subprocess.run([str(setup.resolve()), "/S"], env=env, check=True, timeout=90)
            assert len(list((data / "updates").glob("*.ok"))) == 1, "Open launcher should not be reinstalled"
            assert not list(scratch.glob("ns*/KurtLauncher")), "Setup payload should be removed after completion"
            for name, content in sentinels.items():
                assert (data / name).read_bytes() == content, name
            assert json.loads((data / "profiles.json").read_text(encoding="utf-8")) == [profile]
            print("Actual Setup: isolated per-user install, healthy startup, repeat while open, Unicode paths, data preservation and temp cleanup OK", flush=True)
        except Exception:
            details = []
            for path in [base / "setup-debug.txt", *(data / "updates").glob("*.result")]:
                if path.is_file():
                    details.append(str(path) + "\n" + path.read_text(encoding="utf-8-sig", errors="replace"))
            print("Setup diagnostic:", "\n".join(details), flush=True)
            raise
        finally:
            if pid is None:
                for path in (data / "updates").glob("*.ok"):
                    pid = json.loads(path.read_text(encoding="utf-8"))["pid"]
            if pid:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                # Only files inside this verifier's temporary root may be removed.
                assert target.resolve().is_relative_to(base)
                for path in (target, data / "launcher.lock"):
                    deadline = time.monotonic() + 20
                    while path.exists():
                        try:
                            path.unlink()
                        except PermissionError:
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", type=Path)
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--version", default=version())
    args = parser.parse_args()
    verify(args.setup or ROOT / "artifacts" / f"KurtLauncher-v{args.version}-Setup.exe",
           args.exe or ROOT / "dist/KurtLauncher.exe", args.version)

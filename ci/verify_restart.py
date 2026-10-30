"""Run the real onefile EXE at the same path with an expired inherited runtime."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def verify(executable, current):
    with tempfile.TemporaryDirectory(prefix='kurt-frozen-restart-') as temporary:
        base = Path(temporary).resolve()
        local = base / 'LocalAppData'
        app = local / 'KurtLauncher/app'
        data = local / 'KurtLauncher/data'
        stage = data / 'updates/verified-restart'
        app.mkdir(parents=True)
        stage.mkdir(parents=True)
        target = app / 'KurtLauncher.exe'
        shutil.copy2(executable, target)
        shutil.copy2(executable, stage / target.name)
        value = hashlib.sha512(target.read_bytes()).hexdigest()
        (stage / 'verified.json').write_text(json.dumps({'version':current, 'files':{
            target.name:{'size':target.stat().st_size, 'sha512':value}}}))
        (data / 'settings.json').write_text(json.dumps({'auto_check_updates':False, 'auto_install_updates':False}))
        sentinel = data / 'world.dat'
        sentinel.write_bytes(b'preserved-world')
        health = data / 'updates/restart.ok'
        plan = data / 'updates/restart.json'
        plan.write_text(json.dumps({'installation':str(app), 'stage':str(stage), 'data':str(data),
            'pid':2147483647, 'managed':True, 'create_shortcut':False, 'health':str(health)}))
        env = dict(os.environ, LOCALAPPDATA=str(local), KURT_SKIP_SHORTCUT='1', QT_QPA_PLATFORM='offscreen',
                   _PYI_ARCHIVE_FILE=str(target), _PYI_APPLICATION_HOME_DIR=str(base / 'deleted-old-runtime'),
                   _PYI_PARENT_PROCESS_LEVEL='1')
        env.pop('PYINSTALLER_RESET_ENVIRONMENT', None)
        shell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        pid = None
        try:
            result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(ROOT / 'assets/update-worker.ps1'), '-Plan', str(plan)], env=env,
                capture_output=True, timeout=75, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if health.is_file():
                info = json.loads(health.read_text(encoding='utf-8'))
                pid = info['pid']
            assert result.returncode == 0, result.stderr.decode(errors='replace')
            assert pid and Path(info['executable']).resolve() == target.resolve()
            assert Path(info['data']).resolve() == data.resolve()
            assert not stage.exists()
            assert sentinel.read_bytes() == b'preserved-world'
            assert json.loads((app.parent / 'installation.json').read_text())['version'] == current
            print('Real frozen in-place restart with deleted inherited Python runtime: OK', flush=True)
        finally:
            if pid:
                subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=15)
                deadline = time.monotonic() + 8
                while (data / 'launcher.lock').exists():
                    try:
                        (data / 'launcher.lock').unlink()
                    except PermissionError:
                        if time.monotonic() >= deadline: raise
                        time.sleep(.1)
                # The onefile parent still owns the EXE while it removes its
                # extracted DLLs after the Qt child exits.
                deadline = time.monotonic() + 15
                assert target.resolve().is_relative_to(base)
                while target.exists():
                    try:
                        target.unlink()
                    except PermissionError:
                        if time.monotonic() >= deadline: raise
                        time.sleep(.1)


if __name__ == '__main__':
    from common import version
    verify(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'dist/KurtLauncher.exe',
           sys.argv[2] if len(sys.argv) > 2 else version())

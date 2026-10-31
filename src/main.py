import os
import sys
import time
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtCore import QLockFile, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QFileDialog, QProgressDialog
from core import Store, atomic_json
from data_paths import (DataLocationError, DataChoiceRequired,
                        remember_data_folder, selected_data_folder)
from ui import Window


def progress_dialog():
    dialog = None
    last = 0
    def progress(message, value, maximum):
        nonlocal dialog, last
        if dialog is None:
            dialog = QProgressDialog(message, "", 0, 100)
            dialog.setWindowTitle("Kurt Launcher hazırlanıyor")
            dialog.setCancelButton(None)
            dialog.setWindowFlag(Qt.WindowCloseButtonHint, False)
            dialog.setAutoClose(False)
            dialog.setMinimumDuration(0)
        if time.monotonic() - last >= .05 or value >= maximum:
            dialog.setLabelText(message)
            dialog.setValue(int(100 * value / maximum) if maximum else 0)
            dialog.show()
            QApplication.processEvents()
            last = time.monotonic()
    def close():
        if dialog is not None:
            dialog.close()
    return progress, close


def open_store(update_from=None, progress=lambda *args: None):
    try:
        return Store(update_from=update_from, migrate_legacy=update_from is None, migration_progress=progress)
    except DataLocationError as exc:
        if "--smoke-test" in sys.argv:
            raise
        if isinstance(exc, DataChoiceRequired):
            options = [str(folder) for folder in exc.candidates] + ["Başka bir klasör seç…"]
            choice, accepted = QInputDialog.getItem(None, "Önceki oyunların", str(exc), options, 0, False)
            if not accepted:
                return None
            folder = choice if choice != options[-1] else ""
        else:
            QMessageBox.information(None, "Önceki oyunların", str(exc))
            folder = ""
        if not folder:
            folder = QFileDialog.getExistingDirectory(None, "Eski Kurt Launcher oyun klasörünü seç")
        if not folder:
            return None
        root = selected_data_folder(folder)
        if update_from is None:
            from data_migration import ensure_shared_data
            root = ensure_shared_data(root, progress=progress)
        result = Store(root)
        remember_data_folder(result.root)
        return result


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Kurt Launcher")
    app.setOrganizationName("KurtLauncher")
    app.setQuitOnLastWindowClosed(False)
    try:
        worker_data = None
        if "--update-health" in sys.argv and "--smoke-test" not in sys.argv and os.environ.get("KURT_DATA_DIR"):
            worker_data = Path(os.environ["KURT_DATA_DIR"]).resolve()
        progress, close_progress = progress_dialog()
        try:
            store = open_store(update_from=worker_data, progress=progress)
        finally:
            close_progress()
        if store is None:
            return 0
        lock = QLockFile(str(store.root / "launcher.lock"))
        if not lock.tryLock(100):
            QMessageBox.information(None,"Kurt Launcher","Bu veri klasörünü kullanan bir launcher zaten açık.")
            return 0
        managed = getattr(sys, "frozen", False) and "--smoke-test" not in sys.argv and "--no-self-install" not in sys.argv
        if managed and worker_data is None:
            from installation import prepare_managed_install
            from updater import Updater
            progress, close_progress = progress_dialog()
            try:
                if prepare_managed_install(Updater(store), progress=progress):
                    return 0
            finally:
                close_progress()
        window = Window(store.root, autostart="--smoke-test" not in sys.argv)
        assets = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets"
        app.setWindowIcon(QIcon(str(assets / "icon.svg")))
        if "--smoke-test" in sys.argv:
            # Packaging diagnostic: no network, credentials or Minecraft process.
            from PySide6.QtCore import QThreadPool
            from keyring.backends.Windows import WinVaultKeyring
            from invites import AGENT_SHA256
            import hashlib
            import subprocess
            assert WinVaultKeyring
            assert window.tools_tabs.count() == 8
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            assert Ed25519PublicKey.from_public_bytes(window.updater.public_key)
            helper = assets / "playit/playitd.exe"
            assert hashlib.sha256(helper.read_bytes()).hexdigest() == AGENT_SHA256
            probe = subprocess.run([str(helper), "--help"], capture_output=True, timeout=8,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert probe.returncode == 0
            window.show()
            app.processEvents()
            window.grab().save(str(store.root / "smoke-test.png"))
            (store.root / "smoke-test.ok").write_text("Qt + 8 tool tabs + content/worlds/management + Ed25519 + Minecraft + Windows vault + signed Playit helper SHA256/--help OK",encoding="utf-8")
            window.close()
            QThreadPool.globalInstance().waitForDone()
            return 0
        window.show()
        app.setQuitOnLastWindowClosed(True)
        health = None
        if "--update-health" in sys.argv:
            position = sys.argv.index("--update-health")
            if position + 1 < len(sys.argv):
                health = Path(sys.argv[position + 1]).resolve()
                health_roots = {(store.root / "updates").resolve()}
                if worker_data is not None:
                    health_roots.add((worker_data / "updates").resolve())
                if health.parent in health_roots and health.suffix == ".ok":
                    # Old update workers pass KURT_DATA_DIR. Remember it for ZIP
                    # launches too, without registering isolated smoke-test data.
                    remember_data_folder(store.root)
                    app.processEvents()
                    atomic_json(health, {"status": "Launcher startup OK", "pid": os.getpid(),
                                         "executable": str(Path(sys.executable).resolve()), "data": str(store.root)})
        if managed and worker_data is not None and health is not None:
            from data_paths import common_data_folder
            from installation import app_folder
            if store.root != common_data_folder() or Path(sys.executable).resolve().parent != app_folder():
                window.maintenance_pending = True
                def finish_install():
                    # First acknowledge the previous version's update helper, then
                    # perform a potentially large migration outside its health timeout.
                    result_path = health.with_suffix(".json.result")
                    if not result_path.is_file() or window.worker or window.server_manager.running or (window.launcher.process and window.launcher.process.poll() is None):
                        QTimer.singleShot(1500, finish_install)
                        return
                    if not result_path.read_text(encoding="utf-8-sig").strip().startswith("Update OK"):
                        window.maintenance_pending = False
                        return
                    window.setEnabled(False)
                    progress, close_progress = progress_dialog()
                    try:
                        from data_migration import ensure_shared_data
                        from installation import prepare_managed_install
                        from updater import Updater
                        root = ensure_shared_data(store.root, progress=progress, own_launcher_lock=store.root != common_data_folder())
                        remember_data_folder(root)
                        destination_store = Store(root)
                        if prepare_managed_install(Updater(destination_store), progress=progress):
                            window.relay.stop()
                            window.close()
                        elif root != store.root:
                            import subprocess
                            subprocess.Popen([sys.executable], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                            window.close()
                        else:
                            window.maintenance_pending = False
                            window.setEnabled(True)
                    except Exception as exc:
                        window.maintenance_pending = False
                        window.setEnabled(True)
                        window.report("Ortak klasöre kurulum tamamlanamadı. Eski verilerin korunuyor. " + str(exc))
                    finally:
                        close_progress()
                QTimer.singleShot(1500, finish_install)
        return app.exec()
    except Exception as exc:
        if "--smoke-test" in sys.argv:
            if "store" in locals():
                import traceback
                (store.root / "smoke-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            return 1
        message = str(exc) if isinstance(exc, DataLocationError) else f"Launcher açılamadı ({type(exc).__name__}). Veri klasörünün yazılabilir olduğundan emin olun."
        QMessageBox.critical(None,"Kurt Launcher",message)
        return 1


if __name__ == "__main__":
    sys.exit(main())

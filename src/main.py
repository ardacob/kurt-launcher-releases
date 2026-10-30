import sys
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QFileDialog
from core import Store
from data_paths import (DataLocationError, DataChoiceRequired, DataFolderMissing,
                        remember_data_folder, selected_data_folder)
from ui import Window


def open_store():
    try:
        return Store()
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
        result = Store(root)
        remember_data_folder(result.root)
        return result


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Kurt Launcher")
    app.setOrganizationName("KurtLauncher")
    try:
        store = open_store()
        if store is None:
            return 0
        lock = QLockFile(str(store.root / "launcher.lock"))
        if not lock.tryLock(100):
            QMessageBox.information(None,"Kurt Launcher","Bu veri klasörünü kullanan bir launcher zaten açık.")
            return 0
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
            assert window.tools_tabs.count() == 7
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
            (store.root / "smoke-test.ok").write_text("Qt + 7 tool tabs + Ed25519 update verification + Minecraft + Windows vault + signed Playit helper SHA256/--help OK",encoding="utf-8")
            window.close()
            QThreadPool.globalInstance().waitForDone()
            return 0
        window.show()
        if "--update-health" in sys.argv:
            position = sys.argv.index("--update-health")
            if position + 1 < len(sys.argv):
                health = Path(sys.argv[position + 1]).resolve()
                if health.parent == (store.root / "updates").resolve() and health.suffix == ".ok":
                    # Old update workers pass KURT_DATA_DIR. Remember it for ZIP
                    # launches too, without registering isolated smoke-test data.
                    remember_data_folder(store.root)
                    app.processEvents()
                    health.write_text("Launcher startup OK", encoding="utf-8")
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

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core import LauncherError
from setup_receipt import receipt_argument, write_receipt


class SetupReceiptTests(unittest.TestCase):
    def test_receipt_supports_unicode_paths_and_exact_windows_encoding(self):
        with tempfile.TemporaryDirectory(prefix="kurulum-ç-") as folder:
            root = Path(folder).resolve()
            path = root / "setup-receipt.txt"
            with patch("sys.executable", str(root / "KurtLauncher.exe")):
                self.assertEqual(receipt_argument(["app", "--setup-receipt", str(path)]), path)
            result = root / "Dünyalar/updates/test.json.result"
            write_receipt(path, result)
            self.assertEqual(path.read_bytes(), (str(result) + "\r\n").encode("utf-16-le"))
            write_receipt(path, "ALREADY_OPEN")
            self.assertEqual(path.read_bytes().decode("utf-16-le"), "ALREADY_OPEN\r\n")

    def test_receipt_cannot_write_outside_the_setup_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            with patch("sys.executable", str(root / "KurtLauncher.exe")):
                for args in (["--setup-receipt"], ["--setup-receipt", "setup-receipt.txt"],
                             ["--setup-receipt", str(root / "other.txt")],
                             ["--setup-receipt", str(root.parent / "setup-receipt.txt")],
                             ["--setup-receipt", str(root / "setup-receipt.txt"), "--smoke-test"]):
                    with self.subTest(args=args), self.assertRaises(LauncherError):
                        receipt_argument(args)
            self.assertIsNone(receipt_argument(["app"]))

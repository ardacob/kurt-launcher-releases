"""Small completion handshake between the disposable Setup and the install worker."""
import os
from pathlib import Path
import stat
import sys

from core import LauncherError


def receipt_argument(arguments):
    if "--setup-receipt" not in arguments:
        return None
    position = arguments.index("--setup-receipt")
    if arguments.count("--setup-receipt") != 1 or position + 1 >= len(arguments):
        raise LauncherError("Kurulum sonuç yolu eksik.")
    path = Path(arguments[position + 1])
    if (not path.is_absolute() or path.name != "setup-receipt.txt"
            or path.parent.resolve() != Path(sys.executable).resolve().parent
            or "--smoke-test" in arguments):
        raise LauncherError("Kurulum sonuç yolu geçersiz.")
    if path.exists() or path.is_symlink():
        flags = getattr(path.lstat(), "st_file_attributes", 0)
        if not path.is_file() or flags & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024) or path.is_symlink():
            raise LauncherError("Kurulum sonuç dosyası bağlantı olamaz.")
    return path


def write_receipt(path, result):
    # NSIS FileReadUTF16LE expects no BOM. Binary mode keeps exactly one CRLF.
    with open(path, "wb") as stream:
        stream.write((str(result) + "\r\n").encode("utf-16-le"))
        stream.flush()
        os.fsync(stream.fileno())

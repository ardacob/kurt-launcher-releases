"""Only this step receives the private key; it never becomes an artifact."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from common import ROOT, REPOSITORY, canonical, constant, safe_member, sha256, version


def extract_payload(archive_path, destination):
    allowed = constant(ROOT / "src/updater.py", "TOP_LEVEL")
    seen = set()
    with zipfile.ZipFile(archive_path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 1024 * 1024 * 1024:
            raise ValueError("Build archive too large")
        for info in archive.infolist():
            path = safe_member(info.filename)
            if (len(path.parts) < 2 or path.parts[0] != "KurtLauncher"
                    or path.parts[1] not in allowed or info.is_dir()
                    or (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unexpected build entry: " + info.filename)
            name = str(path).casefold()
            if name in seen:
                raise ValueError("Duplicate archive entry")
            seen.add(name)
            target = destination.joinpath(*path.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))


def main():
    current = version()
    output = ROOT / "artifacts"
    windows = output / f"KurtLauncher-v{current}-Windows.zip"
    package = output / f"KurtLauncher-v{current}.kurtupdate"
    feed = output / "latest.json"
    encoded = os.environ.pop("KURT_SIGNING_KEY_B64", "")
    if not encoded:
        raise ValueError("KURT_SIGNING_KEY_B64 repository secret is not configured")
    try:
        key_bytes = base64.b64decode(encoded, validate=True)
    except Exception:
        raise ValueError("Invalid signing secret encoding") from None
    if len(key_bytes) != 32:
        raise ValueError("Signing key must be exactly 32 bytes")
    with tempfile.TemporaryDirectory(prefix="kurt-sign-") as temporary:
        temporary = Path(temporary)
        source = temporary / "payload"
        source.mkdir()
        extract_payload(windows, source)
        if constant(source / "src/core.py", "APP_VERSION") != current:
            raise ValueError("Built version does not match this commit")
        public = (ROOT / "assets/update-public-key.bin").read_bytes()
        if (source / "assets/update-public-key.bin").read_bytes() != public:
            raise ValueError("Built publisher key was changed")
        key_path = temporary / "key.bin"
        key_path.write_bytes(key_bytes)
        key_path.chmod(0o600)
        del key_bytes, encoded
        try:
            subprocess.run([sys.executable, str(ROOT / "sign_release.py"), "--source", str(source),
                            "--key", str(key_path), "--output", str(package),
                            "--package-url", f"https://github.com/{REPOSITORY}/releases/download/v{current}/{package.name}",
                            "--feed-output", str(feed), "--notes-file", str(ROOT / "release-notes.md")], check=True)
        finally:
            key_path.unlink(missing_ok=True)
        verify = Ed25519PublicKey.from_public_bytes(public)
        envelope = json.loads(feed.read_text(encoding="utf-8"))
        verify.verify(base64.b64decode(envelope["signature"]), canonical(envelope["manifest"]))
        with zipfile.ZipFile(package) as archive:
            envelope = json.loads(archive.read("update.json"))
            verify.verify(base64.b64decode(envelope["signature"]), canonical(envelope["manifest"]))
    hashes = output / f"KurtLauncher-v{current}-SHA256.txt"
    setup = output / f"KurtLauncher-v{current}-Setup.exe"
    hashes.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in (windows, setup, package, feed)), encoding="utf-8")
    print("Publisher signatures verified; no private key in output")


if __name__ == "__main__":
    main()

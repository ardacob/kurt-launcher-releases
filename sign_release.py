"""Publisher tool: create an authenticated update from a built Windows release.

python sign_release.py --source release/KurtLauncher --key /private/key.bin --output KurtLauncher.kurtupdate
Private keys must never be placed in the release source, assets or distribution ZIP.
"""
import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def constant(path, name):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"Missing {name} in {path}")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha512").hexdigest()


def regular_files(directory):
    for parent, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs + files:
            path = Path(parent) / name
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
            if path.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
                raise ValueError("Links/junctions cannot be signed: " + str(path))
        for name in files:
            yield Path(parent) / name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package-url", help="Public HTTPS URL of this exact version's update asset")
    parser.add_argument("--feed-output", type=Path, help="Write signed latest.json for the online channel")
    parser.add_argument("--notes-file", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    version = constant(source / "src/core.py", "APP_VERSION")
    top_level = constant(source / "src/updater.py", "TOP_LEVEL")
    if args.key.resolve().is_relative_to(source):
        parser.error("Private key must be outside the release folder.")
    key = Ed25519PrivateKey.from_private_bytes(args.key.read_bytes())
    from urllib.parse import urlparse
    if bool(args.package_url) != bool(args.feed_output):
        parser.error("--package-url and --feed-output must be provided together.")
    if args.package_url and (urlparse(args.package_url).scheme != "https" or not urlparse(args.package_url).hostname):
        parser.error("Public package URL must use HTTPS.")
    candidates = [source / "assets/update-public-key.bin", source / "_internal/assets/update-public-key.bin"]
    public_file = next((p for p in candidates if p.is_file()), None)
    if not public_file or public_file.read_bytes() != key.public_key().public_bytes_raw():
        parser.error("Private signing key does not match the application's publisher key.")
    files = {}
    sources = []
    paths = []
    for child in sorted(source.iterdir()):
        if child.name not in top_level: continue
        if child.is_symlink(): parser.error("Release cannot contain links.")
        if child.is_dir(): paths.extend(regular_files(child))
        elif child.is_file(): paths.append(child)
    for path in sorted(paths):
        name = path.relative_to(source).as_posix()
        if name.split("/")[0] not in top_level or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        sources.append((path, name))
        files[name] = {"size": path.stat().st_size, "sha512": digest(path)}
    if "KurtLauncher.exe" not in files: parser.error("Build KurtLauncher.exe first.")
    manifest = {"format": 1, "product": "KurtLauncher", "platform": "windows-x64", "version": version, "files": files}
    envelope = {"manifest": manifest, "signature": base64.b64encode(key.sign(canonical(manifest))).decode()}
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        def write(name, content):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compresslevel=6)
        write("update.json", canonical(envelope))
        for path, name in sources: write("payload/" + name, path.read_bytes())
    print("Signed update created:", args.output)
    if args.feed_output:
        online = {"format": 1, "product": "KurtLauncher", "platform": "windows-x64", "version": version,
                  "package_url": args.package_url, "package_sha512": digest(args.output),
                  "package_size": args.output.stat().st_size,
                  "notes": args.notes_file.read_text(encoding="utf-8")[:10000] if args.notes_file else ""}
        feed = {"manifest": online, "signature": base64.b64encode(key.sign(canonical(online))).decode()}
        args.feed_output.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Signed online feed created:", args.feed_output)


if __name__ == "__main__": main()

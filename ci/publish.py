"""Publish all assets atomically through a draft; never replace a public release."""
import json
import os
import urllib.error
from urllib.parse import quote
from common import ROOT, REPOSITORY, release_state, releases, request, sha256, version


def main():
    if (os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_EVENT_NAME") not in ("push", "workflow_dispatch")):
        raise ValueError("Publication is restricted to this repository's main branch")
    current = version()
    tag = "v" + current
    commit = os.environ["GITHUB_SHA"]
    prefix = f"/repos/{REPOSITORY}"
    existing = release_state(current, releases())
    if existing and not existing["draft"]:
        print("Already published; leaving the release unchanged:", tag)
        return
    try:
        ref = request(prefix + "/git/ref/tags/" + tag)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    else:
        obj = ref["object"]
        for _ in range(5):
            if obj["type"] != "tag":
                break
            obj = request(prefix + "/git/tags/" + obj["sha"])["object"]
        if obj["type"] != "commit" or obj["sha"] != commit:
            raise ValueError("Existing version tag points to another commit")
    notes = (ROOT / "release-notes.md").read_text(encoding="utf-8")
    if not notes.startswith("# " + current + "\n"):
        raise ValueError("Release notes must start with '# MAJOR.MINOR.PATCH'")
    names = [f"KurtLauncher-v{current}-Windows.zip", f"KurtLauncher-v{current}-Setup.exe", f"KurtLauncher-v{current}.kurtupdate",
             "latest.json", f"KurtLauncher-v{current}-SHA256.txt"]
    files = [ROOT / "artifacts" / name for name in names]
    if any(not path.is_file() or not path.stat().st_size for path in files):
        raise ValueError("One or more signed release assets are missing")
    if not existing:
        existing = request(prefix + "/releases", "POST", {
            "tag_name": tag, "target_commitish": commit, "name": "Kurt Launcher " + current,
            "body": notes, "draft": True, "prerelease": False})
    elif existing["target_commitish"] not in (commit, "main"):
        raise ValueError("Existing draft was created from another commit")
    release_path = prefix + "/releases/" + str(existing["id"])
    assets = {asset["name"]: asset for asset in request(release_path + "/assets?per_page=100")}
    for path in files:
        if path.name in assets:
            asset = assets[path.name]
            if asset["size"] != path.stat().st_size or asset.get("digest") != "sha256:" + sha256(path):
                raise ValueError("Draft contains a different asset; refusing to overwrite: " + path.name)
            continue
        upload_url = existing["upload_url"].split("{")[0] + "?name=" + quote(path.name)
        asset = request(upload_url, "POST", path.read_bytes(), "application/octet-stream")
        if asset["state"] != "uploaded" or asset["size"] != path.stat().st_size:
            raise ValueError("Incomplete asset upload: " + path.name)
        if asset.get("digest") != "sha256:" + sha256(path):
            raise ValueError("GitHub asset digest mismatch: " + path.name)
    uploaded = request(release_path + "/assets?per_page=100")
    if {a["name"] for a in uploaded} != set(names):
        raise ValueError("Draft assets do not match the five expected release files")
    # Check again after uploads, just before changing the public update channel.
    release_state(current, releases())
    result = request(release_path, "PATCH", {"draft": False, "make_latest": "true", "body": notes})
    print("Published:", result["html_url"])
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"## Kurt Launcher {current}\n\n[Windows Setup, ZIP ve imzalı güncelleme]({result['html_url']})\n\n")
            stream.write("Testler, Windows açılış kontrolü ve Ed25519 imzası doğrulandı.\n")


if __name__ == "__main__":
    main()

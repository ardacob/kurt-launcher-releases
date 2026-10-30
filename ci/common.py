"""Release helpers: standard library only; never import the desktop application."""
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "ardacob/kurt-launcher-releases"
API = "https://api.github.com"


def constant(path, name):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("Missing constant: " + name)


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value):
        raise ValueError("Version must be MAJOR.MINOR.PATCH: " + str(value))
    return tuple(map(int, value.split(".")))


def version():
    value = constant(ROOT / "src/core.py", "APP_VERSION")
    version_tuple(value)
    return value


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def safe_member(name):
    path = PurePosixPath(name)
    if (not name or "\\" in name or ":" in name or path.is_absolute()
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError("Unsafe archive path: " + name)
    return path


def request(path, method="GET", data=None, content_type="application/json"):
    url = path if path.startswith("https://uploads.github.com/") else API + path
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "KurtLauncher-release",
               "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = content_type
        if not isinstance(data, bytes):
            data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=180) as response:
        body = response.read()
        return json.loads(body) if body else None


def releases():
    result = []
    for page in range(1, 101):
        batch = request(f"/repos/{REPOSITORY}/releases?per_page=100&page={page}")
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise RuntimeError("Too many release pages")


def release_state(current, items):
    current_tuple = version_tuple(current)
    existing = None
    for item in items:
        if item["tag_name"] == "v" + current:
            existing = item
        if not item["draft"] and not item.get("prerelease"):
            try:
                other = version_tuple(item["tag_name"].removeprefix("v"))
            except ValueError:
                continue
            if other > current_tuple:
                raise ValueError("Refusing to publish a version older than " + item["tag_name"])
    return existing

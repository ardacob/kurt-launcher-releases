import os
from common import REPOSITORY, release_state, releases, version

current = version()
allowed = (os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
           and os.environ.get("GITHUB_REF") == "refs/heads/main"
           and os.environ.get("GITHUB_EVENT_NAME") in ("push", "workflow_dispatch"))
publish = False
if allowed:
    existing = release_state(current, releases())
    publish = existing is None or existing["draft"]
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
    stream.write(f"version={current}\npublish={str(publish).lower()}\n")
print(f"Version {current}; publication required: {publish}")

"""Dependency preparation only: inspect locked distribution metadata, never service imports."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import sys
import tomllib

from packaging.markers import Marker

lock = tomllib.loads(Path(sys.argv[1]).read_text())
packages = {package["name"]: package for package in lock["package"]}
root = packages["gateway-repository-service"]
queue = [*root["dependencies"], *root["dev-dependencies"]["dev"]]
selected: set[str] = set()
while queue:
    edge = queue.pop()
    if "marker" in edge and not Marker(edge["marker"]).evaluate():
        continue
    name = edge["name"]
    if name in selected:
        continue
    selected.add(name)
    queue.extend(packages[name].get("dependencies", []))
versions: dict[str, str] = {}
editable: dict[str, object] = {}
for name in sorted(selected):
    package = packages[name]
    distribution = importlib.metadata.distribution(name)
    assert distribution.version == package["version"], (name, distribution.version, package["version"])
    versions[name] = distribution.version
    if "editable" in package["source"]:
        assert name == "gateway-repository-contracts"
        direct = json.loads(distribution.read_text("direct_url.json") or "null")
        assert direct["dir_info"]["editable"] is True
        assert direct["url"] == "file:///repository_contracts", direct
        pth = list(Path("/app/.venv/lib/python3.14/site-packages").glob("*.pth"))
        assert any("/repository_contracts/src" in path.read_text().splitlines() for path in pth)
        editable[name] = direct
# The service root is deliberately not installed: production supplies /app/src via PYTHONPATH.
print(json.dumps({"versions": versions, "editable": editable, "root_project": "not-required"}, sort_keys=True))

#!/usr/bin/env python3
"""Select platform wheels from uv.container.lock for phase-exit deps wheelhouse staging."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse

_REQ_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;\\]+)")
_WIN32_MARKER_RE = re.compile(
    r"""sys_platform\s*==\s*(['"])win32\1""",
    re.IGNORECASE,
)


def _normalize_name(name: str) -> str:
    return name.lower().replace("_", "-")


def _is_hash_or_noise_line(stripped: str) -> bool:
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if stripped.startswith("-e"):
        return True
    if stripped.startswith("--hash=") or stripped.startswith("--hash "):
        return True
    return False


def _skip_win32_marker(line: str) -> bool:
    if ";" not in line:
        return False
    marker = line.split(";", 1)[1]
    return _WIN32_MARKER_RE.search(marker) is not None


def iter_export_requirements(text: str) -> list[tuple[str, str]]:
    """Parse uv export requirements.txt into (name, version) for Linux gate."""
    required: list[tuple[str, str]] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if _is_hash_or_noise_line(stripped):
            continue
        line = stripped.rstrip("\\").strip()
        if not line or _is_hash_or_noise_line(line):
            continue
        if _skip_win32_marker(line):
            continue
        m = _REQ_RE.match(line)
        if not m:
            raise ValueError(f"unsupported requirements line: {raw!r}")
        required.append((_normalize_name(m.group(1)), m.group(2)))
    return required


def _parse_requirements(path: Path) -> list[tuple[str, str]]:
    try:
        return iter_export_requirements(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _is_editable_source(source: object) -> bool:
    return isinstance(source, dict) and "editable" in source


def _hash_to_sha256(lock_hash: str) -> str:
    prefix = "sha256:"
    if not lock_hash.startswith(prefix):
        raise ValueError(f"unexpected lock hash: {lock_hash!r}")
    return lock_hash[len(prefix) :]


def _wheel_basename(url: str) -> str:
    return Path(urlparse(url).path).name


def _is_py3_none_any(url: str) -> bool:
    lower = url.lower()
    return lower.endswith("-py3-none-any.whl") or lower.endswith("-py2.py3-none-any.whl")


def _is_platform_wheel(url: str, python_tag: str) -> bool:
    base = _wheel_basename(url.lower())
    tag = python_tag.lower()
    return (
        f"-{tag}-{tag}-" in base
        and "manylinux" in base
        and "x86_64" in base
        and base.endswith(".whl")
    )


def select_wheel_url(
    wheels: list[dict[str, object]], python_tag: str
) -> tuple[str, str, str]:
    if not wheels:
        raise LookupError("no wheels in lock entry")
    for entry in wheels:
        url = str(entry["url"])
        if _is_py3_none_any(url):
            sha = _hash_to_sha256(str(entry["hash"]))
            return url, sha, _wheel_basename(url)
    for entry in wheels:
        url = str(entry["url"])
        if _is_platform_wheel(url, python_tag):
            sha = _hash_to_sha256(str(entry["hash"]))
            return url, sha, _wheel_basename(url)
    raise LookupError(f"no wheel for python_tag={python_tag}")


def load_lock_index(lock_path: Path) -> dict[tuple[str, str], dict[str, object]]:
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    index: dict[tuple[str, str], dict[str, object]] = {}
    for pkg in data.get("package", []):
        name = _normalize_name(str(pkg["name"]))
        version = str(pkg["version"])
        index[(name, version)] = pkg
    return index


def cmd_filter_export(input_path: Path, output_path: Path) -> None:
    required = _parse_requirements(input_path)
    if not required:
        raise SystemExit("filter-export: no requirements after filtering")
    lines = [f"{name}=={version}" for name, version in required]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_select(
    requirements_path: Path, lock_path: Path, python_tag: str
) -> None:
    required = _parse_requirements(requirements_path)
    index = load_lock_index(lock_path)
    for name, version in required:
        pkg = index.get((name, version))
        if pkg is None:
            raise SystemExit(
                f"lock missing package {name}=={version} (requirements vs lock)"
            )
        source = pkg.get("source")
        if _is_editable_source(source):
            continue
        wheels = pkg.get("wheels")
        if not isinstance(wheels, list) or not wheels:
            raise SystemExit(f"no wheels in lock for {name}=={version}")
        try:
            url, sha, basename = select_wheel_url(wheels, python_tag)
        except LookupError as exc:
            raise SystemExit(
                f"no platform wheel for {name}=={version}: {exc}"
            ) from exc
        print(f"{url}\t{sha}\t{basename}")


def cmd_select_regression(lock_path: Path, python_tag: str) -> None:
    index = load_lock_index(lock_path)
    ann = index.get((_normalize_name("annotated-doc"), "0.0.4"))
    if ann is None:
        raise SystemExit("select-regression: annotated-doc 0.0.4 missing from lock")
    ann_wheels = ann.get("wheels")
    if not isinstance(ann_wheels, list):
        raise SystemExit("select-regression: annotated-doc has no wheels")
    ann_url, _, ann_base = select_wheel_url(ann_wheels, python_tag)
    if not _is_py3_none_any(ann_url):
        raise SystemExit(
            f"select-regression: expected universal any wheel for annotated-doc, got {ann_url}"
        )
    if "py3-none-any" not in ann_base:
        raise SystemExit(f"select-regression: unexpected annotated-doc basename {ann_base}")

    col = index.get((_normalize_name("colorama"), "0.4.6"))
    if col is None:
        raise SystemExit("select-regression: colorama 0.4.6 missing from lock")
    col_wheels = col.get("wheels")
    if not isinstance(col_wheels, list):
        raise SystemExit("select-regression: colorama has no wheels")
    col_url, _, _ = select_wheel_url(col_wheels, python_tag)
    if "py2.py3-none-any" not in col_url:
        raise SystemExit(
            f"select-regression: expected py2.py3-none-any for colorama, got {col_url}"
        )

    par = index.get((_normalize_name("pyarrow"), "25.0.0"))
    if par is None:
        raise SystemExit("select-regression: pyarrow 25.0.0 missing from lock")
    par_wheels = par.get("wheels")
    if not isinstance(par_wheels, list):
        raise SystemExit("select-regression: pyarrow has no wheels")
    par_url, _, par_base = select_wheel_url(par_wheels, python_tag)
    if not _is_platform_wheel(par_url, python_tag):
        raise SystemExit(
            f"select-regression: expected cp314 manylinux x86_64 for pyarrow, got {par_url}"
        )
    if "manylinux" not in par_base or "x86_64" not in par_base:
        raise SystemExit(f"select-regression: unexpected pyarrow basename {par_base}")

    cp314t_first = [
        {
            "url": "https://files.pythonhosted.org/packages/t/t/pkg-0.0.1-cp314-cp314t-manylinux_2_28_x86_64.whl",
            "hash": "sha256:" + "a" * 64,
        },
        {
            "url": "https://files.pythonhosted.org/packages/s/s/pkg-0.0.1-cp314-cp314-manylinux_2_28_x86_64.whl",
            "hash": "sha256:" + "b" * 64,
        },
    ]
    cp314t_url = str(cp314t_first[0]["url"])
    if _is_platform_wheel(cp314t_url, python_tag):
        raise SystemExit("select-regression: cp314t wheel must not match cp314 platform filter")
    _, _, picked_base = select_wheel_url(cp314t_first, python_tag)
    if f"-{python_tag.lower()}-{python_tag.lower()}-" not in picked_base.lower():
        raise SystemExit(
            f"select-regression: expected standard {python_tag} ABI wheel, got {picked_base}"
        )
    if "cp314t" in picked_base.lower():
        raise SystemExit(f"select-regression: must not select cp314t wheel, got {picked_base}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_filter = sub.add_parser("filter-export")
    p_filter.add_argument("--input", type=Path, required=True)
    p_filter.add_argument("-o", "--output", type=Path, required=True)

    p_select = sub.add_parser("select")
    p_select.add_argument("--requirements", type=Path, required=True)
    p_select.add_argument("--lock", type=Path, required=True)
    p_select.add_argument("--python-tag", required=True)

    p_reg = sub.add_parser("select-regression")
    p_reg.add_argument("--lock", type=Path, required=True)
    p_reg.add_argument("--python-tag", required=True)

    args = parser.parse_args(argv)
    if args.command == "filter-export":
        cmd_filter_export(args.input, args.output)
    elif args.command == "select":
        cmd_select(args.requirements, args.lock, args.python_tag)
    elif args.command == "select-regression":
        cmd_select_regression(args.lock, args.python_tag)
    else:
        raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()

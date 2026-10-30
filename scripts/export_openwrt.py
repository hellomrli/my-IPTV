#!/usr/bin/env python3
"""Export a self-contained OpenWrt package without copying repository secrets."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ("build_playlists.py", "catchup_server.py", "diagnostics.py", "sync_iptv.py", "openwrt_service.py", "upstream.py")


def export_package(destination: Path) -> None:
    template = ROOT / "openwrt/luci-app-iptv-catchup"
    destination = destination.resolve()
    if destination == template.resolve() or template.resolve() in destination.parents:
        raise ValueError("destination must be outside the package template")
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}; use a new empty path")
    shutil.copytree(template, destination)
    runtime = destination / "root/usr/lib/iptv-catchup"
    runtime.mkdir(parents=True)
    for name in RUNTIME:
        shutil.copyfile(ROOT / "scripts" / name, runtime / name)
    data = destination / "root/etc/iptv-catchup"
    data.mkdir(parents=True)
    for name in ("IPTV.m3u", "catchup.json"):
        shutil.copyfile(ROOT / name, data / name)
    tests = destination / "tests"
    tests.mkdir(exist_ok=True)
    for name in ("test_catchup.py", "test_diagnostics.py", "test_router.py", "test_upstream.py"):
        shutil.copyfile(ROOT / "tests" / name, tests / name)
    for path in destination.rglob("*"):
        path.chmod(0o755 if path.is_dir() or path.name == "iptv-catchup" and path.parent.name == "init.d" else 0o644)
    manifest = {
        "source": "https://github.com/hellomrli/my-IPTV",
        "note": "Exported from reviewed working tree; hashes identify the exact bundled source.",
        "sha256": {str(path.relative_to(destination)): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in sorted(destination.rglob("*")) if path.is_file()},
    }
    (destination / "SOURCE.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new package directory, must not already exist")
    args = parser.parse_args()
    export_package(args.destination)
    print(f"Exported package to {args.destination}")


if __name__ == "__main__":
    main()

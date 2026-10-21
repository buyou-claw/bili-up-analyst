#!/usr/bin/env python3
"""Package this repository into dist/<repo-name>.skill (a zip file).

Usage:
  python package_skill.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

SKIP_DIRS = {".git", ".github", "dist", "__pycache__", "analysis", ".venv", "venv"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    dist = repo / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"{repo.name}.skill"

    files = []
    for path in sorted(repo.rglob("*")):
        rel = path.relative_to(repo)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.is_file() and path.name not in SKIP_FILES and not path.name.endswith(".pyc"):
            files.append((path, f"{repo.name}/{rel.as_posix()}"))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path, arcname in files:
            bundle.write(path, arcname)

    print(f"Packaged {len(files)} files -> {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Install this skill into an agent skills directory.

Usage:
  python install.py [--target <skills_dir>] [--name bili-up-analyst]

Default target: $BILI_SKILLS_DIR, else ~/.agents/skills
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

SKIP = {".git", ".github", "dist", "__pycache__", "analysis", ".venv", "venv", "*.pyc"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", default="", help="skills 目录（默认 $BILI_SKILLS_DIR 或 ~/.agents/skills）")
    ap.add_argument("--name", default="bili-up-analyst")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parent.parent
    target = Path(
        args.target or os.environ.get("BILI_SKILLS_DIR") or (Path.home() / ".agents" / "skills")
    ).expanduser().resolve()
    dest = target / args.name

    if dest.exists():
        shutil.rmtree(dest)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(repo, dest, ignore=shutil.ignore_patterns(*SKIP))
    print(f"Installed skill to: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

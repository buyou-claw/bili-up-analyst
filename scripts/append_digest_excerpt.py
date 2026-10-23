#!/usr/bin/env python3
"""Append a digest excerpt as a supplementary section to each note.

The original note format (9 sections) is preserved; the digest excerpt is appended
as the LAST section: "## 内容精编（补充）". Idempotent: skips notes that already
have the marker (use --force to replace it).

Usage:
  python append_digest_excerpt.py --up-dir "<up_dir>" [--chars 1200] [--force]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import find_up_dir, load_index, video_paths

MARKER = "## 内容精编（补充）"


def build_excerpt(digest_text: str, max_chars: int) -> str:
    """Take the first 1-3 subsections of 内容精编 plus 金句原文, capped at max_chars."""
    section = re.search(r"^## 内容精编\s*\n(.*?)(?=^## |\Z)", digest_text, re.M | re.S)
    body = section.group(1).strip() if section else ""
    chunks = [c.strip() for c in re.split(r"^### ", body, flags=re.M)[1:] if c.strip()]

    chosen: list[str] = []
    total = 0
    for chunk in chunks:
        head, _, rest = chunk.partition("\n")
        text = f"### {head.strip()}\n{rest.strip()}".strip()
        if total and total + len(text) > max_chars:
            break
        chosen.append(text)
        total += len(text)
        if total >= max_chars * 0.8:
            break

    quotes = re.search(r"^## 金句原文\s*\n(.*?)(?=^## |\Z)", digest_text, re.M | re.S)
    out = "\n\n".join(chosen).strip()
    if quotes:
        out = (out + "\n\n" + quotes.group(1).strip()).strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--up-dir", required=True)
    ap.add_argument("--chars", type=int, default=1200, help="节选目标长度（汉字，默认 1200）")
    ap.add_argument("--force", action="store_true", help="替换已存在的补充节")
    args = ap.parse_args()

    up_dir = find_up_dir(args.up_dir)
    index = load_index(up_dir)
    appended = skipped = missing = 0
    for row in index["videos"]:
        paths = video_paths(up_dir, row)
        digest_path: Path = paths["digest"]
        note_path: Path = paths["note"]
        if not digest_path.exists() or not note_path.exists():
            continue
        note = note_path.read_text(encoding="utf-8")
        if MARKER in note:
            if not args.force:
                skipped += 1
                continue
            note = re.split(rf"^{re.escape(MARKER)}.*\Z", note, flags=re.M | re.S)[0].rstrip() + "\n"

        excerpt = build_excerpt(digest_path.read_text(encoding="utf-8"), args.chars)
        if not excerpt:
            missing += 1
            continue
        block = f"\n\n{MARKER}\n\n> 以下节选自 `digests/{digest_path.name}`（完整版见该文件；为保留原话与叙事顺序，未做二次概括）。\n\n{excerpt}\n"
        note_path.write_text(note.rstrip() + block, encoding="utf-8")
        appended += 1

    print(f"UP_DIR={up_dir}")
    print(f"APPENDED={appended} SKIPPED={skipped} NO_EXCERPT={missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

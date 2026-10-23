#!/usr/bin/env python3
"""Append the digest's FULL "内容精编" chapter to each note (whole video, original order).

The original note format (9 sections) is preserved; the digest chapter is appended
as the LAST section: "## 内容精编（补充）". This covers the whole video (4–8
subsections, following the original narrative), not just the opening minutes.

Idempotent: skips notes that already have the marker (use --force to replace it).

Usage:
  python append_digest_excerpt.py --up-dir "<up_dir>" [--chars 0] [--force]

  --chars N > 0: 若内容精编超过 N 字符，则对每段做等比例截取（保证覆盖全片，
                 而不是只截开头）；默认 0 = 完整追加。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import find_up_dir, load_index, video_paths

MARKER = "## 内容精编（补充）"
SECTION_RE = re.compile(r"^## 内容精编\s*\n(.*?)(?=^## |\Z)", re.M | re.S)


def _trim_evenly(chunks: list[str], max_chars: int) -> list[str]:
    """Trim each subsection proportionally so every part of the video is represented."""
    total = sum(len(c) for c in chunks)
    if total <= max_chars:
        return chunks
    share = max_chars / len(chunks)
    out = []
    for chunk in chunks:
        if len(chunk) <= share:
            out.append(chunk)
            continue
        cut = chunk[: int(share)].rstrip()
        # 尽量在句末断开
        boundary = max(cut.rfind(ch) for ch in "。！？；")
        if boundary >= share * 0.6:
            cut = cut[: boundary + 1]
        out.append(cut + "……")
    return out


def build_supplement(digest_text: str, max_chars: int = 0) -> str:
    """Return the whole 内容精编 chapter (all subsections, in original order)."""
    section = SECTION_RE.search(digest_text)
    body = section.group(1).strip() if section else ""
    if not body:
        return ""

    chunks = [f"### {c.strip()}" for c in re.split(r"^### ", body, flags=re.M)[1:] if c.strip()]
    if not chunks:
        return body
    if max_chars > 0:
        chunks = _trim_evenly(chunks, max_chars)
    return "\n\n".join(chunks).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--up-dir", required=True)
    ap.add_argument("--chars", type=int, default=0, help="字符上限（0=完整追加；>0 时按段等比例截取）")
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

        supplement = build_supplement(digest_path.read_text(encoding="utf-8"), args.chars)
        if not supplement:
            missing += 1
            continue
        block = (
            f"\n\n{MARKER}\n\n"
            f"> 以下为整期视频的「内容精编」全文（覆盖全片，按原视频顺序；完整独立文件见 "
            f"`digests/{digest_path.name}`）。原文为保留原话与叙事顺序做压缩，未二次概括。\n\n"
            f"{supplement}\n"
        )
        note_path.write_text(note.rstrip() + block, encoding="utf-8")
        appended += 1

    print(f"UP_DIR={up_dir}")
    print(f"APPENDED={appended} SKIPPED={skipped} NO_SUPPLEMENT={missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

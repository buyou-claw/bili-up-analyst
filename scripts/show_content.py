#!/usr/bin/env python3
"""Print cached transcript text in token-sized parts (for subagents).

File names use '<发布日期>_<标题>' (no BV number); bvid is looked up via index.json.
The output header includes NOTE_FILE — subagents must write their note there.

Usage:
  python show_content.py --up-dir "<up_dir>" --bvid BVxxxx --list
  python show_content.py --up-dir "<up_dir>" --bvid BVxxxx --part 1 --part-chars 4000
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import analysis_root, find_up_dir, find_video_row, load_index, video_paths

MARKER_EVERY = 45.0  # seconds between timestamp markers


def locate(bvid: str, up_dir: str | None) -> tuple[Path, Path]:
    """Return (up_dir, raw_json_path) for a bvid."""
    if up_dir:
        up = find_up_dir(up_dir)
        row = find_video_row(load_index(up), bvid)
        return up, video_paths(up, row)["raw_json"]

    root = analysis_root()
    if root.is_dir():
        for up in root.iterdir():
            if not up.is_dir():
                continue
            try:
                index = load_index(up)
            except Exception:
                continue
            for row in index.get("videos", []):
                if row.get("bvid") == bvid:
                    return up, video_paths(up, row)["raw_json"]

    raise SystemExit(f"找不到 {bvid} 的索引（先跑 up_index.py / fetch_content.py）")


def build_text(data: dict) -> str:
    out = []
    buf = []
    last_mark = -1e9
    for item in data.get("items", []):
        t = float(item.get("t") or 0)
        if t - last_mark >= MARKER_EVERY:
            if buf:
                out.append("".join(buf).strip())
                buf = []
            out.append(f"〔{int(t) // 60:02d}:{int(t) % 60:02d}〕")
            last_mark = t
        buf.append(item.get("text", ""))
    if buf:
        out.append("".join(buf).strip())
    return "".join(out)


def split_parts(text: str, size: int) -> list[str]:
    size = max(size, 500)
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bvid", default="")
    ap.add_argument("--up-dir", default="")
    ap.add_argument("--part", type=int, default=1)
    ap.add_argument("--part-chars", type=int, default=4000)
    ap.add_argument("--list", action="store_true", help="列出该 UP 已抓取的全部视频")
    args = ap.parse_args()

    if args.list:
        if not args.up_dir:
            raise SystemExit("--list 需要同时提供 --up-dir")
        up = find_up_dir(args.up_dir)
        for p in sorted((up / "raw").glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            print(
                f"{p.stem} | bvid={d.get('bvid', '')} | {d.get('pubdate', '')} | "
                f"source={d.get('source', '')} | chars={d.get('chars', 0)}"
            )
        return 0

    if not args.bvid:
        raise SystemExit("需要 --bvid（或使用 --list --up-dir）")

    up, raw_json = locate(args.bvid, args.up_dir or None)
    row = find_video_row(load_index(up), args.bvid)
    paths = video_paths(up, row)
    data = json.loads(raw_json.read_text(encoding="utf-8"))

    text = build_text(data)
    parts = split_parts(text, args.part_chars)
    n = max(1, min(args.part, len(parts)))
    print(f"# {data.get('title', '')}")
    print(f"bvid={data['bvid']} source={data.get('source', '')} chars={len(text)} part={n}/{len(parts)}")
    print(f"NOTE_FILE={paths['note']}")
    print(f"RAW_FILE={raw_json}")
    if data.get("ai_summary"):
        print(f"AI_SUMMARY: {data['ai_summary'][:800]}")
    print("---")
    print(parts[n - 1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

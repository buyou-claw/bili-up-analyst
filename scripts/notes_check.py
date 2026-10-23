#!/usr/bin/env python3
"""Validate per-video notes and report coverage.

Notes are stored as notes/<发布日期>_<标题>.md (no BV number in file names).

Usage:
  python notes_check.py --up-dir "<up_dir>" [--since 2026-09-01] [--until 2026-10-21]
"""

from __future__ import annotations

import argparse

from _common import find_up_dir, load_index, video_paths

REQUIRED = [
    "## 一句话结论",
    "## 核心论点",
    "## 关键数据",
    "## 推理链条",
    "## 思维模型",
    "## 可证伪预测",
    "## 立场与盲区",
    "## 金句",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--up-dir", required=True)
    ap.add_argument("--min-chars", type=int, default=150)
    ap.add_argument("--max-chars", type=int, default=6500)
    ap.add_argument("--since", default="", help="只校验发布日 >= YYYY-MM-DD 的期数")
    ap.add_argument("--until", default="", help="只校验发布日 <= YYYY-MM-DD 的期数")
    args = ap.parse_args()

    up_dir = find_up_dir(args.up_dir)
    notes_dir = up_dir / "notes"
    index = load_index(up_dir)
    rows = index["videos"]
    if args.since:
        rows = [r for r in rows if (r.get("pubdate") or "")[:10] >= args.since]
    if args.until:
        rows = [r for r in rows if (r.get("pubdate") or "")[:10] <= args.until]

    missing: list[str] = []
    warnings: list[str] = []
    total_chars = 0
    for row in rows:
        bvid = row["bvid"]
        slug = video_paths(up_dir, row)["stem"]
        path = notes_dir / f"{slug}.md"
        if not path.exists():
            missing.append(f"{slug} (bvid={bvid})")
            continue
        text = path.read_text(encoding="utf-8")
        # 只校验前 9 节（补充节是给人读的精编全文，不计入长度约束）
        core = text.split("## 内容精编（补充）")[0]
        total_chars += len(core)
        lacking = [h for h in REQUIRED if h not in text]
        if lacking:
            warnings.append(f"{slug}: 缺章节 {','.join(x.replace('## ', '') for x in lacking)}")
        elif len(core) < args.min_chars:
            warnings.append(f"{slug}: 过短({len(core)} 字)")
        elif len(core) > args.max_chars:
            warnings.append(f"{slug}: 过长({len(core)} 字)")

    print(f"UP_DIR={up_dir}")
    print(f"NOTES={len(rows) - len(missing)}/{len(rows)} chars={total_chars} est_tokens={int(total_chars * 0.7)}")
    if missing:
        print(f"MISSING({len(missing)}):\n  " + "\n  ".join(missing))
    for msg in warnings:
        print(f"WARN {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

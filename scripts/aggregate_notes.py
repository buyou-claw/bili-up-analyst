#!/usr/bin/env python3
"""Aggregate predictions and quotes from per-video notes (deterministic, 0 token).

Usage:
  python aggregate_notes.py --up-dir "<up_dir>" [--intro "<path/to/predictions_intro.md>"]

Reads notes/*.md and writes:
  <up_dir>/predictions.md        (full ledger, sorted by publish date; overwritten)
  <up_dir>/synthesis/quotes_all.md
Prints compact stats so the agent does not need to read every note.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from _common import find_up_dir, load_index

NOTE_HEAD = re.compile(r"^# (.+)$")
BVID_RE = re.compile(r"-\s*bvid:\s*(\S+)")
DATE_RE = re.compile(r"-\s*发布:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")


def split_sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    parts = re.split(r"^## ", text, flags=re.M)
    for part in parts[1:]:
        head, _, body = part.partition("\n")
        out[head.strip()] = body.strip()
    return out


def parse_note(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    title = bvid = pubdate = ""
    for line in text.splitlines()[:10]:
        m = NOTE_HEAD.match(line)
        if m and not title:
            title = m.group(1).strip()
        m = BVID_RE.search(line)
        if m and not bvid:
            bvid = m.group(1)
        m = DATE_RE.search(line)
        if m and not pubdate:
            pubdate = m.group(1)
    sections = split_sections(text)
    predictions: list[str] = []
    for raw in sections.get("可证伪预测", "").splitlines():
        line = raw.strip()
        if not line.startswith("-"):
            continue
        item = line.lstrip("- ").strip()
        if not item or item in {"无", "（无）", "无。"}:
            continue
        item = re.sub(r"^\[[ x]\]\s*", "", item)
        predictions.append(item)
    quotes: list[str] = []
    for raw in sections.get("金句", "").splitlines():
        line = raw.strip()
        if line.startswith(">"):
            quotes.append(line.lstrip("> ").strip())
    return {
        "path": path,
        "title": title or path.stem,
        "bvid": bvid,
        "pubdate": pubdate or path.stem[:10],
        "predictions": predictions,
        "quotes": quotes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--up-dir", required=True)
    ap.add_argument("--intro", default="", help="可选：把该 Markdown 文件内容插入账本顶部（人工盘点）")
    args = ap.parse_args()

    up_dir = find_up_dir(args.up_dir)
    index = load_index(up_dir)
    notes = [parse_note(path) for path in sorted((up_dir / "notes").glob("*.md"))]
    notes.sort(key=lambda n: (n["pubdate"], n["title"]))
    if not notes:
        print("notes/ 为空，先跑蒸馏步骤")
        return 1

    pred_rows = []
    for note in notes:
        for item in note["predictions"]:
            pred_rows.append((note["pubdate"], item, note["bvid"], note["title"]))
    pred_rows.sort(key=lambda r: r[0])

    syn_dir = up_dir / "synthesis"
    syn_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# 预测账本 — {index.get('name', '')}",
        "",
        f"> 样本 {len(notes)} 期（{notes[0]['pubdate']} ~ {notes[-1]['pubdate']}）｜共 {len(pred_rows)} 条可证伪预测｜生成 {time.strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    if args.intro:
        intro_path = Path(args.intro).expanduser()
        if intro_path.exists():
            lines.append(intro_path.read_text(encoding="utf-8").strip())
            lines.append("")
        else:
            print(f"WARN intro 文件不存在: {intro_path}")
    lines += ["## 全量账本", "", "| # | 日期 | 预测 | 来源 |", "|---|------|------|------|"]
    for i, (date, item, bvid, title) in enumerate(pred_rows, 1):
        safe_item = item.replace("|", "/")
        safe_title = title.replace("|", "/")[:30]
        lines.append(f"| {i} | {date} | {safe_item} | {bvid} {safe_title} |")
    (up_dir / "predictions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    quote_lines = [f"# 金句库（自动汇总）— {index.get('name', '')}", ""]
    for note in notes:
        if not note["quotes"]:
            continue
        head = f"{note['pubdate']} {note['title'][:40]}（{note['bvid']}）"
        quote_lines.append(f"## {head}")
        for quote in note["quotes"]:
            quote_lines.append(f"> {quote}")
        quote_lines.append("")
    (syn_dir / "quotes_all.md").write_text("\n".join(quote_lines) + "\n", encoding="utf-8")

    months: dict = {}
    for date, *_ in pred_rows:
        months[date[:7]] = months.get(date[:7], 0) + 1
    print(f"UP_DIR={up_dir}")
    print(f"NOTES={len(notes)} PREDICTIONS={len(pred_rows)} QUOTES={sum(len(n['quotes']) for n in notes)}")
    print(f"BY_MONTH={json.dumps(months, ensure_ascii=False)}")
    print(f"PRED_FILE={up_dir / 'predictions.md'}")
    print(f"QUOTES_FILE={syn_dir / 'quotes_all.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

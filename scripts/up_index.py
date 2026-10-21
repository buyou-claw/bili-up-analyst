#!/usr/bin/env python3
"""Build an index of a Bilibili UP's videos; print only a compact summary.

Usage:
  python up_index.py <uid|space_url|nickname> --max 20 [--name NAME]

Writes: <analysis>/<name>_<uid>/index.json + index.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

from _common import analysis_root, ensure_project_imports, get_credential, resolve_uid, safe_name

CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}
EP_RE = re.compile(r"第([0-9零一二两三四五六七八九十百千]+)期")
DATE8_RE = re.compile(r"(20\d{2})([01]\d)([0-3]\d)")


def cn_to_int(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    total, section, num = 0, 0, 0
    for ch in text:
        if ch in CN_DIGITS:
            num = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            unit = CN_UNITS[ch]
            section += (num or 1) * unit
            num = 0
        else:
            return None
    return section + num


def parse_meta(title: str) -> dict:
    episode = style = None
    m = EP_RE.search(title or "")
    if m:
        episode = cn_to_int(m.group(1))
        style = "booked" if "《" in title else ("tilde" if "~" in title else "plain")
    dm = DATE8_RE.search(title or "")
    title_date = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}" if dm else ""
    return {"episode": episode, "series_style": style, "title_date": title_date}


def normalize(raw: dict, order: int) -> dict:
    created = int(raw.get("created") or 0)
    title = raw.get("title") or ""
    return {
        "order": order,
        "bvid": raw.get("bvid") or "",
        "title": title,
        "pubdate": time.strftime("%Y-%m-%d %H:%M", time.localtime(created)) if created else "",
        "created": created,
        "duration": raw.get("length") or "",
        "views": int(raw.get("play") or 0),
        "danmaku": int(raw.get("video_review") or 0),
        "replies": int(raw.get("comment") or 0),
        "favorites": int(raw.get("favorites") or 0),
        "is_pay": bool(raw.get("is_pay")),
        **parse_meta(title),
        "description": (raw.get("description") or "").strip(),
    }


async def fetch(uid: int, max_count: int, cred):
    ensure_project_imports()
    from bili_cli import client

    return await client.get_user_videos(uid, count=max_count, credential=cred)


async def fetch_name(uid: int, cred) -> str:
    ensure_project_imports()
    from bili_cli import client

    info = await client.get_user_info(uid, credential=cred)
    if not isinstance(info, dict):
        return str(uid)
    return str(info.get("name") or (info.get("info") or {}).get("name") or uid)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target", help="UID、空间链接或昵称")
    ap.add_argument("--max", type=int, default=50)
    ap.add_argument("--name", default="", help="覆盖 UP 名称（用于目录名）")
    args = ap.parse_args()

    cred = get_credential()
    if cred is None:
        print("未登录：请先 `bili login`。")
        return 1
    uid, name = resolve_uid(args.target)
    if args.name:
        name = args.name
    if not name or name == str(uid):
        try:
            name = asyncio.run(fetch_name(uid, cred))
        except Exception:
            name = str(uid)
    print(f"UP={name or '?'} UID={uid} fetching latest {args.max} videos...", flush=True)

    raw = asyncio.run(fetch(uid, args.max, cred))
    videos = [normalize(v, i) for i, v in enumerate(raw) if v.get("bvid")]
    if not videos:
        print("没有拉到视频（权限/UID/网络问题）。")
        return 1

    up_dir = analysis_root() / f"{safe_name(name)}_{uid}"
    up_dir.mkdir(parents=True, exist_ok=True)
    index = {
        "uid": uid,
        "name": name,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M"),
        "count": len(videos),
        "videos": videos,
    }
    (up_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    rows = ["# {} ({}) 视频索引".format(name, uid), "", f"- 抓取时间: {index['fetched_at']} | 数量: {len(videos)}", "",
            "| # | BV | 发布时间 | 时长 | 播放 | 期数 | 标题 |", "|---|---|---|---|---|---|---|"]
    for v in videos:
        rows.append(
            f"| {v['order']+1} | {v['bvid']} | {v['pubdate']} | {v['duration']} | {v['views']} | {v['episode'] or ''} | {v['title'].replace('|', '/')[:60]} |"
        )
    (up_dir / "index.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    dates = [v["pubdate"] for v in videos if v["pubdate"]]
    styles: dict = {}
    for v in videos:
        key = v["series_style"] or "other"
        styles[key] = styles.get(key, 0) + 1
    charge = sum(1 for v in videos if v["is_pay"])
    print(f"DIR={up_dir}")
    print(f"COUNT={len(videos)} RANGE={min(dates) if dates else '?'} ~ {max(dates) if dates else '?'}")
    print(f"SERIES={styles} CHARGE={charge}")
    print("LATEST:")
    for v in videos[:5]:
        print(f"  {v['bvid']} {v['pubdate']} {v['duration']:>7} views={v['views']:<8} {v['title'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

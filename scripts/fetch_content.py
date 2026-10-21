#!/usr/bin/env python3
"""Fetch content for indexed videos: subtitle -> AI summary -> local ASR fallback.

Usage:
  python fetch_content.py --up-dir "<up_dir>" [--limit 20] [--since 2026-09-01]
                          [--until 2026-10-21] [--bvid BV...] [--mode auto|subtitle] [--force]

Writes raw/<发布日期>_<标题>.json + raw/<发布日期>_<标题>.md (no BV in file names);
prints compact progress only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from _common import asr_model_dir, ensure_project_imports, find_up_dir, get_credential, video_slug

MIN_TEXT_CHARS = 100


def fmt_ts(t: float) -> str:
    s = int(t)
    return f"{s // 60:02d}:{s % 60:02d}"


def write_raw_md(path: Path, data: dict) -> None:
    lines = [
        f"# {data['title']}",
        "",
        f"- bvid: {data['bvid']} | 发布: {data.get('pubdate', '')} | 时长: {data.get('duration', '')}",
        f"- 来源: {data.get('source', '')} | 字数: {data.get('chars', 0)}",
        "",
    ]
    lines += [f"[{fmt_ts(i['t'])}] {i['text']}" for i in data.get("items", [])]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def fetch_one(bvid: str, row: dict, cred, mode: str, raw_dir: Path, model_dir) -> str:
    slug = video_slug(row)
    out_json = raw_dir / f"{slug}.json"
    ensure_project_imports()
    from bili_cli import client

    known_none = False
    if out_json.exists():
        try:
            cached = json.loads(out_json.read_text(encoding="utf-8"))
        except Exception:
            cached = None
        if cached and (cached.get("source") != "none" or mode == "subtitle"):
            return "cached"
        known_none = bool(cached and cached.get("source") == "none")

    data = {
        "bvid": bvid,
        "title": row.get("title", ""),
        "pubdate": row.get("pubdate", ""),
        "duration": row.get("duration", ""),
        "is_pay": bool(row.get("is_pay")),
        "source": "none",
        "ai_summary": "",
        "items": [],
        "chars": 0,
    }

    # 1) CC / AI subtitles
    if not known_none:
        try:
            _text, sub_items = await client.get_video_subtitle(bvid, credential=cred)
            items = []
            for item in sub_items or []:
                content = (item.get("content") or "").strip()
                if content:
                    items.append({"t": round(float(item.get("from") or 0), 1), "text": content})
            chars = sum(len(i["text"]) for i in items)
            if chars >= MIN_TEXT_CHARS:
                data.update(items=items, source="subtitle", chars=chars)
                print(f"  subtitle ok chars={chars}", flush=True)
        except Exception as exc:
            print(f"  subtitle error: {exc!r}", flush=True)

    # 2) Bilibili AI summary (bonus, not a transcript substitute)
    if data["source"] == "none":
        try:
            ai = await client.get_video_ai_conclusion(bvid, credential=cred)
            data["ai_summary"] = ((ai or {}).get("model_result") or {}).get("summary") or ""
        except Exception as exc:
            print(f"  ai summary error: {exc!r}", flush=True)

    # 3) ASR fallback
    if data["source"] == "none" and mode != "subtitle":
        tmp = raw_dir / f".{slug}.m4a"
        try:
            audio_url = await client.get_audio_url(bvid, credential=cred)
            nbytes = await client.download_audio(audio_url, str(tmp))
            print(f"  audio {nbytes / 1e6:.1f} MB, transcribing...", flush=True)
            from _asr import transcribe

            items = transcribe(str(tmp), str(model_dir), log=lambda msg: print(msg, flush=True))
            chars = sum(len(i["text"]) for i in items)
            data.update(items=items, source="asr", chars=chars)
            print(f"  asr ok chars={chars}", flush=True)
        except Exception as exc:
            print(f"  asr error: {exc!r}", flush=True)
        finally:
            tmp.unlink(missing_ok=True)

    if data["source"] == "none" and data["ai_summary"]:
        data["source"] = "ai"
        data["chars"] = len(data["ai_summary"])

    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    write_raw_md(raw_dir / f"{slug}.md", data)
    return data["source"]


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--up-dir", required=True, help="analysis/<name>_<uid> 目录（或 UID）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 期（0=全部）")
    ap.add_argument("--bvid", action="append", default=[], help="指定 bvid，可重复")
    ap.add_argument("--mode", choices=["auto", "subtitle"], default="auto")
    ap.add_argument("--since", default="", help="只处理发布日 >= YYYY-MM-DD 的视频")
    ap.add_argument("--until", default="", help="只处理发布日 <= YYYY-MM-DD 的视频")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    up_dir = find_up_dir(args.up_dir)
    index = json.loads((up_dir / "index.json").read_text(encoding="utf-8"))
    rows = index["videos"]
    if args.since:
        rows = [r for r in rows if (r.get("pubdate") or "")[:10] >= args.since]
    if args.until:
        rows = [r for r in rows if (r.get("pubdate") or "")[:10] <= args.until]
    if args.bvid:
        wanted = set(args.bvid)
        rows = [r for r in rows if r["bvid"] in wanted]
    if args.limit:
        rows = rows[: args.limit]
    raw_dir = up_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if args.force:
        for row in rows:
            (raw_dir / f"{video_slug(row)}.json").unlink(missing_ok=True)

    cred = get_credential()
    if cred is None:
        print("未登录：请先 `bili login`（充电专属视频还需要对应 UP 的充电会员）。")
        return 1
    model_dir = asr_model_dir()

    print(f"UP_DIR={up_dir}")
    print(f"TARGETS={len(rows)} mode={args.mode} asr_model={model_dir}")
    counts: dict = {}
    started = time.time()
    for i, row in enumerate(rows, 1):
        bvid = row["bvid"]
        print(f"[{i}/{len(rows)}] {bvid} {row['title'][:36]}", flush=True)
        source = await fetch_one(bvid, row, cred, args.mode, raw_dir, model_dir)
        counts[source] = counts.get(source, 0) + 1

    total_chars = 0
    none_list = []
    for row in rows:
        p = raw_dir / f"{video_slug(row)}.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            total_chars += d.get("chars", 0)
            if d.get("source") == "none":
                none_list.append(row["bvid"])
    print(f"CONTENT_DONE counts={counts} chars={total_chars} est_tokens={int(total_chars * 0.75)} wall={time.time() - started:.0f}s")
    if none_list:
        print(f"NO_TEXT={len(none_list)}: {' '.join(none_list)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

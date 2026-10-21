"""Shared helpers for bili-up-analyst scripts (portable version).

Locates bilibili-cli via `import bili_cli`, `BILI_CLI_PROJECT`, or a source
checkout on the current path. All analysis output paths are also configurable.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

DEFAULT_ASR_DIR = Path.home() / ".cache" / "bili-up-analyst" / "faster-whisper-small"


def _find_bili_project() -> Path | None:
    env = os.environ.get("BILI_CLI_PROJECT")
    if env:
        path = Path(env).expanduser().resolve()
        if (path / "bili_cli").is_dir():
            return path
        raise SystemExit(f"BILI_CLI_PROJECT 无效（缺少 bili_cli/ 目录）: {path}")

    try:
        import bili_cli as pkg  # noqa: F401

        return Path(pkg.__file__).resolve().parent.parent
    except Exception:
        pass

    cwd = Path.cwd()
    for path in [cwd, *cwd.parents]:
        if (path / "bili_cli").is_dir() and (path / "pyproject.toml").exists():
            return path
    return None


def project_root() -> Path:
    path = _find_bili_project()
    if path is None:
        raise SystemExit(
            "找不到 bilibili-cli：请先 `pip install bilibili-cli`，"
            "或设置 BILI_CLI_PROJECT=/path/to/bilibili-cli"
        )
    return path


def ensure_project_imports() -> Path:
    try:
        import bili_cli as pkg

        return Path(pkg.__file__).resolve().parent.parent
    except Exception:
        root = project_root()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        return root


def get_credential():
    ensure_project_imports()
    from bili_cli import auth

    return auth.get_credential(mode="optional")


def analysis_root() -> Path:
    custom = os.environ.get("BILI_ANALYSIS_DIR")
    if custom:
        return Path(custom).expanduser().resolve()
    try:
        return project_root() / "analysis"
    except SystemExit:
        return Path.cwd() / "analysis"


def safe_name(text: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\s]+', "_", text or "").strip("._")
    return cleaned[:40] or "up"


_FILENAME_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TRUNC_BOUNDARY = "，。！？；）】》…、.,!?;:"


def _smart_truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    head = text[:max_len]
    cut = max(head.rfind(ch) for ch in _TRUNC_BOUNDARY)
    if cut >= max(8, max_len // 2):
        return head[: cut + 1]
    return head


def sanitize_filename(text: str, max_len: int = 70) -> str:
    cleaned = _FILENAME_BAD.sub("_", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = _smart_truncate(cleaned, max_len).strip(" .")
    return cleaned or "untitled"


def video_slug(video: dict) -> str:
    """Filename stem: '<发布日期>_<标题>' (no BV number in file names)."""
    pubdate = (video.get("pubdate") or "")[:10] or "0000-00-00"
    title = sanitize_filename(video.get("title", ""), max_len=70)
    return f"{pubdate}_{title}"


def video_paths(up_dir: Path, video: dict) -> dict:
    slug = video_slug(video)
    return {
        "stem": slug,
        "raw_json": up_dir / "raw" / f"{slug}.json",
        "raw_md": up_dir / "raw" / f"{slug}.md",
        "note": up_dir / "notes" / f"{slug}.md",
    }


def load_index(up_dir: Path) -> dict:
    return json.loads((up_dir / "index.json").read_text(encoding="utf-8"))


def find_video_row(index: dict, bvid: str) -> dict:
    for row in index.get("videos", []):
        if row.get("bvid") == bvid:
            return row
    raise SystemExit(f"index 中找不到 bvid={bvid}")


def find_up_dir(target: str, create_uid: int | None = None, create_name: str = "") -> Path:
    """Resolve an UP analysis directory from a path, UID, or folder-name fragment."""
    path = Path(target).expanduser()
    if path.is_dir() and (path / "index.json").exists():
        return path.resolve()
    if path.is_dir() and (path / "raw").is_dir():
        return path.resolve()

    root = analysis_root()
    if root.is_dir():
        dirs = [d for d in root.iterdir() if d.is_dir()]
        if str(target).isdigit():
            for d in dirs:
                if d.name.endswith(f"_{target}"):
                    return d
        for d in dirs:
            if target and str(target) in d.name:
                return d

    if create_uid is not None:
        slug = f"{safe_name(create_name)}_{create_uid}" if create_name else str(create_uid)
        out = root / slug
        out.mkdir(parents=True, exist_ok=True)
        return out

    raise SystemExit(f"找不到 UP 分析目录（target={target!r}），请先用 up_index.py 建索引")


def asr_model_dir() -> Path:
    custom = os.environ.get("BILI_ASR_MODEL")
    return Path(custom).expanduser() if custom else DEFAULT_ASR_DIR


def resolve_uid(target: str) -> tuple[int, str]:
    """Accept UID, space URL, or nickname. Returns (uid, name)."""
    target = (target or "").strip()
    m = re.search(r"space\.bilibili\.com/(\d+)", target)
    if m:
        return int(m.group(1)), ""
    if target.isdigit():
        return int(target), ""

    ensure_project_imports()
    import asyncio

    from bili_cli import client

    results = asyncio.run(client.search_user(target))
    if not results:
        raise SystemExit(f"昵称搜索无结果: {target!r}，请改用 UID 或空间链接")
    first = results[0]
    uid = first.get("mid") or first.get("id")
    if uid is None:
        raise SystemExit(f"搜索结果缺少 UID: {first!r}")
    name = first.get("uname") or first.get("name") or target
    return int(uid), str(name)

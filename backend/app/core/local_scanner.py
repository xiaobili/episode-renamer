from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from ..config import settings
from ..models.file import FileInfo
from .utils import generate_id, get_extension, is_video_extension, is_subtitle_extension


def scan_local_directory(
    path: str,
    recursive: bool = True,
    include_subtitles: bool = True,
    video_extensions: Optional[list[str]] = None,
) -> list[FileInfo]:
    base = Path(path)
    if not base.exists():
        raise FileNotFoundError(f"路径不存在: {path}")
    if not base.is_dir():
        raise NotADirectoryError(f"不是目录: {path}")

    exts = set(video_extensions) if video_extensions else settings.video_extensions

    results: list[FileInfo] = []

    if recursive:
        iterator = base.rglob("*")
    else:
        iterator = base.iterdir()

    for entry in iterator:
        try:
            if entry.is_symlink():
                continue

            if entry.is_dir():
                continue

            ext = get_extension(entry.name)
            if not ext:
                continue

            is_video = is_video_extension(ext, exts)
            is_sub = is_subtitle_extension(ext)

            if not is_video and (not is_sub or not include_subtitles):
                continue

            size = 0
            try:
                size = entry.stat().st_size
            except OSError:
                pass

            parent_dir = str(entry.parent)

            results.append(
                FileInfo(
                    id=generate_id(),
                    source="local",
                    path=str(entry.resolve()),
                    filename=entry.name,
                    extension=ext,
                    size=size,
                    is_subtitle=is_sub,
                    parent_dir=parent_dir,
                )
            )
        except (PermissionError, OSError):
            continue

    return results


def scan_directory_timed(
    path: str,
    recursive: bool = True,
    include_subtitles: bool = True,
    video_extensions: Optional[list[str]] = None,
) -> tuple[list[FileInfo], int]:
    start = time.time()
    results = scan_local_directory(path, recursive, include_subtitles, video_extensions)
    elapsed = int((time.time() - start) * 1000)
    return results, elapsed


def match_subtitles(video_path: str, all_files: list[FileInfo]) -> list[FileInfo]:
    video = Path(video_path)
    video_stem = video.stem
    video_parent = video.parent

    matches = []
    for f in all_files:
        if not f.is_subtitle:
            continue
        fp = Path(f.path)
        if fp.parent != video_parent:
            continue
        if fp.stem.startswith(video_stem) or video_stem.startswith(fp.stem):
            matches.append(f)

    return matches

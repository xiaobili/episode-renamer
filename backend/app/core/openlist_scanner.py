from __future__ import annotations

import asyncio
from typing import Optional

from ..models.file import FileInfo
from ..config import settings
from .utils import generate_id, get_extension, is_video_extension, is_subtitle_extension
from .openlist_client import OpenListClient, OpenListFile


def _build_file_info(f: OpenListFile) -> FileInfo:
    ext = get_extension(f.name)
    is_sub = is_subtitle_extension(ext)
    parent_dir = f.path.rsplit("/", 1)[0] if "/" in f.path else "/"
    return FileInfo(
        id=generate_id(),
        source="openlist",
        path=f.path,
        filename=f.name,
        extension=ext,
        size=f.size,
        is_subtitle=is_sub,
        parent_dir=parent_dir,
        provider=f.provider,
        raw_path=f.raw_url or f.path,
    )


async def scan_openlist_directory(
    client: OpenListClient,
    path: str,
    recursive: bool = True,
    include_subtitles: bool = True,
    video_extensions: Optional[list[str]] = None,
    max_concurrent: int = 8,
) -> list[FileInfo]:
    exts = set(video_extensions) if video_extensions else settings.video_extensions
    queue: asyncio.Queue[str] = asyncio.Queue()
    semaphore = asyncio.Semaphore(max_concurrent)
    all_files: list[FileInfo] = []
    seen_dirs: set[str] = set()
    errors: list[str] = []

    print(f"[SCANNER] 开始扫描 path={path!r} recursive={recursive}")

    async def _worker() -> None:
        while True:
            current = await queue.get()
            try:
                async with semaphore:
                    files, _ = await client.list_directory(current)

                dirs_to_queue: list[str] = []
                for f in files:
                    if f.is_dir:
                        dirs_to_queue.append(f.path)
                        continue

                    ext = get_extension(f.name)
                    is_video = is_video_extension(ext, exts)
                    is_sub = is_subtitle_extension(ext)

                    if not is_video and (not is_sub or not include_subtitles):
                        continue

                    all_files.append(_build_file_info(f))

                if recursive:
                    for d in dirs_to_queue:
                        if d not in seen_dirs:
                            seen_dirs.add(d)
                            await queue.put(d)
            except Exception as e:
                msg = f"扫描 {current} 失败: {type(e).__name__}: {e}"
                errors.append(msg)
                print(f"[SCANNER] ERROR: {msg}")
            finally:
                queue.task_done()

    await queue.put(path)
    seen_dirs.add(path)

    workers = [asyncio.create_task(_worker()) for _ in range(max_concurrent)]

    await queue.join()

    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    print(f"[SCANNER] 完成: files={len(all_files)} dirs_visited={len(seen_dirs)} errors={len(errors)}")
    if errors:
        for e in errors[:5]:
            print(f"[SCANNER]   err: {e}")

    return all_files

from fastapi import APIRouter, HTTPException
from typing import Optional
import os

from ..models.api import ScanRequest, ScanResponse
from ..models.file import FileInfo
from ..core.local_scanner import scan_directory_timed
from ..core.openlist_client import OpenListClient
from ..core.openlist_scanner import scan_openlist_directory

router = APIRouter(prefix="/api", tags=["scan"])


_openlist_clients: dict[str, OpenListClient] = {}


def get_client_key(server_url: str, username: str) -> str:
    return f"{server_url}::{username}"


def register_client(client: OpenListClient) -> None:
    _openlist_clients[get_client_key(client.server_url, client.username)] = client


def get_client(server_url: str, username: str) -> Optional[OpenListClient]:
    return _openlist_clients.get(get_client_key(server_url, username))


def get_default_client() -> Optional[OpenListClient]:
    if _openlist_clients:
        return next(iter(_openlist_clients.values()))
    return None


@router.post("/scan", response_model=ScanResponse)
async def scan_directory(req: ScanRequest) -> ScanResponse:
    source = req.source.lower()

    if source == "local":
        try:
            files, elapsed = scan_directory_timed(
                path=req.path,
                recursive=req.recursive,
                include_subtitles=req.include_subtitles,
                video_extensions=req.video_extensions,
            )
        except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
            raise HTTPException(status_code=400, detail=str(e))

        from .renamer import cache_files
        cache_files(files)

        videos = sum(1 for f in files if not f.is_subtitle)
        subs = sum(1 for f in files if f.is_subtitle)

        return ScanResponse(
            success=True,
            source="local",
            total_files=len(files),
            videos=videos,
            subtitles=subs,
            duration_ms=elapsed,
            files=[f.model_dump() for f in files],
        )

    elif source == "openlist":
        client = get_default_client()
        if not client or not client.connected:
            raise HTTPException(status_code=401, detail="请先连接 OpenList")

        try:
            files = await scan_openlist_directory(
                client=client,
                path=req.path,
                recursive=req.recursive,
                include_subtitles=req.include_subtitles,
                video_extensions=req.video_extensions,
            )
        except ConnectionError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        from .renamer import cache_files
        cache_files(files)

        videos = sum(1 for f in files if not f.is_subtitle)
        subs = sum(1 for f in files if f.is_subtitle)

        return ScanResponse(
            success=True,
            source="openlist",
            total_files=len(files),
            videos=videos,
            subtitles=subs,
            files=[f.model_dump() for f in files],
        )

    else:
        raise HTTPException(status_code=400, detail=f"未知数据源: {source}")


@router.post("/browse")
async def browse_local_directory(req: dict):
    path = req.get("path") or os.path.expanduser("~")
    path = os.path.abspath(os.path.expanduser(path))

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"目录不存在: {path}")
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"不是目录: {path}")

    try:
        entries = sorted(
            os.listdir(path),
            key=lambda n: (not os.path.isdir(os.path.join(path, n)), n.lower()),
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"无权限访问: {path}")

    dirs = []
    for name in entries:
        full = os.path.join(path, name)
        if os.path.isdir(full):
            dirs.append({"name": name, "path": full, "type": "dir"})

    parent = os.path.dirname(path) if path != "/" else "/"
    if not parent:
        parent = "/"

    return {
        "success": True,
        "path": path,
        "dirs": dirs,
        "write_access": os.access(path, os.W_OK),
        "parent": parent,
    }

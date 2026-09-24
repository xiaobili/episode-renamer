from fastapi import APIRouter, HTTPException
from typing import Optional

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

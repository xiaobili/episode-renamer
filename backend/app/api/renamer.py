from fastapi import APIRouter, HTTPException
from typing import Optional

from ..models.api import RenamePreviewRequest, RenameExecuteRequest
from ..models.file import (
    FileInfo, RenamePlan, BatchRenameResult, OverrideInfo,
)
from ..core.local_renamer import batch_rename as local_batch_rename
from ..core.openlist_renamer import (
    build_openlist_rename_plan, execute_openlist_batch,
)
from ..config import settings
from ..core.template import PadConfig
from .scanner import get_default_client

router = APIRouter(prefix="/api", tags=["renamer"])


def _pad_from_request(req) -> PadConfig | None:
    """两个字段都没传时返回 None, 保持与改动前完全一致的行为。"""
    if req.episode_pad_digits is None and req.season_pad_digits is None:
        return None
    # 必须显式判 None, 不能用 `x or default` —— 0 是合法输入,
    # 用 or 会让 0 短路成全局默认值, 钳制逻辑永远不触发。
    episode = (
        req.episode_pad_digits
        if req.episode_pad_digits is not None
        else settings.episode_pad_digits
    )
    season = (
        req.season_pad_digits
        if req.season_pad_digits is not None
        else settings.season_pad_digits
    )
    return PadConfig(episode=episode, season=season)


_cached_files: dict[str, list[FileInfo]] = {}


def cache_files(files: list[FileInfo]) -> None:
    key = "files_cache"
    _cached_files[key] = files


def get_cached_files() -> list[FileInfo]:
    return _cached_files.get("files_cache", [])


def find_files_by_ids(file_ids: list[str]) -> list[FileInfo]:
    all_files = get_cached_files()
    id_set = set(file_ids)
    return [f for f in all_files if f.id in id_set]


def clear_cache() -> None:
    _cached_files.clear()


@router.post("/rename/preview")
async def preview_rename(req: RenamePreviewRequest):
    files = find_files_by_ids(req.file_ids)
    results: list[dict] = []
    pad = _pad_from_request(req)

    for f in files:
        source = req.source.lower()

        overrides = req.overrides.get(f.id) or {}
        override = OverrideInfo(**overrides) if overrides else None

        if source == "local":
            from ..core.local_renamer import build_rename_plan
            plan = build_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override, pad=pad,
            )
        elif source == "openlist":
            plan = build_openlist_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override, pad=pad,
            )
        else:
            raise HTTPException(status_code=400, detail=f"未知数据源: {source}")

        results.append({
            "original_path": plan.original_path,
            "original_filename": plan.original_filename,
            "new_path": plan.new_path,
            "new_filename": plan.new_filename,
            "has_conflict": plan.original_filename == plan.new_filename,
            "conflicts": plan.conflicts,
            "show_name": plan.parsed.show_name if plan.parsed else None,
            "season": plan.parsed.season if plan.parsed else None,
            "episode": plan.parsed.episode if plan.parsed else None,
            "confidence": plan.parsed.parse_confidence if plan.parsed else 0,
            "needs_review": plan.parsed.needs_manual_review if plan.parsed else False,
        })

    return {
        "success": True,
        "source": req.source,
        "total": len(results),
        "results": results,
    }


@router.post("/rename/execute")
async def execute_rename(req: RenameExecuteRequest):
    files = find_files_by_ids(req.file_ids)
    if not files:
        raise HTTPException(status_code=400, detail="未找到对应的文件")

    source = req.source.lower()
    pad = _pad_from_request(req)

    if source == "local":
        result = local_batch_rename(
            files=files,
            template=req.template,
            folder_template=req.folder_template,
            create_season_folder=req.create_season_folder,
            overrides=req.overrides,
            dry_run=False,
            conflict_strategy=req.conflict_strategy,
            pad=pad,
        )

    elif source == "openlist":
        client = get_default_client()
        if not client or not client.connected:
            raise HTTPException(status_code=401, detail="请先连接 OpenList")

        plans: list[RenamePlan] = []
        for f in files:
            ov = req.overrides.get(f.id)
            override = OverrideInfo(**ov) if ov else None
            plan = build_openlist_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override, pad=pad,
            )
            plans.append(plan)

        print(f"[RENAME] OpenList execute: {len(plans)} plans, client={client.server_url}")
        for p in plans[:5]:
            print(f"[RENAME]   {p.original_dir}/{p.original_filename} -> {p.new_dir}/{p.new_filename}")
        if len(plans) > 5:
            print(f"[RENAME]   ... +{len(plans)-5} more")

        result = await execute_openlist_batch(client, plans, dry_run=False)

        print(f"[RENAME] OpenList result: executed={result.executed} skipped={result.skipped} failed={result.failed}")
        for r in result.results:
            if not r.success:
                print(f"[RENAME]   ❌ {r.original_filename} -> {r.new_filename} error={r.error} status={r.status}")

    else:
        raise HTTPException(status_code=400, detail=f"未知数据源: {source}")

    return result.model_dump()


@router.post("/rename/dry-run")
async def dry_run_rename(req: RenameExecuteRequest):
    files = find_files_by_ids(req.file_ids)

    source = req.source.lower()
    pad = _pad_from_request(req)

    if source == "local":
        result = local_batch_rename(
            files=files,
            template=req.template,
            folder_template=req.folder_template,
            create_season_folder=req.create_season_folder,
            overrides=req.overrides,
            dry_run=True,
            conflict_strategy=req.conflict_strategy,
            pad=pad,
        )
    elif source == "openlist":
        client = get_default_client()
        if not client or not client.connected:
            raise HTTPException(status_code=401, detail="请先连接 OpenList")

        from ..core.openlist_renamer import build_openlist_rename_plan
        plans = []
        for f in files:
            ov = req.overrides.get(f.id)
            override = OverrideInfo(**ov) if ov else None
            plan = build_openlist_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override, pad=pad,
            )
            plans.append(plan)

        result = await execute_openlist_batch(client, plans, dry_run=True)
    else:
        raise HTTPException(status_code=400, detail=f"未知数据源: {source}")

    return result.model_dump()


@router.delete("/files")
async def clear_files():
    clear_cache()
    return {"success": True, "message": "文件列表已清空"}

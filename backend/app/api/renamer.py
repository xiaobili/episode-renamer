from fastapi import APIRouter, HTTPException
from typing import Optional

from ..models.api import RenamePreviewRequest, RenameExecuteRequest
from ..models.file import (
    FileInfo, ParsedInfo, RenamePlan, BatchRenameResult, OverrideInfo,
)
from ..models.nfo import NfoEntry, NfoOptions
from ..core.local_renamer import batch_rename as local_batch_rename
from ..core.openlist_renamer import (
    build_openlist_rename_plan, execute_openlist_batch,
)
from ..config import settings
from ..core.template import PadConfig
from ..core.nfo_writer import build_nfo_decisions
from ..core.parser import apply_override, parse_filename
from ..core.tmdb_client import TmdbAuthError, TmdbClient
from ..core.tmdb_resolver import (
    STATUS_DISABLED,
    STATUS_MATCHED,
    EpisodeMatch,
    ResolveRequest,
    TmdbResolver,
)
from .scanner import get_default_client
from .tmdb import build_tmdb_client

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


def _tmdb_client_from_request(req) -> Optional[TmdbClient]:
    """未启用或未配置 Key 时返回 None —— 调用方据此降级为 disabled, 不发任何请求。

    优先级与「空串算未提供」的判定**全部收敛在 resolve_tmdb_client 一处**
    （与 /api/tmdb/* 共用, 见那里的注释与 spec §10.3）。这里只做一件事:
    把 None 翻译成 preview/execute 的降级语义（spec §5.4: TMDB 不阻断重命名）。
    """
    return build_tmdb_client(req.tmdb_api_key, req.tmdb_language, req.tmdb_enabled)


def _tmdb_summary(status: str, match: Optional[EpisodeMatch] = None) -> dict:
    show = match.show if match else None
    return {
        "status": status,
        "tv_id": show.tv_id if show else None,
        "name": show.name if show else None,
        "original_name": show.original_name if show else None,
        "year": show.year if show else None,
    }


async def _with_tmdb_titles(
    req, files: list[FileInfo]
) -> tuple[dict[str, dict], dict[str, dict], dict[str, EpisodeMatch]]:
    """查 TMDB 并把标题并进 overrides。

    返回 (合并后的 overrides, 每文件的 TMDB 摘要, 每文件的 EpisodeMatch)。

    第三项供 NFO 生成消费 —— 它是 NFO 内容的唯一来源, 不重新查 TMDB。
    **手动指定的 title 永远优先于 TMDB** —— 这也是 episode_not_found 的兜底手段。
    """
    merged: dict[str, dict] = {
        f.id: dict(req.overrides.get(f.id) or {}) for f in files
    }
    summaries: dict[str, dict] = {}
    matches_by_file: dict[str, EpisodeMatch] = {}

    client = _tmdb_client_from_request(req)
    if client is None:
        for f in files:
            summaries[f.id] = _tmdb_summary(STATUS_DISABLED)
        return merged, summaries, matches_by_file

    # 用「覆盖之后」的解析结果去查 TMDB：用户手改的剧名/季/集才是他想要的那一部
    parsed: dict[str, ParsedInfo] = {}
    for f in files:
        raw = req.overrides.get(f.id) or {}
        parsed[f.id] = apply_override(
            parse_filename(f.filename, f.parent_dir),
            OverrideInfo(**raw) if raw else None,
        )

    resolver = TmdbResolver(client, overrides=req.tmdb_overrides)
    try:
        matches = await resolver.resolve_many([
            ResolveRequest(
                show_name=parsed[f.id].show_name,
                season=parsed[f.id].season,
                episode=parsed[f.id].episode,
            )
            for f in files
        ])
    except TmdbAuthError as exc:
        # 401 是配置错误, 必须让用户看见 —— 不可静默降级成 disabled。
        # 直接用异常自带的消息: TmdbAuthError 的文案本身就是「TMDB API Key 无效」,
        # 再拼一层前缀会得到「TMDB API Key 无效: TMDB API Key 无效」。
        raise HTTPException(status_code=400, detail=str(exc))

    for f, match in zip(files, matches):
        summaries[f.id] = _tmdb_summary(match.status, match)
        matches_by_file[f.id] = match
        if match.status == STATUS_MATCHED and match.episode and match.episode.name:
            if not merged[f.id].get("title"):
                merged[f.id]["title"] = match.episode.name

    return merged, summaries, matches_by_file


def _nfo_options_from_request(req) -> NfoOptions:
    return NfoOptions(
        enabled=bool(getattr(req, "generate_nfo", False)),
        overwrite=bool(getattr(req, "nfo_overwrite", False)),
    )


def _nfo_supported(source: str) -> bool:
    """本期只有本地源能写 NFO。

    OpenList 要写文件得先给 OpenListClient 加 /api/fs/put 上传能力,
    那是独立的一块工作与风险, 见 spec §2 与 §14。
    """
    return source == "local"


def _show_key(plan: RenamePlan) -> str:
    """plan 的剧名（解析失败时为 ""）。剧集级 NFO 按剧分组, 判定也按剧 —— 见 preview。"""
    return plan.parsed.show_name if plan.parsed else ""


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
    pad = _pad_from_request(req)
    source = req.source.lower()

    # 两遍解析的原因: {title} 是模板的渲染输入之一, 所以 TMDB 的标题必须在
    # build_rename_plan 渲染之前到手。第一遍只解析拿 (剧名, 季, 集), 批量查完
    # TMDB 后再把标题并进 overrides, 第二遍才渲染。
    merged, summaries, matches_by_file = await _with_tmdb_titles(req, files)

    # 计划只构建一次 —— NFO 落点的推导与响应共用同一批 plan,
    # 重复构建不但浪费, 两份结果一旦分叉就会出现「预览说写这里、实际写那里」。
    plans: list[RenamePlan] = []
    for f in files:
        overrides_for_f = merged.get(f.id) or {}
        override_for_f = OverrideInfo(**overrides_for_f) if overrides_for_f else None

        if source == "local":
            from ..core.local_renamer import build_rename_plan
            plans.append(build_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override_for_f, pad=pad,
            ))
        elif source == "openlist":
            plans.append(build_openlist_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override_for_f, pad=pad,
            ))
        else:
            raise HTTPException(status_code=400, detail=f"未知数据源: {source}")

    # NFO 落点必须在预览里可见 —— 「tvshow.nfo 会写到哪里」是库根污染的
    # 唯一防线（spec §9.4）。这里只算决策, 绝不落盘。
    nfo_options = _nfo_options_from_request(req)
    nfo_paths_by_file: dict[str, dict] = {}
    nfo_scope = "disabled"
    # NFO 只处理视频。判据用扫描器判定好的 FileInfo.is_subtitle（不是在这里再嗅一次
    # 扩展名）。不滤掉的后果与 local_renamer._is_subtitle_file 里写的是同一件事:
    # 字幕的解析结果与视频一字不差 → 字幕旁多写一个无意义的 .chs.nfo, 且排序会让
    # '….chs.srt' 抢到 group[0], 剧集级决策挂到字幕行上。
    # **预览与执行两处必须同时过滤**, 否则预览显示的落点与实际写出的会不一致。
    video_ids = {f.id for f in files if not f.is_subtitle}

    if nfo_options.enabled:
        if not _nfo_supported(source):
            nfo_scope = "unsupported_source"
        elif _tmdb_client_from_request(req) is None:
            # 启用了 NFO 但没有 TMDB —— 没有任何内容可写, 如实报 disabled,
            # 而不是让它落到下面算出 episode_only（那会暗示「只是没写剧集级」）。
            nfo_scope = "disabled"
        else:
            decisions = build_nfo_decisions(
                [
                    NfoEntry(
                        file_id=plan.file_id,
                        new_path=plan.new_path,
                        show_name=_show_key(plan),
                        season=plan.parsed.season if plan.parsed else None,
                        episode=plan.parsed.episode if plan.parsed else None,
                        show=getattr(matches_by_file.get(plan.file_id), "show", None),
                        season_data=getattr(matches_by_file.get(plan.file_id), "season", None),
                        episode_data=getattr(matches_by_file.get(plan.file_id), "episode", None),
                    )
                    for plan in plans
                    if plan.file_id in video_ids
                ],
                nfo_options,
            )
            for decision in decisions:
                if decision.content is None:
                    continue
                nfo_paths_by_file.setdefault(decision.file_id, {})[decision.kind] = decision.path

            # nfo_scope 说的是「剧集级 NFO 有没有被计划」, 判定按**剧**而不是按文件:
            # 剧集级决策按契约只挂在组内首个 file_id 上（见 build_nfo_decisions 的
            # 顺序/归属契约), 所以同一部剧选了两集时, 第二个文件根本没有 "tvshow" 键。
            # 逐文件 all(...) 会把它假阴性报成 episode_only —— 而 tvshow.nfo 明明
            # 在计划里, 前端据此显示的提示会把真实落点藏起来, 那正是 §9.4 要防的静默。
            planned_shows = {
                _show_key(plan) for plan in plans
                if "tvshow" in nfo_paths_by_file.get(plan.file_id, {})
            }
            # 判据落在**视频**上（NFO 管线只处理视频, 见上面的 video_ids）。字幕的
            # 剧名虽然与同一集的视频相同, 但让一个永远不会有 NFO 的行替批次背书是
            # 同一类错: 行级的东西不该决定批次级的事实。
            video_plans = [plan for plan in plans if plan.file_id in video_ids]
            # 空集上 all(...) 恒为 True: 一个 0 行的批次（路由接受 file_ids: []）会
            # 因此报出 "full" 这个批次级事实 —— 0 行数据推出的事实。没有任何视频
            # 条目时如实报「没有 NFO 计划」, 而不是把自己算成 full/episode_only。
            # （纯字幕批次走的就是这一支: 一个 NFO 都不会写。）
            if not video_plans:
                nfo_scope = "disabled"
            elif all(_show_key(plan) in planned_shows for plan in video_plans):
                nfo_scope = "full"
            else:
                nfo_scope = "episode_only"

    results: list[dict] = []
    for f, plan in zip(files, plans):
        summary = summaries.get(f.id) or _tmdb_summary(STATUS_DISABLED)
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
            "title": plan.parsed.title if plan.parsed else None,
            "confidence": plan.parsed.parse_confidence if plan.parsed else 0,
            "needs_review": plan.parsed.needs_manual_review if plan.parsed else False,
            "tmdb_status": summary["status"],
            "tmdb_match": {
                "tv_id": summary["tv_id"],
                "name": summary["name"],
                "original_name": summary["original_name"],
                "year": summary["year"],
            } if summary["tv_id"] else None,
            "nfo": nfo_paths_by_file.get(f.id) or None,
            "nfo_scope": nfo_scope,
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

    merged, _summaries, matches_by_file = await _with_tmdb_titles(req, files)
    effective_overrides = merged

    if source == "local":
        result = local_batch_rename(
            files=files,
            template=req.template,
            folder_template=req.folder_template,
            create_season_folder=req.create_season_folder,
            overrides=effective_overrides,
            dry_run=False,
            conflict_strategy=req.conflict_strategy,
            pad=pad,
            # _nfo_supported 为假时传**未启用**的 options 而不是 None: 两者在
            # batch_rename 里走同一分支, 但显式传让「OpenList 不写 NFO」这条规则
            # 在调用点就看得见, 而不是依赖 batch_rename 内部的空值判断。
            nfo_options=_nfo_options_from_request(req) if _nfo_supported(source) else NfoOptions(),
            nfo_matches=matches_by_file,
        )

    elif source == "openlist":
        client = get_default_client()
        if not client or not client.connected:
            raise HTTPException(status_code=401, detail="请先连接 OpenList")

        plans: list[RenamePlan] = []
        for f in files:
            ov = effective_overrides.get(f.id)
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

    merged, _summaries, matches_by_file = await _with_tmdb_titles(req, files)
    effective_overrides = merged

    if source == "local":
        result = local_batch_rename(
            files=files,
            template=req.template,
            folder_template=req.folder_template,
            create_season_folder=req.create_season_folder,
            overrides=effective_overrides,
            dry_run=True,
            conflict_strategy=req.conflict_strategy,
            pad=pad,
            nfo_options=_nfo_options_from_request(req) if _nfo_supported(source) else NfoOptions(),
            nfo_matches=matches_by_file,
        )
    elif source == "openlist":
        client = get_default_client()
        if not client or not client.connected:
            raise HTTPException(status_code=401, detail="请先连接 OpenList")

        from ..core.openlist_renamer import build_openlist_rename_plan
        plans = []
        for f in files:
            ov = effective_overrides.get(f.id)
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

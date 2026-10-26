from fastapi import APIRouter, HTTPException
from typing import Optional
import os
import posixpath

from ..models.api import (
    RenameBatchRequest, RenameDryRunRequest, RenameExecuteRequest,
    RenameFinalizeRequest, RenamePreviewRequest,
)
from ..models.file import (
    FileInfo, ParsedInfo, RenamePlan, BatchRenameResult, OverrideInfo,
    SingleRenameResult,
)
from ..models.nfo import NfoOptions
from ..core.local_renamer import (
    batch_rename as local_batch_rename,
    OneOutcome, count_result, execute_one, finalize_show_nfo,
    landed_path_of, plan_files,
)
from ..core.openlist_renamer import (
    build_openlist_rename_plan, execute_openlist_batch, execute_openlist_one,
)
from ..core.openlist_nfo import (
    episode_nfo_for_plan, finalize_openlist_nfo, plan_openlist_nfo,
)
from ..config import settings
from ..core.template import PadConfig
from ..core.nfo_writer import build_nfo_decisions, entry_from_plan
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


def _show_key(plan: RenamePlan) -> str:
    """plan 的剧名（解析失败时为 ""）。剧集级 NFO 按剧分组, 判定也按剧 —— 见 preview。"""
    return plan.parsed.show_name if plan.parsed else ""


def _as_batch_request(
    req: RenameExecuteRequest, overrides: dict[str, dict]
) -> RenameBatchRequest:
    """把单文件请求重打包成 `_with_tmdb_titles` 读的**批量形状**。

    字段用 model_dump 透传而不是逐个抄写: 两个模型的字段集合除
    `file_id`/`override` 与 `file_ids`/`overrides` 这一对外完全相同, 逐个抄写
    必然在下次加字段时漂移 —— 那正是 RenameBatchRequest 被抽出来的理由。
    """
    return RenameBatchRequest(
        **req.model_dump(exclude={"file_id", "override"}),
        file_ids=[req.file_id],
        overrides=overrides,
    )


def _apply_openlist_limits(client, req) -> None:
    """把请求里的限流设置应用到客户端。两个字段都没传时保持现状。"""
    client.apply_limits(
        max_concurrent=req.openlist_max_concurrent,
        request_interval=req.openlist_request_interval,
    )


def _find_one(file_id: str) -> FileInfo:
    files = find_files_by_ids([file_id])
    if not files:
        raise HTTPException(status_code=400, detail="未找到对应的文件")
    return files[0]


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
        if _tmdb_client_from_request(req) is None:
            # 启用了 NFO 但没有 TMDB —— 没有任何内容可写, 如实报 disabled,
            # 而不是让它落到下面算出 episode_only（那会暗示「只是没写剧集级」）。
            nfo_scope = "disabled"
        else:
            decisions = build_nfo_decisions(
                [
                    entry_from_plan(plan, matches_by_file)
                    for plan in plans
                    if plan.file_id in video_ids
                ],
                nfo_options,
                # OpenList 的落点永远是 POSIX 路径, 与宿主机无关。
                path_mod=posixpath if source == "openlist" else os.path,
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
    """执行**一个**文件的重命名。

    **单进程内存依赖**: find_files_by_ids 读的是模块级 _cached_files（见文件末尾
    的注释）, 所以本接口与 /rename/finalize 必须落在同一个进程里。当前部署是
    单 worker uvicorn（Dockerfile 的 CMD 没有 --workers）, 加 --workers 会让
    finalize 拿不到这里的缓存。
    """
    file = _find_one(req.file_id)
    source = req.source.lower()
    pad = _pad_from_request(req)

    # 适配成**批量形状**喂给既有的 _with_tmdb_titles: 它读的是 `req.overrides`
    # （批量形状）, 而本接口收的是单数 `override`。
    #
    # **必须真的重打包, 不能只算一个局部变量**: 直接把 `req` 传进去会
    # AttributeError —— RenameExecuteRequest 没有 overrides 字段。适配只发生在
    # 这里, 预览 / 干跑 / 收尾三条路径读的仍是各自真实的批量请求, 一行不动。
    overrides = {req.file_id: req.override} if req.override else {}
    merged, _summaries, matches_by_file = await _with_tmdb_titles(
        _as_batch_request(req, overrides), [file]
    )

    nfo_options = _nfo_options_from_request(req)

    if source == "local":
        # 本地用 plan_files: 它建 plan **并算冲突**（execute_one 读 plan.conflicts
        # 判 abort）。
        plan = plan_files(
            [file], req.template, req.folder_template, req.create_season_folder,
            merged, pad=pad,
        )[0]
        outcome = execute_one(
            plan,
            conflict_strategy=req.conflict_strategy,
            nfo_options=nfo_options,
            nfo_matches=matches_by_file,
        )
    elif source == "openlist":
        # **OpenList 必须用它自己的 builder**, 不能借道 plan_files —— 两个 builder
        # **不等价**: build_rename_plan 在父目录已是季目录时会**抑制**建季目录
        # （local_renamer._parent_is_season_dir）, build_openlist_rename_plan 不会。
        # 而预览与干跑的 OpenList 分支走的正是 build_openlist_rename_plan ——
        # 借道会让「预览说一套、执行做另一套」, 正是本仓库最忌讳的那一类
        # （见 spec §9.4 与 renamer.py 里那段注释）。另外 plan_files 里的
        # check_conflict 会对**远端路径**做本地 stat, 对 OpenList 毫无意义。
        ov = merged.get(file.id)
        plan = build_openlist_rename_plan(
            file, req.template, req.folder_template,
            req.create_season_folder, OverrideInfo(**ov) if ov else None, pad=pad,
        )
        client = get_default_client()
        if not client or not client.connected:
            raise HTTPException(status_code=401, detail="请先连接 OpenList")
        _apply_openlist_limits(client, req)
        # 这里必须 `await`, 不能 asyncio.run —— 本函数是 async 的, 而
        # asyncio.run 在运行中的事件循环里会抛 RuntimeError。
        # （asyncio.run 那条约定只适用于**测试文件**, 见 Task 3 Step 3。）
        result = await execute_openlist_one(client, plan)
        outcome = OneOutcome(result=result)
        # OpenList 路径没有 abort 合成结果, 恒传 aborted=False。
        outcome.executed, outcome.skipped, outcome.failed = count_result(result, False)
        # 字幕**不算落地**: 它与视频共用同一套 status, 但落点不该给组级 NFO 背书
        # （与本地 execute_one 的 is_video 判据一致）。不挡住的话, 「视频失败、
        # 字幕成功」会把字幕目录算成「有视频落地」, 从而写出 tvshow.nfo。
        outcome.landed_path = None if file.is_subtitle else landed_path_of(result)
        (
            outcome.nfo_written,
            outcome.nfo_carried,
            outcome.nfo_skipped,
        ) = await episode_nfo_for_plan(
            client, plan, result, matches_by_file, nfo_options,
        )
    else:
        raise HTTPException(status_code=400, detail=f"未知数据源: {source}")

    return SingleRenameResult(
        success=outcome.failed == 0,
        # 用**已算好的局部变量** source（已 lower()）, 而不是原始的 req.source:
        # 批量路径报的是规范化后的 "local"/"openlist"（见 openlist_renamer.py 与
        # local_renamer.py 的 BatchRenameResult 构造）, 这里不该漂。
        source=source,
        file_id=file.id,
        result=outcome.result,
        # 落点的**权威判定**（未落地为 None; local 分支里字幕恒为 None ——
        # 那条规则只有 local_renamer 一份, 前端不再自己判 status）。
        landed_path=outcome.landed_path,
        executed=outcome.executed,
        skipped=outcome.skipped,
        failed=outcome.failed,
        nfo_written=outcome.nfo_written,
        nfo_carried=outcome.nfo_carried,
        nfo_skipped=[{"path": p, "reason": r} for p, r in outcome.nfo_skipped],
    ).model_dump()


@router.post("/rename/dry-run")
async def dry_run_rename(req: RenameDryRunRequest):
    files = find_files_by_ids(req.file_ids)

    source = req.source.lower()
    pad = _pad_from_request(req)

    merged, _summaries, matches_by_file = await _with_tmdb_titles(req, files)
    effective_overrides = merged
    nfo_options = _nfo_options_from_request(req)

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
            nfo_options=nfo_options,
            nfo_matches=matches_by_file,
        )
    elif source == "openlist":
        client = get_default_client()
        if not client or not client.connected:
            raise HTTPException(status_code=401, detail="请先连接 OpenList")

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
        written, carried, skipped = await plan_openlist_nfo(
            client, plans, result.results, matches_by_file, nfo_options,
        )
        result.nfo_written = written
        result.nfo_carried = carried
        result.nfo_skipped = [{"path": p, "reason": r} for p, r in skipped]
    else:
        raise HTTPException(status_code=400, detail=f"未知数据源: {source}")

    return result.model_dump()


@router.post("/rename/finalize")
async def finalize_rename(req: RenameFinalizeRequest):
    """批次收尾: 只写剧集级 / 季级 NFO。

    为什么单独一个接口: 这两级 NFO 是**整批**的事实（每部剧一份 tvshow.nfo,
    每个季一份 season.nfo）, 拆成单文件请求后没有任何一个单文件请求能知道整批
    的落地情况。见 spec §4.2。

    **landed 必须来自前端回传的真实结果**, 不能靠这里重算「假定都成功」——
    整批失败时那会在一个没有任何剧集文件的目录里写出 tvshow.nfo。

    **单进程内存依赖**: 与 /rename/execute 同（见那里的注释）。
    """
    source = req.source.lower()
    files = find_files_by_ids(req.file_ids)
    if not files:
        raise HTTPException(status_code=400, detail="未找到对应的文件")

    pad = _pad_from_request(req)
    merged, _summaries, matches_by_file = await _with_tmdb_titles(req, files)
    landed_paths = [p for p in req.landed.values() if p]
    nfo_options = _nfo_options_from_request(req)

    if source == "local":
        plans = plan_files(
            files, req.template, req.folder_template, req.create_season_folder,
            merged, pad=pad,
        )
        written, skipped = finalize_show_nfo(
            plans, landed_paths, matches_by_file, nfo_options,
        )
    elif source == "openlist":
        client = get_default_client()
        if not client or not client.connected:
            raise HTTPException(status_code=401, detail="请先连接 OpenList")
        plans = []
        for f in files:
            ov = merged.get(f.id)
            plans.append(build_openlist_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, OverrideInfo(**ov) if ov else None, pad=pad,
            ))
        written, skipped = await finalize_openlist_nfo(
            client, plans, landed_paths, matches_by_file, nfo_options,
        )
    else:
        raise HTTPException(status_code=400, detail=f"未知数据源: {source}")

    return {
        "success": True,
        "nfo_written": written,
        "nfo_skipped": [{"path": p, "reason": r} for p, r in skipped],
    }


@router.delete("/files")
async def clear_files():
    clear_cache()
    return {"success": True, "message": "文件列表已清空"}

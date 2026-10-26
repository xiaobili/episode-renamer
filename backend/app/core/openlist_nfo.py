"""OpenList 云盘的 NFO 写入。

本模块是云盘 NFO 的**唯一副作用入口**: 远端存在性检查、上传、旧同前缀 NFO
跟随、批次收尾。决策本身仍由 `nfo_writer.build_nfo_decisions` 产出 —— 这里只
负责「把决策落到远端」, 与 `nfo_writer.write_nfo_files` 对本地做的是同一件事。

**路径契约**: OpenList 的路径永远是 POSIX 路径, 所以这里一律用 `posixpath`
推导落点, 不碰 `os.path` / `pathlib.Path` —— 否则 Windows 宿主机会把远端路径
写成 `\\` 分隔, 上传到错误的名字上。
"""
from __future__ import annotations

import posixpath
from typing import Optional

from ..models.file import RenamePlan, RenameResult
from ..models.nfo import NfoDecision, NfoOptions
from .local_renamer import landed_path_of
from .nfo_writer import (
    CARRIED_NFO_TARGET_EXISTS_REASON,
    DROPPED_GROUP_NFO_REASON,
    NOT_RENAMED_NFO_REASON,
    build_nfo_decisions,
    dedupe_skipped_pairs,
    entry_from_plan,
    episode_nfo_path,
    filter_landed_decisions,
)
from .openlist_client import OpenListClient
from .tmdb_resolver import EpisodeMatch


# OpenList 的单文件执行会出现的「视频真的动了」状态。与本地 `_CARRY_STATUSES`
# 同义, 但状态名集合不同（见 openlist_renamer.execute_openlist_one）。
# `moved_not_renamed` 也算: 文件已经离开原处, 它的旧 NFO 同样应该跟过去。
_OPENLIST_CARRY_STATUSES = frozenset({
    "renamed", "renamed_moved", "renamed_fallback",
    "moved_not_renamed", "dry_run",
})


def _is_subtitle(plan: RenamePlan) -> bool:
    """判据用扫描器已经判定好的 FileInfo.is_subtitle, 不在 NFO 层嗅扩展名。"""
    return bool(plan.file_info is not None and plan.file_info.is_subtitle)


def _looks_like_missing(exc: Exception) -> bool:
    """列目录失败是否只是「目录还不存在」。

    干跑会看到尚未创建的季目录 —— 那等价于本地 `Path.exists()` 返回 False,
    应当按「空目录」规划, 而不是把整条计划报成写入失败。除此之外的失败仍
    如实报出来, 不能被静默当成空目录（那会让「将写入」变成假话）。
    """
    text = str(exc).lower()
    return "not found" in text or "不存在" in text or "object not exist" in text


async def _dir_names(
    client: OpenListClient, directory: str, cache: dict[str, set[str]],
) -> set[str]:
    """列出一个远端目录里的文件名，按目录缓存。

    存在性检查必须区分「列目录失败」与「文件不存在」: 前者若被当成后者, 一次
    网络故障就会让生成侧以为目标是空的, 从而覆盖掉用户已有的 NFO。
    """
    if directory not in cache:
        files, _write_access = await client.list_directory(directory)
        cache[directory] = {f.name for f in files}
    return cache[directory]


async def carry_same_stem_nfo(
    client: OpenListClient,
    original_video_path: str,
    new_video_path: str,
    cache: dict[str, set[str]],
    dry_run: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """把与视频同名前缀的旧 `.nfo` 搬到新前缀。返回 (落点, 未跟随的原因)。

    与本地 `local_renamer.carry_same_stem_nfo` 同一套规则:

    - 只跟随**同前缀**的那一个（tvshow.nfo / season.nfo 按路径推不出来）;
    - 目标已存在时放弃 —— 宁可留下可见的孤儿, 也不静默改写别人的元数据;
    - dry_run 不移动, 只算出「那一刻那里会有文件」给调用方列清单。
    """
    src = episode_nfo_path(original_video_path, posixpath)
    dst = episode_nfo_path(new_video_path, posixpath)
    if src == dst:
        return None, None

    src_dir, src_name = posixpath.split(src)
    dst_dir, dst_name = posixpath.split(dst)

    try:
        src_names = await _dir_names(client, src_dir, cache)
    except Exception as exc:  # noqa: BLE001 —— 跟随失败只记原因, 不阻断重命名
        if dry_run and _looks_like_missing(exc):
            return None, None
        return None, f"同名 NFO 跟随移动失败: {exc}"
    if src_name not in src_names:
        return None, None

    try:
        dst_names = await _dir_names(client, dst_dir, cache)
    except Exception as exc:  # noqa: BLE001
        if dry_run and _looks_like_missing(exc):
            dst_names = set()
        else:
            return None, f"同名 NFO 跟随移动失败: {exc}"

    if dst_name in dst_names:
        return None, CARRIED_NFO_TARGET_EXISTS_REASON
    # 跨目录 move 也会撞上**旧文件名**已存在的情况; 只查 dst_name 时, 驱动若
    # 对同名 move 覆盖, 就会悄悄替掉目标目录里的一份用户元数据。拒绝是安全方向。
    if src_dir != dst_dir and src_name != dst_name and src_name in dst_names:
        return None, "同名 NFO 跟随移动失败: 目标目录已有同名文件"

    if dry_run:
        return dst, None

    try:
        if src_dir == dst_dir:
            await client.rename(src, dst_name)
        else:
            await client.move(src_dir, dst_dir, [src_name])
            if src_name != dst_name:
                await client.rename(posixpath.join(dst_dir, src_name), dst_name)
    except Exception as exc:  # noqa: BLE001
        return None, f"同名 NFO 跟随移动失败: {exc}"

    # 让同一次操作里后续的写入规划看见真实状态: 源目录里少了一个, 目标目录里
    # 多了一个。不更新的话, 下一步会把搬过来的文件当成「不存在」而生成新内容。
    cache.setdefault(src_dir, set()).discard(src_name)
    cache.setdefault(dst_dir, set()).add(dst_name)
    return dst, None


async def write_remote_nfo_files(
    client: OpenListClient,
    decisions: list[NfoDecision],
    overwrite: bool,
    cache: dict[str, set[str]],
) -> tuple[list[str], list[tuple[str, str]]]:
    """把决策写到远端。返回 (写入的路径, [(跳过的路径, 原因)])。"""
    written: list[str] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()

    for decision in decisions:
        if decision.content is None:
            skipped.append((decision.path, decision.reason or "无内容"))
            continue
        if decision.path in seen:
            continue
        seen.add(decision.path)

        directory, name = posixpath.split(decision.path)
        try:
            names = await _dir_names(client, directory, cache)
        except Exception as exc:  # noqa: BLE001 —— 写 NFO 失败不能让重命名崩掉
            skipped.append((decision.path, f"写入失败: {exc}"))
            continue

        if name in names and not overwrite:
            skipped.append((decision.path, "已存在"))
            continue

        try:
            await client.put_file(decision.path, decision.content.encode("utf-8"))
            written.append(decision.path)
            cache.setdefault(directory, set()).add(name)
        except Exception as exc:  # noqa: BLE001
            skipped.append((decision.path, f"写入失败: {exc}"))

    return written, dedupe_skipped_pairs(skipped)


def _episode_decision(
    plan: RenamePlan,
    nfo_matches: dict[str, EpisodeMatch],
    options: NfoOptions,
) -> Optional[NfoDecision]:
    """该文件的每集 NFO 决策；字幕与未启用时返回 None。"""
    if not options.enabled or _is_subtitle(plan):
        return None
    decisions = build_nfo_decisions(
        [entry_from_plan(plan, nfo_matches)], options, path_mod=posixpath,
    )
    return next((d for d in decisions if d.kind == "episode"), None)


def _retarget_episode_path(
    decision: NfoDecision, plan: RenamePlan, result: RenameResult,
) -> None:
    """把每集落点改到**真实落点**上（移动后名字可能还停在原名）。"""
    if result.new_path != plan.new_path:
        decision.path = episode_nfo_path(result.new_path, posixpath)


async def episode_nfo_for_plan(
    client: OpenListClient,
    plan: RenamePlan,
    result: RenameResult,
    nfo_matches: dict[str, EpisodeMatch],
    options: NfoOptions,
) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """单文件执行后的 NFO 副作用。返回 (written, carried, skipped)。

    顺序与本地 `execute_one` 一致: **先跟随旧 NFO, 再生成新 NFO**。这样在
    「生成开 + 覆盖关」时, 先搬过去的旧文件占住新位置, 生成报「已存在」,
    用户原有的内容得以保留。
    """
    written: list[str] = []
    carried: list[str] = []
    skipped: list[tuple[str, str]] = []

    # NFO 管线只处理视频。字幕的解析结果与视频一字不差, 不提前挡住的话
    # 它旁边的 `.chs.nfo` 与旧同前缀 NFO 跟随都会发生 —— 纯库污染。
    if _is_subtitle(plan):
        return written, carried, skipped

    decision = _episode_decision(plan, nfo_matches, options)
    if decision is not None:
        _retarget_episode_path(decision, plan, result)

    landed = landed_path_of(result) is not None
    if not landed:
        if decision is not None:
            skipped.append((decision.path, NOT_RENAMED_NFO_REASON))
        return written, carried, skipped

    cache: dict[str, set[str]] = {}
    if result.status in _OPENLIST_CARRY_STATUSES:
        carried_path, carry_reason = await carry_same_stem_nfo(
            client, plan.original_path, result.new_path, cache,
        )
        if carried_path is not None:
            carried.append(carried_path)
        elif carry_reason is not None:
            skipped.append(
                (episode_nfo_path(result.new_path, posixpath), carry_reason),
            )

    if decision is None:
        return written, carried, skipped

    result.nfo_path = decision.path
    written, write_skipped = await write_remote_nfo_files(
        client, [decision], options.overwrite, cache,
    )
    skipped.extend(write_skipped)
    return written, carried, dedupe_skipped_pairs(skipped)


async def plan_openlist_nfo(
    client: OpenListClient,
    plans: list[RenamePlan],
    results: list[RenameResult],
    nfo_matches: dict[str, EpisodeMatch],
    options: NfoOptions,
) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """干跑的 NFO 计划。只做只读列举, 绝不写盘。

    **跟随旧 NFO 与是否生成 NFO 无关**（本地 batch_rename 也是这个契约）,
    所以关闭生成时这里仍要规划 carry; 只是没有「将写入」的决策。
    """
    if not plans:
        return [], [], []

    # 结果行的 id 是 plan.id（execute_openlist_batch / execute_openlist_one 都这样
    # 构造），不是 file_id —— 两套成功路径都靠这个键把 plan 与真实结果对上。
    result_by_plan_id = {r.id: r for r in results if r.id}

    entries = [
        entry_from_plan(plan, nfo_matches)
        for plan in plans
        if not _is_subtitle(plan)
    ]
    if not entries:
        return [], [], []

    skipped: list[tuple[str, str]] = []
    kept: list[NfoDecision] = []
    if options.enabled:
        decisions = build_nfo_decisions(entries, options, path_mod=posixpath)

        dead_file_ids: set[str] = set()
        landed_paths: list[str] = []
        for plan in plans:
            if _is_subtitle(plan):
                continue
            result = result_by_plan_id.get(plan.id)
            if result is None or landed_path_of(result) is None:
                dead_file_ids.add(plan.file_id)
            else:
                landed_paths.append(result.new_path)

        kept, dropped = filter_landed_decisions(
            decisions, dead_file_ids, landed_paths, path_mod=posixpath,
        )

        for decision in dropped:
            if decision.kind == "episode":
                skipped.append((decision.path, NOT_RENAMED_NFO_REASON))
            else:
                skipped.append((decision.path, DROPPED_GROUP_NFO_REASON))

        # 每集决策改指向真实落点（干跑里 new_path 与 plan.new_path 通常相等,
        # 但统一走这条规则, 真执行与干跑的报告口径才不会分叉）。
        for decision in kept:
            if decision.kind != "episode":
                continue
            plan = next((p for p in plans if p.file_id == decision.file_id), None)
            result = result_by_plan_id.get(plan.id) if plan else None
            if plan is not None and result is not None:
                _retarget_episode_path(decision, plan, result)

    cache: dict[str, set[str]] = {}
    carried: list[str] = []
    planned_carried: set[str] = set()
    for plan in plans:
        if _is_subtitle(plan):
            continue
        result = result_by_plan_id.get(plan.id)
        if result is None or result.status not in _OPENLIST_CARRY_STATUSES:
            continue
        carried_path, carry_reason = await carry_same_stem_nfo(
            client, plan.original_path, result.new_path, cache, dry_run=True,
        )
        if carried_path is not None:
            carried.append(carried_path)
            planned_carried.add(carried_path)
        elif carry_reason is not None:
            skipped.append(
                (episode_nfo_path(result.new_path, posixpath), carry_reason),
            )

    planned_written: list[str] = []
    for decision in kept:
        if decision.content is None:
            skipped.append((decision.path, decision.reason or "无内容"))
            continue

        directory, name = posixpath.split(decision.path)
        try:
            names = await _dir_names(client, directory, cache)
        except Exception as exc:  # noqa: BLE001
            if _looks_like_missing(exc):
                names = set()
            else:
                skipped.append((decision.path, f"写入失败: {exc}"))
                continue

        if (name in names or decision.path in planned_carried) and not options.overwrite:
            skipped.append((decision.path, "已存在"))
            continue
        if decision.path not in planned_written:
            planned_written.append(decision.path)

    return planned_written, carried, dedupe_skipped_pairs(skipped)


async def finalize_openlist_nfo(
    client: OpenListClient,
    plans: list[RenamePlan],
    landed_paths: list[str],
    nfo_matches: dict[str, EpisodeMatch],
    options: NfoOptions,
) -> tuple[list[str], list[tuple[str, str]]]:
    """批次收尾: 只写剧集级 / 季级 NFO。返回 (written, skipped)。"""
    if not options.enabled or not plans:
        return [], []

    entries = [
        entry_from_plan(plan, nfo_matches)
        for plan in plans
        if not _is_subtitle(plan)
    ]
    if not entries:
        return [], []

    group_decisions = [
        d for d in build_nfo_decisions(entries, options, path_mod=posixpath)
        if d.kind != "episode"
    ]
    kept, dropped = filter_landed_decisions(
        group_decisions, set(), landed_paths, path_mod=posixpath,
    )

    skipped: list[tuple[str, str]] = [
        (decision.path, DROPPED_GROUP_NFO_REASON) for decision in dropped
    ]
    written, write_skipped = await write_remote_nfo_files(
        client, kept, options.overwrite, {},
    )
    skipped.extend(write_skipped)
    return written, dedupe_skipped_pairs(skipped)

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Optional

from ..models.file import (
    FileInfo, RenamePlan, RenameResult, BatchRenameResult, OverrideInfo,
)
from ..config import settings
from .parser import apply_override, parse_filename
from .template import PadConfig, apply_template, apply_folder_template
from .utils import generate_id
from .openlist_client import OpenListClient, RenameObject


def build_openlist_rename_plan(
    file: FileInfo,
    template: str,
    folder_template: str = "",
    create_season_folder: bool = False,
    override: Optional[OverrideInfo] = None,
    pad: PadConfig | None = None,
) -> RenamePlan:
    # 注意: 这里此前漏了 override.title —— 于是 OpenList 源下手动填的标题
    # 永远进不了文件名。apply_override 一并修好。
    parsed = apply_override(parse_filename(file.filename, file.parent_dir), override)

    new_filename = apply_template(template, parsed, pad=pad)
    new_dir = file.parent_dir

    if create_season_folder and folder_template:
        folder_name = apply_folder_template(folder_template, parsed, pad=pad)
        if folder_name:
            new_dir = str(PurePosixPath(file.parent_dir) / folder_name)

    new_path = str(PurePosixPath(new_dir) / new_filename)

    return RenamePlan(
        id=generate_id(),
        file_id=file.id,
        original_path=file.path,
        new_path=new_path,
        original_filename=file.filename,
        new_filename=new_filename,
        original_dir=file.parent_dir,
        new_dir=new_dir,
        parsed=parsed,
        file_info=file,
    )


async def _ensure_dir(client: OpenListClient, dir_path: str, _cache: dict[str, bool]) -> None:
    if dir_path in _cache:
        return
    parent = str(PurePosixPath(dir_path).parent)
    folder = PurePosixPath(dir_path).name
    try:
        await client.mkdir(parent, folder)
    except Exception:
        pass
    _cache[dir_path] = True


async def execute_openlist_batch(
    client: OpenListClient,
    plans: list[RenamePlan],
    dry_run: bool = False,
) -> BatchRenameResult:
    results: list[RenameResult] = []
    dir_cache: dict[str, bool] = {}

    same_dir_plans = [p for p in plans if p.original_dir == p.new_dir]
    move_plans = [p for p in plans if p.original_dir != p.new_dir]

    executed = skipped = failed = 0

    if same_dir_plans:
        dir_groups: dict[str, list[RenamePlan]] = {}
        for p in same_dir_plans:
            dir_groups.setdefault(p.original_dir, []).append(p)

        for dir_path, group in dir_groups.items():
            same_in_dir = [p for p in group if p.original_filename == p.new_filename]
            need_rename = [p for p in group if p.original_filename != p.new_filename]

            for p in same_in_dir:
                skipped += 1
                results.append(RenameResult(
                    id=p.id,
                    original_path=p.original_path,
                    new_path=p.new_path,
                    original_filename=p.original_filename,
                    new_filename=p.new_filename,
                    success=True,
                    status="skipped_same",
                ))

            if not need_rename:
                continue

            if dry_run:
                for p in need_rename:
                    executed += 1
                    results.append(RenameResult(
                        id=p.id,
                        original_path=p.original_path,
                        new_path=p.new_path,
                        original_filename=p.original_filename,
                        new_filename=p.new_filename,
                        success=True,
                        status="dry_run",
                    ))
                continue

            rename_objs = [
                RenameObject(src_name=p.original_filename, new_name=p.new_filename)
                for p in need_rename
            ]
            try:
                await client.batch_rename(dir_path, rename_objs)
                for p in need_rename:
                    executed += 1
                    results.append(RenameResult(
                        id=p.id,
                        original_path=p.original_path,
                        new_path=p.new_path,
                        original_filename=p.original_filename,
                        new_filename=p.new_filename,
                        success=True,
                        status="renamed",
                    ))
            except Exception as e:
                try:
                    for p in need_rename:
                        await client.rename(p.original_path, p.new_filename)
                        executed += 1
                        results.append(RenameResult(
                            id=p.id,
                            original_path=p.original_path,
                            new_path=p.new_path,
                            original_filename=p.original_filename,
                            new_filename=p.new_filename,
                            success=True,
                            status="renamed_fallback",
                        ))
                except Exception as e2:
                    for p in need_rename:
                        failed += 1
                        results.append(RenameResult(
                            id=p.id,
                            original_path=p.original_path,
                            new_path=p.new_path,
                            original_filename=p.original_filename,
                            new_filename=p.new_filename,
                            success=False,
                            error=f"{e} | {e2}",
                            status="failed",
                        ))

    if move_plans:
        move_groups: dict[tuple[str, str], list[RenamePlan]] = {}
        for p in move_plans:
            key = (p.original_dir, p.new_dir)
            move_groups.setdefault(key, []).append(p)

        for (src_dir, dst_dir), group in move_groups.items():
            if dry_run:
                for p in group:
                    executed += 1
                    results.append(RenameResult(
                        id=p.id,
                        original_path=p.original_path,
                        new_path=p.new_path,
                        original_filename=p.original_filename,
                        new_filename=p.new_filename,
                        success=True,
                        status="dry_run",
                    ))
                continue

            try:
                if src_dir != dst_dir:
                    await _ensure_dir(client, dst_dir, dir_cache)

                names_to_move = [p.original_filename for p in group]
                await client.move(src_dir, dst_dir, names_to_move)

                rename_objs = [
                    RenameObject(src_name=p.original_filename, new_name=p.new_filename)
                    for p in group
                    if p.original_filename != p.new_filename
                ]
                if rename_objs:
                    try:
                        await client.batch_rename(dst_dir, rename_objs)
                    except Exception:
                        for p in group:
                            if p.original_filename != p.new_filename:
                                try:
                                    await client.rename(p.new_path, p.new_filename)
                                except Exception:
                                    pass

                for p in group:
                    executed += 1
                    results.append(RenameResult(
                        id=p.id,
                        original_path=p.original_path,
                        new_path=p.new_path,
                        original_filename=p.original_filename,
                        new_filename=p.new_filename,
                        success=True,
                        status="renamed_moved",
                    ))
            except Exception as e:
                for p in group:
                    try:
                        await client.rename(p.original_path, p.new_filename)
                        executed += 1
                        results.append(RenameResult(
                            id=p.id,
                            original_path=p.original_path,
                            new_path=p.new_path,
                            original_filename=p.original_filename,
                            new_filename=p.new_filename,
                            success=True,
                            status="renamed_fallback",
                        ))
                    except Exception as e2:
                        failed += 1
                        results.append(RenameResult(
                            id=p.id,
                            original_path=p.original_path,
                            new_path=p.new_path,
                            original_filename=p.original_filename,
                            new_filename=p.new_filename,
                            success=False,
                            error=f"{e} | {e2}",
                            status="failed",
                        ))

    return BatchRenameResult(
        success=failed == 0,
        source="openlist",
        executed=executed,
        skipped=skipped,
        failed=failed,
        total=len(plans),
        results=results,
    )


async def execute_openlist_one(
    client: OpenListClient,
    plan: RenamePlan,
) -> RenameResult:
    """执行**一个** OpenList plan。

    与 execute_openlist_batch 的差别不只是循环: 批量版用 client.batch_rename 把
    同目录的多个改名合并成一次 API 调用, 单文件版没有可合并的对象, 改用
    client.rename / client.move。故两个函数的调用序列不同 —— 这是单文件化的
    直接代价, 由前端并发数与客户端限流器共同约束请求量。

    **没有 dry_run 形参**, 这是刻意的: 干跑在本设计里是**批次级**的（spec R9,
    与 local_renamer.execute_one 同源）—— 单文件路径在生产里只被 /rename/execute
    以「真执行」调用, 一个没有调用者的分支就是一处没有判据的分支。
    """
    result = RenameResult(
        id=plan.id,
        original_path=plan.original_path,
        new_path=plan.new_path,
        original_filename=plan.original_filename,
        new_filename=plan.new_filename,
    )

    same_dir = plan.original_dir == plan.new_dir
    same_name = plan.original_filename == plan.new_filename

    if same_dir and same_name:
        result.success = True
        result.status = "skipped_same"
        return result

    dir_cache: dict[str, bool] = {}
    # move 成功之后文件的**真实位置**。它是下面那段补偿的源路径: 移动已经发生,
    # original_path 那个位置**已经空了**。
    moved_to: Optional[str] = None
    try:
        if not same_dir:
            await _ensure_dir(client, plan.new_dir, dir_cache)
            await client.move(plan.original_dir, plan.new_dir, [plan.original_filename])
            moved_to = str(PurePosixPath(plan.new_dir) / plan.original_filename)
            if not same_name:
                await client.rename(moved_to, plan.new_filename)
            result.success = True
            result.status = "renamed_moved"
        else:
            await client.rename(plan.original_path, plan.new_filename)
            result.success = True
            result.status = "renamed"
    except Exception as exc:
        if moved_to is None:
            # 移动本身就没做成（或压根没有移动这一步）—— 文件还在原处, 如实报失败。
            result.success = False
            result.error = str(exc)
            result.status = "failed"
        else:
            # **移动已成功、改名失败**: 文件此刻在 new_dir/original_filename。
            # 批量路径在这里会退回 `client.rename(p.original_path, ...)` —— 那是
            # **移动前**的位置, 在本情形下已经空了, 注定失败; 单文件路径用真实位置
            # 报告, 而不是报 failed。
            #
            # 为什么不能报 failed: landed_path_of 对 failed 返回 None, 于是这个
            # **已经离开原处**的文件从落地表里消失 —— OpenList 的 NFO 与批次收尾
            # 一旦启用, 它就会被当成「没落地」（spec §9.4 的判据全部建立在真实落点
            # 之上）。宁可少一个状态名, 不能报一个假位置。
            #
            # new_path 改成真实落点、new_filename 改回原名: 用户看到的是「它现在在
            # 这里」, 而不是一个它并不在的目标路径。
            result.new_path = moved_to
            result.new_filename = plan.original_filename
            result.success = False
            result.error = f"{exc} | 文件已移动到 {moved_to}, 但未能改名为 {plan.new_filename}"
            result.status = "moved_not_renamed"

    return result

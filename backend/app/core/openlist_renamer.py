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

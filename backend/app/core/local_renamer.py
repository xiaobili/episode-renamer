from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Optional

from ..models.file import (
    FileInfo, RenamePlan, RenameResult, BatchRenameResult, OverrideInfo,
)
from ..config import settings
from .parser import parse_filename, _SEASON_DIR_PATTERNS
from .template import apply_template, apply_folder_template, generate_full_path
from .utils import generate_id


def _parent_is_season_dir(parent_dir: str, season_val: Optional[int]) -> bool:
    if not parent_dir:
        return False
    last_part = parent_dir.rstrip('/').rsplit('/', 1)[-1]
    if not any(p.match(last_part) for p in _SEASON_DIR_PATTERNS):
        return False
    if season_val is not None:
        import re as _re
        m = _re.search(r'(\d{1,2})', last_part)
        if m and int(m.group(1)) == season_val:
            return True
    return bool(re.search(r'(\d{1,2})', last_part))


def build_rename_plan(
    file: FileInfo,
    template: str,
    folder_template: str = "",
    create_season_folder: bool = False,
    override: Optional[OverrideInfo] = None,
) -> RenamePlan:
    parsed = parse_filename(file.filename, file.parent_dir)

    if override:
        if override.show_name is not None:
            parsed.show_name = override.show_name
        if override.season is not None:
            parsed.season = override.season
        if override.episode is not None:
            parsed.episode = override.episode
        if override.title is not None:
            parsed.title = override.title

    new_filename = apply_template(template, parsed)
    new_path = str(Path(file.parent_dir) / new_filename)
    new_dir = file.parent_dir

    skip_season_folder = _parent_is_season_dir(file.parent_dir, parsed.season)

    if create_season_folder and folder_template and not skip_season_folder:
        folder_name = apply_folder_template(folder_template, parsed)
        if folder_name:
            new_dir = str(Path(file.parent_dir) / folder_name)
            new_path = str(Path(new_dir) / new_filename)

    plan = RenamePlan(
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

    return plan


def check_conflict(plan: RenamePlan, all_plans: list[RenamePlan]) -> list[str]:
    conflicts: list[str] = []

    if plan.original_path == plan.new_path:
        conflicts.append("same_name")
        return conflicts

    target = Path(plan.new_path)
    if target.exists():
        conflicts.append("filename_exists")

    for other in all_plans:
        if other.id == plan.id:
            continue
        if other.new_path == plan.new_path:
            conflicts.append("duplicate_in_batch")
            break

    return conflicts


def execute_rename_plan(
    plan: RenamePlan,
    dry_run: bool = False,
    conflict_strategy: str = "skip",
) -> RenameResult:
    result = RenameResult(
        id=plan.id,
        original_path=plan.original_path,
        new_path=plan.new_path,
        original_filename=plan.original_filename,
        new_filename=plan.new_filename,
    )

    src = Path(plan.original_path)
    dst = Path(plan.new_path)

    if not src.exists():
        result.error = f"源文件不存在: {plan.original_path}"
        result.status = "failed"
        return result

    if src.resolve() == dst.resolve():
        result.success = True
        result.status = "skipped_same"
        return result

    if dst.exists():
        if conflict_strategy == "abort":
            result.error = f"目标文件已存在: {plan.new_path}"
            result.status = "conflict"
            return result
        elif conflict_strategy == "skip":
            result.error = f"目标文件已存在，跳过: {plan.new_path}"
            result.status = "skipped_conflict"
            return result
        elif conflict_strategy == "rename_dup":
            counter = 1
            stem = dst.stem
            while dst.exists():
                dst = dst.parent / f"{stem}_{counter}{dst.suffix}"
                counter += 1
            result.new_path = str(dst)
        elif conflict_strategy == "overwrite":
            pass

    if dry_run:
        result.success = True
        result.status = "dry_run"
        return result

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.rename(str(src), str(dst))
        result.success = True
        result.status = "renamed"
    except OSError as e:
        if e.errno == 18:
            try:
                shutil.move(str(src), str(dst))
                result.success = True
                result.status = "moved"
            except Exception as e2:
                result.error = f"跨磁盘移动失败: {e2}"
                result.status = "failed"
        else:
            result.error = f"重命名失败: {e}"
            result.status = "failed"

    return result


def batch_rename(
    files: list[FileInfo],
    template: str,
    folder_template: str = "",
    create_season_folder: bool = False,
    overrides: dict[str, dict] | None = None,
    dry_run: bool = False,
    conflict_strategy: str = "skip",
) -> BatchRenameResult:
    plans: list[RenamePlan] = []
    overrides = overrides or {}

    for f in files:
        ov = overrides.get(f.id)
        override = OverrideInfo(**ov) if ov else None
        plan = build_rename_plan(f, template, folder_template, create_season_folder, override)
        conflicts = check_conflict(plan, [])
        plan.conflicts = conflicts
        plans.append(plan)

    results: list[RenameResult] = []
    executed = skipped = failed = 0

    for plan in plans:
        if plan.conflicts and conflict_strategy == "abort":
            result = RenameResult(
                id=plan.id,
                original_path=plan.original_path,
                new_path=plan.new_path,
                original_filename=plan.original_filename,
                new_filename=plan.new_filename,
                success=False,
                error=f"冲突: {', '.join(plan.conflicts)}",
                status="conflict",
            )
            results.append(result)
            failed += 1
            continue

        result = execute_rename_plan(plan, dry_run=dry_run, conflict_strategy=conflict_strategy)
        results.append(result)

        if result.success and result.status not in ("skipped_conflict", "skipped_same"):
            executed += 1
        elif result.status in ("skipped_conflict", "skipped_same", "conflict"):
            skipped += 1
        else:
            failed += 1

    return BatchRenameResult(
        success=failed == 0,
        source="local",
        executed=executed,
        skipped=skipped,
        failed=failed,
        total=len(plans),
        results=results,
    )

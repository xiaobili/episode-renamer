from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Optional

from ..models.file import (
    FileInfo, RenamePlan, RenameResult, BatchRenameResult, OverrideInfo,
)
from ..models.nfo import NfoDecision, NfoEntry, NfoOptions
from ..config import settings
from .nfo_writer import build_nfo_decisions, write_nfo_files
from .parser import apply_override, parse_filename, _SEASON_DIR_PATTERNS
from .template import PadConfig, apply_template, apply_folder_template
from .tmdb_resolver import EpisodeMatch
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
    pad: PadConfig | None = None,
) -> RenamePlan:
    parsed = apply_override(parse_filename(file.filename, file.parent_dir), override)

    new_filename = apply_template(template, parsed, pad=pad)
    new_path = str(Path(file.parent_dir) / new_filename)
    new_dir = file.parent_dir

    skip_season_folder = _parent_is_season_dir(file.parent_dir, parsed.season)

    if create_season_folder and folder_template and not skip_season_folder:
        folder_name = apply_folder_template(folder_template, parsed, pad=pad)
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
    pad: PadConfig | None = None,
    nfo_options: NfoOptions | None = None,
    nfo_matches: Optional[dict[str, EpisodeMatch]] = None,
) -> BatchRenameResult:
    plans: list[RenamePlan] = []
    overrides = overrides or {}
    nfo_matches = nfo_matches or {}

    for f in files:
        ov = overrides.get(f.id)
        override = OverrideInfo(**ov) if ov else None
        plan = build_rename_plan(
            f, template, folder_template, create_season_folder, override, pad=pad
        )
        conflicts = check_conflict(plan, [])
        plan.conflicts = conflicts
        plans.append(plan)

    results: list[RenameResult] = []
    executed = skipped = failed = 0

    # NFO 条目用**重命名之后**的路径 —— 每集 NFO 靠与视频同名配对,
    # 用原路径推导会让 NFO 与视频对不上。
    nfo_decisions: list[NfoDecision] = []
    nfo_path_by_file: dict[str, str] = {}
    if nfo_options and nfo_options.enabled:
        nfo_decisions = build_nfo_decisions(
            [
                NfoEntry(
                    file_id=plan.file_id,
                    new_path=plan.new_path,
                    show_name=plan.parsed.show_name if plan.parsed else "",
                    season=plan.parsed.season if plan.parsed else None,
                    episode=plan.parsed.episode if plan.parsed else None,
                    # nfo_matches 里没有对应项时 .get() 返回 None,
                    # getattr(None, "show", None) 也是 None —— 三者同时为 None,
                    # NfoEntry.has_metadata 即为 False, 于是不写残缺 NFO。
                    show=getattr(nfo_matches.get(plan.file_id), "show", None),
                    season_data=getattr(nfo_matches.get(plan.file_id), "season", None),
                    episode_data=getattr(nfo_matches.get(plan.file_id), "episode", None),
                )
                for plan in plans
            ],
            nfo_options,
        )
        for decision in nfo_decisions:
            if decision.kind == "episode":
                nfo_path_by_file[decision.file_id] = decision.path

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
        result.nfo_path = nfo_path_by_file.get(plan.file_id)
        results.append(result)

        if result.success and result.status not in ("skipped_conflict", "skipped_same"):
            executed += 1
        elif result.status in ("skipped_conflict", "skipped_same", "conflict"):
            skipped += 1
        else:
            failed += 1

    nfo_written: list[str] = []
    nfo_skipped: list[dict] = []

    if nfo_options and nfo_options.enabled and nfo_decisions:
        if dry_run:
            # 干跑绝不落盘, 但仍要给出完整清单。exists() 是只读检查, 允许。
            for decision in nfo_decisions:
                if decision.content is None:
                    nfo_skipped.append({"path": decision.path, "reason": decision.reason or "无内容"})
                elif Path(decision.path).exists() and not nfo_options.overwrite:
                    nfo_skipped.append({"path": decision.path, "reason": "已存在"})
                elif decision.path not in nfo_written:
                    nfo_written.append(decision.path)
        else:
            written_paths, skipped_pairs = write_nfo_files(nfo_decisions, overwrite=nfo_options.overwrite)
            nfo_written = written_paths
            nfo_skipped = [{"path": p, "reason": r} for p, r in skipped_pairs]

    return BatchRenameResult(
        success=failed == 0,
        source="local",
        executed=executed,
        skipped=skipped,
        failed=failed,
        total=len(plans),
        results=results,
        nfo_written=nfo_written,
        nfo_skipped=nfo_skipped,
    )

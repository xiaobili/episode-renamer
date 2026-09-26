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
from .nfo_writer import (
    build_nfo_decisions, dedupe_skipped_by_path, episode_nfo_path, write_nfo_files,
)
from .parser import apply_override, parse_filename, _SEASON_DIR_PATTERNS
from .template import PadConfig, apply_template, apply_folder_template
from .tmdb_resolver import EpisodeMatch
from .utils import generate_id


def _is_subtitle_file(file_info: Optional[FileInfo]) -> bool:
    """该 plan 是不是字幕 —— NFO 管线只处理视频。

    判据用**扫描器已经判定好的** `FileInfo.is_subtitle`（local_scanner /
    openlist_scanner 与 parser 都会设它），而不是在 NFO 层再嗅一次扩展名:
    那是同一件事的第二次判断, 会与 settings.subtitle_extensions 漂移。

    为什么必须滤掉字幕: 解析器对字幕与视频给出**完全相同**的结果（实测
    Show.S01E01.chs.srt 与 Show.S01E01.1080p.WEB-DL.mkv 都是
    show='Show' s=1 e=1 conf=0.97）, 而 episode_nfo_path 只换扩展名 ——
    于是每个字幕旁会多写一个无意义的 Show.S01E01.chs.nfo（媒体服务器靠与视频
    同名配对, 这种文件对它们毫无意义, 是纯库污染）。更糟的是决策按
    (show_name, season, episode, new_path) 排序, '….chs.srt' < '….mkv',
    字幕会抢到 group[0] —— 剧集级/季级决策就挂到**字幕行**上, 预览里
    tvshow.nfo 的落点会显示在字幕那一行旁边。

    file_info 缺失时按视频处理: 与引入这道过滤之前的行为一致, 宁可多算不可少算
    （少算会让一个本该有 NFO 的视频静默地没有）。
    """
    return bool(file_info is not None and file_info.is_subtitle)


# 「这一行没有落到落点上」的三种结局: 重命名一步都没做（或源文件根本不在）。
# 判据不能写成 `result.new_path != plan.new_path` —— 那只覆盖 rename_dup 那一种,
# 而 skip / abort 策略下 new_path 与 plan.new_path **相等**（相等恰恰是因为没动）。
_NO_LANDING_STATUSES = frozenset({"skipped_conflict", "conflict", "failed"})

# 没改名的行在 nfo_skipped 里的原因串。
_NOT_RENAMED_NFO_REASON = "该文件未改名, 不写 NFO"


def _keep_decision(
    decision: NfoDecision, dead_file_ids: set[str], landed_paths: list[str]
) -> bool:
    """这条决策还该不该写 —— 没落地的行一条都不写。

    每集决策钉着**某一个文件**, 那行没落地就整条丢掉: 它的落点是按 plan.new_path
    算的, 而那个名字此刻属于**另一个视频**（skip 策略下占住目标名的那一个）。
    写下去就是「给 A 写的 NFO 落在 B 的旁边」—— spec 明令禁止的静默错元数据,
    也正是本计划要求写盘阶段避开的「改名失败但 NFO 已写」半状态。
    不改成指向 `episode_nfo_path(plan.original_path)`: 无法保证原路径就是它的真实
    位置（failed 时源文件可能压根不在, conflict 时它可能本该被移进还不存在的季
    目录）。拒绝是安全方向 —— 少写一个 NFO 是可见的（nfo_path 为 None、清单里报
    「该文件未改名」）, 写错一个才是不可见的。

    组级决策（tvshow / season）属于**整组**, 落点由该组全部 new_path 推出, 所以
    判据是该目录（含子树）下有没有真的落地过一个视频, 而不是组代表那一行有没有
    落地 —— 用代表判会让「E01 冲突被跳过、E02 照常改名」这种常见批次丢掉整部剧
    的 tvshow.nfo。整批一条都没落地时（如 abort）组级落点同样是凭空推出来的,
    一并不写。
    """
    if decision.kind == "episode":
        return decision.file_id not in dead_file_ids
    directory = os.path.dirname(decision.path)
    if not directory:
        return False
    prefix = directory.rstrip(os.sep) + os.sep
    return any(p == directory or p.startswith(prefix) for p in landed_paths)


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
                # 字幕不进 NFO（理由见 _is_subtitle_file）。这个过滤只作用于 NFO 的
                # 构造 —— 字幕照常参与下面的重命名。
                for plan in plans
                if not _is_subtitle_file(plan.file_info)
            ],
            nfo_options,
        )
        for decision in nfo_decisions:
            if decision.kind == "episode":
                nfo_path_by_file[decision.file_id] = decision.path

    # 没落地的行不进这两处, 落到别处的行进 landed_paths（组级决策的判据）:
    # 只有真正落地的路径才能证明「那个目录里确实该有一份剧集级 NFO」。
    landed_paths: list[str] = []
    dead_file_ids: set[str] = set()
    # 没落地那一行的每集落点。它不写, 但必须**报出来**（nfo_skipped）——
    # 静默地少写一个 NFO 与静默地写错一个一样不可见, 而后者正是本次修复的对象。
    dead_episode_paths: list[str] = []

    for plan in plans:
        # 冲突行走 abort 时 result 是合成的, 但**不能再 continue**: 下面那段
        # 「没落地 → 不写 NFO」必须对它一样生效, 否则用户选了最保守的策略、看到
        # nfo_path 为 None, 转头却发现自己那一集的 NFO 已经落在别人视频旁边了。
        aborted = bool(plan.conflicts and conflict_strategy == "abort")
        if aborted:
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
        else:
            result = execute_rename_plan(plan, dry_run=dry_run, conflict_strategy=conflict_strategy)
            if (
                nfo_options and nfo_options.enabled
                # 字幕不进 NFO, 所以也不该在这里被重新挂上落点: 字幕的目标名被占用时
                # （rename_dup 的 X_1 那条路径）它同样满足 new_path != plan.new_path,
                # 不过滤就会把自己的 X_1.nfo 写进 nfo_path_by_file —— 预览/结果里
                # 字幕行于是报出一个根本不会写的 NFO 落点。
                and not _is_subtitle_file(plan.file_info)
                and result.new_path != plan.new_path
            ):
                # rename_dup（「自动编号」）下 execute_rename_plan 把真实目标解析成了
                # X_1.mkv, 而每集决策是按 plan.new_path 算的 —— 不跟着改指向的话,
                # 改名后的视频拿不到与它同名的 X_1.nfo（Emby 靠同名配对）, 而 NFO 会
                # 落到 X.nfo: 那是**冲突那一集**的位置, 覆盖模式下还会把它改写掉。
                nfo_path_by_file[plan.file_id] = episode_nfo_path(result.new_path)

        if result.status in _NO_LANDING_STATUSES:
            dead_file_ids.add(plan.file_id)
            dead_path = nfo_path_by_file.pop(plan.file_id, None)
            if dead_path is not None:
                dead_episode_paths.append(dead_path)
        elif not _is_subtitle_file(plan.file_info):
            landed_paths.append(result.new_path)

        result.nfo_path = nfo_path_by_file.get(plan.file_id)
        results.append(result)

        if aborted:
            # abort 下的冲突行计入 failed（与改动前一致）—— 走下面的通用分支会按
            # status="conflict" 把它记成 skipped。
            failed += 1
        elif result.success and result.status not in ("skipped_conflict", "skipped_same"):
            executed += 1
        elif result.status in ("skipped_conflict", "skipped_same", "conflict"):
            skipped += 1
        else:
            failed += 1

    nfo_written: list[str] = []
    nfo_skipped: list[dict] = []

    # 没落地的行: 它们的每集决策一律不写（理由见 _keep_decision）。组级决策由
    # landed_paths 另行判定 —— 那是「整组」的落点, 不能因为组代表那一行没落地
    # 就把整部剧的 tvshow.nfo 丢掉。
    if nfo_decisions and dead_file_ids:
        nfo_decisions = [
            d for d in nfo_decisions
            if _keep_decision(d, dead_file_ids, landed_paths)
        ]

    # 不写要**报出来**: 留白等于静默, 而用户需要知道「这一行没改名, 所以 NFO 也
    # 没写」—— 否则那一行的 nfo_path 是 None、清单里也找不到它。
    nfo_skipped.extend(
        {"path": path, "reason": _NOT_RENAMED_NFO_REASON} for path in dead_episode_paths
    )

    # 真实目标被改过名的那几条（X.mkv → X_1.mkv）, 每集决策改指向改名后的落点。
    # NfoDecision 可变, 故原地改 —— 必须赶在下面写盘 / 干跑列清单之前。
    if nfo_decisions:
        for decision in nfo_decisions:
            moved_to = nfo_path_by_file.get(decision.file_id)
            if decision.kind == "episode" and moved_to is not None and moved_to != decision.path:
                decision.path = moved_to

    if nfo_options and nfo_options.enabled and nfo_decisions:
        if dry_run:
            # 干跑绝不落盘, 但仍要给出完整清单。exists() 是只读检查, 允许。
            planned_written: list[str] = []
            planned_skipped: list[tuple[str, str]] = []
            for decision in nfo_decisions:
                if decision.content is None:
                    planned_skipped.append((decision.path, decision.reason or "无内容"))
                elif Path(decision.path).exists() and not nfo_options.overwrite:
                    # "已存在" 是**前端 ResultDialog 的判据串**: 出现它才追加那行可行动
                    # 提示「如需覆盖既有 NFO，请勾选「覆盖已存在的 NFO」后重新执行」。
                    # 后端测试钉着这个字面值（tests/test_nfo_write.py:295 断言干跑分支
                    # 的 nfo_skipped 里有 reason == "已存在"）, 但**没有任何检查**钉住
                    # 前端消费者那一侧 —— 前端没有测试, 改字后后端照样绿, 那行提示
                    # 却会静默消失。改这里要同步前端。
                    # 另一半在 nfo_writer.write_nfo_files（真实写盘那条路径）。
                    planned_skipped.append((decision.path, "已存在"))
                elif decision.path not in planned_written:
                    planned_written.append(decision.path)
            nfo_written = planned_written
            # 与真实写盘共用同一个去重实现（多剧混放会为组内每个条目各发一条
            # 同路径的决策）—— 两处各写一遍必然漂移: 干跑报 6 个、真跑报 2 个。
            nfo_skipped.extend(
                {"path": p, "reason": r}
                for p, r in dedupe_skipped_by_path(planned_skipped)
            )
        else:
            written_paths, skipped_pairs = write_nfo_files(nfo_decisions, overwrite=nfo_options.overwrite)
            nfo_written = written_paths
            nfo_skipped.extend({"path": p, "reason": r} for p, r in skipped_pairs)

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

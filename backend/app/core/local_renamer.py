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
    build_nfo_decisions, dedupe_skipped_pairs, episode_nfo_path, write_nfo_files,
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

# 组级决策（tvshow / season）被丢弃时的原因串。它的落点由该组全部 new_path 推出,
# 一条都没落地时那就是凭空推出来的 —— 不写, 但要**报出来**（留白等于静默）。
_DROPPED_GROUP_NFO_REASON = "该剧（季）下没有文件真正改名落地, 不写剧集级/季级 NFO"

# 同前缀 NFO 跟随移动时的原因串（spec §9.1.1 的失败处理之一）。
# 不写成同一类里的例外: 目标是**别人已存在的元数据**, 宁可留下可见的孤儿,
# 也不静默改写它。
# 串里明写「覆盖开关不影响跟随」: 同一个路径上生成侧也会报一条「已存在」, 那条
# 带着「去勾覆盖开关」的可行动提示 —— 用户会把两条都读成同一件事, 于是去勾那个
# **对孤儿无效**的开关（跟随无条件重查 dst.exists(), 覆盖开关管不着它）, 孤儿
# 就这么永久留下。这条串自己说清拖住它的是文件、不是开关。
_CARRIED_NFO_TARGET_EXISTS_REASON = "旧前缀 NFO 未跟随: 新名字处已有文件, 覆盖开关不影响跟随"

# 「视频真的动了」的状态集合 —— 只有这些行的同前缀 NFO 才跟随移动。
# dry_run 也算: 那一行**将会**真的动, 干跑要为它列出计划。
# skipped_same 不算: 原路径与目标路径是同一个文件, NFO 的名字本来就没变。
# 没落地的三种状态（_NO_LANDING_STATUSES）不算: 视频没动, 它旁边的 NFO 名字没错。
_CARRY_STATUSES = frozenset({"renamed", "moved", "dry_run"})


def carry_same_stem_nfo(
    original_video_path: str, new_video_path: str, dry_run: bool = False
) -> tuple[Optional[str], Optional[str]]:
    """把与视频同名前缀的 .nfo 一并搬到新前缀（spec §9.1.1）。返回 (落点, 未跟随的原因)。

    为什么需要这条: `.nfo` 既不在 video_extensions 也不在 subtitle_extensions,
    从不进入扫描、不在批次里, 重命名路径上没有任何东西碰它 —— 视频改名后
    `旧名 S01E01.nfo` 必然留下, 成为与新文件名不符的孤儿。字幕没有这个问题
    （字幕在扫描里, 被当独立文件重命名）。

    四条边界: 只对视频（调用点用 _is_subtitle_file 过滤）; 只跟随**同前缀**的那一个
    （tvshow.nfo / season.nfo 隶属剧/季, 这里按路径推导, 永远推不出它们）;
    与「是否生成 NFO」无关（本函数不碰 nfo_options）; 调用点在生成**之前**。

    dry_run 不移动, 只把落点算出来给调用方列清单 —— 与 §9.4 的可见性一致。

    返回 (None, None) 表示「这里没有该跟随的 NFO」, 不是失败: 绝大多数批次如此。

    **不在本期**: OpenList 源。本期云盘不写 NFO（§2）, 跟随在那里同样缺席 ——
    已知限制, 不是遗漏（openlist_renamer 从不调用本函数, 本函数只被本地那条
    batch_rename 调用）。
    """
    src = episode_nfo_path(original_video_path)
    dst = episode_nfo_path(new_video_path)
    if src == dst or not Path(src).exists():
        return None, None
    if Path(dst).exists():
        return None, _CARRIED_NFO_TARGET_EXISTS_REASON
    if dry_run:
        return dst, None
    try:
        # 跨设备也能搬（与 execute_rename_plan 的 errno 18 回退同一考虑）,
        # 失败抛 OSError —— 由调用点报成跳过, 不冒到 batch_rename 外面。
        shutil.move(src, dst)
    except OSError as exc:
        return None, f"同名 NFO 跟随移动失败: {exc}"
    return dst, None


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
    # 跟着视频搬走的既有同前缀 NFO 的**落点**（spec §9.1.1）。与 nfo_written 分开:
    # 它不是生成出来的, 算进「生成 N 个」就是在骗人。
    nfo_carried: list[str] = []
    # 想跟随却没成功的（目标已存在 / 移动失败）。它与生成侧的跳过汇总在
    # nfo_skipped 里, 但原因串各成一类, 用户分得清是「没生成」还是「没搬走」。
    carry_skipped: list[tuple[str, str]] = []

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

        # spec §9.1.1: 同前缀的既有 .nfo 跟着视频一起搬。位置在**这里**是有意的 ——
        # 生成在本函数末尾, 所以「先移动、后生成」这个顺序由代码位置兑现:
        # 「生成开 + 覆盖关」时搬过去的旧 NFO 占住新位置, 生成报「已存在」,
        # 用户原有的内容得以保留。反过来（先生成再搬）会让生成先写、搬动再撞上
        # 「目标已存在」而放弃 —— 用户的内容被生成结果替掉, 旧文件还在原处当孤儿。
        # 视频用 result.new_path（rename_dup 下真实落点是 X_1.mkv, 与每集 NFO 同一判据）。
        if (
            not aborted
            and not _is_subtitle_file(plan.file_info)
            and result.status in _CARRY_STATUSES
        ):
            carried_path, carry_reason = carry_same_stem_nfo(
                plan.original_path, result.new_path, dry_run=dry_run
            )
            if carried_path is not None:
                nfo_carried.append(carried_path)
            elif carry_reason is not None:
                carry_skipped.append((episode_nfo_path(result.new_path), carry_reason))

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

    # 所有「没发生的事」先汇总成 (路径, 原因) 对, 最后统一去重（按**这一对**去重,
    # 见 nfo_writer.dedupe_skipped_pairs）。三处来源都可能对同一个路径发多条:
    # 同一集的两个来源（模板不含清晰度, 都算出同一个落点）、多剧混放为组内每个
    # 条目各发一条组级决策、以及生成侧与跟随侧在同一个目标 NFO 上各报一条。
    # 前两类是同一件事重复发, 必须合并（否则对话框把 1 个路径读成 N 个 ——
    # 数字本身撒谎）; 第三类是**两件不同的事**（那份文件本来就在 → 生成没写;
    # 孤儿想过来 → 没搬成）, 理由串各说各的, 两条都留着。
    skipped_pairs: list[tuple[str, str]] = []

    # 没落地的行: 它们的每集决策一律不写（理由见 _keep_decision）。组级决策由
    # landed_paths 另行判定 —— 那是「整组」的落点, 不能因为组代表那一行没落地
    # 就把整部剧的 tvshow.nfo 丢掉。
    if nfo_decisions and dead_file_ids:
        kept: list[NfoDecision] = []
        for decision in nfo_decisions:
            if _keep_decision(decision, dead_file_ids, landed_paths):
                kept.append(decision)
            elif decision.kind != "episode":
                # 组级决策被丢弃 = 那份剧集级/季级 NFO 不会写。**丢弃要报出来**:
                # 此前它被静默扔掉, 结果里既没有落点也没有跳过记录, 用户无从知道
                # 这部剧本该有的 tvshow.nfo 为什么一个都没写。
                # （每集决策的丢弃另有 dead_episode_paths 那条更具体的原因。）
                skipped_pairs.append((decision.path, _DROPPED_GROUP_NFO_REASON))
        nfo_decisions = kept

    # 不写要**报出来**: 留白等于静默, 而用户需要知道「这一行没改名, 所以 NFO 也
    # 没写」—— 否则那一行的 nfo_path 是 None、清单里也找不到它。
    skipped_pairs.extend(
        (path, _NOT_RENAMED_NFO_REASON) for path in dead_episode_paths
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
            # 跟随移动也算「那一刻那里会有文件」: 移动在生成之前发生, 所以干跑里
            # 被搬走的落点同样要让生成报「已存在」—— 否则干跑报「将写入」、真跑报
            # 「已存在」, 执行前唯一的那点可见性就成了假话。
            planned_carried = set(nfo_carried)
            planned_written: list[str] = []
            for decision in nfo_decisions:
                if decision.content is None:
                    skipped_pairs.append((decision.path, decision.reason or "无内容"))
                elif (Path(decision.path).exists() or decision.path in planned_carried) \
                        and not nfo_options.overwrite:
                    # "已存在" 是**前端 ResultDialog 的判据串**: 出现它才追加那行可行动
                    # 提示「如需覆盖既有 NFO，请勾选「覆盖已存在的 NFO」后重新执行」。
                    # 后端测试钉着这个字面值（tests/test_nfo_write.py:295 断言干跑分支
                    # 的 nfo_skipped 里有 reason == "已存在"）, 但**没有任何检查**钉住
                    # 前端消费者那一侧 —— 前端没有测试, 改字后后端照样绿, 那行提示
                    # 却会静默消失。改这里要同步前端。
                    # 另一半在 nfo_writer.write_nfo_files（真实写盘那条路径）。
                    skipped_pairs.append((decision.path, "已存在"))
                elif decision.path not in planned_written:
                    planned_written.append(decision.path)
            nfo_written = planned_written
        else:
            written_paths, write_skipped = write_nfo_files(
                nfo_decisions, overwrite=nfo_options.overwrite
            )
            nfo_written = written_paths
            skipped_pairs.extend(write_skipped)

    # 跟随侧报的跳过单独一排（它报的是「搬」这件事, 生成侧的报的是「写」）。
    skipped_pairs.extend(carry_skipped)

    # 统一去重（复用写盘/干跑共用的那个实现, 判据是 (路径, 原因) 这一对）:
    # 同一集的两个来源、混放为每个条目各发一条的组级决策都会对同一路径发同样
    # 的原因 —— 那些必须合并, 不去重对话框就会把 1 个路径读成 N 个。
    # 而「生成说已存在」+「跟随说没搬成」是两件不同的事, 两条都留着。
    nfo_skipped = [
        {"path": path, "reason": reason}
        for path, reason in dedupe_skipped_pairs(skipped_pairs)
    ]

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
        nfo_carried=nfo_carried,
    )

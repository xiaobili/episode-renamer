"""剧集文件夹重命名：`{TMDB 剧名} ({年份}) [tmdbid-{tv_id}]`。

**为什么单独一个模块**: 目标名拼装、剧集根推导、混放/嵌套判定都是**纯粹的路径逻辑**,
与「谁触发它」无关。放进路由会让预览与执行各推一遍 —— 本仓库已经为那类分叉付过代价
（见 api/renamer.py 里「计划只构建一次」的注释）。

**三条硬约束**（详见 spec §2）:
1. 这是**批次级**动作。逐文件执行时改目录会让同批其余文件的 `parent_dir` 全部失效。
2. 必须排在 `finalize` **之后**。先改目录的话, `write_nfo_files` 的 `mkdir(parents=True)`
   会在旧名下重建目录并把 `tvshow.nfo` 写进去 —— 媒体库里多出一个只有 NFO 的空文件夹。
3. 季目录（`Season 01` / `第1季` / `S01`）**不单独处理** —— 改的是它们的父目录, 整棵树
   跟着走。要处理的是「文件躺在季目录里时别把季目录当成剧目录」, 判据复用
   `nfo_writer.show_root_of`。

**已知边界**: 混放判定只能看见**本批次**的条目（我们没有未扫描的目录信息）。因此
`/media/未分类/A.mkv` 这种「解析层面同为一部剧」的混放目录, 只有在用户逐行改过剧名
（override）时才判得出来 —— 与 NFO 的混放守卫同一个前提。剩下那一半靠**预览可见性**
兜住: `/rename/preview` 每行返回 `folder.new_path`, 用户在动手前看得到目录会被改成什么。
"""
from __future__ import annotations

import os
import posixpath
from typing import Optional

from ..models.file import RenamePlan
from ..models.show_folder import ShowFolderPlan
from ..models.tmdb import TmdbShow
from .nfo_writer import show_root_of
from .tmdb_resolver import EpisodeMatch
from .utils import safe_filename


# 计划期（纯函数, 不碰文件系统）能给出的拒绝原因。
NO_TMDB_REASON = "该剧未匹配到 TMDB, 无法生成「剧名 (年份) [tmdbid-x]」"
MIXED_SHOWS_REASON = "该目录下混有多部剧, 不重命名"
ALREADY_NAMED_REASON = "目录名已是目标名"
NO_SHOW_DIR_REASON = "无法确定剧集目录"
# 剧集目录直接挂在文件系统根下 —— 多半是「扫的是挂载点/库根」而不是某一部剧的目录。
# 改名会得到 `/绝命毒师 (2008) [tmdbid-1396]` 这种落在根上的目录: 容器里改的是挂载点
# 本身（宿主机上什么都没变）, 宿主机上则需要 root 权限。两种都不该静默发生。
ROOT_TOO_SHALLOW_REASON = "剧集目录直接位于根目录下, 不重命名"

# 执行期（真的碰了磁盘 / 远端）才知道的原因。
TARGET_EXISTS_REASON = "目标目录已存在"
SOURCE_MISSING_REASON = "源目录不存在"


def build_show_folder_name(show: Optional[TmdbShow]) -> str:
    """TMDB 剧集 → 目标目录名。返回 "" 表示「拿不出可用的名字」（调用方据此拒绝）。

    剧名取 TMDB 的本地化标题（受 TMDB_LANGUAGE 影响）: 与 `tvshow.nfo` 的 `<title>`
    同源, 媒体库显示与 NFO 永远一致。年份缺失时**省略**括号段而不是写出 `()`。

    清洗走 `safe_filename`（去掉 `\\ / : * ? " < > |` 并压掉空白）: 目录名里出现
    路径分隔符会直接改变目标路径的层级, 那不是「重命名失败」而是写到别处去。
    """
    if show is None:
        return ""
    name = safe_filename(show.name or "")
    if not name:
        return ""
    year = f" ({show.year})" if show.year else ""
    return f"{name}{year} [tmdbid-{show.tv_id}]"


def _show_of(group: list[RenamePlan], matches: dict[str, EpisodeMatch]) -> Optional[TmdbShow]:
    """组内第一个**匹配到剧集**的 TMDB 数据。

    不看 `status`: `season_not_found` / `episode_not_found` 的 EpisodeMatch 仍然带着
    `show` —— 剧集本身是认得的, 只是某一集对不上。文件夹名只需要剧集级信息。
    """
    for plan in group:
        match = matches.get(plan.file_id)
        if match is not None and match.show is not None:
            return match.show
    return None


def _mixed_show_names(roots: dict[str, str], path_mod) -> set[str]:
    """找出「不能改名」的剧名 —— 同目录混放, 或自己的目录里嵌着别的剧。

    - 两个组的根**相同** → 两组都拒（同目录混放, 谁改名都会带走对方）;
    - A 的根是 B 的根的**祖先** → 只拒 A（搬 A 会把 B 连同它的目录一起搬走）,
      B 自己仍可改 —— 它的根不受 A 的改名影响。
    """
    sep = path_mod.sep
    conflicted: set[str] = set()

    def norm(path: str) -> str:
        return path.rstrip(sep)

    for name, root in roots.items():
        if not root:
            continue
        for other, other_root in roots.items():
            if name == other or not other_root:
                continue
            if norm(root) == norm(other_root):
                conflicted.add(name)
            elif norm(other_root).startswith(norm(root) + sep):
                conflicted.add(name)
    return conflicted


def plan_show_folders(
    plans: list[RenamePlan],
    matches: dict[str, EpisodeMatch],
    path_mod=os.path,
) -> list[ShowFolderPlan]:
    """一批 plan → 每部剧一条改名计划（纯函数, 不碰文件系统）。

    **根用 `plan.new_path` 而不是 `original_path`**: 这一步排在逐文件重命名之后,
    那时磁盘上的目录仍是旧名, 但目标目录（`create_season_folder` 可能新建的季目录）
    已经把文件归位 —— 两者推出的剧集根是同一个, 用 new_path 才能与 NFO 落点同源。

    **存在性（目标是否已存在）不在这里判**: 预览不该为每一行去打一次远端 API,
    且本地/远端两套判据会让「预览说能改、执行说撞名」。存在性在 `apply_*` 里判,
    与 STRM / NFO 的「预览给落点、执行给结果」同一分工。
    """
    groups: dict[str, list[RenamePlan]] = {}
    for plan in plans:
        key = plan.parsed.show_name if plan.parsed else ""
        groups.setdefault(key, []).append(plan)
    if not groups:
        return []

    roots = {
        name: show_root_of([p.new_path for p in group], path_mod)
        for name, group in groups.items()
    }
    conflicted = _mixed_show_names(roots, path_mod)
    sep = path_mod.sep

    result: list[ShowFolderPlan] = []
    for name in sorted(groups):
        group = groups[name]
        root = roots[name]
        target_name = build_show_folder_name(_show_of(group, matches))
        file_ids = [p.file_id for p in group]

        def make(reason: Optional[str]) -> ShowFolderPlan:
            return ShowFolderPlan(
                show_name=name, old_path=root, target_name="",
                reason=reason, file_ids=file_ids,
            )

        # 顺序即优先级: 「为什么不能改」要说最根本的那条。混放排在最前 ——
        # 它说明的是「这个目录根本不是某一部剧的目录」, 与后面几条不在一个层级。
        if name in conflicted:
            result.append(make(MIXED_SHOWS_REASON))
            continue
        if not root or root == sep or not name:
            result.append(make(NO_SHOW_DIR_REASON))
            continue
        if not target_name:
            result.append(make(NO_TMDB_REASON))
            continue
        if posixpath.basename(root.rstrip(sep)) == target_name or \
                os.path.basename(root.rstrip(sep)) == target_name:
            result.append(make(ALREADY_NAMED_REASON))
            continue

        parent = path_mod.dirname(root.rstrip(sep))
        # 父目录为空（相对路径的顶层）或就是它自己（文件系统根）→ 目标名无处可放。
        if not parent or parent == root:
            result.append(make(NO_SHOW_DIR_REASON))
            continue
        # 父目录本身也是根（`/media` 这类顶层目录）→ 改名会把目录搬到文件系统根上。
        # 这条与 _show_root 的「上溯过头」是同一类风险, 但后果更重: 那边是多写一个
        # 落错位置的 NFO, 这边是把一个挂载点改名。
        if path_mod.dirname(parent) == parent:
            result.append(make(ROOT_TOO_SHALLOW_REASON))
            continue

        result.append(ShowFolderPlan(
            show_name=name,
            old_path=root.rstrip(sep),
            new_path=path_mod.join(parent, target_name),
            target_name=target_name,
            reason=None,
            file_ids=file_ids,
        ))
    return result


def _renamed_entry(plan: ShowFolderPlan) -> dict:
    return {
        "old_path": plan.old_path,
        "new_path": plan.new_path,
        "show_name": plan.show_name,
    }


def apply_local_show_folders(
    folder_plans: list[ShowFolderPlan],
) -> tuple[list[dict], list[dict]]:
    """本地：真的改目录名。返回 (已改名, [(路径, 原因)])。

    不覆盖、不自动编号: 目录层面的「自动编号」会产出 `绝命毒师 (2008) [tmdbid-1396]_1`
    这种媒体服务器认不出的名字, 比不改更糟。目标已存在就如实跳过。

    幂等: 旧目录不在、目标在 → 视为**已经改过**（重跑一次不该报「源目录不存在」这种
    听起来像数据丢了的错）。
    """
    renamed: list[dict] = []
    skipped: list[dict] = []

    for plan in folder_plans:
        if plan.reason:
            skipped.append({"path": plan.old_path, "reason": plan.reason})
            continue

        src, dst = plan.old_path, plan.new_path
        if not os.path.isdir(src):
            if dst and os.path.isdir(dst):
                skipped.append({"path": dst, "reason": ALREADY_NAMED_REASON})
            else:
                skipped.append({"path": src, "reason": SOURCE_MISSING_REASON})
            continue
        if os.path.exists(dst):
            skipped.append({"path": dst, "reason": TARGET_EXISTS_REASON})
            continue

        try:
            os.rename(src, dst)
        except OSError as exc:
            # 跨设备改名不是这里的场景（同一父目录内改名）, 失败一律如实报,
            # 不尝试 shutil.move —— 目录移动在中途失败时没有任何回滚手段。
            skipped.append({"path": dst, "reason": f"重命名失败: {exc}"})
            continue
        renamed.append(_renamed_entry(plan))

    return renamed, skipped


async def apply_openlist_show_folders(
    client,
    folder_plans: list[ShowFolderPlan],
) -> tuple[list[dict], list[dict]]:
    """OpenList：改远端目录名。返回 (已改名, [(路径, 原因)])。

    与本地不同, 远端**没有** `exists()` —— 撞名必须靠列一次父目录来判。这多一次
    请求, 但 `/api/fs/rename` 撞名时的行为（覆盖 / 报错）随底层驱动而变, 赌它
    稳妥就等于把「用户已有的目录被合并」这种不可逆事故交给运气。

    同一次列表顺带解决另一件事: 旧目录名不在列表里 = 源已不存在（含「上一次已经
    改完」的幂等场景）。
    """
    renamed: list[dict] = []
    skipped: list[dict] = []

    for plan in folder_plans:
        if plan.reason:
            skipped.append({"path": plan.old_path, "reason": plan.reason})
            continue

        root = plan.old_path.rstrip("/")
        parent = posixpath.dirname(root) or "/"
        old_name = posixpath.basename(root)

        try:
            entries, _write_access = await client.list_directory(parent)
        except Exception as exc:
            skipped.append({"path": parent, "reason": f"无法读取父目录: {exc}"})
            continue

        names = {getattr(entry, "name", "") for entry in entries}
        if plan.target_name in names:
            skipped.append({"path": plan.new_path, "reason": TARGET_EXISTS_REASON})
            continue
        if old_name not in names:
            skipped.append({"path": plan.old_path, "reason": SOURCE_MISSING_REASON})
            continue

        try:
            await client.rename(plan.old_path, plan.target_name)
        except Exception as exc:
            skipped.append({"path": plan.new_path, "reason": f"重命名失败: {exc}"})
            continue
        renamed.append(_renamed_entry(plan))

    return renamed, skipped

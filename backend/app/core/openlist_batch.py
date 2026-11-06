"""OpenList 批量执行：一个请求跑完整批，顺序与并发由后端裁决。

为什么需要它
------------
逐文件接口把四件**批次级**事实交给了调用方：并发数、请求间隔、批次内重名降级、
收尾顺序。调用方（前端）一旦漏掉其中任何一件，后端都不会报错 —— 它只是照着收到
的请求一个个执行。本模块把这四件事收回后端：

· **并发**：文件级 `asyncio.Semaphore`。一个「文件流水线」含 move / rename /
  每集 NFO / STRM 多次 HTTP，客户端限流器仍负责**单次请求**的并发上限，两层各管
  一段，不互相替代（限流器管不到「几个文件同时在跑」）。
· **批次内重名**：两个文件算出同一个目标名时降级为串行。后端 `check_conflict`
  的第二参是空列表，`duplicate_in_batch` 分支从不触发 —— 并发下两个文件会双双
  通过存在性检查，`overwrite` 策略下直接丢数据（spec §10.1）。
· **顺序**：逐文件执行 → 剧集级 NFO 收尾 → 剧集文件夹改名。先改目录会让 NFO 的
  `mkdir(parents=True)` 在旧名下重建目录，把 `tvshow.nfo` 写进一个没有任何剧集
  文件的空文件夹（spec §9.4 明令禁止的库根污染）。
· **落点**：`landed` 在这里算，不再经调用方回传 —— 少一份「按 status 自己判落地」
  的规则副本（「字幕不算落地」那条判不出，见 `landed_path_of` 的调用点）。

与逐文件接口的关系
------------------
`execute_openlist_one` / `episode_nfo_for_plan` / `write_strm_for_plan` /
`finalize_openlist_nfo` 全部原样复用，本模块只负责**编排**。两条路径的差异只在
「谁决定顺序与并发」，不在「每个文件怎么做」—— 这是它们不会分叉的根据。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from ..config import settings
from ..models.file import RenamePlan, RenameResult
from ..models.nfo import NfoOptions
from ..models.strm import StrmOptions
from .local_renamer import count_result, landed_path_of
from .openlist_client import OpenListClient
from .openlist_nfo import episode_nfo_for_plan
from .openlist_renamer import execute_openlist_one
from .strm import write_strm_for_plan
from .tmdb_resolver import EpisodeMatch

ProgressCallback = Callable[[int, int, str], Awaitable[None]]
"""`(已完成数, 总数, 刚完成文件的原始名)`。

**必须是协程**：进度事件的消费者是 SSE 队列（`queue.put` 本身也是协程），同步
回调会把它变成「先跑完再补发」—— 进度条就失去意义了。
"""


@dataclass
class PlanOutcome:
    """一个文件执行后的全部事实：改名结果 + 它自己的 NFO / STRM 副作用。

    `landed_path` 是**权威落点**（未落地为 None），剧集级 NFO 与文件夹收尾都读它，
    不读 `result.status` —— 那条规则只有一份，在 `landed_path_of` 里。
    """
    plan: RenamePlan
    result: RenameResult
    landed_path: Optional[str] = None
    nfo_written: list[str] = field(default_factory=list)
    nfo_carried: list[str] = field(default_factory=list)
    nfo_skipped: list[tuple[str, str]] = field(default_factory=list)
    strm_written: list[str] = field(default_factory=list)
    strm_skipped: list[tuple[str, str]] = field(default_factory=list)
    executed: int = 0
    skipped: int = 0
    failed: int = 0


def resolve_batch_concurrency(
    plans: list[RenamePlan], requested: Optional[int]
) -> int:
    """本批允许几个文件同时跑。

    `requested` 为 None 时回落 `settings.openlist_max_concurrent` —— 与
    `OpenListClient.apply_limits(None, ...)` 的行为**同源**：那边不改 limiter，
    这边也就用同一个默认值。两处若各自读不同的来源，就会出现「设置页改成 2、
    文件级并发仍是 3」这种看不见的偏差。

    批次内目标重名 → 1。这不是保守，是正确性：`check_conflict` 从不报
    `duplicate_in_batch`（第二参恒为空列表），并发下两个文件会双双通过存在性
    检查，`overwrite` 时后者静默覆盖前者。
    """
    limit = settings.openlist_max_concurrent if requested is None else requested
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = max(1, settings.openlist_max_concurrent)

    targets = [plan.new_path for plan in plans]
    if len(set(targets)) != len(targets):
        return 1
    return min(limit, max(1, len(plans)))


async def execute_openlist_plan_once(
    client: OpenListClient,
    plan: RenamePlan,
    *,
    nfo_options: NfoOptions,
    nfo_matches: dict[str, EpisodeMatch],
    strm_options: StrmOptions,
    strm_scan_root: str = "",
    dir_cache: Optional[dict[str, bool]] = None,
) -> PlanOutcome:
    """一个文件的完整流水线：改名 → 每集 NFO → STRM。

    顺序与 `/rename/execute` 的 OpenList 分支逐字一致 —— 那里先 NFO 再 STRM 是
    刻意的（元数据先就位、入口最后写，将来加回滚时有明确边界）。

    NFO / STRM 的异常**降级为该文件的 skipped 条目**，不让它冒成整批失败：走到
    这一步文件已经改名成功，把一条已完成的重命名报成「操作失败」会骗用户再跑
    一遍，然后撞上「目标已存在」。
    """
    result = await execute_openlist_one(client, plan, dir_cache)
    executed, skipped, failed = count_result(result, False)

    is_subtitle = bool(plan.file_info is not None and plan.file_info.is_subtitle)
    # 字幕**不算落地**：它与视频共用同一套 status，但落点不该给组级 NFO 背书
    # （与 execute 路由的判据同源）。
    landed_path = None if is_subtitle else landed_path_of(result)
    fallback_path = result.new_path or plan.new_path

    nfo_written: list[str] = []
    nfo_carried: list[str] = []
    nfo_skipped: list[tuple[str, str]] = []
    try:
        nfo_written, nfo_carried, nfo_skipped = await episode_nfo_for_plan(
            client, plan, result, nfo_matches, nfo_options,
        )
    except Exception as exc:  # noqa: BLE001 —— 见上面 docstring 的降级理由
        nfo_skipped = [(fallback_path, f"NFO 处理失败: {exc}")]

    strm_written: list[str] = []
    strm_skipped: list[tuple[str, str]] = []
    try:
        strm_written, strm_skipped = await write_strm_for_plan(
            client, plan, result, strm_options, strm_scan_root, dir_cache,
        )
    except Exception as exc:  # noqa: BLE001
        strm_skipped = [(fallback_path, f"STRM 写入失败: {exc}")]

    return PlanOutcome(
        plan=plan,
        result=result,
        landed_path=landed_path,
        nfo_written=nfo_written,
        nfo_carried=nfo_carried,
        nfo_skipped=nfo_skipped,
        strm_written=strm_written,
        strm_skipped=strm_skipped,
        executed=executed,
        skipped=skipped,
        failed=failed,
    )


def _failed_outcome(plan: RenamePlan, exc: Exception) -> PlanOutcome:
    """流水线自身抛错时的占位结果（如客户端在 rename 之前就炸了）。

    与前端过去合成的那条失败记录**同形状**：`status="failed"` + 可读的 error，
    计数 0/0/1。区别只是现在由后端写，前端不再需要造这个形状。
    """
    return PlanOutcome(
        plan=plan,
        result=RenameResult(
            id=plan.id,
            original_path=plan.original_path,
            new_path="",
            original_filename=plan.original_filename,
            new_filename="",
            success=False,
            status="failed",
            error=str(exc),
        ),
        failed=1,
    )


async def execute_openlist_plans(
    client: OpenListClient,
    plans: list[RenamePlan],
    *,
    nfo_options: NfoOptions,
    nfo_matches: Optional[dict[str, EpisodeMatch]] = None,
    strm_options: StrmOptions,
    strm_scan_root: str = "",
    max_concurrent: Optional[int] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> list[PlanOutcome]:
    """并发跑完整批，返回**按 plans 顺序**排列的结果。

    结果顺序必须与 plans 一致：它要按行对回用户看见的表。`asyncio.gather` 的
    返回值顺序是对的，但那要求任务按序创建且不丢——这里直接把结果写回下标，
    完成顺序怎样都不影响输出。

    单个文件抛错**不中断整批**（与前端并发池「一律跑完」同一条纪律）：换成
    失败占位继续。
    """
    if not plans:
        return []

    nfo_matches = nfo_matches or {}
    limit = resolve_batch_concurrency(plans, max_concurrent)
    semaphore = asyncio.Semaphore(limit)
    outcomes: list[Optional[PlanOutcome]] = [None] * len(plans)
    done = 0
    # 整批共用一份「目录已确保存在」的缓存（含 STRM 的逐级 mkdir）。
    # 一季几十集落在同一个季目录 / 同一个 STRM 根下, 每集重建一遍目录是纯
    # 浪费: 实测同目录改名 + 远端 STRM 时, 每文件 5 次请求里有 2 次是这种
    # 重复 mkdir, 共享后降到 3 次。
    #
    # **只共享 mkdir 标记, 不共享目录内容列表**: 目录内容会在本批执行过程中
    # 变化（刚改完名的文件就在里面）, 缓存住会让「目标已存在」与「旧 NFO 是否
    # 存在」的判断读到过期快照 —— 前者导致覆盖用户文件, 后者导致漏搬 NFO。
    # 两者都是静默的数据事故, 而多一次 list 只是慢。
    dir_cache: dict[str, bool] = {}

    async def run(index: int, plan: RenamePlan) -> None:
        nonlocal done
        async with semaphore:
            try:
                outcome = await execute_openlist_plan_once(
                    client, plan,
                    nfo_options=nfo_options,
                    nfo_matches=nfo_matches,
                    strm_options=strm_options,
                    strm_scan_root=strm_scan_root,
                    dir_cache=dir_cache,
                )
            except Exception as exc:  # noqa: BLE001
                outcome = _failed_outcome(plan, exc)
        outcomes[index] = outcome
        done += 1
        if on_progress is not None:
            await on_progress(done, len(plans), plan.original_filename)

    await asyncio.gather(*(run(index, plan) for index, plan in enumerate(plans)))

    # gather 保证每个下标都被写过；这里用显式断言把「某个槽位空着」变成一次
    # 立刻可见的错误，而不是被下面的过滤器静默吞掉（少一行结果会让计数与表对不上）。
    assert all(outcome is not None for outcome in outcomes), "批量执行漏掉了结果槽位"
    return [outcome for outcome in outcomes if outcome is not None]


def batch_result_payload(
    outcomes: list[PlanOutcome],
    *,
    nfo_written: Optional[list[str]] = None,
    nfo_skipped: Optional[list[tuple[str, str]]] = None,
    folders_renamed: Optional[list[dict]] = None,
    folders_skipped: Optional[list[dict]] = None,
    nfo_error: Optional[str] = None,
    folders_error: Optional[str] = None,
) -> dict:
    """整批的响应体。字段与前端 `aggregateBatch` 的产出**逐字同形**。

    同形是硬要求：`ResultDialog.vue` 直接消费 `BatchRenameResult` 的字段，换一套
    名字就得同时改对话框与聚合器 —— 而聚合器现在只为本地源服务，两边一旦分叉，
    同一个对话框会对两个源显示不同的东西。

    计数一律来自各 outcome 的 `executed/skipped/failed`（由 `count_result` 给出），
    不在这里按 status 重判 —— 那是第二份规则副本。

    `nfo_error` / `folders_error` 是**收尾阶段**的失败。它们不能变成整批失败：
    走到那一步，每个文件的改名都已在盘上完成，报「操作失败」会骗用户再跑一遍。
    前端据此弹与过去同一句降级提示。
    """
    results = [outcome.result.model_dump() for outcome in outcomes]
    nfo_written_all: list[str] = []
    nfo_carried: list[str] = []
    nfo_skipped_all: list[dict] = []
    strm_written: list[str] = []
    strm_skipped: list[dict] = []

    for outcome in outcomes:
        nfo_written_all.extend(outcome.nfo_written)
        nfo_carried.extend(outcome.nfo_carried)
        nfo_skipped_all.extend(
            {"path": path, "reason": reason}
            for path, reason in outcome.nfo_skipped
        )
        strm_written.extend(outcome.strm_written)
        strm_skipped.extend(
            {"path": path, "reason": reason}
            for path, reason in outcome.strm_skipped
        )

    nfo_written_all.extend(nfo_written or [])
    nfo_skipped_all.extend(
        {"path": path, "reason": reason} for path, reason in (nfo_skipped or [])
    )

    executed = sum(outcome.executed for outcome in outcomes)
    skipped = sum(outcome.skipped for outcome in outcomes)
    failed = sum(outcome.failed for outcome in outcomes)

    return {
        "success": failed == 0,
        "source": "openlist",
        "executed": executed,
        "skipped": skipped,
        "failed": failed,
        "total": len(outcomes),
        # 批次内冲突由后端报在 result 上，这里没有额外的批次级冲突可报
        # （与 aggregateBatch 同一条）。
        "conflicts": [],
        "results": results,
        # errors 取**模型**上的值: results 已经是 dict, 从那里再取 .error 会炸。
        "errors": [
            outcome.result.error for outcome in outcomes if outcome.result.error
        ],
        "nfo_written": nfo_written_all,
        "nfo_carried": nfo_carried,
        "nfo_skipped": nfo_skipped_all,
        "strm_written": strm_written,
        "strm_skipped": strm_skipped,
        # 目录改名的计数是「部剧」而不是「个文件」，不参与 executed/skipped/failed
        # —— 把 1 个目录算成 1 个失败会让用户以为有某一集没改名。
        "folders_renamed": folders_renamed or [],
        "folders_skipped": folders_skipped or [],
        "nfo_error": nfo_error,
        "folders_error": folders_error,
        "dry_run": False,
    }

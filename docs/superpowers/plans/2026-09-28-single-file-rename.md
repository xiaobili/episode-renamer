# 重命名执行单文件化与前端进度条 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/api/rename/execute` 由「一次请求改一批」改为「一次请求改一个」，新增 `/api/rename/finalize` 承担拆开后唯一需要整批视野的部分（剧集级/季级 NFO），前端逐文件并发执行并显示进度条。

**Architecture:** 后端把 `local_renamer.batch_rename` 里的决策规则抽成共用叶子助手，新增 `execute_one`（单文件执行 + 每集 NFO + 跟随既有 NFO）与 `finalize_show_nfo`（只写剧集级/季级）；`batch_rename` 保留为批量参考实现（干跑仍走它），并由一条**交叉判据**钉住两条路径逐项等价。前端新增零依赖纯函数模块 `renameRunner.js`（并发池）与 `renameAggregate.js`（结果聚合），`workspace.js` 用它们重写执行循环，`ExecutingOverlay.vue` 增加进度条。

**Tech Stack:** Python 3.12 / FastAPI / Pydantic 2 / pytest（后端）；Vue 3 / Pinia / Tailwind CSS 4 / node 断言脚本（前端，无测试框架）

**Spec:** [`docs/superpowers/specs/2026-09-28-single-file-rename-design.md`](../specs/2026-09-28-single-file-rename-design.md)

## Global Constraints

- 后端测试命令：`cd backend && python -m pytest -q`。现有 **214** 条必须全绿，任何一条变红都不得提交。
- 前端判据命令：`cd frontend && node scripts/check-all.mjs`。**任何 `check-*.mjs` 新增/改名后，必须同步更新 `check-all.mjs` 里那份硬编码名单**（它是零依赖 runner，名单是它唯一的知识来源）。
- 响应字段名、状态串、原因串**一律逐字沿用**，不得「顺手统一」。特别地：`"已存在"` 是前端 `ResultDialog.vue:201` 的判据串；`skipped_conflict` / `conflict` / `failed` / `skipped_same` / `renamed` / `moved` / `dry_run` 是 `_NO_LANDING_STATUSES`（`local_renamer.py:48`）与 `_CARRY_STATUSES`（`:70`）的成员，改动会静默改变 NFO 行为。
- `_NO_LANDING_STATUSES`、`_CARRY_STATUSES`、`_is_subtitle_file`、`_keep_decision`、`dedupe_skipped_pairs` 的**判据一律不动**，只搬运调用位置。
- 前端并发数**不得写字面量**：一律从 `settingsStore` 读（这是 spec 事实 10 那个「死设置」bug 的防复发判据）。
- `frontend/src/stores/renamePayload.js` 与 `settingsSchema.js` 保持**零 import**（node 要能直接加载它们跑断言）。
- 提交信息用中文，遵循 `<type>(<scope>): <描述>`（本仓库既有风格）。
- 每完成一个 Task 提交一次；**不得**把多个 Task 混进一个提交。

## Review Focus

以下五类是 spec 未逐条点名、但真人使用时会立刻撞上的输入，最可能出问题的排前面。每一项都在它所属 Task 里有对应判据。

1. **同批次内两个文件算出同一个目标名** —— `check_conflict(plan, [])` 的第二参是空列表（`local_renamer.py:307`），`duplicate_in_batch` 分支**从不触发**，所以后端不会报这个冲突。用户会以为 `skip` 策略保护了他。Task 10 在前端检测并降级为串行。
2. **整批一个文件都没落地（全冲突 / 全失败）** —— 此时绝不能写出 `tvshow.nfo`。Task 6 的 `landed` 为空判据钉住它。
3. **`rename_dup` 下的真实落点** —— 视频落到 `X_1.mkv`，每集 NFO 必须跟着落 `X_1.nfo`，否则 Emby 配对不上。Task 2 与 Task 6 各有一条判据。
4. **用户在批次跑到一半时切走剧集 / 关掉「生成 NFO」** —— 载荷必须在发起**那一刻**快照，不能边跑边读响应式状态。Task 10 的 `nfoBlocked` 局部变量（既有写法，见 `workspace.js:525`）必须保留这个形态。
5. **单个文件抛错（网络断、权限）** —— 不得让整批 reject 掉。Task 7 的 `failures` 判据钉住它。

---

### Task 1: 抽出叶子助手，`batch_rename` 改用它们

纯重构，**不改变任何对外行为**。安全网是现有 214 条测试，它们必须一条不改地全绿。

**Files:**
- Modify: `backend/app/core/local_renamer.py`

**Interfaces:**
- Consumes: 无（本任务只用文件内既有代码）
- Produces:
  - `plan_files(files: list[FileInfo], template: str, folder_template: str = "", create_season_folder: bool = False, overrides: dict[str, dict] | None = None, pad: PadConfig | None = None) -> list[RenamePlan]`
  - `_entry_for(plan: RenamePlan, nfo_matches: dict[str, EpisodeMatch]) -> NfoEntry`
  - `count_result(result: RenameResult, aborted: bool) -> tuple[int, int, int]`
  - `_episode_decision_for(plan: RenamePlan, nfo_matches: dict[str, EpisodeMatch], options: NfoOptions) -> NfoDecision | None`

- [ ] **Step 1: 跑一次基线，记下通过数**

Run: `cd backend && python -m pytest -q`
Expected: `214 passed`（若本机 `.env` 干扰则先确认 conftest 的 `_no_ambient_tmdb` 生效；数字不一致时以实际为准并记下来，后面每一步都要与这个基线比）

- [ ] **Step 2: 新增 `plan_files`，并把 `batch_rename` 开头的循环换掉**

在 `check_conflict` 之后、`execute_rename_plan` 之前插入：

```python
def plan_files(
    files: list[FileInfo],
    template: str,
    folder_template: str = "",
    create_season_folder: bool = False,
    overrides: dict[str, dict] | None = None,
    pad: PadConfig | None = None,
) -> list[RenamePlan]:
    """建 plan 并算冲突 —— 批量与单文件两条路径共用。

    `check_conflict(plan, [])` 的第二参**逐字保留空列表**: 现有实现就是传空,
    于是 `duplicate_in_batch` 这条分支从不触发 —— 同一批次内两个文件算出同一个
    目标名时, 后端**不会**报冲突。这是改动前的既有行为, 本次不得改变它
    （前端会在发起前用预览的 new_path 自行检测重名并降级为串行, 见 spec §10.1）。
    """
    overrides = overrides or {}
    plans: list[RenamePlan] = []
    for f in files:
        ov = overrides.get(f.id)
        override = OverrideInfo(**ov) if ov else None
        plan = build_rename_plan(
            f, template, folder_template, create_season_folder, override, pad=pad
        )
        plan.conflicts = check_conflict(plan, [])
        plans.append(plan)
    return plans
```

然后把 `batch_rename` 里这段（`local_renamer.py:297-309`）：

```python
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
```

替换为：

```python
    nfo_matches = nfo_matches or {}
    plans = plan_files(
        files, template, folder_template, create_season_folder, overrides, pad=pad
    )
```

- [ ] **Step 3: 跑测试，确认仍然全绿**

Run: `cd backend && python -m pytest -q`
Expected: 与 Step 1 的基线**数字完全一致**

- [ ] **Step 4: 新增 `_entry_for`，并把 `batch_rename` 里的 NfoEntry 构造换掉**

在 `plan_files` 之后插入：

```python
def _entry_for(plan: RenamePlan, nfo_matches: dict[str, EpisodeMatch]) -> NfoEntry:
    """把 plan 转成一条 NFO 条目。

    nfo_matches 里没有对应项时 .get() 返回 None, getattr(None, "show", None) 也是
    None —— 三者同时为 None, NfoEntry.has_metadata 即为 False, 于是不写残缺 NFO。
    """
    return NfoEntry(
        file_id=plan.file_id,
        new_path=plan.new_path,
        show_name=plan.parsed.show_name if plan.parsed else "",
        season=plan.parsed.season if plan.parsed else None,
        episode=plan.parsed.episode if plan.parsed else None,
        show=getattr(nfo_matches.get(plan.file_id), "show", None),
        season_data=getattr(nfo_matches.get(plan.file_id), "season", None),
        episode_data=getattr(nfo_matches.get(plan.file_id), "episode", None),
    )
```

把 `batch_rename` 里 `build_nfo_decisions([...])` 的列表推导（`:319-340`）替换为：

```python
        nfo_decisions = build_nfo_decisions(
            [
                _entry_for(plan, nfo_matches)
                # 字幕不进 NFO（理由见 _is_subtitle_file）。这个过滤只作用于 NFO 的
                # 构造 —— 字幕照常参与下面的重命名。
                for plan in plans
                if not _is_subtitle_file(plan.file_info)
            ],
            nfo_options,
        )
```

- [ ] **Step 5: 跑测试**

Run: `cd backend && python -m pytest -q`
Expected: 与基线一致

- [ ] **Step 6: 新增 `count_result`，并把计数三分支换掉**

在 `_entry_for` 之后插入：

```python
def count_result(result: RenameResult, aborted: bool) -> tuple[int, int, int]:
    """(executed, skipped, failed) —— 逐字沿用 batch_rename 里那套判据。

    抽出来是因为单文件响应也要给出这三个计数（spec §4.1 / R11）：让前端按
    result.status 自己重判会把规则复制成第二份, 两份必然漂移。
    """
    if aborted:
        # abort 下的冲突行计入 failed（与改动前一致）—— 走下面的通用分支会按
        # status="conflict" 把它记成 skipped。
        return 0, 0, 1
    if result.success and result.status not in ("skipped_conflict", "skipped_same"):
        return 1, 0, 0
    if result.status in ("skipped_conflict", "skipped_same", "conflict"):
        return 0, 1, 0
    return 0, 0, 1
```

把 `batch_rename` 里这段（`:422-431`）：

```python
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
```

替换为：

```python
        one_executed, one_skipped, one_failed = count_result(result, aborted)
        executed += one_executed
        skipped += one_skipped
        failed += one_failed
```

- [ ] **Step 7: 新增 `_episode_decision_for`，并把每集决策的取用换掉**

在 `count_result` 之后插入：

```python
def _episode_decision_for(
    plan: RenamePlan,
    nfo_matches: dict[str, EpisodeMatch],
    options: NfoOptions,
) -> Optional[NfoDecision]:
    """该文件的**每集** NFO 决策；字幕与未启用时返回 None。

    走 build_nfo_decisions 而不是自己拼路径与内容: 内容是否该写（TMDB 未匹配时
    不写残缺 NFO）是 nfo_writer 的规则, 在这里重写一遍就是第二份副本。
    单条目调用时它同时会产出一条 tvshow / 一条 season 决策（那一条目自成一
    组）—— 那两条是**批次级**的, 由 finalize_show_nfo 负责, 这里只取 episode。
    """
    if not options.enabled or _is_subtitle_file(plan.file_info):
        return None
    decisions = build_nfo_decisions([_entry_for(plan, nfo_matches)], options)
    return next((d for d in decisions if d.kind == "episode"), None)
```

- [ ] **Step 8: 跑测试并提交**

Run: `cd backend && python -m pytest -q`
Expected: 与基线一致

```bash
git add backend/app/core/local_renamer.py
git commit -m "refactor(local_renamer): 抽出 plan_files / _entry_for / count_result / _episode_decision_for 四个叶子助手"
```

---

### Task 2: 新增 `execute_one` 与 `finalize_show_nfo`，并用交叉判据钉住两条路径

**Files:**
- Modify: `backend/app/core/local_renamer.py`
- Test: `backend/tests/test_single_file_core.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `plan_files` / `_entry_for` / `count_result` / `_episode_decision_for`
- Produces:
  - `@dataclass OneOutcome`，字段：`result: RenameResult`、`landed_path: Optional[str]`、`dead_episode_path: Optional[str]`、`nfo_written: list[str]`、`nfo_carried: list[str]`、`nfo_skipped: list[tuple[str, str]]`、`executed: int`、`skipped: int`、`failed: int`
  - `landed_path_of(result: RenameResult) -> Optional[str]` —— 落地返回真实落点，未落地返回 `None`（公开，供 OpenList 路径复用，避免跨模块 import 私有名 `_NO_LANDING_STATUSES`）
  - `execute_one(plan: RenamePlan, *, conflict_strategy: str = "skip", nfo_options: NfoOptions | None = None, nfo_matches: dict[str, EpisodeMatch] | None = None) -> OneOutcome`（**无 `dry_run`**，理由见实现处的注释）
  - `finalize_show_nfo(plans: list[RenamePlan], landed_paths: list[str], nfo_matches: dict[str, EpisodeMatch], options: NfoOptions) -> tuple[list[str], list[tuple[str, str]]]`

- [ ] **Step 1: 写交叉判据测试（先红）**

新建 `backend/tests/test_single_file_core.py`：

```python
"""单文件路径与批量路径必须逐项等价（spec R15）。

编排循环存在两份（batch_rename 的循环与 execute_one），叶子助手是共用的。
这条判据就是「两份副本」这个顾虑的答案: 任何一处漂移都会在这里红。

**夹具必须产出非空的四类结果**, 否则断言退化成 [] == [] 恒真、零鉴别力
（本项目已有三次前科）。`test_fixture_is_not_vacuous` 就是为此存在的元判据。

**两条路径必须各跑各的目录**: 批量路径会真的改名, 共用目录时单文件路径的源
文件已经不存在了, 两边根本不是在比同一件事。
"""
import pytest

from app.core.local_renamer import (
    batch_rename, execute_one, finalize_show_nfo, plan_files,
)
import os

from app.core.nfo_writer import dedupe_skipped_pairs
from app.core.tmdb_resolver import STATUS_MATCHED, EpisodeMatch
from app.models.file import FileInfo
from app.models.nfo import NfoOptions
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"

OVERRIDES = {
    "Show.S01E01.mkv": {"show_name": "Show", "season": 1, "episode": 1},
    "Show.S01E02.mkv": {"show_name": "Show", "season": 1, "episode": 2},
    "Show.S01E02.chs.srt": {"show_name": "Show", "season": 1, "episode": 2},
    "Show.S01E03.mkv": {"show_name": "Show", "season": 1, "episode": 3},
}


def _matches():
    """真实元数据 —— 少了它每条决策的 content 都是 None, 两边都写不出文件。"""
    show = TmdbShow(tv_id=1396, name="Show")
    season = TmdbSeason(season_number=1, name="第 1 季")
    return {
        "Show.S01E01.mkv": EpisodeMatch(
            status=STATUS_MATCHED, show=show, season=season,
            episode=TmdbEpisode(episode_number=1, name="试播集"),
        ),
        "Show.S01E02.mkv": EpisodeMatch(
            status=STATUS_MATCHED, show=show, season=season,
            episode=TmdbEpisode(episode_number=2, name="第二集"),
        ),
        # E03 的源文件不存在 → 它不落地, 但**要有**决策才能验「报出来」那条规则
        "Show.S01E03.mkv": EpisodeMatch(
            status=STATUS_MATCHED, show=show, season=season,
            episode=TmdbEpisode(episode_number=3, name="第三集"),
        ),
    }


def _video(dir_path, name, is_subtitle=False):
    path = dir_path / name
    path.write_text("x", encoding="utf-8")
    return FileInfo(
        id=name, source="local", path=str(path), filename=name,
        extension=".srt" if is_subtitle else ".mkv",
        parent_dir=str(dir_path), is_subtitle=is_subtitle,
    )


def _setup(dir_path):
    """一个含「已存在」「可跟随」「不落地」三种情形的批次。

    第三种是**必须**的: 少了它, 两条路径在「文件未改名 → 不写 NFO 但必须报出来」
    这条规则上的分叉完全不可见（execute_one 曾漏掉那条 nfo_skipped 记录, 而
    三条断言全绿）。
    """
    files = [
        _video(dir_path, "Show.S01E01.mkv"),
        _video(dir_path, "Show.S01E02.mkv"),
        _video(dir_path, "Show.S01E02.chs.srt", is_subtitle=True),
        # 源文件**不存在** → status="failed" → 不落地。FileInfo 照造, 但不写盘。
        FileInfo(
            id="Show.S01E03.mkv", source="local",
            path=str(dir_path / "Show.S01E03.mkv"),
            filename="Show.S01E03.mkv", extension=".mkv",
            parent_dir=str(dir_path),
        ),
    ]
    # E02 的目标 NFO 先占住 → 生成侧报「已存在」
    (dir_path / "Show - S01E02.nfo").write_text("old", encoding="utf-8")
    # E01 的旧前缀 NFO 存在 → 跟随侧把它搬过去
    (dir_path / "Show.S01E01.nfo").write_text("legacy", encoding="utf-8")
    return files


def _run_both(tmp_path):
    """同一批输入各跑一个目录, 返回归一掉目录前缀后的可比较字典。"""
    options = NfoOptions(enabled=True, overwrite=False)
    matches = _matches()

    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    batch = batch_rename(
        _setup(batch_dir), TEMPLATE, overrides=OVERRIDES,
        nfo_options=options, nfo_matches=matches,
    )

    single_dir = tmp_path / "single"
    single_dir.mkdir()
    plans = plan_files(_setup(single_dir), TEMPLATE, overrides=OVERRIDES)
    outcomes = [
        execute_one(p, nfo_options=options, nfo_matches=matches) for p in plans
    ]
    landed = [o.landed_path for o in outcomes if o.landed_path is not None]
    show_written, show_skipped = finalize_show_nfo(plans, landed, matches, options)

    def norm(paths):
        return sorted(
            p.replace(str(batch_dir), "<D>").replace(str(single_dir), "<D>")
            for p in paths
        )

    return {
        "batch_counts": (batch.executed, batch.skipped, batch.failed, batch.total),
        "single_counts": (
            sum(o.executed for o in outcomes),
            sum(o.skipped for o in outcomes),
            sum(o.failed for o in outcomes),
            len(outcomes),
        ),
        "batch_written": norm(batch.nfo_written),
        "single_written": norm(
            [p for o in outcomes for p in o.nfo_written] + show_written
        ),
        "batch_carried": norm(batch.nfo_carried),
        "single_carried": norm([p for o in outcomes for p in o.nfo_carried]),
        "batch_skipped": sorted(
            (norm([d["path"]])[0], d["reason"]) for d in batch.nfo_skipped
        ),
        "single_skipped": sorted(
            (norm([p])[0], r)
            for p, r in dedupe_skipped_pairs(
                [x for o in outcomes for x in o.nfo_skipped] + list(show_skipped)
            )
        ),
    }


def test_fixture_is_not_vacuous(tmp_path):
    """**元判据**: 夹具必须产出非空的四类结果。

    它保护的是下面四条等价断言本身还有鉴别力 —— 夹具一旦退化成空集,
    那四条会静默变成 [] == [] 的摆设。删掉本用例, 这种退化就没有任何机械
    判据能发现（本项目已有三次前科）。
    """
    d = _run_both(tmp_path)
    assert d["batch_written"], "nfo_written 为空 —— 夹具失去鉴别力"
    assert d["batch_carried"], "nfo_carried 为空 —— 夹具失去鉴别力"
    assert d["batch_skipped"], "nfo_skipped 为空 —— 夹具失去鉴别力"
    assert d["batch_counts"][0] > 0, "没有一条 executed —— 夹具失去鉴别力"
    # 这一条钉住 E03 那行不落地的文件: 少了它, counts 断言就从「也钉 failed」
    # 退回「只钉 executed/total」, 而元判据自己不会红。
    assert d["batch_counts"][2] > 0, "没有一条 failed —— 夹具失去鉴别力"


def test_two_paths_agree_on_counts(tmp_path):
    d = _run_both(tmp_path)
    assert d["single_counts"] == d["batch_counts"]


def test_two_paths_agree_on_nfo_written(tmp_path):
    d = _run_both(tmp_path)
    assert d["single_written"] == d["batch_written"]


def test_two_paths_agree_on_nfo_carried(tmp_path):
    d = _run_both(tmp_path)
    assert d["single_carried"] == d["batch_carried"]


def test_two_paths_agree_on_nfo_skipped(tmp_path):
    d = _run_both(tmp_path)
    assert d["single_skipped"] == d["batch_skipped"]


def test_rename_dup_failure_reports_the_bumped_path_on_both_paths(tmp_path, monkeypatch):
    """rename_dup 撞上重命名失败时, 两条路径必须报**同一个**落点。

    `execute_rename_plan` 在**尝试重命名之前**就把 result.new_path 改成了 X_1
    （它那段的 dst 循环), 所以失败时它也指向 X_1; batch_rename 的 nfo_path_by_file
    对任何 `new_path != plan.new_path` 的行都做这个改指向, 于是未落地那一行报的是
    X_1.nfo。execute_one 曾经只在 landed 分支里改 —— 分叉就在这里, 而交叉判据的
    夹具里没有「冲突 + 重命名失败」的行, 所以它看不见。

    把 execute_one 里的改指向挪回 landed 判断**之内**本用例必红。
    """
    import os as _os

    (tmp_path / "Show - S01E01.mkv").write_text("occupied", encoding="utf-8")
    video = _video(tmp_path, "Show.S01E01.mkv")

    real_rename = _os.rename

    def boom(src, dst):
        # 只让**改指向之后**的那个目标失败, 制造「rename_dup 已改 new_path 但
        # 重命名抛错」这一种组合。
        if str(dst).endswith("Show - S01E01_1.mkv"):
            raise OSError(13, "Permission denied")
        return real_rename(src, dst)

    monkeypatch.setattr(_os, "rename", boom)

    options = NfoOptions(enabled=True)
    matches = _matches()

    batch = batch_rename(
        [video], TEMPLATE, overrides=OVERRIDES,
        conflict_strategy="rename_dup", nfo_options=options, nfo_matches=matches,
    )
    plan = plan_files([video], TEMPLATE, overrides=OVERRIDES)[0]
    outcome = execute_one(
        plan, conflict_strategy="rename_dup",
        nfo_options=options, nfo_matches=matches,
    )

    assert outcome.result.status == "failed", outcome.result.status
    bumped = os.path.join(str(tmp_path), "Show - S01E01_1.nfo")
    assert outcome.dead_episode_path == bumped
    assert (bumped, "该文件未改名, 不写 NFO") in [
        (d["path"], d["reason"]) for d in batch.nfo_skipped
    ]


def test_rename_dup_episode_nfo_follows_real_target(tmp_path):
    """X.mkv 落到 X_1.mkv 时, 每集 NFO 必须跟着落 X_1.nfo（Emby 靠同名配对）。

    Review Focus 3。去掉 execute_one 里那句 `decision.path = episode_nfo_path(
    result.new_path)` 本用例必然红 —— 那时 nfo_path 会指向 X.nfo, 而那个名字属于
    **冲突的那一集**（覆盖模式下还会把它的 NFO 改写掉）。
    """
    # 先占住目标名, 逼出 rename_dup 的 _1 后缀
    (tmp_path / "Show - S01E01.mkv").write_text("occupied", encoding="utf-8")
    video = _video(tmp_path, "Show.S01E01.mkv")
    overrides = {"Show.S01E01.mkv": {"show_name": "Show", "season": 1, "episode": 1}}

    plans = plan_files([video], TEMPLATE, overrides=overrides)
    outcome = execute_one(
        plans[0], conflict_strategy="rename_dup",
        nfo_options=NfoOptions(enabled=True), nfo_matches={},
    )

    assert outcome.result.new_path.endswith("Show - S01E01_1.mkv"), outcome.result.new_path
    assert outcome.result.nfo_path.endswith("Show - S01E01_1.nfo"), outcome.result.nfo_path
    assert outcome.landed_path == outcome.result.new_path
```

- [ ] **Step 2: 跑它，确认因 ImportError 而红**

Run: `cd backend && python -m pytest tests/test_single_file_core.py -q`
Expected: FAIL — `ImportError: cannot import name 'execute_one'`

- [ ] **Step 3: 实现 `execute_one`**

在 `local_renamer.py` 的 `batch_rename` **之前**插入（`OneOutcome` 需要 `dataclass`，在文件顶部 `from dataclasses import dataclass, field` 加进 import）：

```python
def landed_path_of(result: RenameResult) -> Optional[str]:
    """该结果是否落地: 落地返回真实落点, 未落地返回 None。

    公开（不带下划线）是因为 OpenList 那条路由也要用它 —— 让 renamer.py 跨模块
    import 私有的 _NO_LANDING_STATUSES 会把「哪些状态算没落地」这条规则散到两处。
    """
    if result.status in _NO_LANDING_STATUSES:
        return None
    return result.new_path


@dataclass
class OneOutcome:
    """单个文件的执行结果，以及它自己的 NFO 副作用。

    只有**每集** NFO 在这里 —— 剧集级 / 季级属于整批, 由 finalize_show_nfo 负责。
    """
    result: RenameResult
    landed_path: Optional[str] = None
    dead_episode_path: Optional[str] = None
    nfo_written: list[str] = field(default_factory=list)
    nfo_carried: list[str] = field(default_factory=list)
    nfo_skipped: list[tuple[str, str]] = field(default_factory=list)
    executed: int = 0
    skipped: int = 0
    failed: int = 0


def execute_one(
    plan: RenamePlan,
    *,
    conflict_strategy: str = "skip",
    nfo_options: NfoOptions | None = None,
    nfo_matches: dict[str, EpisodeMatch] | None = None,
) -> OneOutcome:
    """执行**一个** plan: 重命名 + 每集 NFO + 跟随既有同前缀 NFO。

    与 batch_rename 的每文件循环逐字同源（叶子助手共用）。两处的等价性由
    tests/test_single_file_core.py 的交叉判据钉住 —— 改这里要同时跑它。

    **没有 dry_run 形参**, 这是刻意的: 干跑在本设计里是**批次级**的（spec R9,
    /rename/dry-run 仍是批量请求）。曾经照搬过 dry_run, 后果是
    `status="dry_run"` 不在 _NO_LANDING_STATUSES 里 → landed 为真 → **真的把
    每集 NFO 写下去**（实测: 视频没动、NFO 已写）。一个名为 dry_run 的分支会
    改盘, 比没有这个参数糟得多。要加回来, 必须同时加一个能红的判据。
    """
    nfo_matches = nfo_matches or {}
    # 冲突行走 abort 时 result 是合成的, 但**不能提前 return**: 下面那段
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
        result = execute_rename_plan(plan, conflict_strategy=conflict_strategy)

    outcome = OneOutcome(result=result)
    is_video = not _is_subtitle_file(plan.file_info)
    landed = landed_path_of(result) is not None
    decision = (
        _episode_decision_for(plan, nfo_matches, nfo_options)
        if nfo_options is not None
        else None
    )

    # --- 跟随既有同前缀 NFO。**必须在写每集 NFO 之前**, 与 batch_rename 同序 ---
    #
    # 顺序是有意的, 理由与 local_renamer.py:392-396 那段逐字相同: 「生成开 +
    # 覆盖关」时, 先搬过去的旧 NFO 占住新位置, 生成于是报「已存在」, 用户原有的
    # 内容得以保留。反过来（先生成再搬）会让生成先写、搬动再撞上「目标已存在」
    # 而放弃 —— 用户的内容被生成结果替掉, 旧文件还在原处当孤儿。
    if not aborted and is_video and result.status in _CARRY_STATUSES:
        carried_path, carry_reason = carry_same_stem_nfo(
            plan.original_path, result.new_path
        )
        if carried_path is not None:
            outcome.nfo_carried.append(carried_path)
        elif carry_reason is not None:
            outcome.nfo_skipped.append(
                (episode_nfo_path(result.new_path), carry_reason)
            )

    # --- 写每集 NFO（在跟随之后）---
    if decision is not None:
        # rename_dup（「自动编号」）下真实落点是 X_1.mkv, 而每集决策是按
        # plan.new_path 算的 —— 不跟着改指向的话, 改名后的视频拿不到与它同名
        # 的 X_1.nfo（Emby 靠同名配对）, 而 NFO 会落到 X.nfo: 那是**冲突那一
        # 集**的位置, 覆盖模式下还会把它改写掉。
        #
        # **改指向必须在 landed 判断之前**, 这是与 batch_rename 的逐字一致:
        # execute_rename_plan 是在**尝试重命名之前**就把 result.new_path 改成
        # X_1 的, 所以重命名**失败**时它也指向 X_1, 而 batch_rename 的
        # nfo_path_by_file 对任何 `new_path != plan.new_path` 的行都做这个改指向
        # —— 于是未落地那一行报的也是 X_1.nfo。只在 landed 分支里改会让两条路径
        # 对同一个失败行报出不同的落点（实测分叉: batch 报 X_1.nfo, 单文件报
        # X.nfo）, 而夹具里没有「冲突 + 重命名失败」的行, 交叉判据看不见它。
        if result.new_path != plan.new_path:
            decision.path = episode_nfo_path(result.new_path)

        if not landed:
            # 它不写, 但必须**报出来**（nfo_skipped）—— 静默地少写一个 NFO 与
            # 静默地写错一个一样不可见。batch_rename 里 `dead_episode_paths`
            # 那段做同一件事。**漏掉这一句就是两条路径的分叉**: 交叉判据在夹具
            # 含不落地文件时会红。
            outcome.dead_episode_path = decision.path
            outcome.nfo_skipped.append(
                (decision.path, _NOT_RENAMED_NFO_REASON)
            )
        else:
            # nfo_path 报的是**计划落点**, 与是否真的写下去无关 —— 与
            # batch_rename 里 nfo_path_by_file 的语义一致（内容为 None 时它也设）。
            result.nfo_path = decision.path
            written, skipped = write_nfo_files(
                [decision], overwrite=bool(nfo_options and nfo_options.overwrite)
            )
            outcome.nfo_written = written
            outcome.nfo_skipped.extend(skipped)

    if is_video:
        outcome.landed_path = landed_path_of(result)

    outcome.executed, outcome.skipped, outcome.failed = count_result(result, aborted)
    return outcome
```

**注意**：上面那个 `elif ... pass` 分支是**故意的空分支**，写出来是为了让「这里没有决策」这件事在代码里可见。如果你觉得它噪音太大，可以删掉整段 `elif` —— 但**不要**改成写 NFO。

- [ ] **Step 4: 实现 `finalize_show_nfo`**

紧接 `execute_one` 之后插入：

```python
def finalize_show_nfo(
    plans: list[RenamePlan],
    landed_paths: list[str],
    nfo_matches: dict[str, EpisodeMatch],
    options: NfoOptions,
) -> tuple[list[str], list[tuple[str, str]]]:
    """批次收尾: 只写剧集级 / 季级 NFO。返回 (写入的路径, [(跳过路径, 原因)])。

    landed_paths 必须是**真实落点**（前端从单文件响应回传）而不是「假定都成功」:
    整批一个都没落地时, 组级落点就是凭空推出来的 —— 写下去会在一个没有任何剧集
    文件的目录里放一份 tvshow.nfo（spec §9.4 的库根污染）。

    组级决策的 NfoEntry 用 plan.new_path 而非 landed_paths 里的真实路径 —— 推导链
    （common_parent / _show_root / _folder_belongs_to_single_show）只消费
    os.path.dirname, 而 rename_dup 只改文件名词干、目录不变, 两者结论必然相同。
    见 spec R14。
    """
    if not options.enabled or not plans:
        return [], []

    entries = [
        _entry_for(plan, nfo_matches)
        for plan in plans
        if not _is_subtitle_file(plan.file_info)
    ]
    if not entries:
        return [], []

    group_decisions = [
        d for d in build_nfo_decisions(entries, options) if d.kind != "episode"
    ]
    skipped_pairs: list[tuple[str, str]] = []

    kept: list[NfoDecision] = []
    for decision in group_decisions:
        if _keep_decision(decision, set(), landed_paths):
            kept.append(decision)
        else:
            # 组级决策被丢弃 = 那份剧集级/季级 NFO 不会写。**丢弃要报出来**:
            # 静默扔掉的话结果里既没有落点也没有跳过记录, 用户无从知道这部剧本该
            # 有的 tvshow.nfo 为什么一个都没写。
            skipped_pairs.append((decision.path, _DROPPED_GROUP_NFO_REASON))

    written, write_skipped = write_nfo_files(kept, overwrite=options.overwrite)
    skipped_pairs.extend(write_skipped)
    return written, dedupe_skipped_pairs(skipped_pairs)
```

- [ ] **Step 5: 跑新测试**

Run: `cd backend && python -m pytest tests/test_single_file_core.py -q`
Expected: 7 passed

若 `test_two_paths_agree_on_nfo_skipped` 红，先**不要**改测试：说明两条路径的跳过语义确有差异，逐条比对 `batch.nfo_skipped` 与算出来的 `got`，把差异定位到 `execute_one` 或 `finalize_show_nfo`，修实现。

- [ ] **Step 6: 跑全套**

Run: `cd backend && python -m pytest -q`
Expected: 221 passed（214 + 7）

- [ ] **Step 7: 提交**

```bash
git add backend/app/core/local_renamer.py backend/tests/test_single_file_core.py
git commit -m "feat(local_renamer): 新增 execute_one 与 finalize_show_nfo，并以交叉判据钉住与批量路径的等价性"
```

---

### Task 3: `execute_openlist_one`

**Files:**
- Modify: `backend/app/core/openlist_renamer.py`
- Test: `backend/tests/test_openlist_single.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `async def execute_openlist_one(client: OpenListClient, plan: RenamePlan) -> RenameResult`（**无 `dry_run`**：干跑是批次级的，本函数在生产里只被 /rename/execute 以「真执行」调用；一个没有调用者的分支就是一处没有判据的分支）

**背景**：`execute_openlist_batch` 用 `client.batch_rename(dir_path, objs)` 把同目录的多个重命名合并成**一次** API 调用。单文件化后每次请求只有一个文件，故改用 `client.rename(path, new_name)`（同目录改名）与 `client.move(src_dir, dst_dir, [name])`（跨目录）。

- [ ] **Step 1: 写测试（先红）**

新建 `backend/tests/test_openlist_single.py`：

```python
"""OpenList 单文件执行的判据。

异步驱动用**标准库 asyncio.run**, 与 test_tmdb_client.py / test_tmdb_resolver.py
一致 —— 本项目**未装 pytest-asyncio**（requirements-dev.txt 只有 pytest, 且
test_tmdb_client.py 开头把这件事写成了明文的约定）。没有插件时
`@pytest.mark.asyncio` 只是个未知标记, 用例会以「async def functions are not
natively supported」失败, 而补 `asyncio_mode = auto` 也救不了（那个键会被报成
Unknown config option, 只是多一条告警）。
"""
import asyncio

from app.core.openlist_renamer import build_openlist_rename_plan, execute_openlist_one
from app.models.file import FileInfo

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"


class FakeClient:
    """记录调用序列的假客户端。"""

    def __init__(self, fail_rename=False):
        self.calls = []
        self.fail_rename = fail_rename

    async def rename(self, path, new_name):
        self.calls.append(("rename", path, new_name))
        if self.fail_rename:
            raise Exception("重命名失败")
        return {"code": 200}

    async def move(self, src_dir, dst_dir, names):
        self.calls.append(("move", src_dir, dst_dir, tuple(names)))
        return {"code": 200}

    async def mkdir(self, parent_dir, dir_name):
        self.calls.append(("mkdir", parent_dir, dir_name))
        return {"code": 200}

    async def batch_rename(self, src_dir, objs):
        # 单文件路径**不得**调用它 —— 见本任务 Step 3 的断言
        self.calls.append(("batch_rename", src_dir, tuple(o.new_name for o in objs)))
        return {"code": 200}


def _file(name, parent="/media/Show"):
    return FileInfo(
        id=name, source="openlist", path=f"{parent}/{name}", filename=name,
        extension=".mkv", parent_dir=parent,
    )


def test_same_dir_rename_uses_rename_api():
    f = _file("Show.S01E01.mkv")
    plan = build_openlist_rename_plan(
        f, TEMPLATE,
        override=None,
    )
    client = FakeClient()
    result = asyncio.run(execute_openlist_one(client, plan))
    assert result.success is True
    assert result.status == "renamed"
    assert result.new_filename == "Show - S01E01.mkv"
    assert client.calls == [("rename", f.path, "Show - S01E01.mkv")]


def test_same_name_is_skipped_without_any_call():
    f = _file("Show - S01E01.mkv")
    plan = build_openlist_rename_plan(f, TEMPLATE)
    client = FakeClient()
    result = asyncio.run(execute_openlist_one(client, plan))
    assert result.status == "skipped_same"
    assert client.calls == []


def test_move_plan_moves_then_renames():
    f = _file("Show.S01E01.mkv")
    plan = build_openlist_rename_plan(
        f, TEMPLATE, folder_template="Season {season_padded}",
        create_season_folder=True,
    )
    # {season_padded} 走全局默认补零 2 位 → "Season 01"（config.py 的
    # season_pad_digits = 2）。断言写成 "Season 1" 会红。
    assert plan.new_dir.endswith("Season 01"), plan.new_dir
    client = FakeClient()
    result = asyncio.run(execute_openlist_one(client, plan))
    assert result.success is True
    assert client.calls[0][0] == "mkdir"
    assert client.calls[1] == ("move", "/media/Show", "/media/Show/Season 01",
                               ("Show.S01E01.mkv",))
    # **整条元组**, 不只 `[0] == "rename"`: 这一行的正确性全在路径拼接上
    # （openlist_renamer 用 PurePosixPath(new_dir) / original_filename 拼源路径）。
    # 只断言方法名的话, 传 plan.original_path（移动**前**的路径）或 plan.new_filename
    # 当源路径都照样绿 —— 那正是这个断言该拦住的错。
    assert client.calls[2] == ("rename", "/media/Show/Season 01/Show.S01E01.mkv",
                               "Show - S01E01.mkv")


def test_rename_failure_is_reported_not_raised():
    f = _file("Show.S01E01.mkv")
    plan = build_openlist_rename_plan(f, TEMPLATE)
    client = FakeClient(fail_rename=True)
    result = asyncio.run(execute_openlist_one(client, plan))
    assert result.success is False
    assert result.status == "failed"
    assert "重命名失败" in result.error


def test_move_without_rename_skips_the_rename_call():
    """名字已经正确、只有目录要变时, **不得**多发一次 rename。

    `if not same_name:` 那道守卫在生产可达（用户把已正确命名的文件挪进季目录,
    或模板改了季目录模板）。删掉守卫本用例必红: calls 里会多出一次 rename。
    """
    f = _file("Show - S01E01.mkv")
    plan = build_openlist_rename_plan(
        f, TEMPLATE, folder_template="Season {season_padded}",
        create_season_folder=True,
    )
    assert plan.original_filename == plan.new_filename, plan.new_filename
    assert plan.original_dir != plan.new_dir

    client = FakeClient()
    result = asyncio.run(execute_openlist_one(client, plan))

    assert result.status == "renamed_moved"
    assert client.calls == [
        ("mkdir", "/media/Show", "Season 01"),
        ("move", "/media/Show", "/media/Show/Season 01", ("Show - S01E01.mkv",)),
    ]


def test_never_calls_batch_rename():
    """单文件路径不得退化成批量 API —— 那会把「一个文件一次请求」的语义悄悄改掉。"""
    f = _file("Show.S01E01.mkv")
    plan = build_openlist_rename_plan(f, TEMPLATE)
    client = FakeClient()
    asyncio.run(execute_openlist_one(client, plan))
    assert all(c[0] != "batch_rename" for c in client.calls)
```

- [ ] **Step 2: 跑它，确认红**

Run: `cd backend && python -m pytest tests/test_openlist_single.py -q`
Expected: FAIL — `ImportError: cannot import name 'execute_openlist_one'`（若报 `asyncio_mode` 相关错误，见 Step 3 的 `pytest.ini` 说明）

- [ ] **Step 3: 确认异步测试的驱动方式（**不要**引入 pytest-asyncio）**

Run: `cd backend && cat requirements-dev.txt && cat pytest.ini && python -c "import pytest_asyncio"`

Expected: `requirements-dev.txt` 里只有 `pytest`；`pytest.ini` 里**没有** `asyncio_mode`；`import pytest_asyncio` 报 `ModuleNotFoundError`。

这就是本仓库的既有约定 —— `tests/test_tmdb_client.py:1` 写着「本项目未装 pytest-asyncio，用标准库 asyncio.run 驱动异步断言」。**照办**：不要安装新依赖，也不要往 `pytest.ini` 加 `asyncio_mode`（那个键没有插件时只会被报成 `Unknown config option`，多一条告警而救不了任何用例）。测试文件按 Step 1 给的 `asyncio.run(...)` 写法。

若环境**意外**装了 pytest-asyncio（`import` 成功），先如实记录，再照 Step 1 的写法走 —— `asyncio.run` 在任何一种模式下都成立。

- [ ] **Step 4: 实现 `execute_openlist_one`**

在 `openlist_renamer.py` 末尾追加（`RenameResult`、`_ensure_dir` 已在文件里）：

```python
async def execute_openlist_one(
    client: OpenListClient,
    plan: RenamePlan,
) -> RenameResult:
    """执行**一个** OpenList plan。

    与 execute_openlist_batch 的差别不只是循环: 批量版用 client.batch_rename 把
    同目录的多个改名合并成一次 API 调用, 单文件版没有可合并的对象, 改用
    client.rename / client.move。故两个函数的调用序列不同 —— 这是单文件化的
    直接代价, 由前端并发数与客户端限流器共同约束请求量。
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
    try:
        if not same_dir:
            await _ensure_dir(client, plan.new_dir, dir_cache)
            await client.move(plan.original_dir, plan.new_dir, [plan.original_filename])
            if not same_name:
                await client.rename(
                    str(PurePosixPath(plan.new_dir) / plan.original_filename),
                    plan.new_filename,
                )
            result.success = True
            result.status = "renamed_moved"
        else:
            await client.rename(plan.original_path, plan.new_filename)
            result.success = True
            result.status = "renamed"
    except Exception as exc:
        result.success = False
        result.error = str(exc)
        result.status = "failed"

    return result
```

- [ ] **Step 5: 跑测试**

Run: `cd backend && python -m pytest tests/test_openlist_single.py -q`
Expected: 5 passed

- [ ] **Step 6: 跑全套**

Run: `cd backend && python -m pytest -q`
Expected: 227 passed（221 + 6）

- [ ] **Step 7: 提交**

```bash
git add backend/app/core/openlist_renamer.py backend/tests/test_openlist_single.py backend/pytest.ini
git commit -m "feat(openlist_renamer): 新增 execute_openlist_one，改用 rename/move 逐文件执行"
```

---

### Task 4: `OpenListClient` 的可调限流器

**Files:**
- Modify: `backend/app/core/openlist_client.py`
- Test: `backend/tests/test_openlist_limiter.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces:
  - `class _AdaptiveLimiter`，方法 `async __aenter__()` / `async __aexit__(*a)` / `set_limit(n: int) -> None`
  - `OpenListClient.apply_limits(max_concurrent: int | None = None, request_interval: float | None = None) -> None`
  - `OpenListClient._request_interval: float`（实例属性，初值取 `settings.openlist_request_interval`）

- [ ] **Step 1: 写测试（先红）**

新建 `backend/tests/test_openlist_limiter.py`：

```python
"""限流器必须真的限流，且上限可运行时调整。

异步驱动用**标准库 asyncio.run** —— 本项目未装 pytest-asyncio（理由与写法见
tests/test_openlist_single.py 的模块注释）。
"""
import asyncio

import httpx

from app.core.openlist_client import OpenListClient, _AdaptiveLimiter


def test_limiter_never_exceeds_limit():
    async def _run():
        limiter = _AdaptiveLimiter(2)
        peak = 0
        active = 0

        async def worker():
            nonlocal peak, active
            async with limiter:
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(*[worker() for _ in range(10)])
        return peak

    peak = asyncio.run(_run())
    assert peak == 2, f"峰值并发 {peak}，上限 2 未被遵守"


def test_limit_can_be_lowered_at_runtime():
    """调低之后必须**立刻**生效 —— 这是设置页「立即生效」的全部含义。"""
    async def _run():
        limiter = _AdaptiveLimiter(5)
        limiter.set_limit(1)
        peak = 0
        active = 0

        async def worker():
            nonlocal peak, active
            async with limiter:
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(*[worker() for _ in range(6)])
        return peak

    peak = asyncio.run(_run())
    assert peak == 1, f"调低后峰值并发 {peak}，期望 1"


def test_limit_can_be_raised_at_runtime():
    """调高时必须把等待者**全部**唤醒，否则多出来的名额要等下一轮释放才生效。

    判据是 `set_limit` 返回**那一刻**队列里还剩几个等待者 —— 同步可观测, 不依赖
    时序: 调高到 3 而此刻只有 1 个在跑, 队列里的 2 个必须当场被全部摘走。
    `_wake(1)` 会留下 1 个 → 红; 一个都不唤醒 → 留下 2 个 → 红。

    **不用「峰值 == 3」当判据**: 那要求唤醒发生在持有者那 0.05s 睡眠之内, 被 OS
    级调度停顿 50ms 以上就会偶发变成 2（实测 20/20 稳定, 但它依赖时序）。
    峰值只留作附加的健全性检查。
    """
    async def _run():
        limiter = _AdaptiveLimiter(1)
        active = 0
        peak = 0
        started = asyncio.Event()

        async def worker():
            nonlocal active, peak
            async with limiter:
                active += 1
                peak = max(peak, active)
                if active == 1:
                    started.set()
                await asyncio.sleep(0.05)
                active -= 1

        tasks = [asyncio.create_task(worker()) for _ in range(3)]
        await started.wait()
        # 让另外两个确定地排进等待队列（create_task 只是调度, 未必已运行）
        await asyncio.sleep(0.01)
        limiter.set_limit(3)
        # **同步观测**: 此处还没有 await, 被唤醒者尚未运行
        remaining = len(limiter._waiters)
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=1.0)
        return peak, remaining

    peak, remaining = asyncio.run(_run())
    assert remaining == 0, f"调高后仍有 {remaining} 个等待者没被唤醒"
    assert peak >= 2, f"调高后峰值并发仍为 {peak}，等待者未被唤醒"


def test_reconnect_does_not_deadlock_at_limit_one(monkeypatch):
    """401 重连时**不得**持着名额再要名额 —— limit=1 下那会永久挂住。

    这是 `_request` 这条路径的**第一个**判据。把实现改回「持着名额递归调用
    自己」（旧版形状）本用例会挂到 `wait_for` 超时 —— 超时即红, 不是断言失败。

    用假的 `httpx.AsyncClient` 喂三次响应: 401（token 过期）→ login 成功 →
    重试成功。`_reconnect` 会调 `login`, 而 `login` 期望的响应形状请照
    `openlist_client.py` 里 `login` 的实际读取路径造（读 token 的字段名以那里
    为准, 本用例不该猜）。
    """
    import app.core.openlist_client as mod

    class _FakeAsyncClient:
        responses: list = []
        calls: list = []

        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def request(self, method, url, **kwargs):
            _FakeAsyncClient.calls.append((method, url))
            status, payload = _FakeAsyncClient.responses.pop(0)
            return httpx.Response(status, json=payload, request=httpx.Request(method, url))

    async def _run():
        client = mod.OpenListClient("http://x", "u", "p")
        client.token = "expired-token"
        # **请求间隔归零**: 默认 0.5s × 3 次请求 = 1.5s, 而下面的 wait_for 超时
        # 是 2.0s —— 余量只剩 0.5s, 机器一停顿就会**假红**。而假红的信号
        # （TimeoutError）与真死锁**一模一样**, 会把人骗去查一个不存在的死锁。
        # 请求间隔与死锁无关, 归零后耗时降到毫秒级。
        client.apply_limits(max_concurrent=1, request_interval=0.0)
        _FakeAsyncClient.calls = []
        # **四次**, 不是三次: `login()` 结尾还会 `await self._discover_mounts()`,
        # 那又是一次请求。按 `openlist_client.py` 里 login / _discover_mounts 的
        # 实际读取路径造响应; 少一条会在第四次 pop 时 IndexError, 红的理由就不是
        # 死锁了（判据红得对但红得没意义）。
        _FakeAsyncClient.responses = [
            (401, {}),                                        # 1. fs/get: token 过期
            (200, {"code": 200, "data": {"token": "new"}}),    # 2. auth/login
            (200, {"code": 200, "data": {"content": []}}),     # 3. fs/list (discover_mounts)
            (200, {"code": 200, "data": {"ok": True}}),        # 4. 重试 fs/get
        ]
        monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeAsyncClient)
        # 超时即红: 死锁时这个 await 永远不会返回
        return await asyncio.wait_for(client._request("POST", "/api/fs/get"), timeout=2.0)

    data = asyncio.run(_run())
    assert data == {"code": 200, "data": {"ok": True}}
    assert len(_FakeAsyncClient.calls) == 4, _FakeAsyncClient.calls


def test_login_endpoint_401_does_not_recurse(monkeypatch):
    """login 端点自己回 401 时**不得**无限递归。

    `_reconnect` 若不清 token, login 发出的那个请求仍带着已知无效的旧 token;
    login 端点回 401 就会再次触发重连 —— 无限递归, 实测 329 次调用后
    RecursionError。旧实现在这里会**先死锁**, 所以这条路径此前从未被观察到,
    是本设计的 `_request` 重构把它暴露出来的。

    判据是**异常类型 + 请求次数**: 修好后是 `httpx.HTTPStatusError`（login 的
    401 直接冒到调用方）且只发 2 次请求（fs/get + login）; 不清 token 时会一直
    递归, 撞上响应脚本耗尽的 AssertionError 或 RecursionError → 本用例红。
    """
    import app.core.openlist_client as mod

    class _FakeAsyncClient:
        responses: list = []
        calls: list = []

        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def request(self, method, url, **kwargs):
            _FakeAsyncClient.calls.append((method, url))
            if not _FakeAsyncClient.responses:
                # 递归时脚本会被耗尽 —— 这个 raise 让失败**看得懂**, 而不是
                # 一直转到 RecursionError 才崩。
                raise AssertionError(f"响应脚本耗尽, 已发 {len(_FakeAsyncClient.calls)} 次请求")
            status, payload = _FakeAsyncClient.responses.pop(0)
            return httpx.Response(status, json=payload, request=httpx.Request(method, url))

    async def _run():
        client = mod.OpenListClient("http://x", "u", "p")
        client.token = "expired-token"
        # 同上: 间隔归零, 免得这条用例在变异实验里跑出 20 多秒
        client.apply_limits(max_concurrent=2, request_interval=0.0)
        _FakeAsyncClient.calls = []
        # 全部回 401 —— **包括 login 那一次**
        _FakeAsyncClient.responses = [(401, {})] * 50
        monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeAsyncClient)
        try:
            await client._request("POST", "/api/fs/get")
        except BaseException as exc:  # noqa: BLE001 — 本用例要断言异常的**类型**
            return type(exc), len(_FakeAsyncClient.calls)
        raise AssertionError("_request 不该正常返回")

    exc_type, calls = asyncio.run(_run())
    assert exc_type is httpx.HTTPStatusError, f"期望 HTTPStatusError, 得到 {exc_type}"
    assert calls == 2, f"期望 2 次请求 (fs/get + login), 实际 {calls}"


def test_apply_limits_is_a_noop_when_unchanged():
    """值没变就不动 —— 每次请求都替换限流器会摧毁限流本身（spec R13）。

    **两个方向都要钉**:
    · 字段为 None（未提供）→ 不动;
    · 字段**等于当前值** → 也不动。

    只钉前者的判据对「apply_limits 在值非 None 时重建 limiter」这一变异是
    **失明的** —— 而那正是本任务存在的理由（spec R13）。实测: 去掉下面第二段,
    把 `self._limiter.set_limit(...)` 写成 `self._limiter = _AdaptiveLimiter(...)`
    时五条判据全绿。
    """
    client = OpenListClient("http://x", "u", "p")
    before = client._limiter
    client.apply_limits(max_concurrent=None, request_interval=None)
    assert client._limiter is before, "未提供时不该动 limiter"

    # 传**当前值**（而非 None）—— 这一条才拦得住「重建」那种写法
    client.apply_limits(
        max_concurrent=before._limit,
        request_interval=client._request_interval,
    )
    assert client._limiter is before, "值未变时不该重建 limiter"


def test_apply_limits_sets_interval():
    client = OpenListClient("http://x", "u", "p")
    client.apply_limits(request_interval=1.25)
    assert client._request_interval == 1.25
```

- [ ] **Step 2: 跑它，确认红**

Run: `cd backend && python -m pytest tests/test_openlist_limiter.py -q`
Expected: FAIL — `ImportError: cannot import name '_AdaptiveLimiter'`

- [ ] **Step 3: 实现限流器与 `apply_limits`**

在 `openlist_client.py` 顶部（`class OpenListClient` 之前）插入：

```python
class _AdaptiveLimiter:
    """上限可变的并发限流器。

    为什么不用 asyncio.Semaphore 再「需要时换一个」: 替换对象会摧毁限流本身 ——
    在途持有者释放到旧对象, 新对象满额放行, 于是瞬时并发翻倍; 而「值没变就不
    替换」的补丁仍在首个请求处留下抖动。计数器 + 等待者队列是十几行代码,
    且上限可以在等待者入睡之后被调高（被唤醒的等待者重新判条件）。

    **等待者用 Future 而不是 asyncio.Condition**: `Condition.notify*` 必须在
    **持有锁**时调用, 而 `set_limit` 是同步方法（`apply_limits` 也可以从同步
    上下文调用, 见测试里的 `limiter.set_limit(1)`）—— 同步方法没有办法不阻塞
    事件循环地拿到 asyncio.Lock, 直接 notify 会抛
    `RuntimeError: cannot notify on un-acquired lock`。Future 由事件循环线程
    直接 set_result, 同步、即时, 且在没有等待者（也就没有运行中的循环）时天然
    是安全的空操作。
    """

    def __init__(self, limit: int):
        self._limit = max(1, int(limit))
        self._active = 0
        self._waiters: list[asyncio.Future] = []

    async def __aenter__(self):
        while self._active >= self._limit:
            waiter = asyncio.get_running_loop().create_future()
            self._waiters.append(waiter)
            try:
                await waiter
            except BaseException:
                # 被取消。若这个等待者已经吃掉了 _wake 发出的唤醒名额（它已被
                # 摘出队列 = 名额已发到它手上）, 必须把名额转交给下一个等待者,
                # 否则名额空着而后面的人还在睡 —— 这是真实可复现的丢唤醒, 不是
                # 理论担忧。asyncio.Lock 在取消路径上做的也是同一件事。
                if waiter not in self._waiters:
                    self._wake(1)
                raise
            finally:
                # 正常唤醒时已被 _wake 摘掉; 未被唤醒（取消）时还留在队列里, 自己摘。
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
        # 判断与自增之间没有 await ⇒ 与其它任务之间是原子的。
        self._active += 1
        return self

    async def __aexit__(self, *exc_info):
        self._active -= 1
        self._wake(1)

    def set_limit(self, limit: int) -> None:
        limit = max(1, int(limit))
        # 值未变就直接返回。这道早退**行为上不可观测**: 队列非空时必然
        # _active >= _limit, 故 limit == _limit 时下面的 `limit > _active` 恒为假,
        # 不会误唤醒任何人。留着是让「值没变」这件事在代码里看得见 ——
        # 别为它写判据（写不出能红的）。
        if limit == self._limit:
            return
        self._limit = limit
        # 调高后必须唤醒等待者: 它们在旧的（更小的）上限下已入睡, 不会再自己醒。
        if limit > self._active:
            self._wake(limit - self._active)

    def _wake(self, count: int) -> None:
        """唤醒至多 count 个等待者。

        被唤醒者会重新判条件, 抢不到名额的会再排队 —— 而每次释放都会再唤醒
        一个, 所以不存在「有人睡着但名额空着」的窗口。
        """
        while count > 0 and self._waiters:
            waiter = self._waiters.pop(0)
            if waiter.done():
                continue  # 已被取消
            waiter.set_result(None)
            count -= 1
```

把 `OpenListClient.__init__` 里的

```python
        self._semaphore = asyncio.Semaphore(settings.openlist_max_concurrent)
        self._lock = asyncio.Lock()
```

替换为：

```python
        self._limiter = _AdaptiveLimiter(settings.openlist_max_concurrent)
        # 间隔值放在**实例**上（原来是每次读全局 settings）, 否则设置页的值无法
        # 在运行时生效 —— 见 spec §7.2。
        self._request_interval = settings.openlist_request_interval
        self._lock = asyncio.Lock()
```

把 `_wait_interval` 里的

```python
        now = time.monotonic()
        elapsed = now - self.last_request_time
        if elapsed < settings.openlist_request_interval:
            await asyncio.sleep(settings.openlist_request_interval - elapsed)
```

替换为：

```python
        now = time.monotonic()
        elapsed = now - self.last_request_time
        if elapsed < self._request_interval:
            await asyncio.sleep(self._request_interval - elapsed)
```

把 `_request` **重构为「限流器只包住单次 HTTP 尝试」**（不是只把 `async with` 的目标换掉）：

```python
    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """发一次请求（401 时自动重连后重试一次）。

        **限流器只包住单次 HTTP 尝试, 不包住重连** —— 这是刻意的, 也是本次
        重构的全部理由: `_reconnect` 会走 `login` → `_request`, 也就是**在持着
        名额的情况下再要一个名额**。在途请求数已达上限时（每个都撞上 401）
        外层名额永不释放、内层永远拿不到 —— 死锁。

        这不是新引入的: 旧版 `asyncio.Semaphore(settings.openlist_max_concurrent)`
        持着名额递归调用自己, 同样会死锁（默认 3 时, 3 个在途请求同时 401 即
        触发）。但本函数此前**没有任何测试**, 这条路径至今没有判据 —— 本次
        顺带补上（见 Step 1 的 test_reconnect_does_not_deadlock_at_limit_one）。

        与旧实现唯一的行为差异: 调用方传进来的 `headers` 现在**每次重试都会
        带上**（旧版 `kwargs.pop` 之后递归, 重试时只剩 Authorization）。仓库里
        没有任何调用方传 headers, 且新行为才是对的。
        """
        url = f"{self.server_url}{path}"
        headers = kwargs.pop("headers", {})

        while True:
            async with self._limiter:
                await self._wait_interval()

                req_headers = dict(headers)
                if self.token:
                    req_headers["Authorization"] = self.token

                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0), verify=False) as client:
                        resp = await client.request(method, url, headers=req_headers, **kwargs)
                        self.last_request_time = time.monotonic()
                        resp.raise_for_status()
                        return resp.json()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code != 401 or not self.token:
                        raise
                except httpx.RequestError as e:
                    raise ConnectionError(f"OpenList 请求失败: {e}") from e

            # 走到这里说明撞了 401 且 token 还在 —— **出了 limiter 再重连**。
            # 重连自己会发请求（login）, 在名额内做就会与外层争名额。
            await self._reconnect()
```

把 `_reconnect` 改成**先清 token**：

```python
    async def _reconnect(self) -> None:
        # 先清 token: 它正是引起这次重连的那个**已知无效**的值。不清的话,
        # login 自己发出的那个请求还会带着它 —— 若 login 端点也回 401, 嵌套的
        # _request 会再次触发重连, 无限递归到 RecursionError（实测 329 次调用
        # 后崩）。旧实现在这里会**先死锁**, 所以这条路径此前从未被观察到 ——
        # 是 _request 的重构（把重连移出限流器）把它暴露出来的。
        self.token = None
        self.connected = False
        await self.login()
```

在 `login` 方法之前插入：

```python
    def apply_limits(
        self,
        max_concurrent: Optional[int] = None,
        request_interval: Optional[float] = None,
    ) -> None:
        """把设置页的值应用到本客户端。None = 该字段未提供, 保持当前值。

        **已知副作用**: 限流参数设在进程级单例客户端上, 所以一次执行设下的值会
        持续生效到下次被覆盖 —— 之后的预览、扫描、列目录同样受它约束。单用户
        场景下可接受（设置页的值本就是用户想要的稳态）, 但它是隐性状态。
        """
        if max_concurrent is not None:
            self._limiter.set_limit(max_concurrent)
        if request_interval is not None:
            self._request_interval = request_interval
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && python -m pytest tests/test_openlist_limiter.py -q`
Expected: 7 passed

- [ ] **Step 5: 跑全套**

Run: `cd backend && python -m pytest -q`
Expected: 234 passed（227 + 7）

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/openlist_client.py backend/tests/test_openlist_limiter.py
git commit -m "feat(openlist_client): 限流上限与请求间隔改为可运行时调整"
```

---

### Task 5: 请求模型拆分 + `/rename/execute` 单文件化

**Files:**
- Modify: `backend/app/models/api.py`
- Modify: `backend/app/api/renamer.py`
- Modify: `backend/tests/test_rename_routes.py`、`backend/tests/test_rename_nfo_route.py`、`backend/tests/test_nfo_write.py`（模型级构造，见 Step 5）
- Test: `backend/tests/test_rename_single_route.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `plan_files`、Task 2 的 `execute_one` / `OneOutcome`、Task 3 的 `execute_openlist_one`、Task 4 的 `apply_limits`
- Produces:
  - `RenameBatchRequest`（批量的字段集合）
  - `RenameDryRunRequest(RenameBatchRequest)`
  - `RenameExecuteRequest`（单数：`file_id: str` + `override: dict | None`）
  - `SingleRenameResult`（响应模型）

- [ ] **Step 1: 写新路由的判据（先红）**

新建 `backend/tests/test_rename_single_route.py`：

```python
"""单文件执行路由的契约判据。"""
import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.main import app
from app.models.file import FileInfo

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
OVERRIDE = {"show_name": "Test Show", "season": 1, "episode": 2}


@pytest.fixture
def client():
    cache_files([
        FileInfo(
            id="f1", source="local",
            path="/media/Test Show/Test.Show.S01E02.mkv",
            filename="Test.Show.S01E02.mkv", extension=".mkv",
            parent_dir="/media/Test Show",
        )
    ])
    return TestClient(app)


def payload(**extra):
    body = {
        "file_id": "f1",
        "template": TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "override": OVERRIDE,
        "conflict_strategy": "skip",
    }
    body.update(extra)
    return body


def test_contract_uses_singular_file_id(client):
    """契约是单数 —— 传 file_ids 必须被 Pydantic 拒绝（多的字段不静默吞掉）。"""
    res = client.post("/api/rename/execute", json={
        "file_ids": ["f1"], "template": TEMPLATE, "source": "local",
    })
    assert res.status_code == 422, res.text


def test_singular_override_reaches_the_plan(client):
    """override 必须真的进 plan —— 丢掉它会让文件名少一集/少一季且零报错。

    **用一份与文件名解析结果不同的 override**: 文件名 Test.Show.S01E02.mkv 解析出
    (Test Show, 1, 2), override 把它改成 (Other Show, 5, 9)。文件名随之变成
    Other Show - S05E09.mkv —— 只有 override 真的传到了 plan 才会这样。

    两个 pad 字段**都不传**: 免得把补零也搅进来（那会让本判据分不清是 override
    丢了还是 pad 算错了, 而补零已有自己的判据）。
    """
    res = client.post("/api/rename/execute", json=payload(
        override={"show_name": "Other Show", "season": 5, "episode": 9},
    ))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["file_id"] == "f1"
    assert body["result"]["new_filename"] == "Other Show - S05E09.mkv"
    assert body["result"]["new_path"] == "/media/Test Show/Other Show - S05E09.mkv"


def test_missing_source_file_counts_as_failed(client):
    """fixture 的源文件不在磁盘上 —— 如实报 failed, 且计数为 1。"""
    body = client.post("/api/rename/execute", json=payload()).json()
    assert body["result"]["success"] is False
    assert body["result"]["status"] == "failed"
    assert body["failed"] == 1
    assert body["executed"] == 0
    assert body["skipped"] == 0


def test_unknown_file_id_is_rejected(client):
    res = client.post("/api/rename/execute", json=payload(file_id="nope"))
    assert res.status_code == 400
    assert "未找到" in res.json()["detail"]


class _FakeOpenListClient:
    """OpenList 执行路径的最小替身。"""

    connected = True

    def __init__(self):
        self.calls: list = []

    def apply_limits(self, max_concurrent=None, request_interval=None):
        pass

    async def rename(self, path, new_name):
        self.calls.append(("rename", path, new_name))
        return {"code": 200}

    async def move(self, src_dir, dst_dir, names):
        self.calls.append(("move", src_dir, dst_dir, tuple(names)))
        return {"code": 200}

    async def mkdir(self, parent_dir, dir_name):
        self.calls.append(("mkdir", parent_dir, dir_name))
        return {"code": 200}


def test_openlist_execute_agrees_with_preview_on_the_target_path(monkeypatch):
    """OpenList 的**执行**目标必须与**预览**逐字一致。

    两个 builder **不等价**: build_rename_plan 在父目录已是季目录时会抑制建季目录
    （local_renamer._parent_is_season_dir）, build_openlist_rename_plan 不会。
    执行分支若借道 plan_files, 同一份输入下预览报一个落点、执行做另一个 ——
    「预览说一套、执行做另一套」, 本仓库最忌讳的一类。把 openlist 分支改回
    plan_files 本用例必红。

    这也是 OpenList **执行**路由的第一条判据（此前一条都没有）。
    """
    import app.api.renamer as renamer_mod

    fake = _FakeOpenListClient()
    monkeypatch.setattr(renamer_mod, "get_default_client", lambda: fake)

    # 父目录**本身**就是季目录 → 两个 builder 在这里分道扬镳
    cache_files([FileInfo(
        id="f1", source="openlist",
        path="/media/Show/Season 02/Show.S02E03.mkv",
        filename="Show.S02E03.mkv", extension=".mkv",
        parent_dir="/media/Show/Season 02",
    )])
    client = TestClient(app)
    common = {
        "template": TEMPLATE,
        # **故意发大写**: 单文件响应里的 source 必须与批量路径一样是**规范化后**
        # 的 "openlist"（批量路径在 BatchRenameResult 里硬编码小写）。直接透传
        # req.source 时本断言红 —— 那是这条字段唯一的判据。
        "source": "OpenList",
        "path": "/media/Show/Season 02",
        "folder_template": "Season {season_padded}",
        "create_season_folder": True,
    }
    override = {"show_name": "Show", "season": 2, "episode": 3}

    preview = client.post("/api/rename/preview", json={
        **common, "file_ids": ["f1"], "overrides": {"f1": override},
    })
    assert preview.status_code == 200, preview.text
    expected = preview.json()["results"][0]["new_path"]

    executed = client.post("/api/rename/execute", json={
        **common, "file_id": "f1", "override": override,
    })
    assert executed.status_code == 200, executed.text
    assert executed.json()["result"]["new_path"] == expected, (
        "执行落点与预览不一致 —— 两个 builder 被混用了"
    )
    assert executed.json()["source"] == "openlist", "响应里的 source 必须是规范化后的小写"


def test_generate_nfo_flag_controls_the_episode_decision(tmp_path):
    """generate_nfo=False 时**不该**产生任何每集 NFO 决策; 开了就必须有。

    判据用 `result.nfo_path`: None 表示「这条路径根本没进 NFO 管线」。

    夹具必须让文件**真的改名成功**: 源文件不存在时那一行本来就是 `failed`、
    本来就不写 NFO, 断言 `nfo_written == []` 近乎恒真 —— 实测把 `generate_nfo`
    恒置 True 时六条判据全绿, 即原来那条对「忽略开关」这个变异是失明的。

    两个方向各跑一个目录: 第一次 execute 会把文件改名, 同一目录再跑第二次就
    找不到源文件了。
    """
    def _run(dir_name, generate_nfo):
        d = tmp_path / dir_name
        d.mkdir()
        video = d / "Test.Show.S01E02.mkv"
        video.write_text("x", encoding="utf-8")
        cache_files([FileInfo(
            id="f1", source="local", path=str(video),
            filename="Test.Show.S01E02.mkv", extension=".mkv",
            parent_dir=str(d),
        )])
        return TestClient(app).post("/api/rename/execute", json={
            "file_id": "f1", "template": TEMPLATE, "source": "local",
            "path": str(d), "override": OVERRIDE, "conflict_strategy": "skip",
            "generate_nfo": generate_nfo,
        }).json()

    off = _run("off", False)
    assert off["result"]["status"] == "renamed", off["result"]
    assert off["result"]["nfo_path"] is None
    assert off["nfo_written"] == []

    # 对照: 开了就必须有决策。未配 TMDB → 内容为 None、写不出文件, 但**落点在**。
    # 少了这一半, 「忽略 generate_nfo」的变异不会红。
    on = _run("on", True)
    assert on["result"]["status"] == "renamed", on["result"]
    assert on["result"]["nfo_path"] is not None


def test_abort_marks_the_file_as_conflict(tmp_path):
    """abort 在单文件下是「这一个文件不执行」, 不是「整批中止」。

    计数沿用既有归法: abort 下的冲突行计入 **failed** 而非 skipped（batch_rename
    里那段注释写明了这点）。这条判据钉住 execute_one 里**合成冲突结果**那条分支 ——
    Task 2 结束时它还没有任何判据（夹具里没有冲突文件、也没有 abort 用例）。
    把 `aborted` 判断删掉（让它照常走 execute_rename_plan）本用例必红: 那时
    conflict_strategy="abort" 仍会给出 status="conflict", 但计数会落到 skipped。
    """
    video = tmp_path / "Test.Show.S01E02.mkv"
    video.write_text("x", encoding="utf-8")
    # 目标名已被占住 → 触发冲突
    (tmp_path / "Test Show - S01E02.mkv").write_text("occupied", encoding="utf-8")
    cache_files([FileInfo(
        id="f1", source="local", path=str(video),
        filename="Test.Show.S01E02.mkv", extension=".mkv",
        parent_dir=str(tmp_path),
    )])

    res = TestClient(app).post("/api/rename/execute", json={
        "file_id": "f1", "template": TEMPLATE, "source": "local",
        "path": str(tmp_path), "override": OVERRIDE,
        "conflict_strategy": "abort", "generate_nfo": True,
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["result"]["status"] == "conflict"
    assert body["failed"] == 1
    assert body["skipped"] == 0
    assert body["nfo_written"] == []
```

- [ ] **Step 2: 跑它，确认红**

Run: `cd backend && python -m pytest tests/test_rename_single_route.py -q`
Expected: FAIL（`file_id` 被当成未知字段忽略，`file_ids` 缺失 → 422 或 KeyError）

- [ ] **Step 3: 改模型**

把 `backend/app/models/api.py` 的 `class RenameExecuteRequest` 整段替换为：

```python
class RenameBatchRequest(BaseModel):
    """批量请求的字段集合。dry-run 与 finalize 共用它。

    抽出来是因为这两个接口的字段**必须**与批量执行完全一致 —— 它们描述的是
    同一批文件、同一套模板与同一份 TMDB 配置。各写一份必然漂移。
    """
    file_ids: list[str]
    template: str
    folder_template: str = ""
    create_season_folder: bool = False
    overrides: dict[str, dict] = Field(default_factory=dict)
    source: str = "local"
    path: str = ""
    conflict_strategy: str = "skip"
    episode_pad_digits: Optional[int] = None
    season_pad_digits: Optional[int] = None
    tmdb_api_key: Optional[str] = None
    tmdb_language: Optional[str] = None
    tmdb_enabled: Optional[bool] = None
    tmdb_overrides: dict[str, int] = Field(default_factory=dict)
    generate_nfo: bool = False
    nfo_overwrite: bool = False
    # 设置页的 OpenList 限流。None = 未提供, 后端保持当前值（回落 .env）。
    openlist_max_concurrent: Optional[int] = None
    openlist_request_interval: Optional[float] = None


class RenameDryRunRequest(RenameBatchRequest):
    """干跑仍是批量 —— 它是纯计划操作, 不写盘, 没有进度可言。"""


class RenameFinalizeRequest(RenameBatchRequest):
    """批次收尾。landed 是**真实落点**, 由前端从单文件响应回传。

    不含 conflict_strategy 的用法: finalize 不做任何文件操作, 该字段被继承下来
    只为复用模型, 路由不读它。
    """
    landed: dict[str, str] = Field(default_factory=dict)


class RenameExecuteRequest(BaseModel):
    """**单个文件**的执行请求。

    `override` 用单数而非「只有一个键的字典」: 单文件接口收字典-of-1 是无意义的
    形状。路由内适配成 {file_id: override} 喂给既有的 _with_tmdb_titles。
    """
    file_id: str
    template: str
    folder_template: str = ""
    create_season_folder: bool = False
    override: Optional[dict] = None
    source: str = "local"
    path: str = ""
    conflict_strategy: str = "skip"
    episode_pad_digits: Optional[int] = None
    season_pad_digits: Optional[int] = None
    tmdb_api_key: Optional[str] = None
    tmdb_language: Optional[str] = None
    tmdb_enabled: Optional[bool] = None
    tmdb_overrides: dict[str, int] = Field(default_factory=dict)
    generate_nfo: bool = False
    nfo_overwrite: bool = False
    openlist_max_concurrent: Optional[int] = None
    openlist_request_interval: Optional[float] = None
```

在 `backend/app/models/file.py` 的 `BatchRenameResult` 之后追加：

```python
class SingleRenameResult(BaseModel):
    """单文件执行的结果。

    计数（executed / skipped / failed，各为 0 或 1）由**后端**给出, 前端只求和 ——
    让前端按 result.status 重判会把 count_result 那套规则复制成第二份。
    """
    success: bool = False
    source: str = "local"
    file_id: str = ""
    result: RenameResult
    executed: int = 0
    skipped: int = 0
    failed: int = 0
    # 该文件的每集 NFO（生成）。剧集级/季级不属于单个文件, 由 /rename/finalize 汇总。
    nfo_written: list[str] = Field(default_factory=list)
    nfo_carried: list[str] = Field(default_factory=list)
    nfo_skipped: list[dict] = Field(default_factory=list)
```

- [ ] **Step 4: 改路由**

在 `backend/app/api/renamer.py` 里：

导入改为：

```python
from ..models.api import (
    RenameBatchRequest, RenameDryRunRequest, RenameExecuteRequest,
    RenameFinalizeRequest, RenamePreviewRequest,
)
from ..models.file import (
    FileInfo, ParsedInfo, RenamePlan, BatchRenameResult, OverrideInfo,
    SingleRenameResult,
)
from ..core.local_renamer import (
    batch_rename as local_batch_rename,
    OneOutcome, count_result, execute_one, finalize_show_nfo,
    landed_path_of, plan_files,
)
from ..core.openlist_renamer import (
    build_openlist_rename_plan, execute_openlist_batch, execute_openlist_one,
)
```

在 `_show_key` 之后插入三个小助手（第三个是适配器）：

```python
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
```


```python
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
```

把 `@router.post("/rename/execute")` 的整个函数替换为：

```python
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
            nfo_options=(
                _nfo_options_from_request(req) if _nfo_supported(source) else NfoOptions()
            ),
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
        outcome.landed_path = landed_path_of(result)
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
        executed=outcome.executed,
        skipped=outcome.skipped,
        failed=outcome.failed,
        nfo_written=outcome.nfo_written,
        nfo_carried=outcome.nfo_carried,
        nfo_skipped=[{"path": p, "reason": r} for p, r in outcome.nfo_skipped],
    ).model_dump()
```

**注意 OpenList 分支**：`local_renamer` 的导入行里除了 `execute_one / finalize_show_nfo / plan_files`，还要带上 `OneOutcome`、`count_result`、`landed_path_of`。这三个都是**公开名**（`count_result` 在 Task 1、`landed_path_of` 在 Task 2 里刻意不带下划线，就是为了这里）—— 让 renamer.py 跨模块 import 私有的 `_NO_LANDING_STATUSES` 会把「哪些状态算没落地」这条规则散到两处。

把 `@router.post("/rename/dry-run")` 的签名改为 `async def dry_run_rename(req: RenameDryRunRequest):`，函数体**一行不改**。

- [ ] **Step 5: 改写既有路由测试（机械规则）**

对 `tests/test_rename_routes.py` 与 `tests/test_rename_nfo_route.py` 里所有 `/api/rename/execute` 的调用，按下列规则逐处改写：

| 旧 | 新 |
|---|---|
| `"file_ids": ["f1"]` | `"file_id": "f1"` |
| `"file_ids": [X]`（单个元素） | `"file_id": X` |
| `"overrides": {X: {...}}` | `"override": {...}` |
| `res.json()["results"][0]` | `res.json()["result"]` |

`nfo_written` / `nfo_carried` / `nfo_skipped` 在 `BatchRenameResult` 与 `SingleRenameResult` 里**都是顶层字段**，故 `res.json()["nfo_written"]` 这类写法不用改。

**三条多文件用例必须改写语义，不是只改形状。** `tests/test_rename_nfo_route.py` 里有三条用例用**多个** `file_ids`，并断言 `/rename/execute` 写出 `tvshow.nfo` / `season.nfo`：

| 用例（约在） | 原来的主张 | 改成 |
|---|---|---|
| `test_execute_with_tmdb_writes_all_three_kinds`（~331） | execute 写出三种 NFO | execute 只写**它负责的那一份**每集 NFO（落盘 + `result.nfo_path` 指向改名后的路径），并**显式断言组级 NFO 不由 execute 写**（`nfo_written` 里没有 `tvshow.nfo` / `season.nfo`） |
| 两条字幕用例（~411、~501） | 精确集合里含两份组级 NFO | 执行侧**逐个文件各 POST 一次**（每个文件一次 execute），把 `body["result"]` 收进 `by_name`；精确集合断言缩成 `["Test Show - S01E02.nfo"]` |

这不是「断言被迫改」，而是**契约变更本身**：组级 NFO 从 `/rename/execute` 移到了 `/rename/finalize`（spec R1）。改写后第一条还多出一条**能红的新判据** —— 把 `execute_one` 换成 `finalize_show_nfo` + 写盘会让它红。

**还有第 10 处调用点**：`tests/test_nfo_write.py:191` 是**模型级构造**（不是 HTTP 调用），brief 的清单与 grep 都抓不到它，只有跑全套才会暴露。它按纯形状改（`file_ids=[X]` → `file_id=X`），断言不动。

改完后跑一次 grep 确认没有漏网的批量调用：

Run: `cd backend && grep -rn '"file_ids"' tests/ | grep -v 'rename/preview' | grep -v 'dry-run'`

Expected: 只应剩下 preview 与 dry-run 的用例（它们**仍是批量**，不得改）以及 `RenameBatchRequest` 的模型级构造。若出现 execute 的**路由**用例，回到上表继续改。

- [ ] **Step 6: 跑全套**

Run: `cd backend && python -m pytest -q`
Expected: 全绿（数量 = Task 4 结束时的 234 + 新增 7 条 = 241，以实际为准）

- [ ] **Step 7: 提交**

```bash
git add backend/app/models/api.py backend/app/models/file.py backend/app/api/renamer.py \
        backend/tests/test_rename_routes.py backend/tests/test_rename_nfo_route.py \
        backend/tests/test_nfo_write.py backend/tests/test_rename_single_route.py
git commit -m "feat(api): /rename/execute 改为单文件契约，请求模型拆出 RenameBatchRequest"
```

---

### Task 6: `/rename/finalize`

**Files:**
- Modify: `backend/app/api/renamer.py`
- Test: `backend/tests/test_rename_finalize_route.py`（新建）

**Interfaces:**
- Consumes: Task 2 的 `finalize_show_nfo`、Task 5 的 `RenameFinalizeRequest`
- Produces: `POST /api/rename/finalize` → `{"success": bool, "nfo_written": [...], "nfo_skipped": [{"path","reason"}]}`

- [ ] **Step 1: 写判据（先红）**

新建 `backend/tests/test_rename_finalize_route.py`：

```python
"""批次收尾的判据。核心是**只认真实落点**。"""
import os

import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.main import app
from app.models.file import FileInfo

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"


def _video(tmp_path, name, file_id):
    path = tmp_path / name
    path.write_text("x", encoding="utf-8")
    return FileInfo(
        id=file_id, source="local", path=str(path), filename=name,
        extension=".mkv", parent_dir=str(tmp_path),
    )


@pytest.fixture
def env(tmp_path):
    files = [
        _video(tmp_path, "Show.S01E01.mkv", "f1"),
        _video(tmp_path, "Show.S01E02.mkv", "f2"),
    ]
    cache_files(files)
    return {"client": TestClient(app), "files": files, "dir": str(tmp_path)}


def _payload(env, landed, **extra):
    body = {
        "file_ids": [f.id for f in env["files"]],
        "template": TEMPLATE,
        "source": "local",
        "path": env["dir"],
        "overrides": {
            f.id: {"show_name": "Show", "season": 1, "episode": i + 1}
            for i, f in enumerate(env["files"])
        },
        "generate_nfo": True,
        "landed": landed,
    }
    body.update(extra)
    return body


def test_no_landed_files_writes_no_group_nfo(env):
    """**核心判据**：一个文件都没落地 → 一份 tvshow.nfo 都不许写。

    把 landed 过滤删掉（改成「假定全部落地」）本用例必然红 —— 那正是 spec §9.4
    的库根污染: 在一个没有任何剧集文件的目录里放一份 tvshow.nfo。
    """
    res = env["client"].post("/api/rename/finalize", json=_payload(env, landed={}))
    assert res.status_code == 200, res.text
    assert res.json()["nfo_written"] == []
    assert not os.path.exists(os.path.join(env["dir"], "tvshow.nfo"))


def test_group_nfo_written_when_any_file_landed(env):
    """只落地第二集也要写 tvshow.nfo —— 判据是「目录里有视频落地」, 不是组代表。"""
    landed = {"f2": os.path.join(env["dir"], "Show - S01E02.mkv")}
    res = env["client"].post("/api/rename/finalize", json=_payload(env, landed=landed))
    assert res.status_code == 200, res.text
    written = res.json()["nfo_written"]
    assert os.path.join(env["dir"], "tvshow.nfo") in written


def test_finalize_never_writes_episode_nfo(env):
    """每集 NFO 由单文件接口写, 收尾**不得**再写一遍。

    去掉 kind != "episode" 的过滤本用例必然红。
    """
    landed = {"f1": os.path.join(env["dir"], "Show - S01E01.mkv")}
    res = env["client"].post("/api/rename/finalize", json=_payload(env, landed=landed))
    written = res.json()["nfo_written"]
    assert not any(w.endswith("Show - S01E01.nfo") for w in written)
    assert not any(w.endswith("Show - S01E02.nfo") for w in written)


def test_finalize_skips_when_nfo_disabled(env):
    res = env["client"].post("/api/rename/finalize", json=_payload(
        env, landed={"f1": "/x"}, generate_nfo=False))
    assert res.status_code == 200, res.text
    assert res.json()["nfo_written"] == []
```

**注意**：这些用例不传 `tmdb_*`，conftest 已把 Key 钉成空串，故 TMDB 一律 disabled、`has_metadata` 为 False → 决策的 `content` 为 False → **不会有任何文件被写**。因此 `test_group_nfo_written_when_any_file_landed` 会红。

**必须再补一条端到端判据（否则覆盖会凭空消失）**：Task 5 把三条「TMDB 命中 → 盘上真的出现 `tvshow.nfo` / `season.nfo`」的用例改成了「execute 只写每集 NFO」，而上面这些用例跑在**未配 TMDB** 上、只断言 `nfo_skipped` —— 于是改完之后，**全套里再没有任何用例证明组级 NFO 会真的落到盘上**。

补一条（用离线 TMDB 替身，照 `tests/test_rename_nfo_route.py` 里 `matched_client` / `_FakeTmdbClient` 的既有写法）：

```python
def test_finalize_writes_group_nfo_to_disk_when_tmdb_matched(matched_env):
    """TMDB 命中时, 收尾必须把 tvshow.nfo / season.nfo **真的写到盘上**。

    这是「组级 NFO 确实会落盘」在全套里唯一的端到端判据 —— Task 5 把原来那三条
    从 execute 侧删掉了, 少了它, 这条覆盖就只剩 `nfo_skipped` 的间接证据。
    把 finalize_show_nfo 的写盘删掉（只返回跳过）本用例必红。
    """
    res = matched_env["client"].post("/api/rename/finalize", json=_payload(
        matched_env, landed=matched_env["landed"]))
    assert res.status_code == 200, res.text
    written = res.json()["nfo_written"]
    assert os.path.join(matched_env["dir"], "tvshow.nfo") in written
    assert os.path.join(matched_env["dir"], "season.nfo") in written
    for path in written:
        assert os.path.exists(path), path
```

`matched_env` 夹具请照 `test_rename_nfo_route.py` 的 `matched_client` 造（那里已有可用的离线 TMDB 替身与 `MATCHED_PAYLOAD`），不要新写一套。

这正是本任务要暴露的事实：**没有 TMDB 元数据时，收尾一个文件都不写**。所以该用例要改成断言「决策被算出但报成跳过」，而不是断言文件落盘：

```python
def test_group_nfo_planned_when_any_file_landed(env):
    """只落地第二集也要为整剧算出 tvshow 决策 —— 判据是「目录里有视频落地」。

    未配 TMDB 时它报成跳过（"TMDB 未匹配, 不写残缺 NFO"）而不是落盘, 所以这里
    断言的是**跳过清单里出现了 tvshow.nfo 这个路径**, 而不是文件真的写了。
    把 landed 过滤删掉本用例必然红: 那时一条跳过记录都不会有。
    """
    landed = {"f2": os.path.join(env["dir"], "Show - S01E02.mkv")}
    res = env["client"].post("/api/rename/finalize", json=_payload(env, landed=landed))
    assert res.status_code == 200, res.text
    body = res.json()
    tvshow = os.path.join(env["dir"], "tvshow.nfo")
    assert tvshow in [d["path"] for d in body["nfo_skipped"]]


def test_no_landed_files_yields_no_decision_at_all(env):
    res = env["client"].post("/api/rename/finalize", json=_payload(env, landed={}))
    body = res.json()
    tvshow = os.path.join(env["dir"], "tvshow.nfo")
    assert tvshow not in [d["path"] for d in body["nfo_skipped"]]
    assert tvshow not in body["nfo_written"]
```

**实现要求**：`finalize_show_nfo` 在丢弃组级决策时要把它写进 `skipped_pairs`（带 `_DROPPED_GROUP_NFO_REASON`），这样上面两条用例才有东西可断言 —— Task 2 的 Step 4 已经这么实现了。

- [ ] **Step 1b: 补两条分支判据**

上面 6 条之外再补两条 —— 覆盖 `/rename/finalize` 的另外两个分支，它们此前无常驻判据（只被手工验证过）：

```python
def test_openlist_source_returns_empty_without_error(env):
    """OpenList 本期不写 NFO（spec §2）—— 收尾必须**如实返回空**, 而不是报错。

    前端本来就只在 local 时调它, 这里防的是手工调用。去掉路由里
    `_nfo_supported` 那道守卫本用例必红: 它会走到 local 的落盘逻辑。
    """
    res = env["client"].post("/api/rename/finalize", json=_payload(
        env, landed={"f1": "/x"}, source="openlist"))
    assert res.status_code == 200, res.text
    assert res.json() == {"success": True, "nfo_written": [], "nfo_skipped": []}


def test_unknown_file_ids_are_rejected(env):
    """file_ids 一个都找不到时如实报 400, 不要静默返回空。

    静默返回空会让前端以为「收尾成功、只是没有组级 NFO 可写」—— 那是假话。
    """
    body = _payload(env, landed={})
    body["file_ids"] = ["nope"]
    res = env["client"].post("/api/rename/finalize", json=body)
    assert res.status_code == 400, res.text
    assert "未找到" in res.json()["detail"]
```

若 `env` 夹具在按 Step 1b 之前的修正改过名，照实际夹具名适配。

- [ ] **Step 1c: 记录执行期对上面用例的修正**

**Step 1 的 6 条用例里有 4 条在实现期被证明不可用，已按下列理由改写**（以提交进仓库的测试为准，本节的代码块只作历史记录）：

| 原用例 | 问题 | 改法 |
|---|---|---|
| `test_no_landed_files_yields_no_decision_at_all` | 断言 `tvshow not in nfo_skipped` **任何实现都无法满足** —— 正确实现报「该剧下没有文件真正改名落地」、错误实现报「TMDB 未匹配」, 两者都在清单里。它与 `test_nfo_write.py:1041` 那条**带变异验证**的既有判据直接冲突 | 改为断言**丢弃原因**（`_DROPPED_GROUP_NFO_REASON`），改名 `..._drops_the_group_decision` |
| `test_no_landed_files_writes_no_group_nfo` / `test_group_nfo_planned_when_any_file_landed` / `test_finalize_never_writes_episode_nfo` | 跑在**未配 TMDB** 的夹具上 → 每条决策 content 恒为 None → **三条都是空断言**（实测：假定全部落地 / 不过滤 episode / 无视 generate_nfo 三种变异下全绿） | 改用**配了 TMDB 替身**的夹具（复用 `tests/test_rename_nfo_route.py` 的 `_FakeTmdbClient`），三条现在各有杀手变异 |
| `test_group_nfo_written_when_any_file_landed` | 只查路径鉴别不了「按组代表判落地」 | 补 `reason` 断言 |

**教训（写给后续任务的自己）**：Task 6 的用例跑在未配 TMDB 的夹具上，于是所有 NFO 决策的 content 都是 None —— 任何「写了什么」的断言都成了恒真。**判据的夹具必须让被测行为真的发生**，否则它只是在验证「什么都没发生」。


- [ ] **Step 2: 跑它，确认红**

Run: `cd backend && python -m pytest tests/test_rename_finalize_route.py -q`
Expected: FAIL — 404（路由不存在）

- [ ] **Step 3: 实现路由**

在 `renamer.py` 的 `/rename/dry-run` 之后插入：

```python
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
    if not _nfo_supported(source):
        # OpenList 本期不写 NFO（spec §2）。如实返回空, 不报错 —— 前端本来就
        # 只在 local 时调它, 这里防御的是手工调用。
        return {"success": True, "nfo_written": [], "nfo_skipped": []}

    files = find_files_by_ids(req.file_ids)
    if not files:
        raise HTTPException(status_code=400, detail="未找到对应的文件")

    pad = _pad_from_request(req)
    _merged, _summaries, matches_by_file = await _with_tmdb_titles(req, files)
    plans = plan_files(
        files, req.template, req.folder_template, req.create_season_folder,
        _merged, pad=pad,
    )

    landed_paths = [p for p in req.landed.values() if p]
    written, skipped = finalize_show_nfo(
        plans, landed_paths, matches_by_file, _nfo_options_from_request(req)
    )
    return {
        "success": True,
        "nfo_written": written,
        "nfo_skipped": [{"path": p, "reason": r} for p, r in skipped],
    }
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && python -m pytest tests/test_rename_finalize_route.py -q`
Expected: 8 passed

- [ ] **Step 5: 跑全套并提交**

Run: `cd backend && python -m pytest -q`
Expected: 全绿（数量 = Task 5 结束时的 241 + 新增 8 条 = 249，以实际为准）

```bash
git add backend/app/api/renamer.py backend/tests/test_rename_finalize_route.py
git commit -m "feat(api): 新增 /rename/finalize，按前端回传的真实落点写剧集级/季级 NFO"
```

---

### Task 7: 前端并发池 `renameRunner.js`

**Files:**
- Create: `frontend/src/stores/renameRunner.js`
- Create: `frontend/scripts/check-rename-runner.mjs`
- Modify: `frontend/scripts/check-all.mjs`

**Interfaces:**
- Produces:
  - `sleep(ms: number): Promise<void>`
  - `runWithConcurrency(items, limit, worker, { onProgress, intervalMs }?) -> Promise<{ results: any[], failures: {index, item, error}[] }>`

- [ ] **Step 1: 写判据脚本（先红）**

新建 `frontend/scripts/check-rename-runner.mjs`：

```js
// 并发池的机械判据。零依赖，只用 node 内置模块（与其余 check-*.mjs 同规格）。
import { runWithConcurrency, resolveConcurrency, sleep } from '../src/stores/renameRunner.js'

let failed = 0

function assert(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  if (!ok) {
    failed += 1
    console.log('FAIL', label, '得到', JSON.stringify(actual), '期望', JSON.stringify(expected))
  } else {
    console.log('PASS', label)
  }
}

// --- 在途数不得超过 limit（把 limit 当摆设、一次全发 → 本断言红）---
{
  let active = 0
  let peak = 0
  const items = Array.from({ length: 10 }, (_, i) => i)
  await runWithConcurrency(items, 3, async () => {
    active += 1
    peak = Math.max(peak, active)
    await sleep(5)
    active -= 1
  })
  assert('在途数峰值 == limit', peak, 3)
}

// --- 结果按输入顺序（直接返回完成顺序 → 本断言红）---
{
  const items = [0, 1, 2, 3]
  const { results } = await runWithConcurrency(items, 4, async (n) => {
    await sleep((4 - n) * 10)   // 先发的更慢, 完成顺序与输入顺序相反
    return n * 10
  })
  assert('results 按输入顺序', results, [0, 10, 20, 30])
}

// --- 单个 worker 抛错不影响其余（Promise.all 直接 reject → 本断言红）---
{
  const { results, failures } = await runWithConcurrency([1, 2, 3], 3, async (n) => {
    if (n === 2) throw new Error('boom')
    return n
  })
  assert('失败不阻断其余（前）', results[0], 1)
  assert('失败不阻断其余（后）', results[2], 3)
  assert('失败的槽位为空', results[1], undefined)
  assert('失败记入 failures', failures.length, 1)
  assert('failures 带原始下标', failures[0].index, 1)
  assert('failures 带原始条目', failures[0].item, 2)
}

// --- onProgress 次数 == items.length（只在成功时调 → 本断言红）---
{
  let calls = 0
  await runWithConcurrency([1, 2, 3], 2, async () => { throw new Error('x') },
    { onProgress: () => { calls += 1 } })
  assert('onProgress 次数 == 条目数（含失败）', calls, 3)
}

// --- failures 必须按输入下标排序，而不是完成顺序 ---
// **这条断言需要两个以上的失败才可观测**: 只有一个失败时任何顺序都一样, 所以
// 原来那几条用例对 `failures.sort(...)` 这一行是失明的（实测: 删掉排序, 12 个
// 变异里只有它存活）。
{
  const { failures } = await runWithConcurrency([0, 1, 2, 3], 4, async (n) => {
    await sleep((4 - n) * 5)   // 下标小的先睡 → 完成顺序与输入顺序**相反**
    throw new Error('boom')
  })
  assert('failures 按输入下标排序', failures.map(f => f.index), [0, 1, 2, 3])
}

// --- limit 未传必须抛错，不得兜底（加默认值 → 本断言红）---
{
  let threw = false
  try {
    await runWithConcurrency([1], undefined, async () => 1)
  } catch {
    threw = true
  }
  assert('limit 未传时抛错而非兜底', threw, true)
}

// --- 批次内目标重名必须降级为串行（spec §10.1）---
{
  const base = { targets: ['/m/a.mkv', '/m/b.mkv'], localConcurrency: 4, openlistConcurrency: 2 }
  assert('无重名 + local → 用本地并发',
    resolveConcurrency({ ...base, source: 'local' }), 4)
  assert('无重名 + openlist → 用 OpenList 并发',
    resolveConcurrency({ ...base, source: 'openlist' }), 2)
  assert('有重名 → 降级为 1',
    resolveConcurrency({ ...base, source: 'local', targets: ['/m/a.mkv', '/m/a.mkv'] }), 1)
  assert('有重名时 openlist 也降级为 1',
    resolveConcurrency({ ...base, source: 'openlist', targets: ['/m/a.mkv', '/m/a.mkv'] }), 1)
}

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
```

- [ ] **Step 2: 跑它，确认红**

Run: `cd frontend && node scripts/check-rename-runner.mjs`
Expected: FAIL — `Cannot find module '../src/stores/renameRunner.js'`

- [ ] **Step 3: 实现 `renameRunner.js`**

```js
// 并发池。零依赖纯函数 —— node 可以直接 import 它跑断言（本项目没有前端测试
// 设施, 见 settingsSchema.js 的头注释）。
//
// `limit` **必须由调用方传入**: 函数内不设默认值, 未传直接抛错。兜底会让
// 「调用点忘了传设置」静默退化成某个魔数, 而那正是本次要修的那类 bug ——
// 设置项在页面上可改、实际不生效（spec 事实 10）。

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// 在途上限怎么定。抽成纯函数是为了让「批次内目标重名 → 降级串行」这条规则
// 能被 node 判据钉住 —— 内联在 workspace.js 里就没有任何机械判据能发现它被删掉。
//
// 为什么重名必须降级: 后端 check_conflict 的第二参是空列表, duplicate_in_batch
// 分支从不触发, 所以并发下两个文件会双双通过存在性检查 → 双写同一个目标
// （overwrite 策略下是数据丢失）。见 spec §10.1。
export function resolveConcurrency({ source, targets, localConcurrency, openlistConcurrency }) {
  const hasDuplicateTarget = new Set(targets).size !== targets.length
  if (hasDuplicateTarget) return 1
  return source === 'openlist' ? openlistConcurrency : localConcurrency
}

export async function runWithConcurrency(items, limit, worker, { onProgress, intervalMs = 0 } = {}) {
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error(`runWithConcurrency 需要正整数 limit，收到 ${limit}`)
  }

  const results = new Array(items.length)
  const failures = []
  let done = 0
  let next = 0

  async function runOne(index) {
    try {
      if (intervalMs > 0) await sleep(intervalMs)
      results[index] = await worker(items[index], index)
    } catch (error) {
      // 单个文件失败不得中断整批（spec §8「一律跑完」）。记下来, 让调用方汇总。
      failures.push({ index, item: items[index], error })
    } finally {
      done += 1
      // 失败也算「完成」—— 否则进度条永远走不到 100%。
      if (onProgress) onProgress(done, items.length)
    }
  }

  // 固定数量的「泵」, 每个循环取下一个下标 —— 这样在途数恒等于 min(limit, n),
  // 不需要维护队列。
  async function pump() {
    for (;;) {
      const index = next
      next += 1
      if (index >= items.length) return
      await runOne(index)
    }
  }

  const pumps = []
  for (let i = 0; i < Math.min(limit, items.length); i += 1) pumps.push(pump())
  await Promise.all(pumps)

  // failures 按完成顺序 push, 这里按下标排回来 —— 让调用方的报错顺序可预测。
  failures.sort((a, b) => a.index - b.index)
  return { results, failures }
}
```

实现时在文件头注释里写明**两条调用方须知**（都是评审指出的、下游任务会踩的坑）：

```js
// 调用方须知:
// 1. `onProgress` 是**调用方提供的回调, 本模块不接管它的异常** —— 它抛出的异常会
//    逃出 runOne 并让整批 reject（那是调用方自己的 bug, 我们**不**吞掉它: 静默
//    吞掉会让一个坏回调看起来一切正常）。所以它必须是不会抛的纯赋值。
// 2. 失败条目的槽位在 `results` 里是**空洞**（`new Array(n)` 从不赋值），
//    `map` / `forEach` 会静默跳过它。要读失败信息一律查 `failures`, 不要遍历
//    `results`。
```

**实现时在 `finalize` 那一段加一句注释**：只并入 `nfo_written` / `nfo_skipped`，**不并入 `nfo_carried`** —— 收尾响应里根本没有这个字段（携带既有 NFO 是**每文件**的事，由 `/rename/execute` 报）。写明这一点，免得后人看到「别的字段都并了、唯独少一个」时把它当成遗漏去「补」。

- [ ] **Step 4: 跑判据**

Run: `cd frontend && node scripts/check-rename-runner.mjs`
Expected: 全部通过。

- [ ] **Step 5: 把新脚本加进 runner 名单**

编辑 `frontend/scripts/check-all.mjs` 的 `SCRIPTS` 数组，加入：

```js
  'check-rename-runner.mjs',
```

**同时处理该文件头注释里的脚本数**。它有**两处**（第 1 行「那五个 check-*.mjs」、第 7 行「故这里把五个脚本串起来」），只改一处会留下一句假陈述。

**但不要改成「六个」—— 把数字从散文里删掉。** 理由：这个数字每加一个脚本就会再假一次（Task 8 还要加一个），而名单本身就在下面的 `SCRIPTS` 数组里，散文里的计数不提供任何信息。改成「scripts/ 下的那些 check-*.mjs」与「故这里把它们串起来」即可 —— 那样它永远是真的。

改完 `grep -n '五个\|六个' frontend/scripts/check-all.mjs` 应当无命中。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/stores/renameRunner.js frontend/scripts/check-rename-runner.mjs frontend/scripts/check-all.mjs
git commit -m "feat(frontend): 新增并发池 renameRunner 及其判据脚本"
```

---

### Task 8: 前端结果聚合 `renameAggregate.js`

**Files:**
- Create: `frontend/src/stores/renameAggregate.js`
- Create: `frontend/scripts/check-rename-aggregate.mjs`
- Modify: `frontend/scripts/check-all.mjs`

**Interfaces:**
- Consumes: 单文件响应的形状（`{result, executed, skipped, failed, nfo_written, nfo_carried, nfo_skipped}`）
- Produces: `aggregateBatch({ items, finalize, nfoBlockedByScrape, source }) -> BatchRenameResult 同形状的对象`

- [ ] **Step 1: 写判据脚本（先红）**

新建 `frontend/scripts/check-rename-aggregate.mjs`：

```js
import { aggregateBatch } from '../src/stores/renameAggregate.js'

let failed = 0

function assert(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  if (!ok) {
    failed += 1
    console.log('FAIL', label, '得到', JSON.stringify(actual), '期望', JSON.stringify(expected))
  } else {
    console.log('PASS', label)
  }
}

// --- 计数用**后端给的字段**, 不按 status 重判 ---
// 故意喂一条自相矛盾的响应: status 说 skipped_conflict（按 status 重判会记 skipped）,
// 而后端给的计数说 failed。聚合必须采信后者。
// 改成按 result.status 归类 → 本断言红（skipped 变 1、failed 变 0）。
{
  const agg = aggregateBatch({
    items: [{
      executed: 0, skipped: 0, failed: 1,
      result: { status: 'skipped_conflict', error: '目标文件已存在，跳过' },
    }],
  })
  assert('计数采信后端字段（failed）', agg.failed, 1)
  assert('计数采信后端字段（skipped）', agg.skipped, 0)
  assert('计数采信后端字段（executed）', agg.executed, 0)
}

// --- 计数逐条求和 ---
{
  const agg = aggregateBatch({
    items: [
      { executed: 1, skipped: 0, failed: 0, result: { status: 'renamed' } },
      { executed: 0, skipped: 1, failed: 0, result: { status: 'skipped_conflict' } },
      { executed: 0, skipped: 0, failed: 1, result: { status: 'failed' } },
    ],
  })
  assert('executed 求和', agg.executed, 1)
  assert('skipped 求和', agg.skipped, 1)
  assert('failed 求和', agg.failed, 1)
  assert('total == 条目数', agg.total, 3)
  assert('success == (failed === 0)', agg.success, false)
}

// --- finalize 的两项并入批次结果（丢掉 finalize 响应 → 本断言红）---
{
  const agg = aggregateBatch({
    items: [{ executed: 1, skipped: 0, failed: 0, result: { status: 'renamed' },
              nfo_written: ['/m/Show - S01E01.nfo'] }],
    finalize: { nfo_written: ['/m/tvshow.nfo'], nfo_skipped: [{ path: '/m/season.nfo', reason: '已存在' }] },
  })
  assert('finalize 的写入并入', agg.nfo_written, ['/m/Show - S01E01.nfo', '/m/tvshow.nfo'])
  assert('finalize 的跳过并入', agg.nfo_skipped, [{ path: '/m/season.nfo', reason: '已存在' }])
}

// --- 各条 NFO 三项拼接 ---
{
  const agg = aggregateBatch({
    items: [
      { executed: 1, skipped: 0, failed: 0, result: { status: 'renamed' },
        nfo_carried: ['/m/a.nfo'], nfo_skipped: [{ path: '/m/x.nfo', reason: '已存在' }] },
      { executed: 1, skipped: 0, failed: 0, result: { status: 'renamed' },
        nfo_carried: ['/m/b.nfo'] },
    ],
  })
  assert('nfo_carried 拼接', agg.nfo_carried, ['/m/a.nfo', '/m/b.nfo'])
  assert('nfo_skipped 拼接', agg.nfo_skipped, [{ path: '/m/x.nfo', reason: '已存在' }])
}

// --- errors 只收非空 error ---
{
  const agg = aggregateBatch({
    items: [
      { executed: 1, skipped: 0, failed: 0, result: { status: 'renamed', error: null } },
      { executed: 0, skipped: 0, failed: 1, result: { status: 'failed', error: '磁盘满了' } },
    ],
  })
  assert('errors 只收非空', agg.errors, ['磁盘满了'])
}

// --- 空批次不崩 ---
{
  const agg = aggregateBatch({ items: [] })
  assert('空批次 total 为 0', agg.total, 0)
  assert('空批次 success 为 true', agg.success, true)
}

// --- results 必须按输入顺序收齐 ---
// 少了这条, 删掉 `results.push(item.result)` **没有任何断言会红** —— 后果是
// ResultDialog 的明细表**静默消失**: 汇总数字还在, 每一行的详情没了。
{
  const agg = aggregateBatch({
    items: [
      { executed: 1, skipped: 0, failed: 0, result: { status: 'renamed', new_filename: 'a.mkv' } },
      { executed: 0, skipped: 1, failed: 0, result: { status: 'skipped_conflict', new_filename: 'b.mkv' } },
      { executed: 0, skipped: 0, failed: 1, result: { status: 'failed', new_filename: 'c.mkv' } },
    ],
  })
  assert('results 按输入顺序收齐', agg.results.map(r => r.new_filename), ['a.mkv', 'b.mkv', 'c.mkv'])
}

// --- 执行结果恒不是干跑 ---
{
  const agg = aggregateBatch({ items: [], nfoBlockedByScrape: true })
  assert('dry_run 恒为 false', agg.dry_run, false)
  assert('nfo_blocked_by_scrape 透传', agg.nfo_blocked_by_scrape, true)
}

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exitCode = failed === 0 ? 0 : 1
```

- [ ] **Step 2: 跑它，确认红**

Run: `cd frontend && node scripts/check-rename-aggregate.mjs`
Expected: FAIL — `Cannot find module '../src/stores/renameAggregate.js'`

- [ ] **Step 3: 实现 `renameAggregate.js`**

```js
// 逐文件响应 + 收尾响应 → 一个与后端 BatchRenameResult **同形状**的对象。
//
// 同形状是硬要求: ResultDialog.vue 直接消费 BatchRenameResult 的字段, 不改它。
//
// 计数**直接用后端给的 executed/skipped/failed 字段求和**, 绝不按 result.status
// 重判 —— 重判会把 local_renamer.count_result 那套规则复制成第二份, 两份必然
// 漂移（spec R11）。判据见 scripts/check-rename-aggregate.mjs 的第一块。
//
// 零依赖纯函数: node 要能直接 import 它跑断言。

export function aggregateBatch({ items, finalize = null, nfoBlockedByScrape = false, source = 'local' }) {
  const results = []
  const errors = []
  const nfoWritten = []
  const nfoCarried = []
  const nfoSkipped = []
  let executed = 0
  let skipped = 0
  let failed = 0

  for (const item of items) {
    executed += item.executed || 0
    skipped += item.skipped || 0
    failed += item.failed || 0

    if (item.result) {
      results.push(item.result)
      if (item.result.error) errors.push(item.result.error)
    }
    if (item.nfo_written) nfoWritten.push(...item.nfo_written)
    if (item.nfo_carried) nfoCarried.push(...item.nfo_carried)
    if (item.nfo_skipped) nfoSkipped.push(...item.nfo_skipped)
  }

  if (finalize) {
    if (finalize.nfo_written) nfoWritten.push(...finalize.nfo_written)
    if (finalize.nfo_skipped) nfoSkipped.push(...finalize.nfo_skipped)
  }

  return {
    success: failed === 0,
    source,
    executed,
    skipped,
    failed,
    total: items.length,
    // 批次内冲突由后端报在 result 上, 这里没有额外的批次级冲突可报。
    conflicts: [],
    results,
    errors,
    nfo_written: nfoWritten,
    nfo_carried: nfoCarried,
    nfo_skipped: nfoSkipped,
    dry_run: false,
    nfo_blocked_by_scrape: nfoBlockedByScrape,
  }
}
```

- [ ] **Step 4: 跑判据**

Run: `cd frontend && node scripts/check-rename-aggregate.mjs`
Expected: 全部通过

- [ ] **Step 5: 把新脚本加进 runner 名单**

编辑 `frontend/scripts/check-all.mjs` 的 `SCRIPTS` 数组，加入：

```js
  'check-rename-aggregate.mjs',
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/stores/renameAggregate.js frontend/scripts/check-rename-aggregate.mjs frontend/scripts/check-all.mjs
git commit -m "feat(frontend): 新增结果聚合 renameAggregate 及其判据脚本"
```

---

### Task 9: 前端数据层 —— 载荷四形态 + 并发设置项

**Files:**
- Modify: `frontend/src/stores/renamePayload.js`
- Modify: `frontend/scripts/check-rename-payload.mjs`
- Modify: `frontend/src/stores/settingsSchema.js`
- Modify: `frontend/src/stores/settings.js`
- Modify: `frontend/scripts/check-settings-schema.mjs`

**为什么把设置项并进本任务**：Task 10（`workspace.js` 接线）会读 `settingsStore.localConcurrency`。那个字段若还不存在就是 `undefined`，而 `runWithConcurrency` 对非正整数 limit **抛错**（这是有意的）—— 于是执行路径会直接断掉，且没有任何机械判据能发现（前端没有运行时测试）。所以**数据层必须先于接线落地**。

**Interfaces:**
- Consumes: 无
- Produces: `buildRenamePayload({ mode, fileId, fileIds, landed, override, overrides, openlistMaxConcurrent, openlistRequestInterval, ... })`
  - `mode: 'execute'` → 出 `file_id`（单数）+ `override`（单数）+ `conflict_strategy`
  - `mode: 'dry-run'` → 出 `file_ids` + `overrides` + `conflict_strategy`
  - `mode: 'preview'` → 出 `file_ids` + `overrides`
  - `mode: 'finalize'` → 出 `file_ids` + `overrides` + `landed`
  - 后三种模式都出 `openlist_max_concurrent` / `openlist_request_interval`

- [ ] **Step 1: 更新判据（先红）**

在 `check-rename-payload.mjs` 的 `base` 里，把 `fileIds` 一行改为：

```js
  fileIds: ['f1', 'f2'],
  fileId: 'f1',
  override: { title: '我的标题' },
  landed: { f1: '/media/绝命毒师/Season 02/绝命毒师 - S02E01.mkv' },
  openlistMaxConcurrent: 2,
  openlistRequestInterval: 0.5,
```

把文件末尾那段「conflict_strategy 只属于 execute」替换为：

```js
// --- 单文件模式：出 file_id 与 override（单数），不出 file_ids / overrides ---
{
  const one = buildRenamePayload({ ...base, mode: 'execute' })
  assert('execute 载荷带 file_id', one.file_id, 'f1')
  assertKey('execute 载荷不含 file_ids', one, 'file_ids', false)
  assert('execute 载荷带 override', one.override, { title: '我的标题' })
  assertKey('execute 载荷不含 overrides', one, 'overrides', false)
  assert('execute 载荷带 conflict_strategy', one.conflict_strategy, 'skip')
}

// --- 干跑仍是批量 ---
{
  const dry = buildRenamePayload({ ...base, mode: 'dry-run' })
  assert('dry-run 载荷带 file_ids', dry.file_ids, ['f1', 'f2'])
  assertKey('dry-run 载荷不含 file_id', dry, 'file_id', false)
  assert('dry-run 载荷带 overrides', dry.overrides, { f1: { title: '我的标题' } })
  assert('dry-run 载荷带 conflict_strategy', dry.conflict_strategy, 'skip')
}

// --- 收尾：批量 + landed，且**不带** conflict_strategy（它不做文件操作）---
{
  const fin = buildRenamePayload({ ...base, mode: 'finalize' })
  assert('finalize 载荷带 file_ids', fin.file_ids, ['f1', 'f2'])
  assert('finalize 载荷带 landed', fin.landed, base.landed)
  assertKey('finalize 载荷不含 conflict_strategy', fin, 'conflict_strategy', false)
}

// --- landed 是浅拷贝而非同一引用（改它不得污染调用方的对象）---
{
  const fin = buildRenamePayload({ ...base, mode: 'finalize' })
  assert('landed 是浅拷贝', fin.landed === base.landed, false)
}

// --- 预览仍是批量，且不带 conflict_strategy ---
{
  const pv = buildRenamePayload({ ...base, mode: 'preview' })
  assert('preview 载荷带 file_ids', pv.file_ids, ['f1', 'f2'])
  assertKey('preview 载荷不含 conflict_strategy', pv, 'conflict_strategy', false)
}

// --- OpenList 限流随请求下发（不下发 → 设置页那两项又是死的）---
{
  const one = buildRenamePayload({ ...base, mode: 'execute' })
  assert('下发 OpenList 并发', one.openlist_max_concurrent, 2)
  assert('下发 OpenList 间隔', one.openlist_request_interval, 0.5)
}

// --- 形状互斥：execute 传了 fileIds 必须抛错，而不是静默取其一 ---
{
  let threw = false
  try {
    buildRenamePayload({ ...base, mode: 'execute', fileIds: ['f1', 'f2'] })
  } catch {
    threw = true
  }
  assert('execute 模式传 fileIds 抛错', threw, true)
}

// --- 形状互斥：批量模式不传 fileIds 必须抛错 ---
{
  let threw = false
  try {
    buildRenamePayload({ ...base, mode: 'finalize', fileIds: undefined })
  } catch {
    threw = true
  }
  assert('finalize 模式缺 fileIds 抛错', threw, true)
}
```

同时把 `base` 里原来那条 `overrides` 保留（preview / dry-run / finalize 仍用它），并把既有断言 `assert('overrides 透传', on.overrides, ...)` 里的 `on` 改为 `mode: 'preview'` 的载荷。

- [ ] **Step 2: 跑它，确认红**

Run: `cd frontend && node scripts/check-rename-payload.mjs`
Expected: FAIL（`file_id` 为 undefined、缺互斥校验等）

- [ ] **Step 3: 改 `buildRenamePayload`**

把函数签名与返回段替换为：

```js
// 四种形态:
//   preview   —— 批量计划（RenamePreviewRequest）
//   dry-run   —— 批量计划 + 冲突策略（RenameDryRunRequest）。**干跑仍是批量**:
//                它是纯计划操作, 不写盘, 没有进度可言。
//   execute   —— **单个文件**（RenameExecuteRequest）。file_id / override 用单数。
//   finalize  —— 批量收尾（RenameFinalizeRequest）, 额外带 landed 真实落点。
export function buildRenamePayload({
  mode,
  // execute 用单数 fileId / override；preview / dry-run / finalize 用批量。
  fileId,
  fileIds,
  override,
  overrides,
  // finalize 专用：file_id → 真实落点。
  landed,
  path,
  source,
  template,
  folderTemplate,
  createSeasonFolder,
  conflictStrategy,
  episodePadDigits,
  seasonPadDigits,
  tmdb,
  tmdbOverrides,
  scraped,
  generateNfo,
  nfoOverwrite,
  openlistMaxConcurrent,
  openlistRequestInterval,
}) {
  // 形状互斥**必须显式校验**: 传错形状时静默取其一, 会得到「预览 2 个文件、
  // 执行 0 个」这种零报错的错行为（本仓库有前科）。
  if (mode === 'execute') {
    if (!fileId) throw new Error('buildRenamePayload: execute 模式必须传 fileId')
    if (Array.isArray(fileIds) && fileIds.length) {
      throw new Error('buildRenamePayload: execute 模式不得传 fileIds')
    }
  } else if (mode === 'preview' || mode === 'dry-run' || mode === 'finalize') {
    if (!Array.isArray(fileIds)) {
      throw new Error(`buildRenamePayload: ${mode} 模式必须传 fileIds`)
    }
  } else {
    throw new Error(`buildRenamePayload: 未知 mode ${mode}`)
  }
  if (mode === 'finalize' && (!landed || typeof landed !== 'object')) {
    throw new Error('buildRenamePayload: finalize 模式必须传 landed')
  }

  const common = {
    source,
    path,
    template,
    folder_template: folderTemplate,
    create_season_folder: createSeasonFolder,
    episode_pad_digits: episodePadDigits,
    season_pad_digits: seasonPadDigits,
    // 未刮削时**只发 tmdb_enabled: false**，且不发 Key / 语言 / 重选表。
    // 详见改动前的长注释, 三条错误实现都由本文件的判据钉住。
    ...(scraped
      ? {
          tmdb_api_key: tmdb.apiKey,
          tmdb_language: tmdb.language,
          tmdb_overrides: { ...tmdbOverrides },
          tmdb_enabled: tmdb.enabled,
        }
      : { tmdb_enabled: false }),
    generate_nfo: generateNfo,
    nfo_overwrite: nfoOverwrite,
  }

  if (mode === 'execute') {
    return {
      file_id: fileId,
      override: override ?? null,
      ...common,
      conflict_strategy: conflictStrategy,
      openlist_max_concurrent: openlistMaxConcurrent,
      openlist_request_interval: openlistRequestInterval,
    }
  }

  if (mode === 'finalize') {
    // finalize 不做文件操作, 故**不带** conflict_strategy（后端模型也没有它）。
    return { file_ids: fileIds, overrides, landed: { ...landed }, ...common }
  }

  if (mode === 'dry-run') {
    return {
      file_ids: fileIds,
      overrides,
      ...common,
      conflict_strategy: conflictStrategy,
      openlist_max_concurrent: openlistMaxConcurrent,
      openlist_request_interval: openlistRequestInterval,
    }
  }

  return { file_ids: fileIds, overrides, ...common }
}
```

- [ ] **Step 4: 跑判据**

Run: `cd frontend && node scripts/check-rename-payload.mjs`
Expected: 全部通过

- [ ] **Step 5: 给设置判据加断言（先红）**

在 `check-settings-schema.mjs` 里加入：

```js
// --- localConcurrency：新增项，区间 [1,10]，默认 4 ---
assert('localConcurrency 默认 4', defaultSettings().localConcurrency, 4)
assert('localConcurrency 钳到上界 10', normalizeSettings({ localConcurrency: 99 }).localConcurrency, 10)
assert('localConcurrency 钳到下界 1', normalizeSettings({ localConcurrency: 0 }).localConcurrency, 1)
assert('localConcurrency 清空回落默认 4', normalizeSettings({ localConcurrency: null }).localConcurrency, 4)

// --- openlist.concurrency 默认值 3 → 2（spec §7.1）---
assert('openlist.concurrency 默认 2', defaultSettings().openlist.concurrency, 2)
// 老用户已显式存过的值必须保留（不做迁移）—— 静默改掉用户设过的值是另一类 bug
assert('已存的 openlist.concurrency 不被默认值覆盖',
  normalizeSettings({ openlist: { concurrency: 3 } }).openlist.concurrency, 3)
```

**注意**：该脚本既有的断言里若有「`openlist.concurrency` 默认 3」，必须一并改成 2 —— 那条断言钉的正是本次要改的行为。

Run: `cd frontend && node scripts/check-settings-schema.mjs`
Expected: FAIL（`localConcurrency` 为 undefined、`openlist.concurrency` 仍为 3）

- [ ] **Step 6: 改 `settingsSchema.js`**

在 `defaultSettings()` 的返回值里，`conflictStrategy: 'skip',` 之后加：

```js
    // 本地源的并发在途上限。**默认 4**：本地是磁盘操作，瓶颈在 IO 而不在服务端；
    // OpenList 默认 2 是因为它每次请求都要出网打远端 API。
    localConcurrency: 4,
```

把 `openlist` 段里的 `concurrency: 3,` 改为：

```js
      // 默认 2（spec §7.1）。它是**下发到后端**的 —— OpenListClient 用它构造并发
      // 限流器, 见 backend/app/core/openlist_client.py。
      concurrency: 2,
```

在 `normalizeSettings` 的返回对象里，`conflictStrategy` 那几行之后加：

```js
    localConcurrency: clampNumber(
      raw.localConcurrency, 1, 10, def.localConcurrency, true
    ),
```

- [ ] **Step 7: 改 `settings.js` store**

在 `const conflictStrategy = ref(initial.conflictStrategy)` 之后加：

```js
  const localConcurrency = ref(initial.localConcurrency)
```

在 `apply()` 里 `conflictStrategy.value = next.conflictStrategy` 之后加：

```js
    localConcurrency.value = next.localConcurrency
```

在 `toObject()` 的返回里 `conflictStrategy: conflictStrategy.value,` 之后加：

```js
      localConcurrency: localConcurrency.value,
```

在 store 的 `return { ... }` 里加入 `localConcurrency,`。

- [ ] **Step 8: 跑设置判据**

Run: `cd frontend && node scripts/check-settings-schema.mjs`
Expected: 全部通过

- [ ] **Step 9: 跑全套前端判据**

Run: `cd frontend && node scripts/check-all.mjs`
Expected: 全部通过。

- [ ] **Step 10: 提交**

```bash
git add frontend/src/stores/renamePayload.js frontend/scripts/check-rename-payload.mjs \
        frontend/src/stores/settingsSchema.js frontend/src/stores/settings.js \
        frontend/scripts/check-settings-schema.mjs
git commit -m "feat(frontend): 载荷支持四种形态；设置层新增 localConcurrency，OpenList 并发默认改 2"
```

---

### Task 10: `workspace.js` 执行循环接线

**Files:**
- Modify: `frontend/src/stores/workspace.js`

**Interfaces:**
- Consumes: Task 7 的 `runWithConcurrency`、Task 8 的 `aggregateBatch`、Task 9 的 `buildRenamePayload`
- Produces: store 新增暴露 `progress`（`reactive({ done, total, current })`）

- [ ] **Step 1: 加 import**

在 `workspace.js` 顶部：

```js
import { previewRename, executeRename, dryRunRename, finalizeRename } from '../api/renamer'
import { runWithConcurrency, resolveConcurrency } from './renameRunner'
import { aggregateBatch } from './renameAggregate'
```

在 `frontend/src/api/renamer.js` 追加：

```js
export function finalizeRename(data) {
  return request.post('/rename/finalize', data)
}
```

- [ ] **Step 2: 加进度状态**

在 `const executeDryRun = ref(false)` 之后加：

```js
  // 逐文件执行的进度。dryRun 时不填 —— 干跑仍是单次批量请求, 给一个永远 0%
  // 的进度条就是撒谎。
  const progress = reactive({ done: 0, total: 0, current: '' })
```

（若文件顶部没有 `reactive`，在 `import { ref, ... } from 'vue'` 里补上。）

- [ ] **Step 3: 重写 `executeAction`**

把 `async function executeAction(dryRun = false)` 的**函数体**替换为：

```js
  async function executeAction(dryRun = false) {
    const selected = previewRows.value.filter(r => r.selected)
    if (!selected.length) {
      showToast('请先选择文件', 'warning')
      return
    }

    executing.value = !dryRun
    executeDryRun.value = dryRun

    // **在 await 之前**读进局部变量：这是「执行那一刻」的事实，要与载荷说的
    // 一致。放在 await 之后读的话，干跑在途时用户重选剧集（pickShow 会置位
    // scraped）会让记录下来的标志与刚发出去的载荷对不上 —— 结果对话框于是把
    // 「本次没刮削」补在一条**已经刮削过**的载荷上，成了一句假话。
    const nfoBlocked = nfoNeedsScrape.value
    const source = filesStore.source
    const baseArgs = {
      path: selected[0].path.replace(selected[0].filename, ''),
      source,
      template: tplStore.currentTemplate,
      folderTemplate: tplStore.folderTemplate,
      createSeasonFolder: tplStore.createSeasonFolder,
      conflictStrategy: conflictStrategy.value,
      episodePadDigits: settingsStore.episodePadDigits,
      seasonPadDigits: settingsStore.seasonPadDigits,
      tmdb: settingsStore.tmdb,
      tmdbOverrides,
      scraped: scraped.value,
      generateNfo: generateNfo.value,
      nfoOverwrite: nfoOverwrite.value,
      openlistMaxConcurrent: settingsStore.openlist.concurrency,
      openlistRequestInterval: settingsStore.openlist.requestInterval,
    }

    try {
      if (dryRun) {
        const res = await dryRunRename(buildRenamePayload({
          ...baseArgs, mode: 'dry-run', fileIds: selected.map(r => r.id),
          overrides: _collectOverrides(selected),
        }))
        lastResult.value = {
          ...res.data, dry_run: true, nfo_blocked_by_scrape: nfoBlocked,
        }
        resultDialog.value = true
        return
      }

      // --- 单文件并发执行 ---
      const items = selected.map(r => ({
        id: r.id,
        payload: buildRenamePayload({
          ...baseArgs, mode: 'execute', fileId: r.id,
          override: r.override || null,
        }),
      }))

      // 并发上限：批次内目标重名时降级为串行（spec §10.1）。判据在
      // renameRunner.resolveConcurrency 里，由 check-rename-runner.mjs 钉住。
      const limit = resolveConcurrency({
        source,
        targets: selected.map(r => r.new_path),
        localConcurrency: settingsStore.localConcurrency,
        openlistConcurrency: settingsStore.openlist.concurrency,
      })
      const intervalMs = source === 'openlist'
        ? Math.round(settingsStore.openlist.requestInterval * 1000)
        : 0

      progress.done = 0
      progress.total = items.length
      progress.current = ''

      const { results, failures } = await runWithConcurrency(
        items, limit,
        async (item) => {
          progress.current = selected.find(r => r.id === item.id)?.filename || ''
          const res = await executeRename(item.payload)
          return res.data
        },
        {
          intervalMs,
          onProgress: (done) => { progress.done = done },
        },
      )

      // 失败条目补一条同形状的记录，让对话框照样能列出它们 —— 静默丢掉一个
      // 用户明确选中的文件，比报错更糟。
      const settled = results.map((r, i) => r ?? {
        executed: 0, skipped: 0, failed: 1,
        result: {
          id: items[i].id,
          original_path: selected[i].path,
          new_path: '',
          original_filename: selected[i].filename,
          new_filename: '',
          success: false,
          status: 'failed',
          error: failures.find(f => f.index === i)?.error?.message || '请求失败',
        },
      })

      // --- 批次收尾：只写剧集级 / 季级 NFO ---
      let finalizeBody = null
      if (source === 'local' && generateNfo.value) {
        const landed = {}
        settled.forEach((s) => {
          const st = s.result?.status
          // 与后端 _NO_LANDING_STATUSES 同一套判据 —— 未落地的文件不进 landed 表。
          if (st && !['skipped_conflict', 'conflict', 'failed'].includes(st)) {
            landed[s.result.id] = s.result.new_path
          }
        })
        // **必须在 buildPreview() 之前调**：buildPreview 会重扫并刷新后端的
        // _cached_files，之后 finalize 就重建不出同一批 plan 了。
        const fin = await finalizeRename(buildRenamePayload({
          ...baseArgs, mode: 'finalize', fileIds: selected.map(r => r.id),
          overrides: _collectOverrides(selected), landed,
        }))
        finalizeBody = fin.data
      }

      lastResult.value = {
        ...aggregateBatch({
          items: settled, finalize: finalizeBody,
          nfoBlockedByScrape: nfoBlocked, source,
        }),
      }
      resultDialog.value = true
      await buildPreview()
    } catch (e) {
      showToast('操作失败: ' + (e.response?.data?.detail || e.message), 'error')
    } finally {
      executing.value = false
      progress.done = 0
      progress.total = 0
      progress.current = ''
      // 同时复位 executeDryRun：HomeView 用 `v-if="!executeDryRun"` 把遮罩整个卸掉，
      // 若它停留在 true，后续的执行会在「已打开」的状态下第一次挂载遮罩，而
      // <Transition> 在没有 appear 时不会为首挂播放进入过渡 —— spec §11 的
      // 「模态进出 200ms」就静默失效了。
      executeDryRun.value = false
    }
  }
```

在 `executeAction` 之前加一个小助手（预览与执行两处都要收集覆盖，但行集合不同，故由调用方传行进来）：

```js
  // 逐行覆盖收集。**由调用方传入行集合**: 预览用全部预览行、执行只从选中行收集
  // —— 两者的行集合不同（首次预览时 previewRows 还是空的），把它写死在这里会
  // 把这件事实藏起来。
  function _collectOverrides(rows) {
    const overrides = {}
    rows.forEach((r) => { if (r.override) overrides[r.id] = r.override })
    return overrides
  }
```

- [ ] **Step 4: 暴露 `progress`**

在 store 的 `return { ... }` 里，把 `executing, executeDryRun,` 一行改为：

```js
    executing, executeDryRun, progress,
```

- [ ] **Step 5: 跑前端判据**

Run: `cd frontend && node scripts/check-all.mjs`
Expected: 全部通过。

- [ ] **Step 5b: 补上「死设置防复发」的判据**

现在 `workspace.js` 真的接上了设置，可以加这条判据了（它检查的正是本任务刚写下的那行）：

在 `frontend/scripts/check-rename-runner.mjs` 末尾追加：

```js
// --- 死设置防复发：workspace.js 里的并发数必须来自 settingsStore ---
// 这条断言**只能在这里加**: 它检查的是 workspace.js 里那一行, 而那个文件到本任务
// 才被改。提前放进 Task 7 会让 Task 7–9 的 check-all 一直红 —— 一条恒红的判据
// 等于没有判据（没人会去看它为什么红）。
{
  const src = readFileSync(new URL('../src/stores/workspace.js', import.meta.url), 'utf8')
  const m = src.match(/runWithConcurrency\(\s*[^,]+,\s*([^,]+),/)
  const arg = m ? m[1].trim() : ''
  assert('并发数从 settingsStore 读（不是字面量）',
    /settingsStore\.\w*[Cc]oncurrency/.test(arg), true)
}
```

并把 `readFileSync` 加回文件顶部的 import。

Run: `cd frontend && node scripts/check-all.mjs`
Expected: 全部通过。

**实测这条判据能红**：把 `workspace.js` 里传给 `runWithConcurrency` 的第二参改成字面量 `4`，跑一次，确认它红；恢复。

- [ ] **Step 6: 构建一次，确认没有语法/引用错误**

Run: `cd frontend && npx vite build`
Expected: 构建成功

- [ ] **Step 7: 提交**

```bash
git add frontend/src/stores/workspace.js frontend/src/api/renamer.js
git commit -m "feat(frontend): 执行改为逐文件并发 + 批次收尾，并暴露 progress 状态"
```

---

### Task 11: `ExecutingOverlay` 进度条

**Files:**
- Modify: `frontend/src/components/ExecutingOverlay.vue`
- Modify: `frontend/src/views/HomeView.vue`（传入 progress）

**Interfaces:**
- Consumes: Task 10 的 `ws.progress`
- Produces: `ExecutingOverlay` 新增 prop `progress: { done, total, current }`

- [ ] **Step 1: 改组件**

在 `ExecutingOverlay.vue` 的 `<script setup>` 里，props 改为：

```js
const props = defineProps({
  modelValue: Boolean,
  dryRun: Boolean,
  // 逐文件执行的进度。dryRun 时不显示（干跑是单次批量请求, 没有进度可言 ——
  // 给一个永远 0% 的进度条就是撒谎）。
  progress: {
    type: Object,
    default: () => ({ done: 0, total: 0, current: '' }),
  },
})

const percent = computed(() => {
  if (!props.progress.total) return 0
  return Math.round((props.progress.done / props.progress.total) * 100)
})
```

（在 `import { onMounted, ref, watch } from 'vue'` 里补上 `computed`。）

把模板里 `role="status"` 那个 `div` 的内容替换为：

```html
        <Loader2 v-if="dryRun" class="h-6 w-6 animate-spin text-accent" aria-hidden="true" />
        <div class="w-full text-center">
          <div class="text-[14px] font-semibold text-ink">
            {{ dryRun ? '试运行中…' : '正在执行重命名…' }}
          </div>
          <div v-if="!dryRun" class="mt-3">
            <div
              class="h-1.5 w-full overflow-hidden rounded-full bg-sunken"
              role="progressbar"
              :aria-valuenow="progress.done"
              aria-valuemin="0"
              :aria-valuemax="progress.total"
            >
              <div
                class="h-full rounded-full bg-accent transition-[width] duration-200 ease-out"
                :style="{ width: percent + '%' }"
              />
            </div>
            <div class="mt-2 flex items-center justify-between text-[12px] text-ink-2">
              <span>已完成 {{ progress.done }} / {{ progress.total }}</span>
              <span>{{ percent }}%</span>
            </div>
            <div
              v-if="progress.current"
              class="mt-1 truncate text-[11px] text-ink-2"
              :title="progress.current"
            >
              {{ progress.current }}
            </div>
          </div>
          <div v-else class="mt-1 text-[12px] text-ink-2">请稍候，操作进行中请勿关闭</div>
        </div>
```

- [ ] **Step 2: 传入 progress**

在 `HomeView.vue` 里把

```html
  <ExecutingOverlay v-if="!ws.executeDryRun" v-model="ws.executing" :dry-run="ws.executeDryRun" />
```

改为

```html
  <ExecutingOverlay
    v-if="!ws.executeDryRun"
    v-model="ws.executing"
    :dry-run="ws.executeDryRun"
    :progress="ws.progress"
  />
```

- [ ] **Step 3: 跑判据与构建**

Run: `cd frontend && node scripts/check-all.mjs && npx vite build`
Expected: 判据全绿、构建成功

- [ ] **Step 4: 人工验收（必须真跑一次）**

启动应用，扫描一个真实目录，选中若干文件执行重命名，确认：
1. 进度条从 0 走到 100%，数字单调递增；
2. 期间鼠标点不动背后的界面（阻断仍然生效）；
3. 结束后结果对话框的内容与改动前同形（成功 / 跳过 / 失败计数、NFO 清单都在）。

Run: `cd backend && python run.py`（另开一个终端 `cd frontend && npx vite`）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/ExecutingOverlay.vue frontend/src/views/HomeView.vue
git commit -m "feat(frontend): 执行遮罩增加进度条（干跑仍为转圈）"
```

---

### Task 12: 设置页界面

**Files:**
- Modify: `frontend/src/views/SettingsView.vue`

**Interfaces:**
- Consumes: Task 9 的 `settingsStore.localConcurrency` 与载荷字段 `openlistMaxConcurrent` / `openlistRequestInterval`、Task 10 的读取点
- Produces: 设置页的「本地并发」输入项；OpenList 分组提示文案改为「立即生效」

> **前置**：本任务只做**界面**。`settingsSchema.js` / `settings.js` / `check-settings-schema.mjs` 的改动已在 Task 9 落地 —— 数据层必须先于 Task 10 的接线，否则 `settingsStore.localConcurrency` 是 `undefined`，`runWithConcurrency` 会直接抛错。

- [ ] **Step 1: 改设置页**

在 `SettingsView.vue` 里找到 `draft.openlist.concurrency` 所在的 `AppPanel`（标题「OpenList 设置」），在它**之前**插入一个面板：

```html
      <AppPanel title="重命名执行">
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <AppInput
            v-model="draft.localConcurrency"
            type="number"
            label="本地并发"
            :min="1"
            :max="10"
            hint="同时在途的重命名请求数。本地是磁盘操作，默认 4。"
          />
        </div>
      </AppPanel>
```

把 OpenList 分组里那段提示（「这两项当前由服务端的 `openlist_max_concurrent` 与 `openlist_request_interval` 决定。此处保存的值会被保留，但尚未下发到后端。」）整段删除，替换为：

```html
          <div
            class="flex items-start gap-2 rounded-[8px] bg-sunken px-3 py-2.5 text-[12px] text-ink-2"
          >
            <Info class="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <p>
              这两项随每次重命名请求下发，<strong class="text-ink">立即生效</strong>。
              服务端的 <code class="font-mono">OPENLIST_MAX_CONCURRENT</code> /
              <code class="font-mono">OPENLIST_REQUEST_INTERVAL</code> 只在这两项
              未设置时作为初值。注意它们作用于 OpenList 客户端的<strong class="text-ink">全部</strong>请求
              （含扫描与列目录），不只是重命名。
            </p>
          </div>
```

在 `draft` 的初始化与 `apply` 回填处补上 `localConcurrency`（照 `conflictStrategy` 的既有写法各加一行）。

- [ ] **Step 2: 跑前端判据与构建**

Run: `cd frontend && node scripts/check-all.mjs && npx vite build`
Expected: 判据全绿、构建成功

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/SettingsView.vue
git commit -m "feat(settings): 设置页新增本地并发，OpenList 分组提示改为「立即生效」"
```

---

### Task 13: 文档

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新冲突策略说明**

在 README 的冲突策略一行（`**冲突策略** — \`skip\` / \`abort\` / \`rename_dup\` / \`overwrite\` 四种目标已存在时的处理方式`）后补一句：

```markdown
> 执行是**逐文件**进行的，因此 `abort` 的含义是「这一个文件不执行」，不再是「整批中止」。
```

- [ ] **Step 2: 记录接口变更**

在 README 的「技术栈」之前加一节：

```markdown
## 🔌 执行接口

重命名按**单个文件**执行：前端逐个并发发起 `POST /api/rename/execute`，并据此显示进度条。
剧集级 / 季级 NFO（`tvshow.nfo` / `season.nfo`）是整批的事实，由前端在全部文件跑完后调用
`POST /api/rename/finalize` 写出，请求体里的 `landed` 是**实际落地**的文件及其真实落点。

| 接口 | 形态 |
| --- | --- |
| `POST /api/rename/preview` | 批量（纯计划，不写盘） |
| `POST /api/rename/dry-run` | 批量（纯计划，不写盘） |
| `POST /api/rename/execute` | **单文件** |
| `POST /api/rename/finalize` | 批量收尾（只写剧集级 / 季级 NFO） |

> 后端为单 worker 进程运行，`execute` 与 `finalize` 依赖进程内的文件缓存，**不要**加 `--workers`。
```

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs(readme): 记录逐文件执行接口与 abort 语义变更"
```

---

## 完成标准

全部 13 个 Task 完成后，以下三条必须同时成立：

1. `cd backend && python -m pytest -q` 全绿（214 条既有 + 各任务新增）。
2. `cd frontend && node scripts/check-all.mjs` 全绿，且 `check-all.mjs` 的名单里包含 `check-rename-runner.mjs` 与 `check-rename-aggregate.mjs`。
3. Task 11 Step 4 的人工验收通过（进度条走满、界面阻断、结果对话框同形）。

任何一条不成立都**不得**宣布完成。

"""OpenList 批量执行编排的判据。

异步驱动用**标准库 asyncio.run** —— 本项目未装 pytest-asyncio（理由见
tests/test_openlist_single.py 的模块注释）。
"""
import asyncio
import posixpath

from app.core.openlist_batch import (
    batch_result_payload,
    execute_openlist_plan_once,
    execute_openlist_plans,
    resolve_batch_concurrency,
)
from app.core.openlist_renamer import build_openlist_rename_plan
from app.models.file import FileInfo, OverrideInfo
from app.models.nfo import NfoOptions
from app.models.strm import StrmOptions

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
NO_NFO = NfoOptions(enabled=False)
NO_STRM = StrmOptions(enabled=False)


class FakeClient:
    """记录调用序列、可制造在途峰值的假客户端。"""

    def __init__(self, delay: float = 0.0, delays: dict | None = None,
                 fail_names: set[str] | None = None):
        self.delay = delay
        # 按文件名给不同延迟 —— 让「快慢」与计划顺序相反, 用来钉住结果顺序。
        self.delays = delays or {}
        self.fail_names = fail_names or set()
        self.calls: list[tuple] = []
        self.active = 0
        self.peak = 0

    async def rename(self, path, new_name):
        name = posixpath.basename(path)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delays.get(name, self.delay))
            if name in self.fail_names:
                # execute_openlist_one 内部会把它折成 status="failed" 的结果;
                # 这里抛错正是要验证「单文件失败不中断整批」。
                raise Exception("重命名失败")
            self.calls.append(("rename", path, new_name))
            return {"code": 200}
        finally:
            self.active -= 1

    async def move(self, src_dir, dst_dir, names):
        self.calls.append(("move", src_dir, dst_dir, tuple(names)))
        return {"code": 200}

    async def mkdir(self, parent_dir, dir_name):
        self.calls.append(("mkdir", parent_dir, dir_name))
        return {"code": 200}

    async def list_directory(self, path, refresh=False):
        # NFO 跟随移动会列目录。空目录 = 没有既有 NFO, 与本组用例无关。
        # 但**要记下来**: 「目录内容列表不得跨文件缓存」那条判据数的是它。
        self.calls.append(("list", path))
        return [], True

    async def put_file(self, path, content):
        self.calls.append(("put_file", path))
        return {"code": 200}


def _file(name: str, parent: str = "/media/Show", **extra) -> FileInfo:
    return FileInfo(
        id=name, source="openlist", path=f"{parent}/{name}", filename=name,
        extension=posixpath.splitext(name)[1], parent_dir=parent, **extra,
    )


def _plan(file: FileInfo):
    return build_openlist_rename_plan(file, TEMPLATE)


def _run(coro):
    return asyncio.run(coro)


def test_results_follow_plan_order_not_completion_order(monkeypatch):
    """慢文件排在前面时, 结果仍必须按 plans 顺序返回。

    按完成顺序返回会让结果行与用户看见的表格错位 —— 而每一行的文件名都「看着
    合理」, 没有任何报错。这里让第一个文件最慢、第二个最快。
    """
    slow = _file("Show.S01E01.mkv")
    fast = _file("Show.S01E02.mkv")
    plans = [_plan(slow), _plan(fast)]
    client = FakeClient(delays={"Show.S01E01.mkv": 0.05, "Show.S01E02.mkv": 0.0})

    outcomes = _run(execute_openlist_plans(
        client, plans, nfo_options=NO_NFO, strm_options=NO_STRM, max_concurrent=2,
    ))

    assert [o.plan.original_filename for o in outcomes] == [
        "Show.S01E01.mkv", "Show.S01E02.mkv",
    ]
    assert [o.result.status for o in outcomes] == ["renamed", "renamed"]


def test_file_level_concurrency_is_bounded_by_limit():
    """文件级并发不得超过请求里的上限（客户端限流器只管单次 HTTP）。"""
    plans = [_plan(_file(f"Show.S01E0{i}.mkv")) for i in range(1, 7)]
    client = FakeClient(delay=0.02)

    _run(execute_openlist_plans(
        client, plans, nfo_options=NO_NFO, strm_options=NO_STRM, max_concurrent=2,
    ))

    assert client.peak == 2, f"峰值 {client.peak}, 上限 2 未被遵守"


def test_duplicate_targets_degrade_to_serial():
    """两个文件算出同一个目标名 → 必须串行。

    并发下它们会双双通过存在性检查（check_conflict 的第二参恒为空列表,
    duplicate_in_batch 从不触发）, overwrite 策略时会静默覆盖 —— 数据丢失。
    """
    a = _file("Show.S01E01.mkv")
    b = _file("Show.S01E01.1080p.mkv")
    override = OverrideInfo(show_name="Show", season=1, episode=1)
    plans = [
        build_openlist_rename_plan(a, TEMPLATE, override=override),
        build_openlist_rename_plan(b, TEMPLATE, override=override),
    ]
    assert plans[0].new_path == plans[1].new_path, "夹具没造出同名目标"
    assert resolve_batch_concurrency(plans, 6) == 1

    client = FakeClient(delay=0.02)
    _run(execute_openlist_plans(
        client, plans, nfo_options=NO_NFO, strm_options=NO_STRM, max_concurrent=6,
    ))
    assert client.peak == 1, f"重名目标未降级为串行, 峰值 {client.peak}"


def test_progress_reaches_total_exactly_once_per_file():
    """进度必须逐个文件推进, 且最终恰好等于总数（进度条走到 100% 的根据）。"""
    plans = [_plan(_file(f"Show.S01E0{i}.mkv")) for i in range(1, 5)]
    client = FakeClient()
    seen: list[tuple[int, int, str]] = []

    async def on_progress(done, total, current):
        seen.append((done, total, current))

    _run(execute_openlist_plans(
        client, plans, nfo_options=NO_NFO, strm_options=NO_STRM,
        max_concurrent=2, on_progress=on_progress,
    ))

    assert [item[0] for item in seen] == [1, 2, 3, 4]
    assert all(item[1] == 4 for item in seen)
    assert sorted(item[2] for item in seen) == sorted(
        f"Show.S01E0{i}.mkv" for i in range(1, 5)
    )


def test_one_failure_does_not_stop_the_batch():
    """单文件失败只占自己那一行, 其余照旧跑完（与前端并发池同一条纪律）。"""
    plans = [_plan(_file(f"Show.S01E0{i}.mkv")) for i in range(1, 4)]
    client = FakeClient(fail_names={"Show.S01E02.mkv"})

    outcomes = _run(execute_openlist_plans(
        client, plans, nfo_options=NO_NFO, strm_options=NO_STRM, max_concurrent=3,
    ))

    by_name = {o.plan.original_filename: o for o in outcomes}
    assert by_name["Show.S01E02.mkv"].result.status == "failed"
    assert by_name["Show.S01E02.mkv"].failed == 1
    assert by_name["Show.S01E01.mkv"].executed == 1
    assert by_name["Show.S01E03.mkv"].executed == 1


def test_subtitle_never_reports_a_landed_path():
    """字幕与视频共用同一套 status, 但它的落点不得给组级 NFO 背书。"""
    video = _file("Show.S01E01.mkv")
    subtitle = _file("Show.S01E01.chs.ass", is_subtitle=True)
    client = FakeClient()

    video_outcome = _run(execute_openlist_plan_once(
        client, _plan(video), nfo_options=NO_NFO,
        nfo_matches={}, strm_options=NO_STRM,
    ))
    subtitle_outcome = _run(execute_openlist_plan_once(
        client, _plan(subtitle), nfo_options=NO_NFO,
        nfo_matches={}, strm_options=NO_STRM,
    ))

    assert video_outcome.result.status == "renamed"
    assert video_outcome.landed_path == video_outcome.result.new_path
    assert subtitle_outcome.result.status == "renamed"
    assert subtitle_outcome.landed_path is None


def test_exception_in_pipeline_becomes_a_failed_row(monkeypatch):
    """流水线自身抛错时, 该行折成 failed 而不是让整批炸掉。"""
    import app.core.openlist_batch as batch_mod

    plans = [_plan(_file("Show.S01E01.mkv")), _plan(_file("Show.S01E02.mkv"))]
    real = batch_mod.execute_openlist_plan_once

    async def flaky(client, plan, **kwargs):
        if plan.original_filename == "Show.S01E01.mkv":
            raise RuntimeError("客户端炸了")
        return await real(client, plan, **kwargs)

    monkeypatch.setattr(batch_mod, "execute_openlist_plan_once", flaky)
    outcomes = _run(execute_openlist_plans(
        FakeClient(), plans, nfo_options=NO_NFO, strm_options=NO_STRM, max_concurrent=2,
    ))

    assert outcomes[0].result.status == "failed"
    assert outcomes[0].failed == 1
    assert "客户端炸了" in outcomes[0].result.error
    assert outcomes[1].executed == 1


def test_payload_shape_matches_batch_result_contract():
    """响应体字段与 `BatchRenameResult` / 前端聚合器逐字同形。

    ResultDialog 直接消费这些字段; 换名字就得同时改对话框与聚合器 —— 两边一旦
    分叉, 同一个对话框会对两个数据源显示不同的东西。
    """
    plans = [_plan(_file("Show.S01E01.mkv"))]
    outcomes = _run(execute_openlist_plans(
        FakeClient(), plans, nfo_options=NO_NFO, strm_options=NO_STRM, max_concurrent=1,
    ))

    payload = batch_result_payload(
        outcomes,
        nfo_written=["/media/Show/tvshow.nfo"],
        nfo_skipped=[("/media/Show/season.nfo", "已存在")],
        folders_renamed=[{"old_path": "/media/Show", "new_path": "/media/Show (2008)"}],
        folders_error=None,
    )

    for key in (
        "success", "source", "executed", "skipped", "failed", "total",
        "conflicts", "results", "errors", "nfo_written", "nfo_carried",
        "nfo_skipped", "strm_written", "strm_skipped",
        "folders_renamed", "folders_skipped", "dry_run",
    ):
        assert key in payload, f"缺字段 {key}"

    assert payload["source"] == "openlist"
    assert payload["total"] == 1
    assert payload["executed"] == 1
    assert payload["failed"] == 0
    assert payload["success"] is True
    assert payload["dry_run"] is False
    assert payload["nfo_written"] == ["/media/Show/tvshow.nfo"]
    assert payload["nfo_skipped"] == [{"path": "/media/Show/season.nfo", "reason": "已存在"}]
    assert payload["results"][0]["status"] == "renamed"


def test_payload_carries_nonfatal_stage_errors():
    """收尾阶段的失败只落在 nfo_error / folders_error 上, 不翻成整批失败。"""
    outcomes = _run(execute_openlist_plans(
        FakeClient(), [_plan(_file("Show.S01E01.mkv"))],
        nfo_options=NO_NFO, strm_options=NO_STRM, max_concurrent=1,
    ))
    payload = batch_result_payload(
        outcomes, nfo_error="NFO 收尾炸了", folders_error="目录改名炸了",
    )

    assert payload["failed"] == 0 and payload["success"] is True
    assert payload["nfo_error"] == "NFO 收尾炸了"
    assert payload["folders_error"] == "目录改名炸了"
    assert payload["results"][0]["status"] == "renamed"


def test_directory_creation_is_shared_across_the_batch():
    """整批只建一次目录 —— 不是每集一次。

    判据是 **mkdir 的次数**而不是耗时: 「这个目录存在」是整批内单调的事实,
    共用一份缓存即可。每集重建成一次, 在几十集时就会白白多出几十次请求;
    这正是「并发调到 10 还是很慢」的一半来源（另一半是请求间隔）。

    `remote_custom` 下的 STRM 是**逐级**建目录（`/strm` → `/strm/Show`）,
    所以三个文件修好后应只有 2 次 mkdir, 修之前是 6 次。
    """
    plans = [_plan(_file(f"Show.S01E0{i}.mkv")) for i in range(1, 4)]
    client = FakeClient()

    _run(execute_openlist_plans(
        client, plans,
        nfo_options=NO_NFO,
        strm_options=StrmOptions(
            enabled=True, mode="remote_custom",
            base_url="http://ol", remote_root="/strm",
        ),
        strm_scan_root="/media/Show",
        max_concurrent=3,
    ))

    mkdirs = [c for c in client.calls if c[0] == "mkdir"]
    puts = [c for c in client.calls if c[0] == "put_file"]
    assert sorted(mkdirs) == [
        ("mkdir", "/", "strm"), ("mkdir", "/strm", "Show"),
    ], mkdirs
    assert len(puts) == 3, puts


def test_directory_cache_does_not_hide_a_name_conflict():
    """共享的只有 mkdir 标记, **不**是目录内容列表。

    目录内容在本批执行过程中会变（刚改完名的文件就在里面）。若把内容列表也
    缓存起来, 「目标已存在」与「旧 NFO 是否存在」都会读到过期快照 —— 前者覆盖
    用户文件, 后者漏搬 NFO, 两者都是静默的数据事故。所以判据是: 每个文件仍然
    **各自列一次**目录（三条 list, 而不是一条）。
    """
    plans = []
    for i in range(1, 4):
        plan = _plan(_file(f"Show.S01E0{i}.mkv"))
        # 改成「移动进季目录」: status 变 renamed_moved 才会走旧 NFO 跟随,
        # 那条路径要列目录 —— 正是本用例要盯着的东西。
        plan.new_dir = "/media/Show/Season 01"
        plan.new_path = posixpath.join(plan.new_dir, plan.new_filename)
        plans.append(plan)
    client = FakeClient()

    _run(execute_openlist_plans(
        client, plans, nfo_options=NO_NFO, strm_options=NO_STRM, max_concurrent=3,
    ))

    lists = [c for c in client.calls if c[0] == "list"]
    mkdirs = [c for c in client.calls if c[0] == "mkdir"]
    assert len(lists) == 3, lists
    # 季目录是整批共享的那份缓存: 3 个文件只建一次。
    assert mkdirs == [("mkdir", "/media/Show", "Season 01")], mkdirs

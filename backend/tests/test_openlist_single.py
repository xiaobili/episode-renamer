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
        # 单文件路径**不得**调用它 —— 见 test_never_calls_batch_rename
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


def test_move_succeeds_rename_fails_reports_real_location():
    """移动成功、改名失败时**不得**报 failed, 且落点必须是文件真实所在处。

    批量路径的补偿是 `client.rename(p.original_path, ...)`（移动**前**的位置,
    本情形下已经空了, 注定失败）; 单文件路径没有可退的第二次调用, 于是它曾经的
    形状是「move 成功、rename 抛错 → status=failed」—— 而文件**已经在
    new_dir/original_filename 了**: 用户被告知失败, 实际却已经搬走。

    后果不止是文案: `landed_path_of` 对 failed 返回 None, 这个已经移动的文件于是
    从落地表里消失 —— OpenList 的 NFO 一旦启用, 组级判据（spec §9.4）就会把它
    当成没落地。

    判据三件一起: 状态不再是 failed、new_path 是**真实**位置、且 landed_path_of
    认它落地。只改状态名而仍把 new_path 留在目标路径上, 后两条里会红一条。
    """
    from app.core.local_renamer import landed_path_of

    f = _file("Show.S01E01.mkv")
    plan = build_openlist_rename_plan(
        f, TEMPLATE, folder_template="Season {season_padded}",
        create_season_folder=True,
    )
    moved_to = "/media/Show/Season 01/Show.S01E01.mkv"
    client = FakeClient(fail_rename=True)      # move 照常成功, rename 必失败
    result = asyncio.run(execute_openlist_one(client, plan))

    assert result.status == "moved_not_renamed", result.status
    assert result.success is False
    assert result.new_path == moved_to, result.new_path
    assert result.new_filename == "Show.S01E01.mkv", result.new_filename
    assert "重命名失败" in result.error and moved_to in result.error, result.error
    # 关键的一条: 它**算落地**（否则 OpenList 接上 NFO 那天它会被判成没落地）。
    assert landed_path_of(result) == moved_to
    # 调用序列不变: 一次 mkdir + 一次 move + 一次失败的 rename。
    assert [c[0] for c in client.calls] == ["mkdir", "move", "rename"], client.calls

    # 反向钉住: 同目录改名失败（没有任何移动）时仍是**普通的 failed** ——
    # 文件确实没动, 把它报成「已移动」是另一种假话。
    f2 = _file("Show.S01E02.mkv")
    plan2 = build_openlist_rename_plan(f2, TEMPLATE)
    client2 = FakeClient(fail_rename=True)
    result2 = asyncio.run(execute_openlist_one(client2, plan2))
    assert result2.status == "failed", result2.status
    assert landed_path_of(result2) is None


def test_never_calls_batch_rename():
    """单文件路径不得退化成批量 API —— 那会把「一个文件一次请求」的语义悄悄改掉。"""
    f = _file("Show.S01E01.mkv")
    plan = build_openlist_rename_plan(f, TEMPLATE)
    client = FakeClient()
    asyncio.run(execute_openlist_one(client, plan))
    assert all(c[0] != "batch_rename" for c in client.calls)

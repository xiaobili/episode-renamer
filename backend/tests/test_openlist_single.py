"""OpenList 单文件执行的判据。

异步驱动用标准库 asyncio.run，与 test_tmdb_client.py / test_tmdb_resolver.py
一致 —— 本项目**未装 pytest-asyncio**（见 test_tmdb_client.py 开头的说明），
所以这里不写 @pytest.mark.asyncio：没有插件时它只是个未知标记，用例会被
pytest 判为 "async def functions are not natively supported" 而失败。
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
    assert client.calls[2][0] == "rename"


def test_rename_failure_is_reported_not_raised():
    f = _file("Show.S01E01.mkv")
    plan = build_openlist_rename_plan(f, TEMPLATE)
    client = FakeClient(fail_rename=True)
    result = asyncio.run(execute_openlist_one(client, plan))
    assert result.success is False
    assert result.status == "failed"
    assert "重命名失败" in result.error


def test_never_calls_batch_rename():
    """单文件路径不得退化成批量 API —— 那会把「一个文件一次请求」的语义悄悄改掉。"""
    f = _file("Show.S01E01.mkv")
    plan = build_openlist_rename_plan(f, TEMPLATE)
    client = FakeClient()
    asyncio.run(execute_openlist_one(client, plan))
    assert all(c[0] != "batch_rename" for c in client.calls)

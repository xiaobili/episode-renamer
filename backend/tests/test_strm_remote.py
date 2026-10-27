"""STRM 远端写盘与失败降级。"""
import asyncio
import os

from app.core.strm import (
    MISSING_REMOTE_ROOT,
    NOT_LANDED_STRM_REASON,
    ensure_remote_dir,
    write_strm_for_plan,
)
from app.core.openlist_renamer import build_openlist_rename_plan
from app.models.file import FileInfo, RenameResult
from app.models.strm import StrmOptions

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"


class FakeClient:
    def __init__(self, fail_mkdir=False, fail_put=None):
        self.fail_mkdir = fail_mkdir
        self.fail_put = fail_put
        self.calls = []

    async def mkdir(self, parent_dir, dir_name):
        self.calls.append(("mkdir", parent_dir, dir_name))
        if self.fail_mkdir:
            raise Exception("object already exists")
        return {"code": 200}

    async def put_file(self, path, content):
        self.calls.append(("put", path, content))
        if self.fail_put:
            raise Exception(self.fail_put)
        return {"code": 200}


def _plan(name="Show.S01E01.mkv", parent="/115/Show A", is_subtitle=False):
    file = FileInfo(
        id=name, source="openlist", path=f"{parent}/{name}", filename=name,
        extension=".srt" if is_subtitle else ".mkv", parent_dir=parent,
        is_subtitle=is_subtitle,
    )
    return build_openlist_rename_plan(file, TEMPLATE)


def _result(plan, *, status="renamed", new_path=None):
    return RenameResult(
        id=plan.id,
        original_path=plan.original_path,
        new_path=new_path or plan.new_path,
        original_filename=plan.original_filename,
        new_filename=plan.new_filename,
        success=status != "failed",
        status=status,
    )


def _options(**kwargs):
    base = dict(
        enabled=True,
        mode="remote_custom",
        base_url="http://openlist:5244",
        local_root="",
        remote_root="/strm",
    )
    base.update(kwargs)
    return StrmOptions(**base)


def test_remote_custom_writes_with_mirrored_dirs():
    plan = _plan()
    client = FakeClient()
    written, skipped = asyncio.run(
        write_strm_for_plan(client, plan, _result(plan), _options(), "/115")
    )

    target = "/strm/Show A/Show A - S01E01.strm"
    assert written == [target]
    assert skipped == []
    assert ("mkdir", "/", "strm") in client.calls
    assert ("mkdir", "/strm", "Show A") in client.calls
    put = [call for call in client.calls if call[0] == "put"]
    assert put == [(
        "put", target,
        b"http://openlist:5244/d/115/Show A/Show A - S01E01.mkv\n",
    )]


def test_remote_custom_creates_show_dir_when_scan_root_is_the_show_dir():
    # 一次只扫一部剧（扫描根 = 剧目录）时, 相对路径为空; 剧集名目录仍必须建出来。
    plan = _plan()
    client = FakeClient()
    written, _ = asyncio.run(
        write_strm_for_plan(client, plan, _result(plan), _options(), "/115/Show A"),
    )

    assert written == ["/strm/Show A/Show A - S01E01.strm"]
    assert ("mkdir", "/strm", "Show A") in client.calls


def test_remote_same_writes_next_to_video_without_mkdir():
    plan = _plan()
    client = FakeClient()
    written, _ = asyncio.run(
        write_strm_for_plan(
            client, plan, _result(plan), _options(mode="remote_same"), "/115",
        )
    )
    assert written == ["/115/Show A/Show A - S01E01.strm"]
    assert [call[0] for call in client.calls] == ["put"]


def test_local_mode_writes_disk_and_ignores_client(tmp_path):
    plan = _plan()
    client = FakeClient()
    written, _ = asyncio.run(
        write_strm_for_plan(
            client, plan, _result(plan),
            _options(mode="local", local_root=str(tmp_path)), "/115",
        )
    )
    target = os.path.join(str(tmp_path), "Show A", "Show A - S01E01.strm")
    assert written == [target]
    assert client.calls == []
    with open(target, "rb") as handle:
        assert handle.read().startswith(b"http://openlist:5244/d/115/")


def test_ensure_remote_dir_is_cached_per_directory():
    client = FakeClient()
    cache: dict[str, bool] = {}
    asyncio.run(ensure_remote_dir(client, "/strm/Show A", cache))
    asyncio.run(ensure_remote_dir(client, "/strm/Show A", cache))
    assert len([call for call in client.calls if call[0] == "mkdir"]) == 2


def test_mkdir_failure_is_ignored_because_dir_may_exist():
    plan = _plan()
    client = FakeClient(fail_mkdir=True)
    written, _ = asyncio.run(
        write_strm_for_plan(client, plan, _result(plan), _options(), "/115"),
    )
    assert written == ["/strm/Show A/Show A - S01E01.strm"]


def test_put_failure_is_reported_not_raised():
    plan = _plan()
    client = FakeClient(fail_put="quota exceeded")
    written, skipped = asyncio.run(
        write_strm_for_plan(client, plan, _result(plan), _options(), "/115"),
    )
    assert written == []
    assert skipped == [
        ("/strm/Show A/Show A - S01E01.strm", "写入失败: quota exceeded"),
    ]


def test_subtitle_is_skipped_silently():
    plan = _plan("Show.S01E01.chs.srt", is_subtitle=True)
    client = FakeClient()
    written, skipped = asyncio.run(
        write_strm_for_plan(client, plan, _result(plan), _options(), "/115"),
    )
    assert (written, skipped, client.calls) == ([], [], [])


def test_not_landed_reports_video_path():
    plan = _plan()
    client = FakeClient()
    written, skipped = asyncio.run(
        write_strm_for_plan(client, plan, _result(plan, status="failed"), _options(), "/115"),
    )
    assert written == []
    assert skipped == [(plan.new_path, NOT_LANDED_STRM_REASON)]
    assert client.calls == []


def test_missing_remote_root_reports_reason():
    plan = _plan()
    written, skipped = asyncio.run(
        write_strm_for_plan(
            FakeClient(), plan, _result(plan), _options(remote_root=" "), "/115",
        ),
    )
    assert written == []
    assert skipped == [(plan.new_path, MISSING_REMOTE_ROOT)]

"""OpenList 远端 NFO 写入的判据。

异步驱动用标准库 asyncio.run —— 本项目未装 pytest-asyncio（理由见
tests/test_openlist_single.py 的模块注释）。
"""
import asyncio
import posixpath

from app.core.nfo_writer import (
    CARRIED_NFO_TARGET_EXISTS_REASON,
    DROPPED_GROUP_NFO_REASON,
    NOT_RENAMED_NFO_REASON,
)
from app.core.openlist_nfo import (
    episode_nfo_for_plan,
    finalize_openlist_nfo,
    plan_openlist_nfo,
)
from app.core.openlist_renamer import build_openlist_rename_plan
from app.core.tmdb_resolver import EpisodeMatch
from app.models.file import FileInfo, OverrideInfo, RenameResult
from app.models.nfo import NfoOptions
from app.models.openlist import OpenListFile
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow


TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
OPTIONS = NfoOptions(enabled=True, overwrite=False)


class FakeClient:
    """记录调用的远端替身；dirs 是「目录 → 文件名集合」。"""

    def __init__(self, dirs=None, fail_list=None, fail_put=None, missing=None):
        self.dirs = {k: set(v) for k, v in (dirs or {}).items()}
        self.fail_list = set(fail_list or ())
        self.missing = set(missing or ())
        self.fail_put = fail_put
        self.calls: list = []

    async def list_directory(self, path, refresh=False):
        self.calls.append(("list", path))
        if path in self.fail_list:
            raise Exception("network down")
        if path in self.missing:
            raise Exception("列出目录失败: object not found")
        return [
            OpenListFile(name=name, path=f"{path}/{name}")
            for name in self.dirs.get(path, set())
        ], True

    async def put_file(self, path, content):
        self.calls.append(("put", path, content))
        if self.fail_put:
            raise Exception(self.fail_put)
        directory, name = posixpath.split(path)
        self.dirs.setdefault(directory, set()).add(name)
        return {"code": 200}

    async def rename(self, path, new_name):
        self.calls.append(("rename", path, new_name))
        directory, name = posixpath.split(path)
        self.dirs.setdefault(directory, set()).discard(name)
        self.dirs.setdefault(directory, set()).add(new_name)
        return {"code": 200}

    async def move(self, src_dir, dst_dir, names):
        self.calls.append(("move", src_dir, dst_dir, tuple(names)))
        for name in names:
            self.dirs.setdefault(src_dir, set()).discard(name)
            self.dirs.setdefault(dst_dir, set()).add(name)
        return {"code": 200}


def _file(name, parent="/media/Show", is_subtitle=False):
    return FileInfo(
        id=name, source="openlist", path=f"{parent}/{name}", filename=name,
        extension=".srt" if is_subtitle else ".mkv", parent_dir=parent,
        is_subtitle=is_subtitle,
    )


def _match(show_name="Show", season=1, episode=1, with_episode=True):
    return EpisodeMatch(
        status="matched",
        show=TmdbShow(tv_id=1, name=show_name, original_name=show_name, year=2020),
        season=TmdbSeason(season_number=season, name="Season 1", tmdb_id=2),
        episode=(
            TmdbEpisode(episode_number=episode, name="Pilot", tmdb_id=3)
            if with_episode else None
        ),
    )


def _plan(name="Show.S01E01.mkv", parent="/media/Show", override=None, **kwargs):
    return build_openlist_rename_plan(_file(name, parent), TEMPLATE, override=override, **kwargs)


def _result(plan, status="renamed", new_path=None, success=True):
    return RenameResult(
        id=plan.id,
        original_path=plan.original_path,
        new_path=new_path or plan.new_path,
        original_filename=plan.original_filename,
        new_filename=plan.new_filename,
        success=success,
        status=status,
    )


def test_episode_nfo_uses_real_landed_path():
    """移动成功、改名失败时, NFO 必须跟着**真实文件名**走, 而不是计划名。"""
    plan = _plan(
        folder_template="Season {season_padded}", create_season_folder=True,
    )
    moved_to = "/media/Show/Season 01/Show.S01E01.mkv"
    result = _result(plan, status="moved_not_renamed", new_path=moved_to, success=False)
    client = FakeClient(dirs={
        "/media/Show": {"Show.S01E01.mkv"},
        "/media/Show/Season 01": set(),
    })

    written, carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()}, OPTIONS,
    ))

    expected = "/media/Show/Season 01/Show.S01E01.nfo"
    assert written == [expected]
    assert carried == []
    assert skipped == []
    assert [c for c in client.calls if c[0] == "put"][0][1] == expected
    assert result.nfo_path == expected


def test_existing_remote_nfo_is_skipped_without_overwrite():
    plan = _plan()
    result = _result(plan)
    target = "/media/Show/Show - S01E01.nfo"
    client = FakeClient(dirs={"/media/Show": {"Show.S01E01.mkv", "Show - S01E01.nfo"}})

    written, _carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()}, OPTIONS,
    ))

    assert written == []
    assert not any(c[0] == "put" for c in client.calls)
    assert (target, "已存在") in skipped


def test_overwrite_replaces_existing_remote_nfo():
    plan = _plan()
    result = _result(plan)
    client = FakeClient(dirs={"/media/Show": {"Show.S01E01.mkv", "Show - S01E01.nfo"}})

    written, _carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()},
        NfoOptions(enabled=True, overwrite=True),
    ))

    assert written == ["/media/Show/Show - S01E01.nfo"]
    assert skipped == []
    assert any(c[0] == "put" for c in client.calls)


def test_carry_moves_old_same_stem_nfo_before_write():
    plan = _plan()
    result = _result(plan)
    old_nfo = "/media/Show/Show.S01E01.nfo"
    new_nfo = "/media/Show/Show - S01E01.nfo"
    client = FakeClient(dirs={"/media/Show": {"Show.S01E01.mkv", "Show.S01E01.nfo"}})

    written, carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()}, OPTIONS,
    ))

    assert carried == [new_nfo]
    # 搬过去的旧 NFO 占住了新位置 → 生成侧如实报「已存在」, 用户内容不被替掉。
    assert written == []
    assert (new_nfo, "已存在") in skipped
    assert ("rename", old_nfo, "Show - S01E01.nfo") in client.calls
    assert not any(c[0] == "put" for c in client.calls)


def test_carry_refuses_when_target_exists():
    plan = _plan()
    result = _result(plan)
    new_nfo = "/media/Show/Show - S01E01.nfo"
    client = FakeClient(dirs={"/media/Show": {
        "Show.S01E01.mkv", "Show.S01E01.nfo", "Show - S01E01.nfo",
    }})

    _written, carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()}, OPTIONS,
    ))

    assert carried == []
    assert (new_nfo, CARRIED_NFO_TARGET_EXISTS_REASON) in skipped
    assert not any(c[0] in ("rename", "move", "put") for c in client.calls)


def test_subtitle_is_excluded():
    plan = _plan("Show.S01E01.chs.srt")
    plan.file_info = _file("Show.S01E01.chs.srt", is_subtitle=True)
    result = _result(plan)
    client = FakeClient(dirs={"/media/Show": {"Show.S01E01.chs.srt"}})

    written, carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()}, OPTIONS,
    ))

    assert (written, carried, skipped) == ([], [], [])
    assert client.calls == []


def test_not_landed_reports_skip():
    plan = _plan()
    result = _result(plan, status="failed", success=False)
    client = FakeClient(dirs={"/media/Show": {"Show.S01E01.mkv"}})

    written, carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()}, OPTIONS,
    ))

    assert written == []
    assert carried == []
    assert skipped == [("/media/Show/Show - S01E01.nfo", NOT_RENAMED_NFO_REASON)]
    assert client.calls == []


def test_missing_metadata_reports_skip():
    plan = _plan()
    result = _result(plan)
    client = FakeClient(dirs={"/media/Show": {"Show.S01E01.mkv"}})

    written, _carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {}, OPTIONS,
    ))

    assert written == []
    assert ("/media/Show/Show - S01E01.nfo", "TMDB 未匹配, 不写残缺 NFO") in skipped
    assert not any(c[0] == "put" for c in client.calls)


def test_list_failure_is_skipped_not_raised():
    plan = _plan()
    result = _result(plan)
    client = FakeClient(
        dirs={"/media/Show": {"Show.S01E01.mkv"}},
        fail_list={"/media/Show"},
    )

    written, _carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()}, OPTIONS,
    ))

    assert written == []
    assert any("写入失败" in reason for _path, reason in skipped), skipped


def test_upload_failure_is_skipped_not_raised():
    plan = _plan()
    result = _result(plan)
    client = FakeClient(
        dirs={"/media/Show": {"Show.S01E01.mkv"}}, fail_put="上传炸了",
    )

    written, _carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()}, OPTIONS,
    ))

    assert written == []
    assert ("/media/Show/Show - S01E01.nfo", "写入失败: 上传炸了") in skipped


def test_finalize_writes_tvshow_and_season():
    plan = _plan()
    result = _result(plan)
    client = FakeClient(dirs={"/media/Show": {"Show - S01E01.mkv"}})

    written, skipped = asyncio.run(finalize_openlist_nfo(
        client, [plan], [result.new_path], {plan.file_id: _match()}, OPTIONS,
    ))

    assert sorted(written) == [
        "/media/Show/season.nfo",
        "/media/Show/tvshow.nfo",
    ]
    assert skipped == []


def test_finalize_drops_group_when_nothing_landed():
    plan = _plan()
    client = FakeClient(dirs={"/media/Show": {"Show - S01E01.mkv"}})

    written, skipped = asyncio.run(finalize_openlist_nfo(
        client, [plan], [], {plan.file_id: _match()}, OPTIONS,
    ))

    assert written == []
    assert {reason for _path, reason in skipped} == {DROPPED_GROUP_NFO_REASON}
    assert not any(c[0] == "put" for c in client.calls)


def test_finalize_refuses_mixed_show_directory():
    plan_a = _plan("A.S01E01.mkv", override=OverrideInfo(show_name="剧甲", season=1, episode=1))
    plan_b = _plan("B.S01E01.mkv", override=OverrideInfo(show_name="剧乙", season=1, episode=1))
    matches = {
        plan_a.file_id: _match(show_name="剧甲"),
        plan_b.file_id: _match(show_name="剧乙"),
    }
    client = FakeClient(dirs={"/media/Show": {
        "剧甲 - S01E01.mkv", "剧乙 - S01E01.mkv",
    }})

    written, skipped = asyncio.run(finalize_openlist_nfo(
        client, [plan_a, plan_b],
        [plan_a.new_path, plan_b.new_path], matches, OPTIONS,
    ))

    assert written == []
    assert any("混放" in reason for _path, reason in skipped), skipped
    assert not any(c[0] == "put" for c in client.calls)


def test_plan_dry_run_never_writes_or_moves():
    plan = _plan()
    result = _result(plan, status="dry_run")
    client = FakeClient(dirs={"/media/Show": {"Show.S01E01.mkv"}})

    written, carried, skipped = asyncio.run(plan_openlist_nfo(
        client, [plan], [result], {plan.file_id: _match()}, OPTIONS,
    ))

    # 与本地干跑一致: 每个视频自己的每集 NFO + 批次级的 tvshow / season。
    assert written == [
        "/media/Show/Show - S01E01.nfo",
        "/media/Show/tvshow.nfo",
        "/media/Show/season.nfo",
    ]
    assert carried == []
    assert skipped == []
    assert not any(c[0] in ("put", "rename", "move") for c in client.calls)


def test_plan_dry_run_lists_planned_carry_as_existing():
    plan = _plan()
    result = _result(plan, status="dry_run")
    new_nfo = "/media/Show/Show - S01E01.nfo"
    client = FakeClient(dirs={"/media/Show": {"Show.S01E01.mkv", "Show.S01E01.nfo"}})

    written, carried, skipped = asyncio.run(plan_openlist_nfo(
        client, [plan], [result], {plan.file_id: _match()}, OPTIONS,
    ))

    # 每集那一份会被跟随过来的旧 NFO 占住 → 只报「已存在」; 组级两份仍会写出。
    assert written == [
        "/media/Show/tvshow.nfo",
        "/media/Show/season.nfo",
    ]
    assert carried == [new_nfo]
    assert (new_nfo, "已存在") in skipped
    assert not any(c[0] in ("put", "rename", "move") for c in client.calls)


def test_plan_dry_run_treats_missing_destination_dir_as_empty():
    """干跑时目标季目录还不存在 —— 不能把「目录缺失」当成跟随失败。"""
    plan = _plan(
        folder_template="Season {season_padded}", create_season_folder=True,
    )
    result = _result(plan, status="dry_run")
    new_nfo = "/media/Show/Season 01/Show - S01E01.nfo"
    client = FakeClient(
        dirs={"/media/Show": {"Show.S01E01.mkv", "Show.S01E01.nfo"}},
        missing={"/media/Show/Season 01"},
    )

    written, carried, skipped = asyncio.run(plan_openlist_nfo(
        client, [plan], [result], {plan.file_id: _match()}, OPTIONS,
    ))

    assert carried == [new_nfo]
    assert new_nfo not in written
    assert not any("跟随移动失败" in reason for _path, reason in skipped), skipped


def test_plan_dry_run_keeps_carry_when_nfo_is_off():
    """跟随旧 NFO 与「是否生成 NFO」无关 —— 关闭生成时干跑仍要列出跟随计划。"""
    plan = _plan()
    result = _result(plan, status="dry_run")
    new_nfo = "/media/Show/Show - S01E01.nfo"
    client = FakeClient(dirs={"/media/Show": {"Show.S01E01.mkv", "Show.S01E01.nfo"}})

    written, carried, skipped = asyncio.run(plan_openlist_nfo(
        client, [plan], [result], {plan.file_id: _match()},
        NfoOptions(enabled=False),
    ))

    assert written == []
    assert carried == [new_nfo]
    assert skipped == []
    assert not any(c[0] in ("put", "rename", "move") for c in client.calls)


def test_plan_dry_run_uses_real_landed_path():
    plan = _plan(
        folder_template="Season {season_padded}", create_season_folder=True,
    )
    moved_to = "/media/Show/Season 01/Show.S01E01.mkv"
    result = _result(plan, status="dry_run", new_path=moved_to)
    client = FakeClient(dirs={
        "/media/Show": {"Show.S01E01.mkv"},
        "/media/Show/Season 01": set(),
    })

    written, _carried, _skipped = asyncio.run(plan_openlist_nfo(
        client, [plan], [result], {plan.file_id: _match()}, OPTIONS,
    ))

    assert "/media/Show/Season 01/Show.S01E01.nfo" in written


def test_carry_across_directories_moves_then_renames():
    plan = _plan(
        folder_template="Season {season_padded}", create_season_folder=True,
    )
    result = _result(plan, status="renamed_moved")
    new_nfo = "/media/Show/Season 01/Show - S01E01.nfo"
    client = FakeClient(dirs={
        "/media/Show": {"Show.S01E01.mkv", "Show.S01E01.nfo"},
        "/media/Show/Season 01": set(),
    })

    written, carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()}, OPTIONS,
    ))

    assert carried == [new_nfo]
    assert written == []
    assert (new_nfo, "已存在") in skipped
    assert ("move", "/media/Show", "/media/Show/Season 01", ("Show.S01E01.nfo",)) in client.calls
    assert ("rename", "/media/Show/Season 01/Show.S01E01.nfo",
            "Show - S01E01.nfo") in client.calls


def test_carry_cross_directory_refuses_same_old_name_conflict():
    """跨目录跟随前必须同时检查「旧文件名」是否会覆盖目标目录里的同名文件。"""
    plan = _plan(
        folder_template="Season {season_padded}", create_season_folder=True,
    )
    result = _result(plan, status="renamed_moved")
    client = FakeClient(dirs={
        "/media/Show": {"Show.S01E01.mkv", "Show.S01E01.nfo"},
        # 目标目录已有**旧文件名** Show.S01E01.nfo, 但新名字还不存在
        "/media/Show/Season 01": {"Show.S01E01.nfo"},
    })

    written, carried, skipped = asyncio.run(episode_nfo_for_plan(
        client, plan, result, {plan.file_id: _match()}, OPTIONS,
    ))

    assert carried == []
    assert any("目标目录已有同名文件" in reason for _path, reason in skipped), skipped
    assert not any(c[0] in ("move", "rename") for c in client.calls)
    # 生成侧不受影响: 它写的是新名字, 目标目录里没有。
    assert written == ["/media/Show/Season 01/Show - S01E01.nfo"]

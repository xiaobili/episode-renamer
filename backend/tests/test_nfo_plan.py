from app.core.nfo_writer import (
    build_nfo_decisions,
    common_parent,
    episode_nfo_path,
)
from app.models.nfo import NfoEntry, NfoOptions
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow


def show(tv_id=1396, name="绝命毒师"):
    return TmdbShow(tv_id=tv_id, name=name, original_name="Breaking Bad", year=2008)


def season(number=2):
    return TmdbSeason(season_number=number, name=f"第 {number} 季", tmdb_id=3575)


def episode(number=5):
    return TmdbEpisode(episode_number=number, name="Breakage", tmdb_id=62085)


# entry() 的 show 形参会遮蔽模块级的 show() 工厂（多剧混放的用例要按条目指定
# 各自的剧），所以这里留一个工厂别名给默认值用。
_default_show = show


def entry(new_path, show_name="绝命毒师", season_no=2, episode_no=5, with_meta=True, show=None):
    return NfoEntry(
        file_id=new_path,
        new_path=new_path,
        show_name=show_name,
        season=season_no,
        episode=episode_no,
        show=(show if show is not None else _default_show()) if with_meta else None,
        season_data=season(season_no) if with_meta and season_no else None,
        episode_data=episode(episode_no) if with_meta and episode_no else None,
    )


def by_kind(decisions, kind):
    return [d for d in decisions if d.kind == kind]


OPTIONS = NfoOptions(enabled=True, overwrite=False)


# --- 路径工具 ---

def test_episode_nfo_path_swaps_extension():
    assert episode_nfo_path("/media/剧/Season 02/剧 - S02E05.mkv") == "/media/剧/Season 02/剧 - S02E05.nfo"


def test_episode_nfo_path_handles_dots_in_name():
    assert episode_nfo_path("/m/Show.S02E05.1080p.mkv") == "/m/Show.S02E05.1080p.nfo"


def test_common_parent_of_sibling_dirs():
    assert common_parent(["/media/剧/Season 02/a.mkv", "/media/剧/Season 02/b.mkv"]) == "/media/剧/Season 02"


def test_common_parent_goes_up_for_split_seasons():
    assert common_parent(["/media/剧/S01/a.mkv", "/media/剧/S02/b.mkv"]) == "/media/剧"


def test_common_parent_of_single_path():
    assert common_parent(["/media/剧/S01/a.mkv"]) == "/media/剧/S01"


# --- 关闭时不产生任何决策 ---

def test_disabled_produces_nothing():
    assert build_nfo_decisions([entry("/m/剧/a.mkv")], NfoOptions(enabled=False)) == []


def test_empty_entries_produce_nothing():
    assert build_nfo_decisions([], OPTIONS) == []


# --- 每集 NFO ---

def test_episode_nfo_is_sibling_of_video():
    decisions = by_kind(build_nfo_decisions([entry("/m/绝命毒师/绝命毒师 - S02E05.mkv")], OPTIONS), "episode")
    assert len(decisions) == 1
    assert decisions[0].path == "/m/绝命毒师/绝命毒师 - S02E05.nfo"
    assert decisions[0].content is not None
    assert "<title>Breakage</title>" in decisions[0].content


def test_episode_nfo_skipped_without_metadata():
    # Review Focus 4：TMDB 未匹配时不写 NFO, 但也要给出一条带原因的「不写」决策,
    # 否则预览表那一列会是空白, 用户不知道是没查还是查不到
    decisions = by_kind(
        build_nfo_decisions([entry("/m/绝命毒师/a.mkv", with_meta=False)], OPTIONS), "episode")
    assert len(decisions) == 1
    assert decisions[0].content is None
    assert decisions[0].reason


def test_every_entry_gets_exactly_one_episode_decision():
    entries = [entry(f"/m/剧/S02/E{n:02d}.mkv", episode_no=n) for n in (5, 6, 7)]
    decisions = by_kind(build_nfo_decisions(entries, OPTIONS), "episode")
    assert len(decisions) == 3


# --- 剧集根与季目录 ---

def test_tvshow_goes_to_show_root_and_season_to_season_folder():
    # spec §9.1：season.nfo 落在季目录（Emby 只在季目录下找它）
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/Season 02/绝命毒师 - S02E05.mkv", episode_no=5),
        entry("/m/绝命毒师/Season 03/绝命毒师 - S03E01.mkv", season_no=3, episode_no=1),
    ], OPTIONS)

    tvshow = by_kind(decisions, "tvshow")
    assert len(tvshow) == 1
    assert tvshow[0].path == "/m/绝命毒师/tvshow.nfo"

    seasons = by_kind(decisions, "season")
    assert [s.path for s in seasons] == [
        "/m/绝命毒师/Season 02/season.nfo",
        "/m/绝命毒师/Season 03/season.nfo",
    ]


def test_season_nfo_still_written_without_season_folders():
    # Review Focus 5：未开季文件夹时, 视频所在目录既是剧集根也是季目录,
    # season.nfo 仍要写, 而不是因为「没有季文件夹」就跳过
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/绝命毒师 - S02E05.mkv", episode_no=5),
        entry("/m/绝命毒师/绝命毒师 - S02E06.mkv", episode_no=6),
    ], OPTIONS)

    assert [d.path for d in by_kind(decisions, "tvshow")] == ["/m/绝命毒师/tvshow.nfo"]
    assert [d.path for d in by_kind(decisions, "season")] == ["/m/绝命毒师/season.nfo"]


def test_split_season_folders_put_tvshow_at_show_root():
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/S01/绝命毒师 - S01E01.mkv", season_no=1, episode_no=1),
        entry("/m/绝命毒师/S02/绝命毒师 - S02E01.mkv", season_no=2, episode_no=1),
    ], OPTIONS)

    assert [d.path for d in by_kind(decisions, "tvshow")] == ["/m/绝命毒师/tvshow.nfo"]
    assert [d.path for d in by_kind(decisions, "season")] == [
        "/m/绝命毒师/S01/season.nfo",
        "/m/绝命毒师/S02/season.nfo",
    ]


def test_two_shows_get_two_tvshow_files():
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/a.mkv", show_name="绝命毒师"),
        entry("/m/律师/b.mkv", show_name="绝命律师"),
    ], OPTIONS)

    assert [d.path for d in by_kind(decisions, "tvshow")] == [
        "/m/律师/tvshow.nfo", "/m/绝命毒师/tvshow.nfo",
    ]


def test_tvshow_written_only_once_per_show():
    entries = [entry(f"/m/绝命毒师/E{n:02d}.mkv", episode_no=n) for n in (1, 2, 3)]
    assert len(by_kind(build_nfo_decisions(entries, OPTIONS), "tvshow")) == 1


# --- Review Focus 2：多剧混放 ---

def test_mixed_shows_in_one_directory_are_refused():
    # /media/未分类/ 下同时有 A 剧与 B 剧。把 tvshow.nfo 写进去会让 Emby
    # 把整个目录当成一部剧 —— 不可逆。
    decisions = build_nfo_decisions([
        entry("/m/未分类/a.mkv", show_name="绝命毒师", show=show(1396, "绝命毒师")),
        entry("/m/未分类/b.mkv", show_name="绝命律师", show=show(2, "绝命律师")),
    ], OPTIONS)

    tvshow = by_kind(decisions, "tvshow")
    season_decisions = by_kind(decisions, "season")

    assert len(tvshow) == 2, "每部剧各有一条决策（内容是「不写」）"
    assert all(d.content is None for d in tvshow)
    assert all("多部剧" in d.reason for d in tvshow)

    assert all(d.content is None for d in season_decisions)
    assert all("多部剧" in d.reason for d in season_decisions)

    # 但每集 NFO 照常写 —— 它落在视频旁边, 与目录是否混放无关
    assert all(d.content is not None for d in by_kind(decisions, "episode"))


def test_mixed_shows_in_parent_do_not_block_subdirectory_shows():
    # 反向情形：两部剧各在自己的子目录里, 不能因为「父目录混放」而误拒
    decisions = build_nfo_decisions([
        entry("/m/未分类/绝命毒师/a.mkv", show_name="绝命毒师", show=show(1396, "绝命毒师")),
        entry("/m/未分类/绝命律师/b.mkv", show_name="绝命律师", show=show(2, "绝命律师")),
    ], OPTIONS)

    assert all(d.content is not None for d in by_kind(decisions, "tvshow"))
    assert [d.path for d in by_kind(decisions, "tvshow")] == [
        "/m/未分类/绝命律师/tvshow.nfo", "/m/未分类/绝命毒师/tvshow.nfo",
    ]


def test_same_show_in_one_directory_is_allowed():
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/a.mkv", episode_no=1),
        entry("/m/绝命毒师/b.mkv", episode_no=2),
    ], OPTIONS)
    assert all(d.content is not None for d in by_kind(decisions, "tvshow"))


# --- 无元数据时的剧集级文件 ---

def test_show_level_files_skipped_without_show_metadata():
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/a.mkv", with_meta=False),
    ], OPTIONS)

    assert all(d.content is None for d in by_kind(decisions, "tvshow"))
    assert all(d.content is None for d in by_kind(decisions, "season"))
    assert all(d.reason for d in by_kind(decisions, "tvshow"))


# --- 顺序契约 ---

def test_decisions_are_deterministic():
    entries = [
        entry("/m/剧B/E02.mkv", show_name="剧B", episode_no=2),
        entry("/m/剧A/E01.mkv", show_name="剧A", episode_no=1),
    ]
    decisions = build_nfo_decisions(entries, OPTIONS)
    assert [d.kind for d in decisions] == ["episode", "episode", "tvshow", "tvshow", "season", "season"]

    # 同一入参集合换个顺序, 结果必须逐项一致
    decisions_reversed = build_nfo_decisions(list(reversed(entries)), OPTIONS)
    assert [d.path for d in decisions] == [d.path for d in decisions_reversed]


# --- 执行 Task 2 时补的两条用例 -------------------------------------------------
# 上面对应计划原文的 20 条全绿之后, 变异验证（逐条打断实现, 看哪条用例变红）暴露了
# 三个盲区 —— 打断实现后 20 条**一条都不红**。补在下面, 关闭盲区。

def test_mixed_directory_refusal_is_decided_per_file():
    # 盲区一/二：计划原文里每部剧在混放目录下都只有 1 个文件, 于是「组内每个条目
    # 各一条拒绝决策」（计划明确要求的行为, 见 Task 2 的 file_id 说明）与「每部剧
    # 只发一条」在断言下无法区分 —— 两者数量都是 2。同理, season 的断言是
    # all(...) over 一个可能为空的列表, 干脆不产生 season 决策也能全绿。
    # 这条用 2+1 个文件把两个 count 都钉住。
    decisions = build_nfo_decisions([
        entry("/m/未分类/a1.mkv", show_name="绝命毒师", episode_no=5),
        entry("/m/未分类/a2.mkv", show_name="绝命毒师", episode_no=6),
        entry("/m/未分类/b1.mkv", show_name="绝命律师", episode_no=5),
    ], OPTIONS)

    tvshow = by_kind(decisions, "tvshow")
    seasons = by_kind(decisions, "season")

    assert len(tvshow) == 3, "每个文件各一条, 预览表才能逐行显示原因"
    assert len(seasons) == 3, "季级同样按文件各一条"
    assert all(d.content is None and "多部剧" in d.reason for d in tvshow)
    assert all(d.content is None and "多部剧" in d.reason for d in seasons)

    # 每集 NFO 不受影响
    assert len(by_kind(decisions, "episode")) == 3


def test_written_season_decisions_carry_content():
    # 盲区三：计划原文只对 tvshow 与 episode 断言过 content is not None, 从未
    # 断言过季级决策真的带了 XML。把 season_data 的取值取反（季级恒为「不写」）
    # 20 条全绿。
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/Season 02/绝命毒师 - S02E05.mkv", episode_no=5),
        entry("/m/绝命毒师/Season 03/绝命毒师 - S03E01.mkv", season_no=3, episode_no=1),
    ], OPTIONS)

    assert all(d.content is not None for d in by_kind(decisions, "tvshow"))
    seasons = by_kind(decisions, "season")
    assert [s.path for s in seasons] == [
        "/m/绝命毒师/Season 02/season.nfo",
        "/m/绝命毒师/Season 03/season.nfo",
    ]
    assert all(s.content is not None for s in seasons)
    assert "<seasonnumber>2</seasonnumber>" in seasons[0].content
    assert "<seasonnumber>3</seasonnumber>" in seasons[1].content

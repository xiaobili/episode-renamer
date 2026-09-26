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

    tvshow = by_kind(decisions, "tvshow")
    season_decisions = by_kind(decisions, "season")

    # 先钉基数, 再断言内容: 三条 all() 都建立在可能为空的列表上, 空列表恒真。
    # 少了这两行, 「show_data is None 时干脆不发决策」这个变异能让本用例全绿。
    assert len(tvshow) == 1, "剧集级决策必须存在（内容是「不写」），不能直接省略"
    assert len(season_decisions) == 1

    assert all(d.content is None for d in tvshow)
    assert all(d.content is None for d in season_decisions)
    assert all(d.reason for d in tvshow)


# --- 顺序契约 ---

def test_decisions_are_deterministic():
    # 剧A 有两个文件（同一季、不同集, 一个在子目录）, 这样剧A 的组与季组都不止
    # 一个条目 —— 否则 group[0] 无歧义, 归属漂移根本测不出来。
    entries = [
        entry("/m/剧B/E02.mkv", show_name="剧B", episode_no=2),
        entry("/m/剧A/E01.mkv", show_name="剧A", episode_no=1),
        entry("/m/剧A/S02/E03.mkv", show_name="剧A", season_no=2, episode_no=3),
    ]
    decisions = build_nfo_decisions(entries, OPTIONS)
    assert [d.kind for d in decisions] == [
        "episode", "episode", "episode", "tvshow", "tvshow", "season", "season",
    ]

    # 同一入参集合换个顺序, 结果必须**逐项**一致 —— 不只是路径: 剧集级/季级决策
    # 的 file_id（它挂在预览表的哪一行）也不能随输入顺序漂移。
    decisions_reversed = build_nfo_decisions(list(reversed(entries)), OPTIONS)
    assert [(d.kind, d.path, d.file_id) for d in decisions] == [
        (d.kind, d.path, d.file_id) for d in decisions_reversed
    ]


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


# --- 审查轮补的四条用例 ---------------------------------------------------------
# 审查者把上面两轮补的用例当线索, 又在同一批「all() 建立在可能为空的列表上」和
# 「取任一非 None vs 取第一条」上各找到一处活下来的洞, 外加两处可达但无覆盖的分支。

def test_show_level_files_written_on_partial_metadata():
    # 同一目录里只有部分文件匹配到 TMDB: 剧集级与季级文件仍要写 —— 取「组内任一
    # 非 None 的 show / season_data」, 而不是「第一条」。
    # 排序后第一条恰好是**未匹配**的那个文件（episode 1 < episode 2）, 所以把取值
    # 改成 group[0] / season_group[0] 就会误判为「没元数据」→ 本用例变红。
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/a.mkv", episode_no=1, with_meta=False),
        entry("/m/绝命毒师/b.mkv", episode_no=2),
    ], OPTIONS)

    tvshow = by_kind(decisions, "tvshow")
    assert len(tvshow) == 1
    assert tvshow[0].content is not None, "有一条匹配上就该写剧集级 NFO"

    seasons = by_kind(decisions, "season")
    assert len(seasons) == 1
    assert seasons[0].content is not None, "季级同理: 取组内任一非 None 的 season_data"

    episodes = by_kind(decisions, "episode")
    assert len(episodes) == 2
    assert [d.content is not None for d in episodes] == [False, True], "未匹配的那条单独「不写」"


def test_nested_show_under_a_mixed_root_is_refused():
    # 非对称布局：A 剧的文件直接躺在 /m/未分类 下, B 剧的在它**子目录**里。
    # 只查「恰好等于 root 的那个目录」时, A 的 root（/m/未分类）下没有别的剧的
    # 文件直接躺着 → tvshow.nfo 会被写出去, Emby 就把整个 /m/未分类 当成 A 剧。
    # 判定必须覆盖 root 的整棵子树。
    #
    # 剧B 的公共父目录是 /m/未分类/剧B/S01 —— 一个季目录 —— 故剧集根要再上溯一层
    # 到 /m/未分类/剧B（见 nfo_writer._show_root）。校验用的就是这个上溯后的根,
    # 拿季目录去查会漏掉别的剧。**这条期望是审查裁定后改的**, 原为
    # /m/未分类/剧B/S01/tvshow.nfo。
    decisions = build_nfo_decisions([
        entry("/m/未分类/A.mkv", show_name="剧A", season_no=1, episode_no=1),
        entry("/m/未分类/剧B/S01/B.mkv", show_name="剧B", season_no=1, episode_no=1),
    ], OPTIONS)

    tvshow = by_kind(decisions, "tvshow")
    assert [d.path for d in tvshow] == [
        "/m/未分类/tvshow.nfo",           # 剧A：root 之下嵌套着剧B → 不写
        "/m/未分类/剧B/tvshow.nfo",       # 剧B：S01 是季目录, 剧集根上溯到剧B → 照写
    ]
    assert tvshow[0].content is None
    assert "多部剧" in tvshow[0].reason
    assert tvshow[1].content is not None

    seasons = by_kind(decisions, "season")
    assert [d.path for d in seasons] == [
        "/m/未分类/season.nfo",
        "/m/未分类/剧B/S01/season.nfo",
    ]
    assert seasons[0].content is None
    assert "多部剧" in seasons[0].reason
    assert seasons[1].content is not None

    # 每集 NFO 照写 —— 它落在视频旁边, 与目录是否混放无关
    assert all(d.content is not None for d in by_kind(decisions, "episode"))


def test_sibling_show_directories_are_not_mistaken_for_nesting():
    # 上面那条扩展判定范围的用例的反向保险。这里刻意用**同级目录**而不是
    # root/S01/：/m/未分类/剧 与 /m/未分类/剧B 只是兄弟, 谁也不在谁之下,
    # 但前者的路径是后者的**字符串前缀** —— 判嵌套时若只做
    # `startswith(root)` 而不带上分隔符, 剧B 会被误判成在 剧 之下 → 误拒。
    decisions = build_nfo_decisions([
        entry("/m/未分类/剧/a.mkv", show_name="剧", season_no=1, episode_no=1),
        entry("/m/未分类/剧B/b.mkv", show_name="剧B", season_no=1, episode_no=1),
    ], OPTIONS)

    assert [d.path for d in by_kind(decisions, "tvshow")] == [
        "/m/未分类/剧/tvshow.nfo", "/m/未分类/剧B/tvshow.nfo",
    ]
    assert all(d.content is not None for d in by_kind(decisions, "tvshow"))
    assert all(d.content is not None for d in by_kind(decisions, "season"))


def test_entry_without_season_number_gets_no_season_nfo():
    # season is None 在生产中可达: Task 3 会传 plan.parsed.season or None, 任何
    # 解析不出季号的文件都走这里 —— 不产出 season.nfo, 每集与剧集级 NFO 照常,
    # 且每集 NFO 里的 <season> 标签省略（None 不进 XML）。
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/a.mkv", season_no=None, episode_no=5),
        entry("/m/未分类/a.mkv", show_name="剧A", season_no=None, episode_no=1),
        entry("/m/未分类/b.mkv", show_name="剧B", season_no=None, episode_no=1),
    ], OPTIONS)

    # 一条 season 决策都不该有: 绝命毒师 那条是「不进 seasons 字典」,
    # 未分类 那两条走的是混放分支里的 `item.season is None: continue`。
    assert by_kind(decisions, "season") == []

    tvshow = by_kind(decisions, "tvshow")
    assert len(tvshow) == 3
    assert tvshow[2].path == "/m/绝命毒师/tvshow.nfo"
    assert tvshow[2].content is not None, "季号缺失不影响剧集级 NFO"
    assert all(d.content is None and "多部剧" in d.reason for d in tvshow[:2])

    episodes = by_kind(decisions, "episode")
    assert len(episodes) == 3
    assert all(d.content is not None for d in episodes), "季号缺失不影响每集 NFO"
    assert all("<season>" not in d.content for d in episodes)


# --- 审查裁定补的用例：单季布局下的剧集根 ---------------------------------------
# spec §9.3 的「剧集根 = 公共父目录」只举了多季布局（Season 02 + Season 03、
# S01 + S02）, 于是**单季**时公共父退化成季目录本身, tvshow.nfo 落进季文件夹 ——
# 而 Emby / Jellyfin 只在剧集根找它, 等于没写。下面两条钉住 _show_root 的上溯。

def test_single_season_folder_still_puts_tvshow_at_the_show_root():
    # 三种季目录写法（Season 02 / S02 / 第2季）都必须能上溯: 判定复用
    # parser._SEASON_DIR_PATTERNS, 换了写法就漏判等于没修。
    for season_dir in ("Season 02", "S02", "第2季"):
        decisions = build_nfo_decisions([
            entry(f"/m/绝命毒师/{season_dir}/绝命毒师 - S02E05.mkv", episode_no=5),
        ], OPTIONS)

        assert [d.path for d in by_kind(decisions, "tvshow")] == [
            "/m/绝命毒师/tvshow.nfo",
        ], f"{season_dir}: 季文件夹按构造不是剧集根, tvshow.nfo 要上溯一层"
        # season.nfo 不受影响: 它本来就该落在季目录里
        assert [d.path for d in by_kind(decisions, "season")] == [
            f"/m/绝命毒师/{season_dir}/season.nfo",
        ]


def test_show_root_does_not_ascend_past_the_filesystem_root():
    # 上溯的兜底：季目录已经在最外层时保持原样。把 tvshow.nfo 写到 / 下比不写
    # 更糟; 相对路径上溯则得到空串, 还会破坏路径形状（绝对/相对）的一致性。
    at_root = build_nfo_decisions([entry("/Season 02/x.mkv")], OPTIONS)
    assert [d.path for d in by_kind(at_root, "tvshow")] == ["/Season 02/tvshow.nfo"]

    relative = build_nfo_decisions([entry("Season 02/x.mkv")], OPTIONS)
    assert [d.path for d in by_kind(relative, "tvshow")] == ["Season 02/tvshow.nfo"]

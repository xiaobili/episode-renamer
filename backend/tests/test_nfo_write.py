import os
from pathlib import Path

from app.core.local_renamer import batch_rename
from app.core.nfo_writer import build_nfo_decisions, write_nfo_files
from app.core.tmdb_resolver import EpisodeMatch
from app.models.api import RenameExecuteRequest, RenamePreviewRequest
from app.models.file import FileInfo
from app.models.nfo import NfoDecision, NfoEntry, NfoOptions
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow


def make_entry(new_path, show_name="绝命毒师", season_no=2, episode_no=5):
    return NfoEntry(
        file_id=new_path,
        new_path=new_path,
        show_name=show_name,
        season=season_no,
        episode=episode_no,
        show=TmdbShow(tv_id=1396, name=show_name, original_name="Breaking Bad", year=2008),
        season_data=TmdbSeason(season_number=season_no, name=f"第 {season_no} 季", tmdb_id=3575),
        episode_data=TmdbEpisode(episode_number=episode_no, name="Breakage", tmdb_id=62085),
    )


OPTIONS = NfoOptions(enabled=True, overwrite=False)


def test_writes_all_three_kinds(tmp_path):
    video = tmp_path / "绝命毒师" / "Season 02" / "绝命毒师 - S02E05.mkv"
    video.parent.mkdir(parents=True)

    decisions = build_nfo_decisions([make_entry(str(video))], OPTIONS)
    written, skipped = write_nfo_files(decisions)

    assert skipped == []
    # tvshow.nfo 在剧集根（季目录上溯一层）—— 见 nfo_writer._show_root。
    # 这一条曾是「简报期望 vs HEAD 的 Task 2」的冲突点，审查裁定为 Task 2 错、
    # 已在本轮修好，故此处恢复简报字面。
    assert sorted(written) == sorted([
        str(video.with_suffix(".nfo")),
        str(tmp_path / "绝命毒师" / "Season 02" / "season.nfo"),
        str(tmp_path / "绝命毒师" / "tvshow.nfo"),
    ])
    for path in written:
        assert os.path.isfile(path)


def test_creates_missing_directories(tmp_path):
    # 开了「创建季文件夹」时季目录由重命名创建; 但若重命名因冲突被跳过,
    # 目录可能不存在 —— 写 NFO 必须自己兜住
    video = tmp_path / "剧" / "Season 09" / "剧 - S09E01.mkv"
    decisions = build_nfo_decisions([make_entry(str(video), season_no=9, episode_no=1)], OPTIONS)

    written, _skipped = write_nfo_files(decisions)
    assert written
    assert os.path.isdir(str(tmp_path / "剧" / "Season 09"))


def test_existing_file_is_skipped_when_overwrite_is_off(tmp_path):
    # Review Focus 3：默认不覆盖既有 NFO
    target = tmp_path / "剧 - S02E05.nfo"
    target.write_text("既有内容", encoding="utf-8")

    decisions = [NfoDecision(file_id="f1", kind="episode", path=str(target), content="<新/>")]
    written, skipped = write_nfo_files(decisions, overwrite=False)

    assert written == []
    assert skipped == [(str(target), "已存在")]
    assert target.read_text(encoding="utf-8") == "既有内容"


def test_existing_file_is_overwritten_when_asked(tmp_path):
    target = tmp_path / "剧 - S02E05.nfo"
    target.write_text("既有内容", encoding="utf-8")

    decisions = [NfoDecision(file_id="f1", kind="episode", path=str(target), content="<新/>")]
    written, skipped = write_nfo_files(decisions, overwrite=True)

    assert written == [str(target)]
    assert skipped == []
    assert target.read_text(encoding="utf-8") == "<新/>"


def test_decisions_without_content_are_reported_as_skipped(tmp_path):
    decisions = [NfoDecision(file_id="f1", kind="episode",
                             path=str(tmp_path / "a.nfo"), content=None, reason="无 TMDB 数据")]
    written, skipped = write_nfo_files(decisions)

    assert written == []
    assert skipped == [(str(tmp_path / "a.nfo"), "无 TMDB 数据")]
    assert not (tmp_path / "a.nfo").exists()


def test_duplicate_paths_are_written_once(tmp_path):
    # 多剧混放分支会给组内每个条目各生成一条同路径的 tvshow 决策
    target = tmp_path / "tvshow.nfo"
    decisions = [
        NfoDecision(file_id="f1", kind="tvshow", path=str(target), content="<a/>"),
        NfoDecision(file_id="f2", kind="tvshow", path=str(target), content="<a/>"),
    ]
    written, skipped = write_nfo_files(decisions, overwrite=True)

    assert written == [str(target)]
    assert skipped == []


def test_written_content_is_utf8_with_chinese(tmp_path):
    # 本用例的鉴别力是**有条件的**, 别当它比实际更强:
    # 在 UTF-8 locale（本机与多数开发机）下, write_text 带不带 encoding="utf-8"
    # 写出**相同字节**, 没有任何字节级断言能区分二者 —— 删掉那行参数本用例仍绿。
    # 它证明的是「中文内容确实按 UTF-8 写成、读得回来」, **不是**「那行参数存在」。
    # 「参数必需」由一次冻结 locale 的隔离脚本证明（见 task-3-report.md §5 M1）:
    # LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 下默认编码退化成 ascii, 缺参数时
    # 中文内容抛 UnicodeEncodeError —— 它是 ValueError 的子类, write_nfo_files 的
    # except OSError 接不住, 会炸掉整批重命名。注意**整份套件在那个 locale 下跑
    # 不起来**（用例自己的中文目录名都建不了, os.mkdir 就抛), 所以证据是那次隔离
    # 脚本而不是跑套件。CI 与 Docker 常用 LANG=C/POSIX（PEP 538 会coerce 成
    # C.UTF-8, 见本机 LC_ALL=C 全绿）, 真出事的只有强制 ASCII 的环境。
    target = tmp_path / "剧 - S02E05.nfo"
    decisions = [NfoDecision(file_id="f1", kind="episode", path=str(target),
                             content="<episodedetails><title>绝命毒师</title></episodedetails>")]
    write_nfo_files(decisions, overwrite=True)

    assert "绝命毒师" in target.read_text(encoding="utf-8")


def test_failures_are_reported_not_raised(tmp_path):
    # 写失败（如只读目标）不能让整批重命名崩掉 —— 重命名已经成功了
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)  # 只读目录
    try:
        decisions = [NfoDecision(file_id="f1", kind="episode",
                                 path=str(blocked / "a.nfo"), content="<x/>")]
        written, skipped = write_nfo_files(decisions, overwrite=True)

        # root 用户会绕过权限位, 因此两种结果都接受, 关键是「不抛异常」
        if written:
            assert skipped == []
        else:
            assert len(skipped) == 1
            assert "写入失败" in skipped[0][1]
    finally:
        blocked.chmod(0o700)


# --- 以下为简报未给的批处理集成用例 -------------------------------------------
# 简报的 8 条只测 write_nfo_files 本身。batch_rename 的接线段（nfo_options /
# nfo_matches 的取值、dry-run 的「只列清单」、nfo_path 的归属、混放下的实际落盘）
# 若没有用例，8 条全绿也说明不了它 —— 例如把 new_path 换成 original_path、
# 或在 dry-run 里照写不误，上面 8 条一条都不会红。
#
# 剧名取自**父目录名**（parser._inherit_show_from_parent 的既有行为）, 所以视频
# 都放在名为「绝命毒师」的目录里; 混放场景只能用 overrides 指定剧名 —— 同一个
# 目录下的两个文件从文件名推导出的剧名必然相同。

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
SHOW_DIR = "绝命毒师"


def make_match(show_name="绝命毒师", season_no=2, episode_no=5):
    return EpisodeMatch(
        status="matched",
        show=TmdbShow(tv_id=1396, name=show_name, original_name="Breaking Bad", year=2008),
        season=TmdbSeason(season_number=season_no, name=f"第 {season_no} 季", tmdb_id=3575),
        episode=TmdbEpisode(episode_number=episode_no, name="Breakage", tmdb_id=62085),
    )


def make_video(tmp_path, filename="绝命毒师.S02E05.mkv", subdir=SHOW_DIR):
    parent = tmp_path / subdir
    parent.mkdir(parents=True, exist_ok=True)
    video = parent / filename
    video.write_bytes(b"fake video")
    return video


def make_file(video, file_id="f1"):
    return FileInfo(id=file_id, path=str(video), filename=video.name, parent_dir=str(video.parent))


def named_options(overwrite=False):
    return NfoOptions(enabled=True, overwrite=overwrite)


def test_request_models_expose_the_two_nfo_switches_defaulting_off():
    # 「覆盖已存在」必须默认关闭 —— 名字写错或默认值写成 True 都不会有别的东西发现
    for model in (RenamePreviewRequest, RenameExecuteRequest):
        request = model(file_ids=[], template="{show}")
        assert request.generate_nfo is False
        assert request.nfo_overwrite is False


def test_batch_rename_writes_nfo_next_to_the_renamed_video(tmp_path):
    video = make_video(tmp_path)

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        nfo_options=named_options(),
        nfo_matches={"f1": make_match()},
    )

    show_dir = tmp_path / SHOW_DIR
    new_nfo = show_dir / "绝命毒师 - S02E05.nfo"
    assert (show_dir / "绝命毒师 - S02E05.mkv").is_file()
    assert result.results[0].nfo_path == str(new_nfo)
    assert str(new_nfo) in result.nfo_written
    assert result.nfo_skipped == []
    assert "绝命毒师" in new_nfo.read_text(encoding="utf-8")
    # 未开季文件夹：视频所在目录既是剧集根也是季目录
    assert (show_dir / "tvshow.nfo").is_file()
    assert (show_dir / "season.nfo").is_file()
    # 旧路径不得留下 NFO
    assert not (show_dir / "绝命毒师.S02E05.nfo").exists()


def test_batch_rename_nfo_follows_the_post_rename_path(tmp_path):
    """每集 NFO 靠与视频同名配对, 所以落点必须跟着**新**路径走, 不是原路径。"""
    video = make_video(tmp_path)

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        folder_template="Season {season_padded}",
        create_season_folder=True,
        nfo_options=named_options(),
        nfo_matches={"f1": make_match()},
    )

    show_dir = tmp_path / SHOW_DIR
    new_dir = show_dir / "Season 02"
    assert result.executed == 1
    assert (new_dir / "绝命毒师 - S02E05.mkv").is_file()
    assert result.results[0].nfo_path == str(new_dir / "绝命毒师 - S02E05.nfo")
    assert (new_dir / "绝命毒师 - S02E05.nfo").is_file()
    assert (new_dir / "season.nfo").is_file()
    # 剧集级在**剧集根**（季目录上溯一层）, 不在季文件夹里 —— 见 _show_root
    assert (show_dir / "tvshow.nfo").is_file()
    assert not (new_dir / "tvshow.nfo").exists()
    # 旧目录不得留下任何 NFO
    assert not (show_dir / "绝命毒师 - S02E05.nfo").exists()
    assert not (show_dir / "season.nfo").exists()
    assert not (show_dir / "绝命毒师.S02E05.nfo").exists()


def test_dry_run_lists_the_nfo_plan_without_writing_anything(tmp_path):
    video = make_video(tmp_path)

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        dry_run=True,
        nfo_options=named_options(),
        nfo_matches={"f1": make_match()},
    )

    show_dir = tmp_path / SHOW_DIR
    planned = show_dir / "绝命毒师 - S02E05.nfo"
    assert result.results[0].status == "dry_run"
    assert str(planned) in result.nfo_written
    assert result.nfo_skipped == []
    # 干跑绝不落盘
    assert not planned.exists()
    assert not (show_dir / "tvshow.nfo").exists()
    assert not (show_dir / "season.nfo").exists()


def test_existing_nfo_is_neither_overwritten_nor_touched(tmp_path):
    video = make_video(tmp_path)
    existing = tmp_path / SHOW_DIR / "绝命毒师 - S02E05.nfo"
    existing.write_text("既有内容", encoding="utf-8")

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        nfo_options=named_options(overwrite=False),
        nfo_matches={"f1": make_match()},
    )

    assert {"path": str(existing), "reason": "已存在"} in result.nfo_skipped
    assert str(existing) not in result.nfo_written
    assert existing.read_text(encoding="utf-8") == "既有内容"


def test_dry_run_reports_existing_nfo_as_skipped_via_a_read_only_check(tmp_path):
    video = make_video(tmp_path)
    existing = tmp_path / SHOW_DIR / "绝命毒师 - S02E05.nfo"
    existing.write_text("既有内容", encoding="utf-8")

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        dry_run=True,
        nfo_options=named_options(overwrite=False),
        nfo_matches={"f1": make_match()},
    )

    assert {"path": str(existing), "reason": "已存在"} in result.nfo_skipped
    assert str(existing) not in result.nfo_written
    assert existing.read_text(encoding="utf-8") == "既有内容"


def test_overwrite_replaces_the_existing_nfo_when_asked(tmp_path):
    """「覆盖已存在」必须是显式开关：开了就真的覆盖, 没开才不动它。"""
    video = make_video(tmp_path)
    existing = tmp_path / SHOW_DIR / "绝命毒师 - S02E05.nfo"
    existing.write_text("既有内容", encoding="utf-8")

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        nfo_options=named_options(overwrite=True),
        nfo_matches={"f1": make_match()},
    )

    assert str(existing) in result.nfo_written
    assert {"path": str(existing), "reason": "已存在"} not in result.nfo_skipped
    content = existing.read_text(encoding="utf-8")
    assert "既有内容" not in content
    assert "绝命毒师" in content


def test_rename_dup_keeps_the_episode_nfo_paired_with_the_video(tmp_path):
    """`rename_dup`（界面上的「自动编号」）把目标解析成 X_1.mkv —— 每集 NFO 必须
    跟着改名后的视频走（X_1.nfo）。不跟的话视频没有同名 NFO, 而 NFO 会落到 X.nfo:
    那是冲突那一集的位置, 覆盖模式下还会把它的内容改写掉。"""
    video = make_video(tmp_path)
    show_dir = tmp_path / SHOW_DIR
    clash_video = show_dir / "绝命毒师 - S02E05.mkv"
    clash_video.write_bytes(b"existing video")
    clash_nfo = show_dir / "绝命毒师 - S02E05.nfo"
    clash_nfo.write_text("冲突那一集的既有 NFO", encoding="utf-8")

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        conflict_strategy="rename_dup",
        nfo_options=named_options(overwrite=True),
        nfo_matches={"f1": make_match()},
    )

    renamed_video = show_dir / "绝命毒师 - S02E05_1.mkv"
    renamed_nfo = show_dir / "绝命毒师 - S02E05_1.nfo"
    assert renamed_video.is_file()
    assert result.results[0].new_path == str(renamed_video)
    assert result.results[0].nfo_path == str(renamed_nfo)
    assert renamed_nfo.is_file(), "NFO 必须与改名后的视频同名配对"
    assert str(renamed_nfo) in result.nfo_written
    # 冲突那一集的视频与它的 NFO 都不该被碰
    assert clash_video.read_bytes() == b"existing video"
    assert clash_nfo.read_text(encoding="utf-8") == "冲突那一集的既有 NFO"


def test_rename_dup_does_not_attach_an_nfo_landing_spot_to_the_subtitle(tmp_path):
    """`rename_dup` 下字幕也不得被挂上落点。

    与上一条同形, 但字幕的目标名也被占用 —— 字幕同样满足 `new_path != plan.new_path`,
    所以不过滤的话它会把自己的 `…_1.nfo` 写进 nfo_path_by_file。而那个路径**与视频的
    完全相同**（两者都取 episode_nfo_path(…_1.*) 的形式）, 于是预览/结果里两行报出
    同一个 NFO 落点 —— 其中字幕那一行报的是根本不会写的文件。

    变异验证: 去掉 local_renamer 里那处 `and not _is_subtitle_file(plan.file_info)`
    → 本用例 FAILED（results[1].nfo_path 变成 str(…_1.nfo)）。
    注: 这道过滤目前**只有这条用例**钉着 —— 去掉它时其余 36 条用例全绿。
    """
    video = make_video(tmp_path, filename="绝命毒师.S02E05.mkv")
    subtitle = make_subtitle(video)
    show_dir = tmp_path / SHOW_DIR
    # 把视频与字幕的**目标名**都占住, 让两者都走 rename_dup
    (show_dir / "绝命毒师 - S02E05.mkv").write_bytes(b"existing video")
    (show_dir / "绝命毒师 - S02E05.srt").write_bytes(b"existing subtitle")

    result = batch_rename(
        [make_file(video, "f1"), subtitle], TEMPLATE,
        conflict_strategy="rename_dup",
        nfo_options=named_options(overwrite=True),
        nfo_matches={"f1": make_match(), "f2": make_match()},
    )

    renamed_nfo = show_dir / "绝命毒师 - S02E05_1.nfo"
    assert result.results[0].new_path == str(show_dir / "绝命毒师 - S02E05_1.mkv")
    assert result.results[0].nfo_path == str(renamed_nfo), "视频的 NFO 仍跟着改名后的视频"
    # 字幕照常被改名, 但一个落点都不报
    assert result.results[1].new_path == str(show_dir / "绝命毒师 - S02E05_1.srt")
    assert result.results[1].nfo_path is None
    assert result.nfo_written == [str(renamed_nfo), str(show_dir / "tvshow.nfo"),
                                  str(show_dir / "season.nfo")]


def test_dry_run_reports_unmatched_entries_with_the_real_reason(tmp_path):
    video = make_video(tmp_path)

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        dry_run=True,
        nfo_options=named_options(),
        nfo_matches={},
    )

    assert result.nfo_written == []
    assert {"path": str(tmp_path / SHOW_DIR / "绝命毒师 - S02E05.nfo"),
            "reason": "TMDB 未匹配, 不写残缺 NFO"} in result.nfo_skipped
    assert not (tmp_path / SHOW_DIR / "绝命毒师 - S02E05.nfo").exists()


def test_unmatched_file_reports_the_skip_and_writes_no_partial_nfo(tmp_path):
    video = make_video(tmp_path)

    # TMDB 未匹配：nfo_matches 里没有这个 file_id
    result = batch_rename(
        [make_file(video)], TEMPLATE,
        nfo_options=named_options(),
        nfo_matches={},
    )

    show_dir = tmp_path / SHOW_DIR
    assert result.nfo_written == []
    assert {"path": str(show_dir / "绝命毒师 - S02E05.nfo"),
            "reason": "TMDB 未匹配, 不写残缺 NFO"} in result.nfo_skipped
    assert not (show_dir / "绝命毒师 - S02E05.nfo").exists()
    assert not (show_dir / "tvshow.nfo").exists()
    assert not (show_dir / "season.nfo").exists()


def test_without_nfo_options_only_the_rename_happens(tmp_path):
    video = make_video(tmp_path)

    result = batch_rename([make_file(video)], TEMPLATE)

    show_dir = tmp_path / SHOW_DIR
    assert result.nfo_written == []
    assert result.nfo_skipped == []
    assert result.results[0].nfo_path is None
    assert not (show_dir / "tvshow.nfo").exists()
    assert not (show_dir / "绝命毒师 - S02E05.nfo").exists()


def test_nfo_matches_may_be_omitted_entirely(tmp_path):
    """nfo_matches 的默认值就是 None：调用方不传它时不能炸, 只当作全部未匹配。"""
    video = make_video(tmp_path)

    result = batch_rename([make_file(video)], TEMPLATE, nfo_options=named_options())

    assert result.nfo_written == []
    assert {"path": str(tmp_path / SHOW_DIR / "绝命毒师 - S02E05.nfo"),
            "reason": "TMDB 未匹配, 不写残缺 NFO"} in result.nfo_skipped


def test_mixed_shows_in_one_directory_write_episode_nfo_only(tmp_path):
    """混放目录里每集 NFO 照写、剧集级一条不落 —— 这是整件事的安全底线。"""
    first = make_video(tmp_path, filename="绝命毒师.S02E05.mkv")
    second = make_video(tmp_path, filename="绝命律师.S01E01.mkv")

    result = batch_rename(
        [make_file(first, "f1"), make_file(second, "f2")], TEMPLATE,
        # 同一目录下两个文件从文件名推导出的剧名相同, 只能靠手动覆盖区分两部剧
        overrides={"f2": {"show_name": "绝命律师"}},
        nfo_options=named_options(),
        nfo_matches={
            "f1": make_match(),
            "f2": make_match(show_name="绝命律师", season_no=1, episode_no=1),
        },
    )

    show_dir = tmp_path / SHOW_DIR
    assert sorted(result.nfo_written) == sorted([
        str(show_dir / "绝命毒师 - S02E05.nfo"),
        str(show_dir / "绝命律师 - S01E01.nfo"),
    ])
    # 2 条**而不是 4 条**: 混放分支为组内每个条目各发一条同路径的决策（这里 4 条
    # 决策、2 个路径）, 跳过清单按路径去重后才对得上「有 2 个文件不会被写」。
    # 去重前这里是 4 —— 对话框会把它读成「跳过 4 个」。
    assert [(item["path"], item["reason"]) for item in result.nfo_skipped] == [
        (str(show_dir / "tvshow.nfo"), f"{show_dir} 下有多部剧混放, 不写剧集级 NFO"),
        (str(show_dir / "season.nfo"), f"{show_dir} 下有多部剧混放, 不写剧集级 NFO"),
    ]
    assert not (show_dir / "tvshow.nfo").exists()
    assert not (show_dir / "season.nfo").exists()


def test_mixed_shows_do_not_inflate_the_skipped_count(tmp_path):
    """3 文件混放批次（6 条决策 / 2 个路径）报 2 条跳过, 干跑与真跑一个数字。

    这是 1 部剧 2 集 + 1 部剧 1 集：混放守卫按**组内每个条目**各发一条同路径的
    剧集级/季级决策, 于是 6 条决策只对应 2 个真实路径 —— 不去重就报「跳过 6 个」。
    干跑那条路径是**另一份实现**（local_renamer 自己拼清单, 不走 write_nfo_files）,
    两处各写一遍必然漂移, 所以这里对同一个夹具先干跑后真跑, 断言两者相等。
    """
    first = make_video(tmp_path, filename="绝命毒师.S02E05.mkv")
    second = make_video(tmp_path, filename="绝命毒师.S02E06.mkv")
    third = make_video(tmp_path, filename="绝命律师.S01E01.mkv")
    files = [make_file(first, "f1"), make_file(second, "f2"), make_file(third, "f3")]
    matches = {
        "f1": make_match(),
        "f2": make_match(episode_no=6),
        "f3": make_match(show_name="绝命律师", season_no=1, episode_no=1),
    }

    # 剧名取自**父目录名**, 所以第三个文件得靠手改剧名才会与另外两个分属两部剧
    # （否则三部文件同属「绝命毒师」, 守卫不拒绝, 也就复现不出这个形状）。
    overrides = {"f3": {"show_name": "绝命律师"}}
    dry = batch_rename(files, TEMPLATE, dry_run=True, overrides=overrides,
                       nfo_options=named_options(), nfo_matches=matches)
    real = batch_rename(files, TEMPLATE, overrides=overrides,
                        nfo_options=named_options(), nfo_matches=matches)

    assert dry.nfo_written == real.nfo_written
    assert len(real.nfo_written) == 3, "每集 NFO 照写（3 个视频）"
    assert len(real.nfo_skipped) == 2, "2 个路径（tvshow + season）而不是 6 条决策"
    assert len(dry.nfo_skipped) == 2, "干跑那条实现必须报同一个数字"
    assert [item["path"] for item in dry.nfo_skipped] == [
        item["path"] for item in real.nfo_skipped
    ]


def make_subtitle(video, file_id="f2"):
    """与视频同集的字幕。除扩展名与 is_subtitle 外, 其余字段与那个视频一字不差 ——
    这正是它会与视频抢 group[0] 的原因。"""
    sub = video.with_suffix(".chs.srt")
    sub.write_bytes(b"fake subtitle")
    return FileInfo(
        id=file_id, path=str(sub), filename=sub.name, extension=".srt",
        parent_dir=str(sub.parent), is_subtitle=True,
    )


def test_subtitle_gets_no_nfo_and_show_level_files_land_on_the_video(tmp_path):
    """字幕不进 NFO 管线, 且剧集级决策不能挂到字幕行上。

    判据用的是扫描器判定好的 FileInfo.is_subtitle。字幕一旦进了管线会有两个后果:
    (1) 每个字幕旁多一个无意义的 绝命毒师 - S02E05.chs.nfo（解析器给字幕与视频
        **完全相同**的结果, 而 episode_nfo_path 只换扩展名）;
    (2) 决策按 (show_name, season, episode, new_path) 排序, '….chs.srt' < '….mkv',
        字幕抢到 group[0] —— tvshow.nfo / season.nfo 的落点会显示在字幕行上。

    这里给字幕也配了**完整的 TMDB 匹配**（现实中它确实会有: 解析结果与视频相同,
    走的是同一次解析）, 否则过滤掉的是「一个本来就写不出内容的字幕」, 过滤与否
    都看不出来 —— 那样这条用例就是零鉴别力的。

    变异验证: 去掉 local_renamer 里的过滤 → 本用例 FAILED（字幕旁出现 .chs.nfo,
    且 nfo_written 多一条）。
    """
    video = make_video(tmp_path, filename="绝命毒师.S02E05.mkv")
    subtitle = make_subtitle(video)

    result = batch_rename(
        [make_file(video, "f1"), subtitle], TEMPLATE,
        nfo_options=named_options(),
        nfo_matches={"f1": make_match(), "f2": make_match()},
    )

    show_dir = tmp_path / SHOW_DIR
    # 字幕旁 0 个 .nfo —— 整个目录里恰好只有该有的三个
    assert sorted(p.name for p in show_dir.glob("*.nfo")) == [
        "season.nfo", "tvshow.nfo", "绝命毒师 - S02E05.nfo",
    ]
    assert result.nfo_written == [
        str(show_dir / "绝命毒师 - S02E05.nfo"),
        str(show_dir / "tvshow.nfo"),
        str(show_dir / "season.nfo"),
    ]
    # 剧集级/季级决策挂在**视频**那一行（f1）, 不是字幕（f2）
    assert result.results[0].nfo_path == str(show_dir / "绝命毒师 - S02E05.nfo")
    assert result.results[1].nfo_path is None
    # 过滤只作用于 NFO: 字幕照常重命名（那是既有功能, 不能被这道过滤碰坏）
    assert result.results[1].success is True
    assert not Path(subtitle.path).is_file(), "字幕原文件应已被重命名"
    assert (show_dir / "绝命毒师 - S02E05.srt").is_file()


# --- 没落地的行不写 NFO（审查 Important 1）------------------------------------
# 写盘阶段原来看的是「这条决策算出来了没有」, 而不是「这一行真的落到那儿了没有」。
# 于是 skip 策略下目标名被占用时（视频一步没动）, 给**它**算的每集 NFO 会落在
# **占住这个名字的另一个视频**旁边; abort 下更糟: 行上报着 nfo_path=None, 磁盘上
# 却出现了一个新文件。这两条用例就是审查复现的 CASE1 / CASE2。

def test_file_that_was_not_renamed_writes_no_nfo(tmp_path):
    """CASE1: strategy=skip、目标名被另一个视频占住 —— 一个字都不许落盘。

    变异验证: 去掉 local_renamer 里 `_keep_decision` 那道过滤（或把它换成恒真）
    → 本用例 FAILED: 绝命毒师 - S02E05.nfo 会出现在**占用者**旁边（那是一个
    与它毫无关系的视频）, 且 nfo_written 非空。
    """
    video = make_video(tmp_path, filename="绝命毒师.S02E05.mkv")
    show_dir = tmp_path / SHOW_DIR
    occupier = show_dir / "绝命毒师 - S02E05.mkv"
    occupier.write_bytes(b"occupying video")

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        conflict_strategy="skip",
        nfo_options=named_options(),
        nfo_matches={"f1": make_match()},
    )

    assert result.results[0].status == "skipped_conflict"
    assert result.results[0].nfo_path is None
    assert result.skipped == 1 and result.failed == 0
    # 视频一步没动, 所以它旁边也不该多出任何 NFO
    assert video.is_file()
    assert not (show_dir / "绝命毒师 - S02E05.nfo").exists()
    assert not (show_dir / "绝命毒师.S02E05.nfo").exists()
    # 整批一条都没落地 → 剧集级/季级的落点同样是凭空推出来的, 一并不写
    assert result.nfo_written == []
    assert not (show_dir / "tvshow.nfo").exists()
    assert not (show_dir / "season.nfo").exists()
    # 不写要报出来（留白等于静默）: 这一行的 NFO 被跳过, 原因是它没改名
    assert result.nfo_skipped == [{
        "path": str(show_dir / "绝命毒师 - S02E05.nfo"),
        "reason": "该文件未改名, 不写 NFO",
    }]
    assert occupier.read_bytes() == b"occupying video"


def test_abort_strategy_writes_no_nfo_for_the_conflicted_row(tmp_path):
    """CASE2: strategy=abort —— 用户选了最保守的策略, 不能反而多出一个文件。

    abort 那条分支原先在给 result.nfo_path 赋值**之前**就 `continue` 了, 于是
    行上永远报 None, 而写盘阶段照样把那一集的 NFO 写出去 —— 用户被告知「这一行
    没有落点」, 转头却发现自己的 NFO 已经躺在别人视频旁边。

    abort 行必须**走到**下面那段共用逻辑（没落地 → 不写 + 报跳过）, 所以本用例
    同时钉住那个既有的 `continue` 残留: 恢复它, 本用例 FAILED（nfo_written 非空,
    且 nfo_skipped 里没有那条「该文件未改名」）。

    计数与改动前一致: abort 的冲突行计入 failed, 不是 skipped。
    """
    video = make_video(tmp_path, filename="绝命毒师.S02E05.mkv")
    show_dir = tmp_path / SHOW_DIR
    (show_dir / "绝命毒师 - S02E05.mkv").write_bytes(b"occupying video")

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        conflict_strategy="abort",
        nfo_options=named_options(),
        nfo_matches={"f1": make_match()},
    )

    assert result.results[0].status == "conflict"
    assert result.results[0].nfo_path is None
    assert result.failed == 1 and result.skipped == 0
    assert video.is_file()
    assert result.nfo_written == []
    assert not (show_dir / "绝命毒师 - S02E05.nfo").exists()
    assert not (show_dir / "tvshow.nfo").exists()
    assert [item["path"] for item in result.nfo_skipped] == [
        str(show_dir / "绝命毒师 - S02E05.nfo"),
    ]


def test_a_conflicted_first_episode_does_not_drop_the_show_level_nfo(tmp_path):
    """反面: 组代表那一行没落地, 也不能把整部剧的 tvshow.nfo 丢掉。

    E05 的目标名被占（跳过）, E06 照常改名 —— 剧集级/季级决策按契约挂在组内
    **第一条**（排序后是 E05, 也就是那条没落地的行）上。判据写成「决策的 file_id
    没落地就整条丢掉」会把这个批次的两份剧集级 NFO 一起吞掉, 而 E06 明明就在
    那个目录里。组级决策属于**整组**, 判据必须是「该目录下有没有真的落地一个
    视频」。

    变异验证: 把 _keep_decision 的组级分支也换成 `decision.file_id not in
    dead_file_ids` → 本用例 FAILED（tvshow.nfo / season.nfo 都不再被写）。
    """
    conflicted = make_video(tmp_path, filename="绝命毒师.S02E05.mkv")
    renamed = make_video(tmp_path, filename="绝命毒师.S02E06.mkv")
    show_dir = tmp_path / SHOW_DIR
    (show_dir / "绝命毒师 - S02E05.mkv").write_bytes(b"occupying video")

    result = batch_rename(
        [make_file(conflicted, "f1"), make_file(renamed, "f2")], TEMPLATE,
        conflict_strategy="skip",
        nfo_options=named_options(),
        nfo_matches={"f1": make_match(), "f2": make_match(episode_no=6)},
    )

    assert [r.status for r in result.results] == ["skipped_conflict", "renamed"]
    assert result.results[0].nfo_path is None
    assert result.results[1].nfo_path == str(show_dir / "绝命毒师 - S02E06.nfo")
    assert sorted(result.nfo_written) == sorted([
        str(show_dir / "绝命毒师 - S02E06.nfo"),
        str(show_dir / "tvshow.nfo"),
        str(show_dir / "season.nfo"),
    ])
    # 没落地那一集的 NFO 一个字节都没写, 但清单里报了它
    assert not (show_dir / "绝命毒师 - S02E05.nfo").exists()
    assert result.nfo_skipped == [{
        "path": str(show_dir / "绝命毒师 - S02E05.nfo"),
        "reason": "该文件未改名, 不写 NFO",
    }]

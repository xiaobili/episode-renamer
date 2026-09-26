import os

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
    # 简报此处期望 `tmp_path / "绝命毒师" / "tvshow.nfo"`（季目录上溯一层）。
    # HEAD 的 Task 2（已审查）取「公共父目录」字面语义：只有一个季目录时公共父
    # 就是该季目录，故 tvshow.nfo 落在 Season 02/ 下 —— 两者不可兼得，见
    # task-3-report.md 的「待裁定」第 1 条。本用例的目标是 write_nfo_files，
    # 故按 HEAD 现有的 Task 2 契约断言，不在此隐式要求改 Task 2。
    assert sorted(written) == sorted([
        str(video.with_suffix(".nfo")),
        str(tmp_path / "绝命毒师" / "Season 02" / "season.nfo"),
        str(tmp_path / "绝命毒师" / "Season 02" / "tvshow.nfo"),
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
    assert len(result.nfo_skipped) == 4, "4 条: 两部剧各一条 tvshow + 各一条 season"
    assert all("多部剧混放" in item["reason"] for item in result.nfo_skipped)
    assert not (show_dir / "tvshow.nfo").exists()
    assert not (show_dir / "season.nfo").exists()

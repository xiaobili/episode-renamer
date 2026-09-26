import os
import shutil
from pathlib import Path

from app.core import local_renamer
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
    那是冲突那一集的位置, 覆盖模式下还会把它的内容改写掉。

    **同一件事也适用于跟随**（spec §9.1.1 边界 4 的落点判据）: 调用点必须用
    `result.new_path`（真实目标 X_1）, 不是 `plan.new_path`（X）。用 plan.new_path
    时孤儿算出的目标是**冲突那一集**的 NFO, 它当然已存在 → 报一个**假的**「新名字处
    已有文件」, 孤儿原地不动, 而新视频旁边一个配对 NFO 都没有。

    变异验证: 把调用点的 `result.new_path` 改成 `plan.new_path` → 本用例 FAILED
    （nfo_carried 为空, 旧前缀的孤儿还在）。
    """
    video = make_video(tmp_path)
    old_nfo = make_existing_nfo(video)
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
    # 孤儿跟随到**真实目标**（_1）的前缀, 不是计划目标（X = 冲突那一集）的前缀
    assert result.nfo_carried == [str(renamed_nfo)]
    assert not old_nfo.exists()
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
    # 不写要报出来（留白等于静默）: 这一行的 NFO 被跳过, 原因是它没改名。
    # 另外两条是组级决策（tvshow / season）: 整批没落地, 它们的落点同样是凭空
    # 推出来的, 一并不写 —— 此前它们被静默丢掉, 清单里查无此物（收尾项 3）。
    assert result.nfo_skipped == [{
        "path": str(show_dir / "tvshow.nfo"),
        "reason": "该剧（季）下没有文件真正改名落地, 不写剧集级/季级 NFO",
    }, {
        "path": str(show_dir / "season.nfo"),
        "reason": "该剧（季）下没有文件真正改名落地, 不写剧集级/季级 NFO",
    }, {
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
    # 三条: 两组级决策（收尾项 3, 整批没落地不写但报出来）+ 这一行的每集落点
    assert [item["path"] for item in result.nfo_skipped] == [
        str(show_dir / "tvshow.nfo"),
        str(show_dir / "season.nfo"),
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


# --- 既有的同前缀 NFO 跟随视频改名（spec §9.1.1）-------------------------------
# 旧的 绝命毒师.S02E05.nfo 既不在 video_extensions 也不在 subtitle_extensions,
# 从不进入扫描、不在批次里, 重命名路径上原先没有任何东西碰它 —— 视频改名后它
# 必然留下, 成为与新文件名不符的孤儿。这一节钉住「同前缀的那一个 .nfo 跟着走」。

CARRY_TARGET_EXISTS_REASON = "旧前缀 NFO 未跟随: 新名字处已有文件, 覆盖开关不影响跟随"
DROPPED_GROUP_REASON = "该剧（季）下没有文件真正改名落地, 不写剧集级/季级 NFO"


def make_existing_nfo(video, content="别的工具写的元数据"):
    """与视频**同前缀**的既有 NFO —— 主用例: 用户没开生成, 这文件是别的工具写的。"""
    nfo = video.with_suffix(".nfo")
    nfo.write_text(content, encoding="utf-8")
    return nfo


def test_existing_same_stem_nfo_follows_the_video_when_generation_is_off(tmp_path):
    """边界 3: 跟随是**重命名**的一部分, 与「是否生成 NFO」无关。

    主用例恰恰是这一条: 用户没开生成（NfoOptions 未启用）, 旁边的 NFO 是别的
    工具写的 —— 视频改名后它必须跟着走, 否则留下一个与视频名不符的孤儿。

    变异验证: 去掉 batch_rename 里的 carry 调用 → 本用例 FAILED（nfo_carried
    为空, 且 绝命毒师.S02E05.nfo 仍在原处）。
    """
    video = make_video(tmp_path)
    old_nfo = make_existing_nfo(video)

    result = batch_rename([make_file(video)], TEMPLATE, nfo_options=NfoOptions())

    show_dir = tmp_path / SHOW_DIR
    new_nfo = show_dir / "绝命毒师 - S02E05.nfo"
    assert (show_dir / "绝命毒师 - S02E05.mkv").is_file()
    assert result.nfo_carried == [str(new_nfo)]
    assert new_nfo.read_text(encoding="utf-8") == "别的工具写的元数据"
    assert not old_nfo.exists(), "旧前缀的 NFO 不得留下"
    # 跟随不是生成: 没开生成就既没有写入清单也没有跳过清单
    assert result.nfo_written == [] and result.nfo_skipped == []


def test_carried_nfo_occupies_the_target_before_generation_so_the_original_survives(tmp_path):
    """边界 4（顺序是关键）: 先跟随移动、后生成。

    移过去的旧 NFO 占住新位置 → 「生成开 + 覆盖关」时生成报「已存在」→ 用户原有
    的内容得以保留。反过来（先生成再移动）会让生成先写入 绝命毒师 - S02E05.nfo,
    移动再撞上「目标已存在」而放弃 —— 用户的内容被生成结果替掉, 旧文件还留在原处。

    变异验证: 把 carry 挪到函数末尾的写盘之后 → 本用例 FAILED（新 NFO 的内容变成
    生成的 XML, 而不是「用户原有的内容」, 且 nfo_carried 为空）。
    """
    video = make_video(tmp_path)
    old_nfo = make_existing_nfo(video, "用户原有的内容")

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        nfo_options=named_options(overwrite=False),
        nfo_matches={"f1": make_match()},
    )

    show_dir = tmp_path / SHOW_DIR
    new_nfo = show_dir / "绝命毒师 - S02E05.nfo"
    assert new_nfo.read_text(encoding="utf-8") == "用户原有的内容", "既有的 NFO 内容必须活下来"
    assert not old_nfo.exists()
    # 跟随 ≠ 生成: 落点报在 nfo_carried 里, 不进 nfo_written
    assert result.nfo_carried == [str(new_nfo)]
    assert str(new_nfo) not in result.nfo_written
    # 它占住位置这件事对用户可见: 生成报「已存在」, 对话框据此给出可行动提示
    assert {"path": str(new_nfo), "reason": "已存在"} in result.nfo_skipped


def test_dry_run_lists_the_carried_nfo_without_moving_it(tmp_path):
    """干跑不移动, 但必须列出将跟随的 NFO（与 §9.4 的可见性一致）。

    并且干跑必须与真跑报同一个「已存在」: 移动在**生成之前**发生, 所以生成那一刻
    新位置上已经有这个文件了 —— 干跑若把新 NFO 列进「将写入」, 就是把执行前唯一
    的可见性变成假话。

    变异验证: ①去掉 dry_run 分支里的 carry → nfo_carried 为空, FAILED;
    ②去掉干跑「已存在」判据里的 carried 项 → 新 NFO 落进 nfo_written, FAILED。
    """
    video = make_video(tmp_path)
    old_nfo = make_existing_nfo(video, "用户原有的内容")

    result = batch_rename(
        [make_file(video)], TEMPLATE, dry_run=True,
        nfo_options=named_options(overwrite=False),
        nfo_matches={"f1": make_match()},
    )

    show_dir = tmp_path / SHOW_DIR
    new_nfo = show_dir / "绝命毒师 - S02E05.nfo"
    assert result.nfo_carried == [str(new_nfo)]
    assert {"path": str(new_nfo), "reason": "已存在"} in result.nfo_skipped
    assert str(new_nfo) not in result.nfo_written
    # 干跑绝不落盘: 视频与 NFO 都还在原处, 新位置什么都没有
    assert video.is_file()
    assert old_nfo.read_text(encoding="utf-8") == "用户原有的内容"
    assert not new_nfo.exists()


def test_carry_follows_the_video_into_a_new_season_folder(tmp_path):
    """开了季文件夹时落点是**新目录**: 同前缀 NFO 必须跟着过去, 不能留在旧目录。

    落点与每集 NFO 同一判据（result.new_path → episode_nfo_path）, 目录由视频那一步
    先 mkdir 出来 —— 顺序上跟随在重命名之后, 所以目标目录那时已经存在。
    """
    video = make_video(tmp_path)
    old_nfo = make_existing_nfo(video)

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        folder_template="Season {season_padded}", create_season_folder=True,
        nfo_options=NfoOptions(),
    )

    show_dir = tmp_path / SHOW_DIR
    new_nfo = show_dir / "Season 02" / "绝命毒师 - S02E05.nfo"
    assert result.nfo_carried == [str(new_nfo)]
    assert new_nfo.read_text(encoding="utf-8") == "别的工具写的元数据"
    assert not old_nfo.exists()
    assert not (show_dir / "绝命毒师 - S02E05.nfo").exists()
    assert sorted(p.name for p in show_dir.rglob("*.nfo")) == ["绝命毒师 - S02E05.nfo"]


def test_carry_does_not_overwrite_an_existing_target_nfo(tmp_path):
    """失败处理之一: 目标已存在 → 不覆盖, 两个文件都不动（报跳过）。

    宁可留下可见的孤儿, 也不静默改写别人的元数据。视频照常改名 —— 跟随失败不许
    牵连已经成功的重命名。
    """
    video = make_video(tmp_path)
    old_nfo = make_existing_nfo(video, "旧的")
    show_dir = tmp_path / SHOW_DIR
    target = show_dir / "绝命毒师 - S02E05.nfo"
    target.write_text("已经在那儿的", encoding="utf-8")

    result = batch_rename([make_file(video)], TEMPLATE, nfo_options=NfoOptions())

    assert result.nfo_carried == []
    assert {"path": str(target), "reason": CARRY_TARGET_EXISTS_REASON} in result.nfo_skipped
    assert target.read_text(encoding="utf-8") == "已经在那儿的"
    assert old_nfo.read_text(encoding="utf-8") == "旧的", "源文件也不许动"
    assert result.executed == 1 and result.failed == 0
    assert (show_dir / "绝命毒师 - S02E05.mkv").is_file()


def test_carry_skip_reason_survives_alongside_the_generation_skip(tmp_path):
    """跟随的跳过不许被生成侧的「已存在」吃掉（去重判据是 (路径, 原因) 这一对）。

    同一个路径上会发生**两件不同的事**: 那份文件本来就在（生成没写, 它那条理由
    带着「去勾覆盖开关」的可行动提示）, 以及孤儿想过来却没搬成（跟随没成）。
    只按路径去重时生成侧胜出, 界面于是把用户引去勾一个**对孤儿无效**的开关 ——
    跟随无条件重查 dst.exists(), 覆盖开关管不着它 —— 孤儿就这么永久留下且无人提及。
    所以两条理由都留着, 各自写明是哪件事（跟随那条自己点明「覆盖开关不影响跟随」）。

    变异验证: 把 dedupe_skipped_pairs 改回只按路径去重 → 本用例 FAILED
    （跟随那条理由消失, 界面只剩「已存在」）。
    """
    video = make_video(tmp_path)
    old_nfo = make_existing_nfo(video, "旧的")
    show_dir = tmp_path / SHOW_DIR
    target = show_dir / "绝命毒师 - S02E05.nfo"
    target.write_text("已经在那儿的", encoding="utf-8")

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        nfo_options=named_options(overwrite=False),
        nfo_matches={"f1": make_match()},
    )

    reasons = [item["reason"] for item in result.nfo_skipped if item["path"] == str(target)]
    assert "已存在" in reasons, "生成侧那条（带可行动提示）"
    assert CARRY_TARGET_EXISTS_REASON in reasons, "跟随侧那条（说明拖住它的是文件）"
    assert result.nfo_carried == []
    assert old_nfo.read_text(encoding="utf-8") == "旧的"
    assert target.read_text(encoding="utf-8") == "已经在那儿的"


def test_a_failed_carry_move_does_not_abort_the_batch(tmp_path, monkeypatch):
    """失败处理之二: 跟随移动失败不阻断批量（重命名那时已经成功了）。

    变异验证: 去掉 carry 里的 try/except → 本用例 ERROR（OSError 冒到 batch_rename
    外面, 整批重命名跟着崩）。
    """
    video = make_video(tmp_path)
    old_nfo = make_existing_nfo(video, "用户原有的内容")

    real_move = shutil.move

    def flaky_move(src, dst, *args, **kwargs):
        if str(dst).endswith(".nfo"):
            raise OSError(13, "Permission denied")
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr(local_renamer.shutil, "move", flaky_move)

    result = batch_rename([make_file(video)], TEMPLATE, nfo_options=NfoOptions())

    show_dir = tmp_path / SHOW_DIR
    assert result.executed == 1 and result.failed == 0, "重命名本身不受影响"
    assert (show_dir / "绝命毒师 - S02E05.mkv").is_file()
    assert old_nfo.read_text(encoding="utf-8") == "用户原有的内容"
    assert result.nfo_carried == []
    failures = [item for item in result.nfo_skipped if item["reason"].startswith("同名 NFO 跟随移动失败")]
    assert [item["path"] for item in failures] == [str(show_dir / "绝命毒师 - S02E05.nfo")]


def test_carry_never_touches_tvshow_or_season_nfo(tmp_path):
    """边界 2: 只跟随**同前缀**的那一个 —— tvshow.nfo / season.nfo 隶属剧/季, 不隶属某个视频。

    变异验证: 把 carry 写成「把原目录里所有 .nfo 都搬走」→ 本用例 FAILED
    （tvshow.nfo / season.nfo 被改名或消失）。
    """
    video = make_video(tmp_path)
    old_nfo = make_existing_nfo(video)
    show_dir = tmp_path / SHOW_DIR
    show_nfo = show_dir / "tvshow.nfo"
    season_nfo = show_dir / "season.nfo"
    show_nfo.write_text("<tvshow/>", encoding="utf-8")
    season_nfo.write_text("<season/>", encoding="utf-8")

    result = batch_rename([make_file(video)], TEMPLATE, nfo_options=NfoOptions())

    assert result.nfo_carried == [str(show_dir / "绝命毒师 - S02E05.nfo")]
    assert show_nfo.read_text(encoding="utf-8") == "<tvshow/>"
    assert season_nfo.read_text(encoding="utf-8") == "<season/>"
    assert not old_nfo.exists()
    assert sorted(p.name for p in show_dir.glob("*.nfo")) == [
        "season.nfo", "tvshow.nfo", "绝命毒师 - S02E05.nfo",
    ]


def test_carry_does_not_apply_to_subtitles(tmp_path):
    """边界 1: 只对视频生效, 不对字幕 —— 字幕本就不该有 .nfo。

    字幕旁边那个 绝命毒师.S02E06.chs.nfo 是「NFO 只跟随视频」要防的垃圾, 不是
    「同前缀的那一个」: 它必须留在原处。

    **字幕刻意取**另一集（E06）而不是与本例视频同集（E05）: 同集时字幕算出的
    落点 绝命毒师 - S02E05.nfo 与视频算出的**是同一个路径**, 视频先搬过去之后
    字幕那一步就只会报「目标已存在」—— 去掉过滤的变异照样全绿, 这条用例就成了
    零鉴别力的空断言（实测如此, 故改成另一集: 两个落点必须互不相干）。

    变异验证: 去掉 carry 调用处的 _is_subtitle_file 判断 → 本用例 FAILED
    （字幕的 .nfo 被搬成 绝命毒师 - S02E06.nfo, nfo_carried 多一条）。
    """
    video = make_video(tmp_path, filename="绝命毒师.S02E05.mkv")
    video_nfo = make_existing_nfo(video)
    show_dir = tmp_path / SHOW_DIR
    sub = show_dir / "绝命毒师.S02E06.chs.srt"
    sub.write_bytes(b"fake subtitle")
    subtitle = FileInfo(
        id="f2", path=str(sub), filename=sub.name, extension=".srt",
        parent_dir=str(sub.parent), is_subtitle=True,
    )
    sub_nfo = sub.with_suffix(".nfo")
    sub_nfo.write_text("垃圾", encoding="utf-8")

    result = batch_rename([make_file(video, "f1"), subtitle], TEMPLATE, nfo_options=NfoOptions())

    assert result.nfo_carried == [str(show_dir / "绝命毒师 - S02E05.nfo")]
    assert sub_nfo.is_file() and sub_nfo.read_text(encoding="utf-8") == "垃圾"
    assert not video_nfo.exists()
    assert not (show_dir / "绝命毒师 - S02E06.nfo").exists()
    # 字幕本身照常重命名（既有的那道过滤只作用于 NFO）
    assert (show_dir / "绝命毒师 - S02E06.srt").is_file()


# --- 上一阶段留下的三处收尾（同一文件、同一类）--------------------------------

def test_dead_episode_nfo_paths_are_reported_once(tmp_path):
    """同一集的两个来源都没落地时, 那条落点路径只许出现一次。

    nfo_path_by_file 以 file_id 为键, 两个来源各占一个键却指向**同一个**
    episode_nfo_path（模板里没有清晰度, 两个来源算出同一个新路径）; 两行都 failed
    时各自 pop 一次, 于是同一条路径被 append 两次 —— 对话框会把「1 个路径」读成
    「跳过 2 个」。数字本身撒谎, 与混放那处是同一类, 用的是同一个去重实现。

    变异验证: 把 dead_episode_paths 的收集恢复成不去重的 list 直接展开 →
    本用例 FAILED（该路径出现 2 次）。
    """
    show_dir = tmp_path / SHOW_DIR
    show_dir.mkdir(parents=True, exist_ok=True)
    # 两个来源都不在盘上 → 两行都 failed → 都没有落点
    first = show_dir / "绝命毒师.S02E05.1080p.mkv"
    second = show_dir / "绝命毒师.S02E05.720p.mkv"
    files = [
        FileInfo(id="f1", path=str(first), filename=first.name, parent_dir=str(show_dir)),
        FileInfo(id="f2", path=str(second), filename=second.name, parent_dir=str(show_dir)),
    ]

    result = batch_rename(files, TEMPLATE, nfo_options=named_options())

    dead = str(show_dir / "绝命毒师 - S02E05.nfo")
    assert [r.status for r in result.results] == ["failed", "failed"]
    assert [item["path"] for item in result.nfo_skipped].count(dead) == 1


def test_already_correctly_named_video_still_gets_an_nfo(tmp_path):
    """skipped_same（名字本来就是对的那一行）也必须照写 NFO。

    这是「给已经整理好的库补 NFO」的流程: 名字不用改, 但 NFO 要写。判据是
    _NO_LANDING_STATUSES —— 往里加 skipped_same 就会静默地退掉这条流程, 而它的
    症状（一个 NFO 都没写）与「TMDB 没匹配上」长得一样, 用户无从分辨。

    变异验证: 把 "skipped_same" 加进 _NO_LANDING_STATUSES → 本用例 FAILED
    （nfo_written 为空）。
    """
    video = make_video(tmp_path, filename="绝命毒师 - S02E05.mkv")

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        nfo_options=named_options(),
        nfo_matches={"f1": make_match()},
    )

    show_dir = tmp_path / SHOW_DIR
    assert result.results[0].status == "skipped_same"
    assert result.skipped == 1 and result.failed == 0
    assert str(show_dir / "绝命毒师 - S02E05.nfo") in result.nfo_written
    assert (show_dir / "绝命毒师 - S02E05.nfo").is_file()
    assert video.is_file(), "名字本来就对, 视频不该被动过"


def test_dropped_group_nfo_is_reported_as_skipped(tmp_path):
    """整批没落地时组级决策被丢弃 —— 丢弃必须**报出来**（留白等于静默）。

    组级决策（tvshow / season）的落点由该组全部 new_path 推出, 一条都没落地时
    它同样是凭空推出来的, 一并不写。此前它是被静默丢掉的: 结果里既没有落点也没有
    跳过记录, 用户无法知道「这部剧本该有的 tvshow.nfo 为什么没写」。

    变异验证: 去掉 _keep_decision 分支里那条 skipped_pairs.append → 本用例 FAILED
    （两条断言都查不到这个路径）。
    """
    video = make_video(tmp_path, filename="绝命毒师.S02E05.mkv")
    show_dir = tmp_path / SHOW_DIR
    (show_dir / "绝命毒师 - S02E05.mkv").write_bytes(b"occupying video")

    result = batch_rename(
        [make_file(video)], TEMPLATE,
        conflict_strategy="skip",
        nfo_options=named_options(),
        nfo_matches={"f1": make_match()},
    )

    reasons = {item["path"]: item["reason"] for item in result.nfo_skipped}
    assert reasons[str(show_dir / "tvshow.nfo")] == DROPPED_GROUP_REASON
    assert reasons[str(show_dir / "season.nfo")] == DROPPED_GROUP_REASON

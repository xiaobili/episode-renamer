"""单文件路径与批量路径必须逐项等价（spec R15）。

编排循环存在两份（batch_rename 的循环与 execute_one），叶子助手是共用的。
这条判据就是「两份副本」这个顾虑的答案: 任何一处漂移都会在这里红。

**夹具必须产出非空的四类结果**, 否则断言退化成 [] == [] 恒真、零鉴别力
（本项目已有三次前科）。`test_fixture_is_not_vacuous` 就是为此存在的元判据。

**两条路径必须各跑各的目录**: 批量路径会真的改名, 共用目录时单文件路径的源
文件已经不存在了, 两边根本不是在比同一件事。
"""
import pytest

from app.core.local_renamer import (
    batch_rename, execute_one, finalize_show_nfo, plan_files,
)
import os

from app.core.nfo_writer import dedupe_skipped_pairs
from app.core.tmdb_resolver import STATUS_MATCHED, EpisodeMatch
from app.models.file import FileInfo
from app.models.nfo import NfoOptions
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"

OVERRIDES = {
    "Show.S01E01.mkv": {"show_name": "Show", "season": 1, "episode": 1},
    "Show.S01E02.mkv": {"show_name": "Show", "season": 1, "episode": 2},
    "Show.S01E02.chs.srt": {"show_name": "Show", "season": 1, "episode": 2},
    "Show.S01E03.mkv": {"show_name": "Show", "season": 1, "episode": 3},
}


def _matches():
    """真实元数据 —— 少了它每条决策的 content 都是 None, 两边都写不出文件。"""
    show = TmdbShow(tv_id=1396, name="Show")
    season = TmdbSeason(season_number=1, name="第 1 季")
    return {
        "Show.S01E01.mkv": EpisodeMatch(
            status=STATUS_MATCHED, show=show, season=season,
            episode=TmdbEpisode(episode_number=1, name="试播集"),
        ),
        "Show.S01E02.mkv": EpisodeMatch(
            status=STATUS_MATCHED, show=show, season=season,
            episode=TmdbEpisode(episode_number=2, name="第二集"),
        ),
        # E03 的源文件不存在 → 它不落地, 但**要有**决策才能验「报出来」那条规则
        "Show.S01E03.mkv": EpisodeMatch(
            status=STATUS_MATCHED, show=show, season=season,
            episode=TmdbEpisode(episode_number=3, name="第三集"),
        ),
    }


def _video(dir_path, name, is_subtitle=False):
    path = dir_path / name
    path.write_text("x", encoding="utf-8")
    return FileInfo(
        id=name, source="local", path=str(path), filename=name,
        extension=".srt" if is_subtitle else ".mkv",
        parent_dir=str(dir_path), is_subtitle=is_subtitle,
    )


def _setup(dir_path):
    """一个含「已存在」「可跟随」「不落地」三种情形的批次。

    第三种是**必须**的: 少了它, 两条路径在「文件未改名 → 不写 NFO 但必须报出来」
    这条规则上的分叉完全不可见（execute_one 曾漏掉那条 nfo_skipped 记录, 而
    三条断言全绿）。
    """
    files = [
        _video(dir_path, "Show.S01E01.mkv"),
        _video(dir_path, "Show.S01E02.mkv"),
        _video(dir_path, "Show.S01E02.chs.srt", is_subtitle=True),
        # 源文件**不存在** → status="failed" → 不落地。FileInfo 照造, 但不写盘。
        FileInfo(
            id="Show.S01E03.mkv", source="local",
            path=str(dir_path / "Show.S01E03.mkv"),
            filename="Show.S01E03.mkv", extension=".mkv",
            parent_dir=str(dir_path),
        ),
    ]
    # E02 的目标 NFO 先占住 → 生成侧报「已存在」
    (dir_path / "Show - S01E02.nfo").write_text("old", encoding="utf-8")
    # E01 的旧前缀 NFO 存在 → 跟随侧把它搬过去
    (dir_path / "Show.S01E01.nfo").write_text("legacy", encoding="utf-8")
    return files


def _run_both(tmp_path):
    """同一批输入各跑一个目录, 返回归一掉目录前缀后的可比较字典。"""
    options = NfoOptions(enabled=True, overwrite=False)
    matches = _matches()

    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    batch = batch_rename(
        _setup(batch_dir), TEMPLATE, overrides=OVERRIDES,
        nfo_options=options, nfo_matches=matches,
    )

    single_dir = tmp_path / "single"
    single_dir.mkdir()
    plans = plan_files(_setup(single_dir), TEMPLATE, overrides=OVERRIDES)
    outcomes = [
        execute_one(p, nfo_options=options, nfo_matches=matches) for p in plans
    ]
    landed = [o.landed_path for o in outcomes if o.landed_path is not None]
    show_written, show_skipped = finalize_show_nfo(plans, landed, matches, options)

    def norm(paths):
        return sorted(
            p.replace(str(batch_dir), "<D>").replace(str(single_dir), "<D>")
            for p in paths
        )

    return {
        "batch_counts": (batch.executed, batch.skipped, batch.failed, batch.total),
        "single_counts": (
            sum(o.executed for o in outcomes),
            sum(o.skipped for o in outcomes),
            sum(o.failed for o in outcomes),
            len(outcomes),
        ),
        "batch_written": norm(batch.nfo_written),
        "single_written": norm(
            [p for o in outcomes for p in o.nfo_written] + show_written
        ),
        "batch_carried": norm(batch.nfo_carried),
        "single_carried": norm([p for o in outcomes for p in o.nfo_carried]),
        "batch_skipped": sorted(
            (norm([d["path"]])[0], d["reason"]) for d in batch.nfo_skipped
        ),
        "single_skipped": sorted(
            (norm([p])[0], r)
            for p, r in dedupe_skipped_pairs(
                [x for o in outcomes for x in o.nfo_skipped] + list(show_skipped)
            )
        ),
    }


def test_fixture_is_not_vacuous(tmp_path):
    """**元判据**: 夹具必须产出非空的四类结果。

    它保护的是下面四条等价断言本身还有鉴别力 —— 夹具一旦退化成空集,
    那四条会静默变成 [] == [] 的摆设。删掉本用例, 这种退化就没有任何机械
    判据能发现（本项目已有三次前科）。
    """
    d = _run_both(tmp_path)
    assert d["batch_written"], "nfo_written 为空 —— 夹具失去鉴别力"
    assert d["batch_carried"], "nfo_carried 为空 —— 夹具失去鉴别力"
    assert d["batch_skipped"], "nfo_skipped 为空 —— 夹具失去鉴别力"
    assert d["batch_counts"][0] > 0, "没有一条 executed —— 夹具失去鉴别力"
    # 这一条钉住 E03 那行不落地的文件: 少了它, counts 断言就从「也钉 failed」
    # 退回「只钉 executed/total」, 而元判据自己不会红。
    assert d["batch_counts"][2] > 0, "没有一条 failed —— 夹具失去鉴别力"


def test_two_paths_agree_on_counts(tmp_path):
    d = _run_both(tmp_path)
    assert d["single_counts"] == d["batch_counts"]


def test_two_paths_agree_on_nfo_written(tmp_path):
    d = _run_both(tmp_path)
    assert d["single_written"] == d["batch_written"]


def test_two_paths_agree_on_nfo_carried(tmp_path):
    d = _run_both(tmp_path)
    assert d["single_carried"] == d["batch_carried"]


def test_two_paths_agree_on_nfo_skipped(tmp_path):
    d = _run_both(tmp_path)
    assert d["single_skipped"] == d["batch_skipped"]


def test_rename_dup_failure_reports_the_bumped_path_on_both_paths(tmp_path, monkeypatch):
    """rename_dup 撞上重命名失败时, 两条路径必须报**同一个**落点。

    `execute_rename_plan` 在**尝试重命名之前**就把 result.new_path 改成了 X_1
    （它那段的 dst 循环), 所以失败时它也指向 X_1; batch_rename 的 nfo_path_by_file
    对任何 `new_path != plan.new_path` 的行都做这个改指向, 于是未落地那一行报的是
    X_1.nfo。execute_one 曾经只在 landed 分支里改 —— 分叉就在这里, 而交叉判据的
    夹具里没有「冲突 + 重命名失败」的行, 所以它看不见。

    把 execute_one 里的改指向挪回 landed 判断**之内**本用例必红。
    """
    import os as _os

    (tmp_path / "Show - S01E01.mkv").write_text("occupied", encoding="utf-8")
    video = _video(tmp_path, "Show.S01E01.mkv")

    real_rename = _os.rename

    def boom(src, dst):
        # 只让**改指向之后**的那个目标失败, 制造「rename_dup 已改 new_path 但
        # 重命名抛错」这一种组合。
        if str(dst).endswith("Show - S01E01_1.mkv"):
            raise OSError(13, "Permission denied")
        return real_rename(src, dst)

    monkeypatch.setattr(_os, "rename", boom)

    options = NfoOptions(enabled=True)
    matches = _matches()

    batch = batch_rename(
        [video], TEMPLATE, overrides=OVERRIDES,
        conflict_strategy="rename_dup", nfo_options=options, nfo_matches=matches,
    )
    plan = plan_files([video], TEMPLATE, overrides=OVERRIDES)[0]
    outcome = execute_one(
        plan, conflict_strategy="rename_dup",
        nfo_options=options, nfo_matches=matches,
    )

    assert outcome.result.status == "failed", outcome.result.status
    bumped = os.path.join(str(tmp_path), "Show - S01E01_1.nfo")
    assert outcome.dead_episode_path == bumped
    assert (bumped, "该文件未改名, 不写 NFO") in [
        (d["path"], d["reason"]) for d in batch.nfo_skipped
    ]


def test_rename_dup_episode_nfo_follows_real_target(tmp_path):
    """X.mkv 落到 X_1.mkv 时, 每集 NFO 必须跟着落 X_1.nfo（Emby 靠同名配对）。

    Review Focus 3。去掉 execute_one 里那句 `decision.path = episode_nfo_path(
    result.new_path)` 本用例必然红 —— 那时 nfo_path 会指向 X.nfo, 而那个名字属于
    **冲突的那一集**（覆盖模式下还会把它的 NFO 改写掉）。
    """
    # 先占住目标名, 逼出 rename_dup 的 _1 后缀
    (tmp_path / "Show - S01E01.mkv").write_text("occupied", encoding="utf-8")
    video = _video(tmp_path, "Show.S01E01.mkv")
    overrides = {"Show.S01E01.mkv": {"show_name": "Show", "season": 1, "episode": 1}}

    plans = plan_files([video], TEMPLATE, overrides=overrides)
    outcome = execute_one(
        plans[0], conflict_strategy="rename_dup",
        nfo_options=NfoOptions(enabled=True), nfo_matches={},
    )

    assert outcome.result.new_path.endswith("Show - S01E01_1.mkv"), outcome.result.new_path
    assert outcome.result.nfo_path.endswith("Show - S01E01_1.nfo"), outcome.result.nfo_path
    assert outcome.landed_path == outcome.result.new_path

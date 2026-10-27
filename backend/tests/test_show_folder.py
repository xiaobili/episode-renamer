"""剧集文件夹重命名：`剧名 (年份) [tmdbid-x]`。

覆盖三件事：
1. 目标名的拼装（年份缺失、非法字符、空名）；
2. 剧集根的推导（Season 子目录上溯、混放 / 嵌套拒绝、无 TMDB 拒绝、幂等）；
3. 两个执行器真的动盘 / 真的调客户端（含目标已存在时不覆盖）。
"""
import asyncio
import os

from app.core.local_renamer import build_rename_plan
from app.core.show_folder import (
    ALREADY_NAMED_REASON,
    MIXED_SHOWS_REASON,
    NO_TMDB_REASON,
    ROOT_TOO_SHALLOW_REASON,
    SOURCE_MISSING_REASON,
    TARGET_EXISTS_REASON,
    ShowFolderPlan,
    apply_local_show_folders,
    apply_openlist_show_folders,
    build_show_folder_name,
    plan_show_folders,
)
from app.core.tmdb_resolver import STATUS_DISABLED, STATUS_MATCHED, EpisodeMatch
from app.models.file import FileInfo, OverrideInfo
from app.models.openlist import OpenListFile
from app.models.tmdb import TmdbShow

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
SHOW = TmdbShow(tv_id=1396, name="绝命毒师", original_name="Breaking Bad", year=2008)


def _info(path: str) -> FileInfo:
    return FileInfo(
        id=path,
        path=path,
        filename=os.path.basename(path),
        extension=os.path.splitext(path)[1],
        parent_dir=os.path.dirname(path),
    )


def _plans(paths: list[str]):
    return [build_rename_plan(_info(p), TEMPLATE) for p in paths]


def _matches(plans, show=SHOW, status=STATUS_MATCHED):
    return {p.file_id: EpisodeMatch(status=status, show=show) for p in plans}


# --- 1. 目标名拼装 ---------------------------------------------------------

def test_name_uses_tmdb_title_year_and_id():
    assert build_show_folder_name(SHOW) == "绝命毒师 (2008) [tmdbid-1396]"


def test_name_omits_year_when_tmdb_has_none():
    # TMDB 的 first_air_date 偶有缺失；此时不能写出「()」这种空括号。
    assert build_show_folder_name(
        SHOW.model_copy(update={"year": None})
    ) == "绝命毒师 [tmdbid-1396]"


def test_name_sanitises_illegal_filename_chars():
    show = SHOW.model_copy(update={"name": "Breaking/Bad: 绝命"})
    assert build_show_folder_name(show) == "Breaking Bad 绝命 (2008) [tmdbid-1396]"


def test_empty_tmdb_name_yields_empty():
    # 空名必须返回 ""（调用方据此拒绝），而不是拼出 " (2008) [tmdbid-1396]"
    # 这种把目录改名成只剩年份的形态。
    assert build_show_folder_name(SHOW.model_copy(update={"name": "   "})) == ""


# --- 2. 剧集根推导 ---------------------------------------------------------

def test_single_season_subfolder_is_stepped_over(tmp_path):
    show_dir = tmp_path / "绝命毒师" / "Season 01"
    plans = _plans([
        str(show_dir / "Breaking.Bad.S01E01.mkv"),
        str(show_dir / "Breaking.Bad.S01E02.mkv"),
    ])

    result = plan_show_folders(plans, _matches(plans))

    assert len(result) == 1
    assert result[0].old_path == str(tmp_path / "绝命毒师")
    assert result[0].new_path == str(tmp_path / "绝命毒师 (2008) [tmdbid-1396]")
    assert result[0].reason is None
    assert sorted(result[0].file_ids) == sorted(p.file_id for p in plans)


def test_multi_season_layout_shares_one_root(tmp_path):
    plans = _plans([
        str(tmp_path / "绝命毒师" / "Season 01" / "Breaking.Bad.S01E01.mkv"),
        str(tmp_path / "绝命毒师" / "Season 02" / "Breaking.Bad.S02E01.mkv"),
    ])

    result = plan_show_folders(plans, _matches(plans))

    assert len(result) == 1, "一部剧只应产生一条文件夹计划"
    assert result[0].old_path == str(tmp_path / "绝命毒师")


def test_files_directly_in_show_dir_use_that_dir(tmp_path):
    plans = _plans([str(tmp_path / "绝命毒师" / "Breaking.Bad.S01E01.mkv")])

    result = plan_show_folders(plans, _matches(plans))

    assert result[0].old_path == str(tmp_path / "绝命毒师")
    assert result[0].new_path == str(tmp_path / "绝命毒师 (2008) [tmdbid-1396]")


def _plans_named(pairs: list[tuple[str, str]]):
    """(路径, 覆盖剧名) → plans。

    混放场景必须靠**覆盖剧名**区分两部剧：解析器对同一目录下的两个文件都会
    从父目录继承同一个剧名（`_inherit_show_from_parent` 的权重 0.85 高于文件名），
    不覆盖的话它们在解析层面就是「同一部剧」—— 与 NFO 混放判据同一套前提。
    """
    return [
        build_rename_plan(_info(p), TEMPLATE, override=OverrideInfo(show_name=name))
        for p, name in pairs
    ]


def test_mixed_shows_in_the_same_dir_are_both_refused(tmp_path):
    # 混放目录下改名会把别的剧一起搬走 —— 不可逆, 必须拒绝。
    shared = tmp_path / "未分类"
    plans = _plans_named([
        (str(shared / "A.S01E01.mkv"), "剧A"),
        (str(shared / "B.S01E01.mkv"), "剧B"),
    ])
    other = TmdbShow(tv_id=42, name="别的剧", year=2019)
    matches = {
        plans[0].file_id: EpisodeMatch(status=STATUS_MATCHED, show=SHOW),
        plans[1].file_id: EpisodeMatch(status=STATUS_MATCHED, show=other),
    }

    result = plan_show_folders(plans, matches)

    assert len(result) == 2
    for plan in result:
        assert plan.reason == MIXED_SHOWS_REASON
        assert plan.new_path == ""


def test_nested_show_dir_refuses_only_the_ancestor(tmp_path):
    # /lib/剧A/*.mkv 与 /lib/剧A/剧B/*.mkv：改 剧A 会把 剧B 一起带走, 故只拒祖先。
    outer = tmp_path / "剧A"
    plans = _plans_named([
        (str(outer / "A.S01E01.mkv"), "剧A"),
        (str(outer / "剧B" / "B.S01E01.mkv"), "剧B"),
    ])
    other = TmdbShow(tv_id=42, name="剧B", year=2019)
    matches = {
        plans[0].file_id: EpisodeMatch(status=STATUS_MATCHED, show=SHOW),
        plans[1].file_id: EpisodeMatch(status=STATUS_MATCHED, show=other),
    }

    result = plan_show_folders(plans, matches)
    by_show = {p.show_name: p for p in result}

    assert by_show["剧A"].reason == MIXED_SHOWS_REASON
    assert by_show["剧B"].reason is None
    assert by_show["剧B"].new_path.endswith("剧B (2019) [tmdbid-42]")


def test_no_tmdb_match_is_refused(tmp_path):
    plans = _plans([str(tmp_path / "绝命毒师" / "Breaking.Bad.S01E01.mkv")])

    result = plan_show_folders(plans, {})

    assert result[0].reason == NO_TMDB_REASON
    assert result[0].new_path == ""


def test_disabled_tmdb_is_refused_with_the_same_reason(tmp_path):
    plans = _plans([str(tmp_path / "绝命毒师" / "Breaking.Bad.S01E01.mkv")])

    result = plan_show_folders(plans, _matches(plans, show=None, status=STATUS_DISABLED))

    assert result[0].reason == NO_TMDB_REASON


def test_already_named_dir_is_idempotent(tmp_path):
    target = tmp_path / "绝命毒师 (2008) [tmdbid-1396]"
    plans = _plans([str(target / "Breaking.Bad.S01E01.mkv")])

    result = plan_show_folders(plans, _matches(plans))

    assert result[0].reason == ALREADY_NAMED_REASON
    assert result[0].new_path == ""


def test_show_dir_at_filesystem_root_is_refused(tmp_path):
    # 根目录没有父目录可改名, 且拼出来的目标会落在文件系统根上。
    plans = _plans(["/Breaking.Bad.S01E01.mkv"])

    result = plan_show_folders(plans, _matches(plans))

    assert result[0].reason  # 任一原因都行, 但绝不能给出一个可执行的目标路径
    assert result[0].new_path == ""


def test_top_level_dir_is_refused(tmp_path):
    """`/media` 这种**直接挂在根下**的目录不改名。

    它是「扫的是挂载点而不是剧目录」的典型形态: 目标会算成
    `/绝命毒师 (2008) [tmdbid-1396]` —— 容器里改的是挂载点本身（宿主机上什么都没变）,
    宿主机上则需要 root 权限。两种都不该静默发生。
    """
    plans = _plans(["/media/Breaking.Bad.S01E01.mkv"])

    result = plan_show_folders(plans, _matches(plans))

    assert result[0].reason == ROOT_TOO_SHALLOW_REASON
    assert result[0].new_path == ""


def test_show_dir_one_level_deeper_is_allowed(tmp_path):
    # `/media/绝命毒师` 是 docker-compose 里最常见的挂载布局 —— 不能被上面那条误伤。
    plans = _plans(["/media/绝命毒师/Breaking.Bad.S01E01.mkv"])

    result = plan_show_folders(plans, _matches(plans))

    assert result[0].reason is None
    assert result[0].new_path == "/media/绝命毒师 (2008) [tmdbid-1396]"


# --- 3a. 本地执行 ----------------------------------------------------------

def _folder_plan(old: str, new: str, show_name="绝命毒师") -> ShowFolderPlan:
    return ShowFolderPlan(
        show_name=show_name, old_path=old, new_path=new,
        target_name=os.path.basename(new),
        file_ids=[old],
    )


def test_local_rename_moves_the_whole_tree(tmp_path):
    season_dir = tmp_path / "绝命毒师" / "Season 01"
    season_dir.mkdir(parents=True)
    (season_dir / "ep.mkv").write_bytes(b"x")

    target = tmp_path / "绝命毒师 (2008) [tmdbid-1396]"
    renamed, skipped = apply_local_show_folders([
        _folder_plan(str(tmp_path / "绝命毒师"), str(target)),
    ])

    assert skipped == []
    assert renamed == [{
        "old_path": str(tmp_path / "绝命毒师"),
        "new_path": str(target),
        "show_name": "绝命毒师",
    }]
    # 季目录跟着父目录走, 文件仍在原位（相对路径不变）
    assert (target / "Season 01" / "ep.mkv").exists()
    assert not (tmp_path / "绝命毒师").exists()


def test_local_rename_refuses_existing_target(tmp_path):
    old = tmp_path / "绝命毒师"
    old.mkdir()
    target = tmp_path / "绝命毒师 (2008) [tmdbid-1396]"
    target.mkdir()

    renamed, skipped = apply_local_show_folders([_folder_plan(str(old), str(target))])

    assert renamed == []
    assert skipped == [{"path": str(target), "reason": TARGET_EXISTS_REASON}]
    assert old.exists() and target.exists(), "两边都必须原样保留"


def test_local_rename_is_idempotent_when_already_moved(tmp_path):
    target = tmp_path / "绝命毒师 (2008) [tmdbid-1396]"
    target.mkdir()

    renamed, skipped = apply_local_show_folders([
        _folder_plan(str(tmp_path / "绝命毒师"), str(target)),
    ])

    assert renamed == []
    assert skipped == [{"path": str(target), "reason": ALREADY_NAMED_REASON}]


def test_local_rename_reports_missing_source(tmp_path):
    renamed, skipped = apply_local_show_folders([
        _folder_plan(str(tmp_path / "绝命毒师"), str(tmp_path / "绝命毒师 (2008) [tmdbid-1396]")),
    ])

    assert renamed == []
    assert skipped[0]["reason"] == SOURCE_MISSING_REASON


def test_local_rename_reports_plan_reasons_without_touching_disk(tmp_path):
    old = tmp_path / "绝命毒师"
    old.mkdir()
    plan = _folder_plan(str(old), "")
    plan.reason = NO_TMDB_REASON

    renamed, skipped = apply_local_show_folders([plan])

    assert renamed == []
    assert skipped == [{"path": str(old), "reason": NO_TMDB_REASON}]
    assert old.exists()


# --- 3b. OpenList 执行 -----------------------------------------------------

class FakeOpenList:
    def __init__(self, parent_names=(), fail_rename=None):
        self.parent_names = list(parent_names)
        self.fail_rename = fail_rename
        self.renamed = []
        self.listed = []

    async def list_directory(self, path, refresh=False):
        self.listed.append(path)
        return [OpenListFile(name=n, is_dir=True) for n in self.parent_names], True

    async def rename(self, path, new_name):
        self.renamed.append((path, new_name))
        if self.fail_rename:
            raise Exception(self.fail_rename)
        return {"code": 200}


def test_openlist_rename_calls_client_rename():
    client = FakeOpenList(parent_names=["绝命毒师"])
    renamed, skipped = asyncio.run(apply_openlist_show_folders(client, [
        _folder_plan("/115/绝命毒师", "/115/绝命毒师 (2008) [tmdbid-1396]"),
    ]))

    assert skipped == []
    assert renamed[0]["new_path"] == "/115/绝命毒师 (2008) [tmdbid-1396]"
    assert client.renamed == [("/115/绝命毒师", "绝命毒师 (2008) [tmdbid-1396]")]
    # 撞名检查必须问**父目录**, 不是剧目录自己
    assert client.listed == ["/115"]


def test_openlist_rename_skips_when_target_exists():
    client = FakeOpenList(parent_names=["绝命毒师 (2008) [tmdbid-1396]"])
    renamed, skipped = asyncio.run(apply_openlist_show_folders(client, [
        _folder_plan("/115/绝命毒师", "/115/绝命毒师 (2008) [tmdbid-1396]"),
    ]))

    assert renamed == []
    assert skipped[0]["reason"] == TARGET_EXISTS_REASON
    assert client.renamed == []


def test_openlist_rename_reports_client_failure():
    client = FakeOpenList(parent_names=["绝命毒师"], fail_rename="permission denied")
    renamed, skipped = asyncio.run(apply_openlist_show_folders(client, [
        _folder_plan("/115/绝命毒师", "/115/绝命毒师 (2008) [tmdbid-1396]"),
    ]))

    assert renamed == []
    assert "permission denied" in skipped[0]["reason"]


def test_openlist_rename_treats_missing_target_as_not_yet_renamed():
    # 父目录里既没有旧名也没有新名（远端状态被外部改过）—— 如实报失败,
    # 不要报成功、也不要报「已改名」。
    client = FakeOpenList(parent_names=[])
    renamed, skipped = asyncio.run(apply_openlist_show_folders(client, [
        _folder_plan("/115/绝命毒师", "/115/绝命毒师 (2008) [tmdbid-1396]"),
    ]))

    assert renamed == []
    assert skipped[0]["reason"] == SOURCE_MISSING_REASON
    assert client.renamed == []

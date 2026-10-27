"""STRM 的纯函数判据：URL 拼装、文件名、相对目录与剧集目录。

这几件事都没有副作用，所以单独一个文件；需要落盘 / 出网的用例在
test_strm_local.py 与 test_strm_remote.py。
"""
from app.core.openlist_renamer import build_openlist_rename_plan
from app.core.strm import (
    build_strm_url,
    rel_dir_of,
    rooted_rel_dir,
    show_dir_of,
    strm_filename,
)
from app.models.file import FileInfo

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"


def _plan(name="Show.S01E01.mkv", parent="/115/Show A"):
    file = FileInfo(
        id=name, source="openlist", path=f"{parent}/{name}", filename=name,
        extension=".mkv", parent_dir=parent,
    )
    return build_openlist_rename_plan(file, TEMPLATE)


# --- URL：原样写入，不做百分号编码（用户要求「内容不要有转义」）---


def test_strm_url_keeps_raw_path_without_escaping():
    url = build_strm_url("http://h:5244", "/115/剧 名/S01E01 #1.mkv")
    assert url == "http://h:5244/d/115/剧 名/S01E01 #1.mkv"


def test_strm_url_keeps_path_separators():
    url = build_strm_url("http://h", "/115/Show/Season 01/a.mkv")
    assert url == "http://h/d/115/Show/Season 01/a.mkv"


def test_strm_url_strips_trailing_slash_of_base():
    assert build_strm_url("http://h:5244/", "/a.mkv") == "http://h:5244/d/a.mkv"


def test_strm_url_has_exactly_one_slash_after_d():
    # 远端路径本身以 / 开头, 拼的时候不能变成 /d//115。
    assert build_strm_url("http://h", "//115/a.mkv") == "http://h/d/115/a.mkv"


def test_strm_url_keeps_question_mark_and_hash_raw():
    # 刻意不编码的**代价**（见 build_strm_url 的 docstring）: 文件名里带 ? / #
    # 时它们会被播放器当成 query / fragment。这条钉住「我们确实没编码」。
    assert build_strm_url("http://h", "/a/b?c#d.mkv") == "http://h/d/a/b?c#d.mkv"


def test_strm_url_empty_base_returns_empty():
    assert build_strm_url("", "/a.mkv") == ""
    assert build_strm_url("   ", "/a.mkv") == ""


def test_strm_url_empty_path_returns_empty():
    assert build_strm_url("http://h", "") == ""


# --- 文件名 ---


def test_strm_filename_replaces_extension():
    assert strm_filename("Show - S01E01.mkv") == "Show - S01E01.strm"


def test_strm_filename_without_extension_appends_suffix():
    assert strm_filename("Show - S01E01") == "Show - S01E01.strm"


# --- 相对扫描根 ---


def test_rel_dir_of_is_relative_to_scan_root():
    assert rel_dir_of("/115/剧/Season 01", "/115") == "剧/Season 01"


def test_rel_dir_of_equal_root_is_flat():
    # 扫描根就是剧目录本身时不该多出一层同名目录。
    assert rel_dir_of("/115/剧", "/115/剧") == ""


def test_rel_dir_of_empty_root_is_flat():
    assert rel_dir_of("/115/剧", "") == ""


def test_rel_dir_of_outside_root_falls_back_to_flat():
    # 越界不得返回 ../../xxx —— 否则本地模式会写到输出根外面。
    assert rel_dir_of("/other/剧", "/115") == ""


# --- 剧集名目录 ---


def test_show_dir_prefers_parsed_show_name():
    plan = _plan(parent="/115/Show A")
    assert show_dir_of(plan, "/115/Show A", "/115") == "Show A"


def test_show_dir_sanitizes_illegal_chars():
    # 剧名可能带路径分隔符（用户手填 / 解析残渣），目录名里绝不能有 ——
    # 否则远端会多出一层目录, 本地会写到输出根之外。
    plan = _plan(parent="/115/Show A")
    plan.parsed.show_name = "Bad/Name:2"
    name = show_dir_of(plan, "/115/Show A", "/115")
    assert "/" not in name and ":" not in name and name


def test_show_dir_falls_back_to_landing_dir_name():
    # 解析不出剧名（这里把 parsed 清空）时用落点目录名, 而不是空串。
    plan = _plan(parent="/115/Show A")
    plan.parsed.show_name = ""
    assert show_dir_of(plan, "/115/Show A", "/115") == "Show A"


def test_show_dir_empty_when_nothing_usable():
    plan = _plan(parent="/115/Show A")
    plan.parsed.show_name = ""
    assert show_dir_of(plan, "/", "/") == ""


def test_rooted_rel_dir_prefixes_show():
    assert rooted_rel_dir("", "Show A") == "Show A"
    assert rooted_rel_dir("Season 01", "Show A") == "Show A/Season 01"


def test_rooted_rel_dir_drops_duplicate_show_segment():
    # 扫描根在剧目录之上时首段已是剧名, 不能再冠一层。
    assert rooted_rel_dir("Show A", "Show A") == "Show A"
    assert rooted_rel_dir("Show A/Season 01", "Show A") == "Show A/Season 01"


def test_rooted_rel_dir_without_show_keeps_rel():
    assert rooted_rel_dir("Season 01", "") == "Season 01"
    assert rooted_rel_dir("", "") == ""

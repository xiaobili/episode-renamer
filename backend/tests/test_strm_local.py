"""STRM 落点推导与本地写盘。"""
import os

from app.core.strm import (
    MISSING_BASE_URL,
    MISSING_LOCAL_ROOT,
    NOT_LANDED_STRM_REASON,
    safe_local_target,
    strm_target_for_plan,
    write_strm_local,
)
from app.core.openlist_renamer import build_openlist_rename_plan
from app.models.file import FileInfo, RenameResult
from app.models.strm import StrmOptions

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"


def _file(name="Show.S01E01.mkv", parent="/115/Show A", is_subtitle=False):
    return FileInfo(
        id=name, source="openlist", path=f"{parent}/{name}", filename=name,
        extension=".srt" if is_subtitle else ".mkv", parent_dir=parent,
        is_subtitle=is_subtitle,
    )


def _plan(name="Show.S01E01.mkv", parent="/115/Show A", is_subtitle=False):
    return build_openlist_rename_plan(_file(name, parent, is_subtitle), TEMPLATE)


def _result(plan, *, status="renamed", new_path=None):
    result = RenameResult(
        id=plan.id,
        original_path=plan.original_path,
        new_path=new_path or plan.new_path,
        original_filename=plan.original_filename,
        new_filename=plan.new_filename,
        success=status != "failed",
        status=status,
    )
    return result


def _options(**kwargs):
    base = dict(
        enabled=True,
        mode="local",
        base_url="http://openlist:5244",
        local_root="/tmp/strm",
        remote_root="/strm",
    )
    base.update(kwargs)
    return StrmOptions(**base)


def test_local_target_mirrors_scan_root(tmp_path):
    plan = _plan(parent="/115/Show A")
    target, reason = strm_target_for_plan(
        plan, _result(plan), _options(local_root=str(tmp_path)), "/115",
    )
    assert reason is None
    assert target.path == os.path.join(str(tmp_path), "Show A", "Show A - S01E01.strm")
    assert target.url == "http://openlist:5244/d/115/Show A/Show A - S01E01.mkv"


def test_local_target_still_has_show_dir_when_scan_root_is_the_show_dir(tmp_path):
    # 扫描根就是剧目录时也必须有剧名目录 —— 否则一次扫一部剧就会把所有 strm
    # 平铺进输出根, 输出根里分不出哪部剧是哪个。
    plan = _plan(parent="/115/Show A")
    target, _ = strm_target_for_plan(
        plan, _result(plan), _options(local_root=str(tmp_path)), "/115/Show A",
    )
    assert target.path == os.path.join(str(tmp_path), "Show A", "Show A - S01E01.strm")


def test_local_target_has_single_show_dir_when_root_is_above_show(tmp_path):
    # 扫描根在剧目录之上: 相对路径首段已是剧名, 不能再冠一层。
    plan = _plan(parent="/115/Show A")
    target, _ = strm_target_for_plan(
        plan, _result(plan), _options(local_root=str(tmp_path)), "/115",
    )
    assert target.path.count("Show A") == 2  # 目录一层 + 文件名里的剧名
    assert os.path.dirname(target.path) == os.path.join(str(tmp_path), "Show A")


def test_target_follows_real_landing_path(tmp_path):
    # 视频被移进季目录：strm 必须跟着真实落点走，而不是 plan.new_path。
    plan = _plan(parent="/115/Show A")
    landed = "/115/Show A/Season 01/Show A - S01E01.mkv"
    target, _ = strm_target_for_plan(
        plan, _result(plan, new_path=landed), _options(local_root=str(tmp_path)), "/115",
    )
    assert target.path == os.path.join(
        str(tmp_path), "Show A", "Season 01", "Show A - S01E01.strm",
    )
    assert target.url.endswith(
        "/d/115/Show A/Season 01/Show A - S01E01.mkv"
    )


def test_subtitle_has_no_target_and_no_reason():
    plan = _plan("Show.S01E01.chs.srt", is_subtitle=True)
    assert strm_target_for_plan(plan, _result(plan), _options(), "/115") == (None, None)


def test_disabled_has_no_target_and_no_reason():
    plan = _plan()
    assert strm_target_for_plan(
        plan, _result(plan), _options(enabled=False), "/115",
    ) == (None, None)


def test_not_landed_reports_reason():
    plan = _plan()
    result = _result(plan, status="failed")
    target, reason = strm_target_for_plan(plan, result, _options(), "/115")
    assert target is None
    assert reason == NOT_LANDED_STRM_REASON


def test_skipped_same_still_gets_a_target(tmp_path):
    # 文件名本来就对也算落地 —— strm 仍需要存在。
    plan = _plan()
    result = _result(plan, status="skipped_same")
    target, reason = strm_target_for_plan(
        plan, result, _options(local_root=str(tmp_path)), "/115",
    )
    assert reason is None and target is not None


def test_missing_local_root_reports_reason():
    plan = _plan()
    target, reason = strm_target_for_plan(
        plan, _result(plan), _options(local_root="   "), "/115",
    )
    assert target is None and reason == MISSING_LOCAL_ROOT


def test_missing_base_url_reports_reason():
    plan = _plan()
    target, reason = strm_target_for_plan(
        plan, _result(plan), _options(base_url=""), "/115",
    )
    assert target is None and reason == MISSING_BASE_URL


def test_safe_local_target_rejects_escape(tmp_path):
    assert safe_local_target(str(tmp_path), "../evil", "a.strm") is None


def test_safe_local_target_accepts_nested(tmp_path):
    target = safe_local_target(str(tmp_path), "剧/Season 01", "a.strm")
    assert target == os.path.join(str(tmp_path), "剧", "Season 01", "a.strm")


def test_write_strm_local_creates_dirs_and_writes(tmp_path):
    target = os.path.join(str(tmp_path), "剧", "Season 01", "a.strm")
    write_strm_local(target, b"http://h/d/a.mkv\n")
    with open(target, "rb") as handle:
        assert handle.read() == b"http://h/d/a.mkv\n"


def test_write_strm_local_overwrites(tmp_path):
    target = os.path.join(str(tmp_path), "a.strm")
    with open(target, "wb") as handle:
        handle.write(b"old")
    write_strm_local(target, b"new")
    with open(target, "rb") as handle:
        assert handle.read() == b"new"

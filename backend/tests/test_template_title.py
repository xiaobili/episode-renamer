from app.core.template import apply_template
from app.models.file import ParsedInfo


TEMPLATE = "{show} - S{season_padded}E{episode_padded} - {title}{extension}"


def make_info(title=None):
    return ParsedInfo(
        show_name="绝命毒师",
        season=2,
        episode=5,
        title=title,
        extension=".mkv",
        original_filename="Breaking.Bad.S02E05.mkv",
    )


def test_title_renders_when_present():
    result = apply_template(TEMPLATE, make_info("Breakage"))
    assert result == "绝命毒师 - S02E05 - Breakage.mkv"


def test_title_renders_empty_when_absent():
    # Review Focus 5：TMDB 没查到时 title 为 None。
    # 期望是文件名照常生成、标题位留空 —— 而不是整个重命名失败。
    # 模板自带的 " - " 分隔符留在原地, 所以是 " - .mkv"：
    # _resolve_variable 只替换 {title} 本身, 不会连分隔符一起收掉。
    # 这与 test_rename_routes.py 中同形状的断言（"Test Show - S01E02 - .mkv"）一致。
    result = apply_template(TEMPLATE, make_info(None))
    assert result == "绝命毒师 - S02E05 - .mkv"


def test_template_without_title_variable_is_unaffected():
    result = apply_template("{show} - S{season_padded}E{episode_padded}{extension}", make_info("Breakage"))
    assert result == "绝命毒师 - S02E05.mkv"

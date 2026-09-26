from app.core.template import PadConfig, apply_template, apply_folder_template
from app.config import settings
from app.models.file import ParsedInfo

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"


def make_info():
    return ParsedInfo(
        show_name="Test Show",
        season=1,
        episode=2,
        extension=".mkv",
        original_filename="Test.Show.S01E02.mkv",
    )


def test_no_pad_falls_back_to_global_settings():
    # 向后兼容：pad=None 必须与改动前逐字节一致
    result = apply_template(TEMPLATE, make_info())
    assert result == "Test Show - S01E02.mkv"
    assert settings.episode_pad_digits == 2
    assert settings.season_pad_digits == 2


def test_explicit_pad_overrides_global_settings():
    pad = PadConfig(episode=3, season=1)
    result = apply_template(TEMPLATE, make_info(), pad=pad)
    assert result == "Test Show - S1E002.mkv"


def test_pad_does_not_affect_unpadded_variables():
    # {episode} 与 {episode_padded} 同模板共存时，只有后者受 pad 影响。
    #
    # 计划此处原用 `"{episode}|{episode_padded}"` 断言 `"2|002"`，有两处笔误：
    # ①`|` 在 utils.ILLEGAL_FILENAME_CHARS 内，会被 safe_filename 换成空格；
    # ②模板无 {extension} 而 include_extension 默认 True，会补出 `.mkv`。
    # 改为不含非法字符、显式声明 {extension} 的写法，测试意图（只有 _padded
    # 受 pad 影响）不变，且不掺入 safe_filename 的改写行为。
    info = make_info()
    result = apply_template(
        "{episode}_{episode_padded}{extension}", info, pad=PadConfig(episode=3, season=2)
    )
    assert result == "2_002.mkv"


def test_folder_template_honours_pad():
    result = apply_folder_template(
        "Season {season_padded}", make_info(), pad=PadConfig(episode=2, season=3)
    )
    assert result == "Season 001"


def test_folder_template_without_pad_uses_globals():
    # make_info() 的 season=1，全局默认补零 2 位 -> "01"。
    # 计划此处原写 "Season 02"，与本任务的 fixture（season=1）及同文件其余
    # 5 条断言（S01 / S001）均不自洽，判定为断言笔误而非 fixture 有误。
    result = apply_folder_template("Season {season_padded}", make_info())
    assert result == "Season 01"


def test_pad_of_one_disables_padding():
    result = apply_template(TEMPLATE, make_info(), pad=PadConfig(episode=1, season=1))
    assert result == "Test Show - S1E2.mkv"


def test_generate_full_path_is_removed():
    import app.core.template as tpl

    assert not hasattr(tpl, "generate_full_path")

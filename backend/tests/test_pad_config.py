import pytest

from app.core.template import PadConfig


def test_pad_config_stores_in_range_values():
    pad = PadConfig(episode=3, season=1)
    assert pad.episode == 3
    assert pad.season == 1


def test_pad_config_is_frozen():
    pad = PadConfig(episode=2, season=2)
    with pytest.raises(Exception):
        pad.episode = 5


def test_episode_zero_is_clamped_to_one():
    # 用户清空数字框后留下 0：str(0).zfill(2) == "00" 尚可,
    # 但 0 作为补零位数无意义，统一钳到 1
    assert PadConfig(episode=0, season=2).episode == 1


def test_episode_negative_is_clamped_to_one():
    # str(-1).zfill(2) == "-1" -> 会产出 Show - S01E-1.mkv 这类损坏文件名
    assert PadConfig(episode=-1, season=2).episode == 1


def test_episode_oversized_is_clamped_to_six():
    assert PadConfig(episode=99, season=2).episode == 6


def test_season_zero_is_clamped_to_one():
    assert PadConfig(episode=2, season=0).season == 1


def test_season_negative_is_clamped_to_one():
    assert PadConfig(episode=2, season=-3).season == 1


def test_season_oversized_is_clamped_to_six():
    assert PadConfig(episode=2, season=99).season == 6


def test_both_fields_clamped_independently():
    pad = PadConfig(episode=99, season=0)
    assert pad.episode == 6
    assert pad.season == 1

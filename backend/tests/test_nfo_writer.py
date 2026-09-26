import xml.etree.ElementTree as ET

from app.core.nfo_writer import (
    XML_DECLARATION,
    build_episode_nfo,
    build_season_nfo,
    build_tvshow_nfo,
)
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow


SHOW = TmdbShow(
    tv_id=1396,
    name="绝命毒师",
    original_name="Breaking Bad",
    year=2008,
    overview="一名高中化学教师得知自己身患肺癌后……",
    rating=8.9,
    votes=15000,
    genres=["剧情", "犯罪"],
    premiered="2008-01-20",
    status="Ended",
)


def parse(xml_text: str) -> ET.Element:
    """把生成的字符串解析回来。用字符串拼接生成非法 XML 时这里会直接抛异常 ——
    这正是本组测试要守住的底线。"""
    return ET.fromstring(xml_text.split("\n", 1)[1])


# --- tvshow ---

def test_tvshow_root_and_core_fields():
    root = parse(build_tvshow_nfo(SHOW))

    assert root.tag == "tvshow"
    assert root.findtext("title") == "绝命毒师"
    assert root.findtext("originaltitle") == "Breaking Bad"
    assert root.findtext("year") == "2008"
    assert root.findtext("rating") == "8.9"
    assert root.findtext("premiered") == "2008-01-20"
    assert root.findtext("status") == "Ended"


def test_tvshow_emits_sorttitle_from_name():
    # sorttitle 是给按标题排序的刮削器用的, 取 name 而不是 original_name ——
    # 这条断言把两者的区分钉住（SHOW 的 name 与 original_name 不同）。
    root = parse(build_tvshow_nfo(SHOW))
    assert root.findtext("sorttitle") == "绝命毒师"


def test_tvshow_emits_uniqueid_and_tmdbid():
    # spec §8.2：缺 <uniqueid type="tmdb"> 时 Emby 会重新在线刮削，NFO 形同白写
    root = parse(build_tvshow_nfo(SHOW))

    uniqueid = root.find("uniqueid")
    assert uniqueid is not None
    assert uniqueid.get("type") == "tmdb"
    assert uniqueid.get("default") == "true"
    assert uniqueid.text == "1396"
    assert root.findtext("tmdbid") == "1396"


def test_tvshow_emits_one_genre_tag_per_genre():
    root = parse(build_tvshow_nfo(SHOW))
    assert [g.text for g in root.findall("genre")] == ["剧情", "犯罪"]


def test_tvshow_omits_missing_fields_instead_of_empty_tags():
    # Review Focus 4 的前置：空标签会让部分刮削器把「简介为空」当真值而覆盖
    minimal = TmdbShow(tv_id=1, name="无简介剧")
    root = parse(build_tvshow_nfo(minimal))

    assert root.find("plot") is None
    assert root.find("rating") is None
    assert root.find("votes") is None
    assert root.find("genre") is None
    assert root.find("premiered") is None
    assert root.findtext("title") == "无简介剧"


def test_whitespace_only_value_is_omitted():
    # 纯空白与空串同样危险: 刮削器会把「只有空白的字段」当成「该字段为空」的真值,
    # 从而覆盖媒体库里已有的正确数据。_text 的 .strip() 就是为此,
    # 去掉它本套测试会全绿 —— 这条补上那个洞。
    show = TmdbShow(tv_id=4, name="剧", overview="   ", status="\t\n")
    root = parse(build_tvshow_nfo(show))
    assert root.find("plot") is None
    assert root.find("status") is None
    assert root.findtext("title") == "剧"   # 非空白的照常写出


def test_tvshow_escapes_ampersand_and_angle_brackets():
    # Review Focus 1：「Tom & Jerry」这类剧名在真实媒体库里很常见。
    # 字符串拼接会产出非法 XML —— 连自己都解析不了。
    tricky = TmdbShow(tv_id=2, name="Tom & Jerry", overview="a < b > c")
    root = parse(build_tvshow_nfo(tricky))

    assert root.findtext("title") == "Tom & Jerry"
    assert root.findtext("plot") == "a < b > c"

    raw = build_tvshow_nfo(tricky)
    assert "&amp;" in raw
    assert "&lt;" in raw


def test_tvshow_starts_with_xml_declaration():
    assert build_tvshow_nfo(SHOW).startswith(XML_DECLARATION)


def test_tvshow_is_indented():
    assert "\n  <title>" in build_tvshow_nfo(SHOW)


def test_tvshow_zero_votes_is_kept():
    # 0 是合法值, 不能用 `if value` 判断 —— 那会把 0 当成缺失
    show = TmdbShow(tv_id=3, name="剧", votes=0)
    assert parse(build_tvshow_nfo(show)).findtext("votes") == "0"


# --- season ---

def test_season_core_fields():
    season = TmdbSeason(season_number=2, name="第 2 季", overview="s2",
                        air_date="2009-03-08", tmdb_id=3575)
    root = parse(build_season_nfo(season))

    assert root.tag == "season"
    assert root.findtext("title") == "第 2 季"
    assert root.findtext("seasonnumber") == "2"
    assert root.findtext("plot") == "s2"
    assert root.findtext("premiered") == "2009-03-08"
    assert root.find("uniqueid").text == "3575"


def test_season_without_tmdb_id_omits_uniqueid():
    root = parse(build_season_nfo(TmdbSeason(season_number=1, name="第 1 季")))
    assert root.find("uniqueid") is None


def test_season_number_zero_is_kept():
    # TMDB 用 season 0 表示特别篇。0 是合法值。
    root = parse(build_season_nfo(TmdbSeason(season_number=0, name="特别篇")))
    assert root.findtext("seasonnumber") == "0"


# --- episode ---

def test_episode_core_fields():
    episode = TmdbEpisode(episode_number=5, name="Breakage", overview="e5",
                          air_date="2009-04-05", rating=8.7, tmdb_id=62085)
    root = parse(build_episode_nfo(episode, season_number=2, show_title="绝命毒师"))

    assert root.tag == "episodedetails"
    assert root.findtext("title") == "Breakage"
    assert root.findtext("showtitle") == "绝命毒师"
    assert root.findtext("season") == "2"
    assert root.findtext("episode") == "5"
    assert root.findtext("plot") == "e5"
    assert root.findtext("aired") == "2009-04-05"
    assert root.findtext("rating") == "8.7"
    assert root.find("uniqueid").text == "62085"


def test_episode_omits_missing_overview():
    root = parse(build_episode_nfo(TmdbEpisode(episode_number=1, name="试播集"),
                                   season_number=1, show_title="剧"))
    assert root.find("plot") is None
    assert root.findtext("title") == "试播集"


def test_episode_escapes_titles():
    episode = TmdbEpisode(episode_number=1, name="Rock & Roll <Live>")
    root = parse(build_episode_nfo(episode, season_number=1, show_title="A & B"))
    assert root.findtext("title") == "Rock & Roll <Live>"
    assert root.findtext("showtitle") == "A & B"


def test_episode_number_zero_is_kept():
    root = parse(build_episode_nfo(TmdbEpisode(episode_number=0, name="序"),
                                   season_number=1, show_title="剧"))
    assert root.findtext("episode") == "0"

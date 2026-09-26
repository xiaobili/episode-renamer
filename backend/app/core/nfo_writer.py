from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from ..models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow


XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def _text(parent: ET.Element, tag: str, value) -> None:
    """写一个文本子标签。值为 None 或空白时**整个标签省略**。

    空标签（<plot/>）会被部分刮削器当成「该字段为空」的真值, 从而覆盖掉
    媒体库里已有的正确数据 —— 省略比写空安全。
    """
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    ET.SubElement(parent, tag).text = text


def _uniqueid(parent: ET.Element, tmdb_id: Optional[int]) -> None:
    """<uniqueid type="tmdb" default="true"> 是 Emby / Jellyfin 锁定条目的锚点。

    缺了它, 媒体服务器会重新走一遍在线刮削, 这次生成的 NFO 等于白写。
    """
    if tmdb_id is None:
        return
    node = ET.SubElement(parent, "uniqueid", {"type": "tmdb", "default": "true"})
    node.text = str(tmdb_id)


def _serialize(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return f"{XML_DECLARATION}\n{ET.tostring(root, encoding='unicode')}\n"


def build_tvshow_nfo(show: TmdbShow) -> str:
    root = ET.Element("tvshow")
    _text(root, "title", show.name)
    _text(root, "originaltitle", show.original_name)
    _text(root, "sorttitle", show.name)
    _text(root, "year", show.year)
    _text(root, "plot", show.overview)
    _text(root, "rating", show.rating)
    _text(root, "votes", show.votes)
    for genre in show.genres:
        _text(root, "genre", genre)
    _text(root, "premiered", show.premiered)
    _text(root, "status", show.status)
    _uniqueid(root, show.tv_id)
    _text(root, "tmdbid", show.tv_id)
    return _serialize(root)


def build_season_nfo(season: TmdbSeason) -> str:
    root = ET.Element("season")
    _text(root, "title", season.name)
    _text(root, "seasonnumber", season.season_number)
    _text(root, "plot", season.overview)
    _text(root, "premiered", season.air_date)
    _uniqueid(root, season.tmdb_id)
    return _serialize(root)


def build_episode_nfo(episode: TmdbEpisode, season_number: int, show_title: str) -> str:
    root = ET.Element("episodedetails")
    _text(root, "title", episode.name)
    _text(root, "showtitle", show_title)
    _text(root, "season", season_number)
    _text(root, "episode", episode.episode_number)
    _text(root, "plot", episode.overview)
    _text(root, "aired", episode.air_date)
    _text(root, "rating", episode.rating)
    _uniqueid(root, episode.tmdb_id)
    return _serialize(root)

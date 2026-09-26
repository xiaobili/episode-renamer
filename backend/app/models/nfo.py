from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .tmdb import TmdbEpisode, TmdbSeason, TmdbShow


@dataclass(frozen=True)
class NfoOptions:
    """NFO 生成选项, 由请求体构造。"""

    enabled: bool = False
    overwrite: bool = False


@dataclass
class NfoEntry:
    """一个待写 NFO 的视频。

    new_path 是**重命名之后**的路径 —— 每集 NFO 靠与视频同名配对识别,
    用原文件名推导落点会让 NFO 与视频对不上。
    """

    file_id: str
    new_path: str
    show_name: str
    season: Optional[int] = None
    episode: Optional[int] = None
    show: Optional[TmdbShow] = None
    season_data: Optional[TmdbSeason] = None
    episode_data: Optional[TmdbEpisode] = None

    @property
    def has_metadata(self) -> bool:
        """TMDB 未匹配时没有 episode_data —— 此时不写 NFO。

        写一个没有标题与 <uniqueid> 的残缺 NFO 比不写更糟: 媒体服务器会拿它
        覆盖掉正确的既有数据。
        """
        return self.show is not None and self.episode_data is not None


@dataclass
class NfoDecision:
    """一个文件的写入决策。content 为 None 表示不写, reason 说明原因。"""

    file_id: str
    kind: str          # tvshow | season | episode
    path: str
    content: Optional[str] = None
    reason: str = ""

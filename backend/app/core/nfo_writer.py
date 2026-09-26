from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from ..models.nfo import NfoDecision, NfoEntry, NfoOptions
from ..models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow
from .parser import _SEASON_DIR_PATTERNS


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


def episode_nfo_path(video_path: str) -> str:
    """每集 NFO 的落点: 与视频同名同目录, 扩展名换成 .nfo。

    Emby / Jellyfin / Kodi 都是靠**文件名配对**识别每集 NFO 的,
    不读 XML 内容来判断它属于哪一集。所以这里必须与视频严格同名。
    """
    base, _extension = os.path.splitext(video_path)
    return base + ".nfo"


def common_parent(paths: list[str]) -> str:
    """一组路径的公共父目录。

    用公共父而不是「第一个文件的所在目录」: 视频可能分处 Season 02 / Season 03
    两个子目录, 此时剧集根应上溯一层。
    """
    if not paths:
        return ""
    directories = [os.path.dirname(p) for p in paths]
    if len(directories) == 1:
        return directories[0]
    return os.path.commonpath(directories)


def _show_root(paths: list[str]) -> str:
    """剧集根 = 公共父目录, 但**季文件夹按构造不是剧集根 —— 命中季目录时再上溯一层**。

    为什么非要这一步: Emby / Jellyfin 只在**剧集根**找 `tvshow.nfo`, 写进
    `Season 02/` 等于没写。单季布局（该剧只有一个季文件夹, 或用户只勾选了一季）
    下公共父目录恰好就是那个季文件夹本身; 多季布局（`Season 02/` + `Season 03/`）
    才会自然上溯到剧名目录 —— 所以这条缺口只在单季时暴露。

    这一层不是「多余的防御」: spec §9.3 的「剧集根 = 该剧所有选中视频新路径的公共
    父目录」只举了多季的例子（`Season 02` + `Season 03`、`S01` + `S02`）, 单季布局
    是它没覆盖的缺口, 审查裁定后在此补齐。删掉它, 单季布局的 `tvshow.nfo` 又会
    落回季目录。

    季目录判定复用 `parser._SEASON_DIR_PATTERNS`（`local_renamer` 用的是同一套）,
    不再新写一套正则。**只影响剧集根**: `season.nfo` 的落点仍是该季视频的公共父
    目录（那本来就该是季目录）。
    """
    root = common_parent(paths)
    if not root:
        return root
    if not any(p.match(os.path.basename(root.rstrip(os.sep))) for p in _SEASON_DIR_PATTERNS):
        return root

    parent = os.path.dirname(root.rstrip(os.sep))
    # 上溯到空串或文件系统根时保持原样: 把 tvshow.nfo 写到 / 下比不写更糟,
    # 且路径形状（绝对/相对）必须与入参保持一致 —— common_parent 不吃混用。
    if not parent or os.path.dirname(parent) == parent:
        return root
    return parent


def _folder_belongs_to_single_show(root: str, show_name: str, all_entries: list[NfoEntry]) -> bool:
    """公共父目录（及其下任意层级）不得混有别的剧。

    不满足时说明这是「多部剧混放」的目录（如 /media/未分类/）。把 tvshow.nfo
    写进去会让 Emby 把整个目录识别成一部剧 —— 不可逆的数据污染。

    **判定范围是「root 及其子树」, 不只是「恰好等于 root 的那个目录」**：
    非对称布局（A 剧的文件直接躺在 root 下, B 剧的在 root/B/S01/）下, 只查同目录
    会把 tvshow.nfo 写进 root —— 那正是本设计要防的那件事。反过来, 判宽了最多是
    某个古怪布局下少写一个剧集级 NFO: 预览的 NFO 列会显示「仅每集 NFO」,
    可见而非静默, 与不可逆的媒体库污染不是一个量级。**拒绝是安全方向。**

    合法的分剧布局不会被误伤: 各剧各占 /media/ShowA/、/media/ShowB/ 时互不嵌套;
    同一部剧的文件分处 root/ 与 root/S01/ 时 show_name 相同, 不触发。
    """
    root_prefix = root.rstrip(os.sep) + os.sep
    for other in all_entries:
        if other.show_name == show_name:
            continue
        other_dir = os.path.dirname(other.new_path)
        if other_dir == root or other_dir.startswith(root_prefix):
            return False
    return True


def build_nfo_decisions(entries: list[NfoEntry], options: NfoOptions) -> list[NfoDecision]:
    """为每条 entry 算出「写什么、写哪里」, 以及不写时的原因。

    纯函数, 不碰文件系统 —— 库根污染的全部防护都集中在这里, 因此必须能被
    穷举测试。真正写盘的只有 write_nfo_files（Task 3）。

    **顺序契约**: 返回值先是每集决策（按 show_name, season, episode, new_path 排序）,
    然后是剧集级、再是季级（分别按剧名 / (剧名, 季号) 排序）。下游的预览与测试
    依赖这个顺序, 不要改成「每部剧的剧集级与季级相邻」那种交错顺序。

    剧集级/季级决策每项只发一条, 它的 file_id 取组内按上述键排序的**第一条**
    （即 group[0] / season_group[0], 分组用的是同一套排序, 与入参顺序无关）。
    """
    if not options.enabled or not entries:
        return []

    # 三桶分离收集, 最后按「每集 → 剧集级 → 季级」拼接返回, 以兑现上面的顺序契约。
    episode_decisions: list[NfoDecision] = []
    tvshow_decisions: list[NfoDecision] = []
    season_decisions: list[NfoDecision] = []

    # --- 每集 NFO：与视频一一对应, 按路径排序保证确定性 ---
    ordered = sorted(entries, key=lambda e: (e.show_name, e.season or 0, e.episode or 0, e.new_path))
    for item in ordered:
        path = episode_nfo_path(item.new_path)
        if not item.has_metadata:
            episode_decisions.append(NfoDecision(
                file_id=item.file_id, kind="episode", path=path, content=None,
                reason="TMDB 未匹配, 不写残缺 NFO",
            ))
            continue
        episode_decisions.append(NfoDecision(
            file_id=item.file_id, kind="episode", path=path,
            content=build_episode_nfo(item.episode_data, item.season, item.show.name),
        ))

    # --- 剧集级与季级：按剧分组 ---
    # 分组时沿用已排好序的 ordered: 剧集级/季级决策只发一条, 它挂在哪个 file_id 上
    # （预览表的哪一行）不能随入参顺序变化。按 entries 的原始顺序分组会让
    # group[0] / season_group[0] 随输入顺序漂移 —— 路径虽然不变, 归属会变。
    by_show: dict[str, list[NfoEntry]] = {}
    for item in ordered:
        by_show.setdefault(item.show_name, []).append(item)

    for show_name in sorted(by_show):
        group = by_show[show_name]
        # 用**上溯后**的剧集根: 混放校验判定的是「真正的剧集根及其子树」,
        # 拿季目录去查会漏掉同剧根下的别的剧（startswith 前缀检查仍能覆盖子树）。
        show_root = _show_root([e.new_path for e in group])

        if not _folder_belongs_to_single_show(show_root, show_name, entries):
            for item in group:
                tvshow_decisions.append(NfoDecision(
                    file_id=item.file_id, kind="tvshow",
                    path=os.path.join(show_root, "tvshow.nfo"), content=None,
                    reason=f"{show_root} 下有多部剧混放, 不写剧集级 NFO",
                ))
                if item.season is None:
                    continue
                season_root = common_parent([
                    e.new_path for e in group if e.season == item.season
                ])
                season_decisions.append(NfoDecision(
                    file_id=item.file_id, kind="season",
                    path=os.path.join(season_root, "season.nfo"), content=None,
                    reason=f"{show_root} 下有多部剧混放, 不写剧集级 NFO",
                ))
            continue

        show_data = next((e.show for e in group if e.show is not None), None)
        if show_data is None:
            tvshow_decisions.append(NfoDecision(
                file_id=group[0].file_id, kind="tvshow",
                path=os.path.join(show_root, "tvshow.nfo"), content=None,
                reason="TMDB 未匹配, 不写残缺 NFO",
            ))
        else:
            tvshow_decisions.append(NfoDecision(
                file_id=group[0].file_id, kind="tvshow",
                path=os.path.join(show_root, "tvshow.nfo"),
                content=build_tvshow_nfo(show_data),
            ))

        seasons: dict[int, list[NfoEntry]] = {}
        for item in group:
            if item.season is not None:
                seasons.setdefault(item.season, []).append(item)

        for season_number in sorted(seasons):
            season_group = seasons[season_number]
            season_root = common_parent([e.new_path for e in season_group])
            season_data = next(
                (e.season_data for e in season_group if e.season_data is not None), None,
            )
            if season_data is None:
                season_decisions.append(NfoDecision(
                    file_id=season_group[0].file_id, kind="season",
                    path=os.path.join(season_root, "season.nfo"), content=None,
                    reason="TMDB 未匹配, 不写残缺 NFO",
                ))
            else:
                season_decisions.append(NfoDecision(
                    file_id=season_group[0].file_id, kind="season",
                    path=os.path.join(season_root, "season.nfo"),
                    content=build_season_nfo(season_data),
                ))

    return episode_decisions + tvshow_decisions + season_decisions


def write_nfo_files(
    decisions: list[NfoDecision],
    overwrite: bool = False,
) -> tuple[list[str], list[tuple[str, str]]]:
    """把决策落盘。返回 (写入的路径, [(跳过的路径, 原因)])。

    这是本模块唯一的副作用。刻意做得薄: 决策已被 build_nfo_decisions 全部
    算好, 这里只负责 mkdir / write / 报错。
    """
    written: list[str] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()

    for decision in decisions:
        if decision.content is None:
            skipped.append((decision.path, decision.reason or "无内容"))
            continue

        # 多剧混放分支会为组内每个条目生成同路径的决策, 这里去重
        if decision.path in seen:
            continue
        seen.add(decision.path)

        target = Path(decision.path)
        if target.exists() and not overwrite:
            skipped.append((decision.path, "已存在"))
            continue

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(decision.content, encoding="utf-8")
            written.append(decision.path)
        except OSError as exc:
            # 写 NFO 失败不能让整批重命名崩掉 —— 重命名那个时候已经成功了
            skipped.append((decision.path, f"写入失败: {exc}"))

    return written, skipped

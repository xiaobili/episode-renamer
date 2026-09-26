# NFO 生成 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 随重命名一并生成 Emby / Jellyfin / Kodi 规范的 `tvshow.nfo` + `season.nfo` + 每集 `SxxExx.nfo`，让刮削不再依赖在线查询。

**Architecture:** 全部决策逻辑做成纯函数（`build_nfo_decisions`），只把「写盘」这一个不可逆动作隔离在一个薄函数里（`write_nfo_files`）。剧集根与季目录都由「视频新路径的公共父目录」机械推导，配一道 show_name 一致性校验拦下多剧混放的目录。XML 用 `ElementTree` 生成，杜绝剧名含 `&` / `<` 时产出非法文件。

**Tech Stack:** Python 3.9+ / FastAPI / Pydantic 2 / pytest；Vue 3 + Pinia

**Spec:** `docs/superpowers/specs/2026-09-26-tmdb-metadata-and-nfo-design.md`（§8–§9、§10.2、§11、§12.3–§12.4、§13 的 `test_nfo_writer` / `test_nfo_plan` / `test_rename_nfo_route`）

**本条计划是两期中的第二期，强依赖第一期。** 第一期（TMDB 元数据集成）在 `docs/superpowers/plans/2026-09-26-tmdb-metadata.md`。**开工前先核实第一期已合入**：`backend/app/core/tmdb_resolver.py` 存在且导出 `EpisodeMatch`。若不存在，本计划必须整体搁置 —— 这正是本项目 `plans/2026-09-25-frontend-3-features.md` 的 Task 8 曾经踩过的坑（前置条件写着「后端未合入时必须跳过」，两头都空，于是设置页 5 项成了死设置）。

## Global Constraints

- **`season.nfo` 必须落在季目录，不是剧集根**（spec §9.1）。Emby / Jellyfin 只在季目录下查找 `season.nfo`，放错位置会静默失效。
- **每集 NFO 靠文件名与视频配对识别**（spec §8.2）。`绝命毒师 - S02E05.nfo` 必须与 `绝命毒师 - S02E05.mkv` 同名同目录 —— 因此落点由**视频的新路径**推导，不能用原文件名。
- **`<uniqueid type="tmdb">` 必须存在**（spec §8.2）。缺失时媒体服务器会重新走在线刮削，NFO 形同白写。
- **XML 用 `ElementTree` 生成，禁止字符串拼接**（spec §8.3）。剧名含 `&`、`<`、`>` 时拼接必然产出非法文件。
- **字段缺失时省略标签**，不写空标签 —— 空 `<plot/>` 会被部分刮削器当作「简介为空」而覆盖。
- **`tvshow.nfo` 与 `season.nfo` 受同一道 show_name 一致性校验把关**（spec §9.3）。校验不过则两者都不写：该目录根本不是一部剧的目录。
- **「覆盖已存在」默认关闭**（spec §9.4）。
- **OpenList 源不写 NFO**（spec §2）。TMDB 查询与 `{title}` 在 OpenList 下照常生效，仅 NFO 缺席。
- **dry-run 绝不落盘**，但仍要列出将写入的清单与跳过原因。
- **不新增运行时依赖**。测试用标准库 `tempfile` / `pathlib` 的 `tmp_path` fixture。
- 不得改动 API 路径、方法，或既有响应字段的语义。新字段一律追加。

## Review Focus

以下是 spec 隐含、但容易被实现者漏掉、且最可能咬到真实用户的输入。每条对应的测试已挂在拥有该代码的任务里：

1. **剧名含 `&` / `<` / `>`** —— 「Tom & Jerry」「进击的巨人 <最终季>」这类剧名在真实媒体库里很常见。期望：NFO 是合法 XML（`&amp;` / `&lt;`），解析器能读回来；用字符串拼接会产出连自己都解析不了的文件。
2. **多部剧混放在同一目录（如 `/media/未分类/`）** —— 期望：拒绝写 `tvshow.nfo` 与 `season.nfo`，只写每集 NFO，并在预览里标注原因。写进去会让 Emby 把整个目录识别成一部剧，**不可逆**。
3. **目标 NFO 已存在且「覆盖」开关关闭** —— 期望：跳过、不修改既有文件、在结果里报告跳过原因；重命名本身照常完成。
4. **TMDB 未匹配（`disabled` / `episode_not_found` / `unavailable`）** —— 期望：**不产生任何 NFO**，也不产生半截文件；重命名照常完成。写一个没有标题与 `<uniqueid>` 的残缺 NFO 比不写更糟。
5. **未启用「创建季文件夹」** —— 期望：`tvshow.nfo` 与 `season.nfo` 落在视频同目录（此时该目录既是剧集根也是季目录），`season.nfo` **仍然要写**，而不是因为「没有季文件夹」就跳过。

## File Structure

| 文件 | 职责 | 本次改动 |
|---|---|---|
| `backend/app/models/nfo.py` | NFO 选项、条目、决策的数据形状 | 新建 |
| `backend/app/core/nfo_writer.py` | XML 构建 + 路径推导 + 决策（纯函数）+ 写盘（唯一副作用） | 新建 |
| `backend/app/models/file.py` | 重命名结果模型 | `RenameResult` 加 `nfo_path`；`BatchRenameResult` 加 `nfo_written` / `nfo_skipped` |
| `backend/app/models/api.py` | 请求模型 | 两个 Request 各加 `generate_nfo` / `nfo_overwrite` |
| `backend/app/core/local_renamer.py` | 本地重命名 | `batch_rename` 接受 NFO 选项与匹配数据，重命名后写 NFO |
| `backend/app/api/renamer.py` | 三个重命名路由 | `_with_tmdb_titles` 暴露 matches；预览返回 NFO 落点；OpenList 守卫 |
| `backend/tests/test_nfo_writer.py` | XML 构建 | 新建 |
| `backend/tests/test_nfo_plan.py` | 路径推导与剧集根判定 | 新建 |
| `backend/tests/test_rename_nfo_route.py` | 路由集成 | 新建 |
| `frontend/src/stores/workspace.js` | 工作区状态 | `generateNfo` / `nfoOverwrite`、下发、预览行 `nfo` 字段 |
| `frontend/src/components/TemplateConfig.vue` | 模板与选项面板 | NFO 勾选（OpenList 下置灰） |
| `frontend/src/components/FileTable.vue` | 预览表 | 新增「NFO」列 |

---

### Task 1: NFO 数据形状与 XML 构建

先做纯函数：三种 XML 的构建。它们是本计划里最容易被测穷尽、也最容易出静默错误（非法 XML、空标签）的部分。

**Files:**
- Create: `backend/app/models/nfo.py`
- Create: `backend/app/core/nfo_writer.py`（先只写 XML 构建部分）
- Create: `backend/tests/test_nfo_writer.py`

**Interfaces:**
- Consumes: `TmdbShow` / `TmdbSeason` / `TmdbEpisode`（第一期 Task 1）
- Produces:
  - `app.models.nfo.NfoOptions(enabled: bool = False, overwrite: bool = False)` —— frozen dataclass
  - `app.models.nfo.NfoEntry` —— dataclass，字段 `file_id: str`、`new_path: str`、`show_name: str`、`season: Optional[int]`、`episode: Optional[int]`、`show: Optional[TmdbShow]`、`season_data: Optional[TmdbSeason]`、`episode_data: Optional[TmdbEpisode]`，属性 `has_metadata -> bool`
  - `app.models.nfo.NfoDecision` —— dataclass，字段 `file_id: str`、`kind: str`、`path: str`、`content: Optional[str]`、`reason: str`
  - `app.core.nfo_writer.XML_DECLARATION` —— str 常量
  - `app.core.nfo_writer.build_tvshow_nfo(show: TmdbShow) -> str`
  - `app.core.nfo_writer.build_season_nfo(season: TmdbSeason) -> str`
  - `app.core.nfo_writer.build_episode_nfo(episode: TmdbEpisode, season_number: int, show_title: str) -> str`

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_nfo_writer.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_nfo_writer.py -v
```

预期：全部 FAIL，报 `ModuleNotFoundError: No module named 'app.core.nfo_writer'`

- [ ] **Step 3: 建立 NFO 数据形状**

创建 `backend/app/models/nfo.py`：

```python
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
```

- [ ] **Step 4: 实现 XML 构建**

创建 `backend/app/core/nfo_writer.py`：

```python
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from ..models.nfo import NfoDecision, NfoEntry, NfoOptions
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
```

`os`、`Path`、`NfoDecision`、`NfoEntry`、`NfoOptions` 的 import 本任务尚未用到，**先不要写** —— Task 2 与 Task 3 会分别加上。

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_nfo_writer.py -v
```

预期：15 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/models/nfo.py backend/app/core/nfo_writer.py backend/tests/test_nfo_writer.py
git commit -m "feat(backend): NFO XML 构建（ElementTree 生成, 缺字段省略标签, 恒写 uniqueid）"
```

---

### Task 2: 路径推导、剧集根判定与写入决策

本任务实现 spec §9 的全部防护：公共父目录推导、多剧混放拒绝、每集 NFO 与视频同名配对。

**Files:**
- Modify: `backend/app/core/nfo_writer.py`（追加路径与决策部分）
- Create: `backend/tests/test_nfo_plan.py`

**Interfaces:**
- Consumes: `NfoEntry` / `NfoDecision` / `NfoOptions`（Task 1）；三个 XML 构建函数（Task 1）
- Produces:
  - `app.core.nfo_writer.episode_nfo_path(video_path: str) -> str`
  - `app.core.nfo_writer.common_parent(paths: list[str]) -> str`
  - `app.core.nfo_writer.build_nfo_decisions(entries: list[NfoEntry], options: NfoOptions) -> list[NfoDecision]`
  - **顺序契约**：`build_nfo_decisions` 返回的列表中，每集决策按 `(show_name, season, episode, new_path)` 排序，其后是剧集级（`tvshow`）、再是季级（`season`），各自按剧名 / `(剧名, 季号)` 排序。下游测试依赖此顺序。

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_nfo_plan.py`：

```python
from app.core.nfo_writer import (
    build_nfo_decisions,
    common_parent,
    episode_nfo_path,
)
from app.models.nfo import NfoEntry, NfoOptions
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow


def show(tv_id=1396, name="绝命毒师"):
    return TmdbShow(tv_id=tv_id, name=name, original_name="Breaking Bad", year=2008)


def season(number=2):
    return TmdbSeason(season_number=number, name=f"第 {number} 季", tmdb_id=3575)


def episode(number=5):
    return TmdbEpisode(episode_number=number, name="Breakage", tmdb_id=62085)


def entry(new_path, show_name="绝命毒师", season_no=2, episode_no=5, with_meta=True):
    return NfoEntry(
        file_id=new_path,
        new_path=new_path,
        show_name=show_name,
        season=season_no,
        episode=episode_no,
        show=show() if with_meta else None,
        season_data=season(season_no) if with_meta and season_no else None,
        episode_data=episode(episode_no) if with_meta and episode_no else None,
    )


def by_kind(decisions, kind):
    return [d for d in decisions if d.kind == kind]


OPTIONS = NfoOptions(enabled=True, overwrite=False)


# --- 路径工具 ---

def test_episode_nfo_path_swaps_extension():
    assert episode_nfo_path("/media/剧/Season 02/剧 - S02E05.mkv") == "/media/剧/Season 02/剧 - S02E05.nfo"


def test_episode_nfo_path_handles_dots_in_name():
    assert episode_nfo_path("/m/Show.S02E05.1080p.mkv") == "/m/Show.S02E05.1080p.nfo"


def test_common_parent_of_sibling_dirs():
    assert common_parent(["/media/剧/Season 02/a.mkv", "/media/剧/Season 02/b.mkv"]) == "/media/剧/Season 02"


def test_common_parent_goes_up_for_split_seasons():
    assert common_parent(["/media/剧/S01/a.mkv", "/media/剧/S02/b.mkv"]) == "/media/剧"


def test_common_parent_of_single_path():
    assert common_parent(["/media/剧/S01/a.mkv"]) == "/media/剧/S01"


# --- 关闭时不产生任何决策 ---

def test_disabled_produces_nothing():
    assert build_nfo_decisions([entry("/m/剧/a.mkv")], NfoOptions(enabled=False)) == []


def test_empty_entries_produce_nothing():
    assert build_nfo_decisions([], OPTIONS) == []


# --- 每集 NFO ---

def test_episode_nfo_is_sibling_of_video():
    decisions = by_kind(build_nfo_decisions([entry("/m/绝命毒师/绝命毒师 - S02E05.mkv")], OPTIONS), "episode")
    assert len(decisions) == 1
    assert decisions[0].path == "/m/绝命毒师/绝命毒师 - S02E05.nfo"
    assert decisions[0].content is not None
    assert "<title>Breakage</title>" in decisions[0].content


def test_episode_nfo_skipped_without_metadata():
    # Review Focus 4：TMDB 未匹配时不写 NFO, 但也要给出一条带原因的「不写」决策,
    # 否则预览表那一列会是空白, 用户不知道是没查还是查不到
    decisions = by_kind(
        build_nfo_decisions([entry("/m/绝命毒师/a.mkv", with_meta=False)], OPTIONS), "episode")
    assert len(decisions) == 1
    assert decisions[0].content is None
    assert decisions[0].reason


def test_every_entry_gets_exactly_one_episode_decision():
    entries = [entry(f"/m/剧/S02/E{n:02d}.mkv", episode_no=n) for n in (5, 6, 7)]
    decisions = by_kind(build_nfo_decisions(entries, OPTIONS), "episode")
    assert len(decisions) == 3


# --- 剧集根与季目录 ---

def test_tvshow_goes_to_show_root_and_season_to_season_folder():
    # spec §9.1：season.nfo 落在季目录（Emby 只在季目录下找它）
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/Season 02/绝命毒师 - S02E05.mkv", episode_no=5),
        entry("/m/绝命毒师/Season 03/绝命毒师 - S03E01.mkv", season_no=3, episode_no=1),
    ], OPTIONS)

    tvshow = by_kind(decisions, "tvshow")
    assert len(tvshow) == 1
    assert tvshow[0].path == "/m/绝命毒师/tvshow.nfo"

    seasons = by_kind(decisions, "season")
    assert [s.path for s in seasons] == [
        "/m/绝命毒师/Season 02/season.nfo",
        "/m/绝命毒师/Season 03/season.nfo",
    ]


def test_season_nfo_still_written_without_season_folders():
    # Review Focus 5：未开季文件夹时, 视频所在目录既是剧集根也是季目录,
    # season.nfo 仍要写, 而不是因为「没有季文件夹」就跳过
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/绝命毒师 - S02E05.mkv", episode_no=5),
        entry("/m/绝命毒师/绝命毒师 - S02E06.mkv", episode_no=6),
    ], OPTIONS)

    assert [d.path for d in by_kind(decisions, "tvshow")] == ["/m/绝命毒师/tvshow.nfo"]
    assert [d.path for d in by_kind(decisions, "season")] == ["/m/绝命毒师/season.nfo"]


def test_split_season_folders_put_tvshow_at_show_root():
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/S01/绝命毒师 - S01E01.mkv", season_no=1, episode_no=1),
        entry("/m/绝命毒师/S02/绝命毒师 - S02E01.mkv", season_no=2, episode_no=1),
    ], OPTIONS)

    assert [d.path for d in by_kind(decisions, "tvshow")] == ["/m/绝命毒师/tvshow.nfo"]
    assert [d.path for d in by_kind(decisions, "season")] == [
        "/m/绝命毒师/S01/season.nfo",
        "/m/绝命毒师/S02/season.nfo",
    ]


def test_two_shows_get_two_tvshow_files():
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/a.mkv", show_name="绝命毒师"),
        entry("/m/律师/b.mkv", show_name="绝命律师"),
    ], OPTIONS)

    assert [d.path for d in by_kind(decisions, "tvshow")] == [
        "/m/律师/tvshow.nfo", "/m/绝命毒师/tvshow.nfo",
    ]


def test_tvshow_written_only_once_per_show():
    entries = [entry(f"/m/绝命毒师/E{n:02d}.mkv", episode_no=n) for n in (1, 2, 3)]
    assert len(by_kind(build_nfo_decisions(entries, OPTIONS), "tvshow")) == 1


# --- Review Focus 2：多剧混放 ---

def test_mixed_shows_in_one_directory_are_refused():
    # /media/未分类/ 下同时有 A 剧与 B 剧。把 tvshow.nfo 写进去会让 Emby
    # 把整个目录当成一部剧 —— 不可逆。
    decisions = build_nfo_decisions([
        entry("/m/未分类/a.mkv", show_name="绝命毒师", show=show(1396, "绝命毒师")),
        entry("/m/未分类/b.mkv", show_name="绝命律师", show=show(2, "绝命律师")),
    ], OPTIONS)

    tvshow = by_kind(decisions, "tvshow")
    season_decisions = by_kind(decisions, "season")

    assert len(tvshow) == 2, "每部剧各有一条决策（内容是「不写」）"
    assert all(d.content is None for d in tvshow)
    assert all("多部剧" in d.reason for d in tvshow)

    assert all(d.content is None for d in season_decisions)
    assert all("多部剧" in d.reason for d in season_decisions)

    # 但每集 NFO 照常写 —— 它落在视频旁边, 与目录是否混放无关
    assert all(d.content is not None for d in by_kind(decisions, "episode"))


def test_mixed_shows_in_parent_do_not_block_subdirectory_shows():
    # 反向情形：两部剧各在自己的子目录里, 不能因为「父目录混放」而误拒
    decisions = build_nfo_decisions([
        entry("/m/未分类/绝命毒师/a.mkv", show_name="绝命毒师", show=show(1396, "绝命毒师")),
        entry("/m/未分类/绝命律师/b.mkv", show_name="绝命律师", show=show(2, "绝命律师")),
    ], OPTIONS)

    assert all(d.content is not None for d in by_kind(decisions, "tvshow"))
    assert [d.path for d in by_kind(decisions, "tvshow")] == [
        "/m/未分类/绝命律师/tvshow.nfo", "/m/未分类/绝命毒师/tvshow.nfo",
    ]


def test_same_show_in_one_directory_is_allowed():
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/a.mkv", episode_no=1),
        entry("/m/绝命毒师/b.mkv", episode_no=2),
    ], OPTIONS)
    assert all(d.content is not None for d in by_kind(decisions, "tvshow"))


# --- 无元数据时的剧集级文件 ---

def test_show_level_files_skipped_without_show_metadata():
    decisions = build_nfo_decisions([
        entry("/m/绝命毒师/a.mkv", with_meta=False),
    ], OPTIONS)

    assert all(d.content is None for d in by_kind(decisions, "tvshow"))
    assert all(d.content is None for d in by_kind(decisions, "season"))
    assert all(d.reason for d in by_kind(decisions, "tvshow"))


# --- 顺序契约 ---

def test_decisions_are_deterministic():
    entries = [
        entry("/m/剧B/E02.mkv", show_name="剧B", episode_no=2),
        entry("/m/剧A/E01.mkv", show_name="剧A", episode_no=1),
    ]
    decisions = build_nfo_decisions(entries, OPTIONS)
    assert [d.kind for d in decisions] == ["episode", "episode", "tvshow", "tvshow", "season", "season"]

    # 同一入参集合换个顺序, 结果必须逐项一致
    decisions_reversed = build_nfo_decisions(list(reversed(entries)), OPTIONS)
    assert [d.path for d in decisions] == [d.path for d in decisions_reversed]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_nfo_plan.py -v
```

预期：全部 FAIL，报 `ImportError: cannot import name 'build_nfo_decisions' from 'app.core.nfo_writer'`

- [ ] **Step 3: 实现路径推导与决策**

在 `backend/app/core/nfo_writer.py` 的 import 区补齐：

```python
import os

from ..models.nfo import NfoDecision, NfoEntry, NfoOptions
```

（`import os` 放在既有 `import xml.etree.ElementTree as ET` 之前，保持标准库分组在文件顶部。）

在文件末尾追加：

```python
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


def _folder_belongs_to_single_show(root: str, show_name: str, all_entries: list[NfoEntry]) -> bool:
    """公共父目录下, 本批次的所有视频必须同属一部剧。

    不满足时说明这是「多部剧混放」的目录（如 /media/未分类/）。把 tvshow.nfo
    写进去会让 Emby 把整个目录识别成一部剧 —— 不可逆的数据污染。
    """
    for other in all_entries:
        if os.path.dirname(other.new_path) == root and other.show_name != show_name:
            return False
    return True


def build_nfo_decisions(entries: list[NfoEntry], options: NfoOptions) -> list[NfoDecision]:
    """为每条 entry 算出「写什么、写哪里」, 以及不写时的原因。

    纯函数, 不碰文件系统 —— 库根污染的全部防护都集中在这里, 因此必须能被
    穷举测试。真正写盘的只有 write_nfo_files（Task 3）。
    """
    if not options.enabled or not entries:
        return []

    decisions: list[NfoDecision] = []

    # --- 每集 NFO：与视频一一对应, 按路径排序保证确定性 ---
    ordered = sorted(entries, key=lambda e: (e.show_name, e.season or 0, e.episode or 0, e.new_path))
    for item in ordered:
        path = episode_nfo_path(item.new_path)
        if not item.has_metadata:
            decisions.append(NfoDecision(
                file_id=item.file_id, kind="episode", path=path, content=None,
                reason="TMDB 未匹配, 不写残缺 NFO",
            ))
            continue
        decisions.append(NfoDecision(
            file_id=item.file_id, kind="episode", path=path,
            content=build_episode_nfo(item.episode_data, item.season, item.show.name),
        ))

    # --- 剧集级与季级：按剧分组 ---
    by_show: dict[str, list[NfoEntry]] = {}
    for item in entries:
        by_show.setdefault(item.show_name, []).append(item)

    for show_name in sorted(by_show):
        group = by_show[show_name]
        show_root = common_parent([e.new_path for e in group])

        if not _folder_belongs_to_single_show(show_root, show_name, entries):
            for item in group:
                decisions.append(NfoDecision(
                    file_id=item.file_id, kind="tvshow",
                    path=os.path.join(show_root, "tvshow.nfo"), content=None,
                    reason=f"{show_root} 下有多个剧目, 不写剧集级 NFO",
                ))
                if item.season is None:
                    continue
                season_root = common_parent([
                    e.new_path for e in group if e.season == item.season
                ])
                decisions.append(NfoDecision(
                    file_id=item.file_id, kind="season",
                    path=os.path.join(season_root, "season.nfo"), content=None,
                    reason=f"{show_root} 下有多个剧目, 不写剧集级 NFO",
                ))
            continue

        show_data = next((e.show for e in group if e.show is not None), None)
        if show_data is None:
            decisions.append(NfoDecision(
                file_id=group[0].file_id, kind="tvshow",
                path=os.path.join(show_root, "tvshow.nfo"), content=None,
                reason="TMDB 未匹配, 不写残缺 NFO",
            ))
        else:
            decisions.append(NfoDecision(
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
                decisions.append(NfoDecision(
                    file_id=season_group[0].file_id, kind="season",
                    path=os.path.join(season_root, "season.nfo"), content=None,
                    reason="TMDB 未匹配, 不写残缺 NFO",
                ))
            else:
                decisions.append(NfoDecision(
                    file_id=season_group[0].file_id, kind="season",
                    path=os.path.join(season_root, "season.nfo"),
                    content=build_season_nfo(season_data),
                ))

    return decisions
```

**注意多剧混放分支里的 `file_id`**：该分支为组内**每个**条目各生成一条 `tvshow` 决策（同一条路径会重复出现）。这是有意为之 —— 预览表按文件行展示，每个文件都要能看到「这部剧的剧集级 NFO 没写、原因是混放」。Task 3 的 `write_nfo_files` 靠路径去重，不会重复写入。

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_nfo_plan.py -v
```

预期：20 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/nfo_writer.py backend/tests/test_nfo_plan.py
git commit -m "feat(backend): NFO 路径推导与剧集根判定（公共父目录 + 多剧混放拒绝）"
```

---

### Task 3: 写盘与重命名集成

这是本计划唯一产生副作用的任务。写盘必须隔离得足够薄，好让「重命名失败但 NFO 写成功」这类半成品状态不至于发生。

**Files:**
- Modify: `backend/app/core/nfo_writer.py`（追加 `write_nfo_files`）
- Modify: `backend/app/models/file.py:61-82`（`RenameResult` / `BatchRenameResult`）
- Modify: `backend/app/models/api.py`（两个 Request）
- Modify: `backend/app/core/local_renamer.py:172-232`（`batch_rename`）
- Create: `backend/tests/test_nfo_write.py`

**Interfaces:**
- Consumes: `build_nfo_decisions`（Task 2）；`NfoOptions` / `NfoEntry`（Task 1）；`EpisodeMatch`（**第一期** Task 2）
- Produces:
  - `app.core.nfo_writer.write_nfo_files(decisions: list[NfoDecision], overwrite: bool = False) -> tuple[list[str], list[tuple[str, str]]]` —— 返回 `(写入路径, [(跳过路径, 原因)])`，按路径去重
  - `RenameResult.nfo_path: Optional[str]`
  - `BatchRenameResult.nfo_written: list[str]` / `nfo_skipped: list[dict]`
  - `RenamePreviewRequest.generate_nfo` / `nfo_overwrite`；`RenameExecuteRequest` 同
  - `batch_rename(..., nfo_options: Optional[NfoOptions] = None, nfo_matches: Optional[dict[str, EpisodeMatch]] = None)`

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_nfo_write.py`：

```python
import os

from app.core.nfo_writer import build_nfo_decisions, write_nfo_files
from app.models.nfo import NfoDecision, NfoEntry, NfoOptions
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow


def make_entry(new_path, show_name="绝命毒师", season_no=2, episode_no=5):
    return NfoEntry(
        file_id=new_path,
        new_path=new_path,
        show_name=show_name,
        season=season_no,
        episode=episode_no,
        show=TmdbShow(tv_id=1396, name=show_name, original_name="Breaking Bad", year=2008),
        season_data=TmdbSeason(season_number=season_no, name=f"第 {season_no} 季", tmdb_id=3575),
        episode_data=TmdbEpisode(episode_number=episode_no, name="Breakage", tmdb_id=62085),
    )


OPTIONS = NfoOptions(enabled=True, overwrite=False)


def test_writes_all_three_kinds(tmp_path):
    video = tmp_path / "绝命毒师" / "Season 02" / "绝命毒师 - S02E05.mkv"
    video.parent.mkdir(parents=True)

    decisions = build_nfo_decisions([make_entry(str(video))], OPTIONS)
    written, skipped = write_nfo_files(decisions)

    assert skipped == []
    assert sorted(written) == sorted([
        str(video.with_suffix(".nfo")),
        str(tmp_path / "绝命毒师" / "Season 02" / "season.nfo"),
        str(tmp_path / "绝命毒师" / "tvshow.nfo"),
    ])
    for path in written:
        assert os.path.isfile(path)


def test_creates_missing_directories(tmp_path):
    # 开了「创建季文件夹」时季目录由重命名创建; 但若重命名因冲突被跳过,
    # 目录可能不存在 —— 写 NFO 必须自己兜住
    video = tmp_path / "剧" / "Season 09" / "剧 - S09E01.mkv"
    decisions = build_nfo_decisions([make_entry(str(video), season_no=9, episode_no=1)], OPTIONS)

    written, _skipped = write_nfo_files(decisions)
    assert written
    assert os.path.isdir(str(tmp_path / "剧" / "Season 09"))


def test_existing_file_is_skipped_when_overwrite_is_off(tmp_path):
    # Review Focus 3：默认不覆盖既有 NFO
    target = tmp_path / "剧 - S02E05.nfo"
    target.write_text("既有内容", encoding="utf-8")

    decisions = [NfoDecision(file_id="f1", kind="episode", path=str(target), content="<新/>")]
    written, skipped = write_nfo_files(decisions, overwrite=False)

    assert written == []
    assert skipped == [(str(target), "已存在")]
    assert target.read_text(encoding="utf-8") == "既有内容"


def test_existing_file_is_overwritten_when_asked(tmp_path):
    target = tmp_path / "剧 - S02E05.nfo"
    target.write_text("既有内容", encoding="utf-8")

    decisions = [NfoDecision(file_id="f1", kind="episode", path=str(target), content="<新/>")]
    written, skipped = write_nfo_files(decisions, overwrite=True)

    assert written == [str(target)]
    assert skipped == []
    assert target.read_text(encoding="utf-8") == "<新/>"


def test_decisions_without_content_are_reported_as_skipped(tmp_path):
    decisions = [NfoDecision(file_id="f1", kind="episode",
                             path=str(tmp_path / "a.nfo"), content=None, reason="无 TMDB 数据")]
    written, skipped = write_nfo_files(decisions)

    assert written == []
    assert skipped == [(str(tmp_path / "a.nfo"), "无 TMDB 数据")]
    assert not (tmp_path / "a.nfo").exists()


def test_duplicate_paths_are_written_once(tmp_path):
    # 多剧混放分支会给组内每个条目各生成一条同路径的 tvshow 决策
    target = tmp_path / "tvshow.nfo"
    decisions = [
        NfoDecision(file_id="f1", kind="tvshow", path=str(target), content="<a/>"),
        NfoDecision(file_id="f2", kind="tvshow", path=str(target), content="<a/>"),
    ]
    written, skipped = write_nfo_files(decisions, overwrite=True)

    assert written == [str(target)]
    assert skipped == []


def test_written_content_is_utf8_with_chinese(tmp_path):
    target = tmp_path / "剧 - S02E05.nfo"
    decisions = [NfoDecision(file_id="f1", kind="episode", path=str(target),
                             content="<episodedetails><title>绝命毒师</title></episodedetails>")]
    write_nfo_files(decisions, overwrite=True)

    assert "绝命毒师" in target.read_text(encoding="utf-8")


def test_failures_are_reported_not_raised(tmp_path):
    # 写失败（如只读目标）不能让整批重命名崩掉 —— 重命名已经成功了
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)  # 只读目录
    try:
        decisions = [NfoDecision(file_id="f1", kind="episode",
                                 path=str(blocked / "a.nfo"), content="<x/>")]
        written, skipped = write_nfo_files(decisions, overwrite=True)

        # root 用户会绕过权限位, 因此两种结果都接受, 关键是「不抛异常」
        if written:
            assert skipped == []
        else:
            assert len(skipped) == 1
            assert "写入失败" in skipped[0][1]
    finally:
        blocked.chmod(0o700)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_nfo_write.py -v
```

预期：全部 FAIL，报 `ImportError: cannot import name 'write_nfo_files' from 'app.core.nfo_writer'`

- [ ] **Step 3: 实现写盘**

在 `backend/app/core/nfo_writer.py` 的 import 区加上 `from pathlib import Path`，并在文件末尾追加：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_nfo_write.py -v
```

预期：8 passed

- [ ] **Step 5: 扩展结果模型**

编辑 `backend/app/models/file.py`。

把 `RenameResult` 替换为：

```python
class RenameResult(BaseModel):
    id: str = ""
    original_path: str
    new_path: str
    original_filename: str = ""
    new_filename: str = ""
    success: bool = False
    error: Optional[str] = None
    status: str = "pending"
    # 该文件的每集 NFO 落点。剧集级（tvshow / season）不属于单个文件,
    # 汇总在 BatchRenameResult 上, 不在这里重复 N 遍。
    nfo_path: Optional[str] = None
```

把 `BatchRenameResult` 替换为：

```python
class BatchRenameResult(BaseModel):
    success: bool = False
    source: str = "local"
    executed: int = 0
    skipped: int = 0
    failed: int = 0
    total: int = 0
    conflicts: list[dict] = Field(default_factory=list)
    results: list[RenameResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    # NFO 汇总。dry_run 时这两项描述的是「将写入 / 将跳过」的计划, 不落盘。
    nfo_written: list[str] = Field(default_factory=list)
    nfo_skipped: list[dict] = Field(default_factory=list)
```

- [ ] **Step 6: 给请求模型加字段**

编辑 `backend/app/models/api.py`，在两个 Request 的 `tmdb_overrides` 之后各加：

```python
    generate_nfo: bool = False
    nfo_overwrite: bool = False
```

- [ ] **Step 7: 在 `batch_rename` 中集成**

编辑 `backend/app/core/local_renamer.py`。

把 import 区改为：

```python
from ..models.file import (
    FileInfo, RenamePlan, RenameResult, BatchRenameResult, OverrideInfo,
)
from ..models.nfo import NfoDecision, NfoEntry, NfoOptions
from ..config import settings
from .nfo_writer import build_nfo_decisions, write_nfo_files
from .parser import apply_override, parse_filename, _SEASON_DIR_PATTERNS
from .template import PadConfig, apply_template, apply_folder_template
from .utils import generate_id
```

把 `batch_rename` 的签名与函数体替换为：

```python
def batch_rename(
    files: list[FileInfo],
    template: str,
    folder_template: str = "",
    create_season_folder: bool = False,
    overrides: dict[str, dict] | None = None,
    dry_run: bool = False,
    conflict_strategy: str = "skip",
    pad: PadConfig | None = None,
    nfo_options: NfoOptions | None = None,
    nfo_matches: dict | None = None,
) -> BatchRenameResult:
    plans: list[RenamePlan] = []
    overrides = overrides or {}
    nfo_matches = nfo_matches or {}

    for f in files:
        ov = overrides.get(f.id)
        override = OverrideInfo(**ov) if ov else None
        plan = build_rename_plan(
            f, template, folder_template, create_season_folder, override, pad=pad
        )
        conflicts = check_conflict(plan, [])
        plan.conflicts = conflicts
        plans.append(plan)

    results: list[RenameResult] = []
    executed = skipped = failed = 0

    # NFO 条目用**重命名之后**的路径 —— 每集 NFO 靠与视频同名配对,
    # 用原路径推导会让 NFO 与视频对不上。
    nfo_decisions: list[NfoDecision] = []
    nfo_path_by_file: dict[str, str] = {}
    if nfo_options and nfo_options.enabled:
        nfo_decisions = build_nfo_decisions(
            [
                NfoEntry(
                    file_id=plan.file_id,
                    new_path=plan.new_path,
                    show_name=plan.parsed.show_name if plan.parsed else "",
                    season=plan.parsed.season if plan.parsed else None,
                    episode=plan.parsed.episode if plan.parsed else None,
                    # nfo_matches 里没有对应项时 .get() 返回 None,
                    # getattr(None, "show", None) 也是 None —— 三者同时为 None,
                    # NfoEntry.has_metadata 即为 False, 于是不写残缺 NFO。
                    show=getattr(nfo_matches.get(plan.file_id), "show", None),
                    season_data=getattr(nfo_matches.get(plan.file_id), "season", None),
                    episode_data=getattr(nfo_matches.get(plan.file_id), "episode", None),
                )
                for plan in plans
            ],
            nfo_options,
        )
        for decision in nfo_decisions:
            if decision.kind == "episode":
                nfo_path_by_file[decision.file_id] = decision.path

    for plan in plans:
        if plan.conflicts and conflict_strategy == "abort":
            result = RenameResult(
                id=plan.id,
                original_path=plan.original_path,
                new_path=plan.new_path,
                original_filename=plan.original_filename,
                new_filename=plan.new_filename,
                success=False,
                error=f"冲突: {', '.join(plan.conflicts)}",
                status="conflict",
            )
            results.append(result)
            failed += 1
            continue

        result = execute_rename_plan(plan, dry_run=dry_run, conflict_strategy=conflict_strategy)
        result.nfo_path = nfo_path_by_file.get(plan.file_id)
        results.append(result)

        if result.success and result.status not in ("skipped_conflict", "skipped_same"):
            executed += 1
        elif result.status in ("skipped_conflict", "skipped_same", "conflict"):
            skipped += 1
        else:
            failed += 1

    nfo_written: list[str] = []
    nfo_skipped: list[dict] = []

    if nfo_options and nfo_options.enabled and nfo_decisions:
        if dry_run:
            # 干跑绝不落盘, 但仍要给出完整清单。exists() 是只读检查, 允许。
            for decision in nfo_decisions:
                if decision.content is None:
                    nfo_skipped.append({"path": decision.path, "reason": decision.reason or "无内容"})
                elif Path(decision.path).exists() and not nfo_options.overwrite:
                    nfo_skipped.append({"path": decision.path, "reason": "已存在"})
                elif decision.path not in nfo_written:
                    nfo_written.append(decision.path)
        else:
            written_paths, skipped_pairs = write_nfo_files(nfo_decisions, overwrite=nfo_options.overwrite)
            nfo_written = written_paths
            nfo_skipped = [{"path": p, "reason": r} for p, r in skipped_pairs]

    return BatchRenameResult(
        success=failed == 0,
        source="local",
        executed=executed,
        skipped=skipped,
        failed=failed,
        total=len(plans),
        results=results,
        nfo_written=nfo_written,
        nfo_skipped=nfo_skipped,
    )
```

`Path` 已在 `local_renamer.py` 顶部导入（第 6 行 `from pathlib import Path`），直接用，不要在函数体内做局部 import。

- [ ] **Step 8: 运行全量测试确认无回归**

```bash
cd backend && python -m pytest tests/ -v
```

预期：全部 PASS。既有重命名测试不传 `nfo_options`，走的是 `None` 分支，行为与改动前逐字节一致。

- [ ] **Step 9: 提交**

```bash
git add backend/app/core/nfo_writer.py backend/app/models/file.py backend/app/models/api.py \
        backend/app/core/local_renamer.py backend/tests/test_nfo_write.py
git commit -m "feat(backend): NFO 写盘与重命名集成（dry-run 只列清单 / 默认不覆盖 / 写失败不阻断）"
```

---

### Task 4: 路由接入与 OpenList 守卫

**Files:**
- Modify: `backend/app/api/renamer.py`（`_with_tmdb_titles` 暴露 matches、三个路由、OpenList 守卫）
- Create: `backend/tests/test_rename_nfo_route.py`
- Create: `backend/tests/test_preview_nfo_fields.py`

**Interfaces:**
- Consumes: `NfoOptions` / `NfoEntry`（Task 1）；`build_nfo_decisions`（Task 2）；`batch_rename(..., nfo_options=, nfo_matches=)`（Task 3）；`EpisodeMatch`（第一期）
- Produces:
  - `_with_tmdb_titles(req, files) -> tuple[dict[str, dict], dict[str, dict], dict[str, EpisodeMatch]]` —— **签名从第一期的二元组变为三元组**，新增 `matches: file_id -> EpisodeMatch`
  - `_nfo_options_from_request(req) -> NfoOptions`
  - `_nfo_supported(source: str) -> bool`
  - 预览响应行新增 `nfo`（`{episode, tvshow, season}` —— **键名是 `tvshow` 不是 `show`**，与本步骤代码的三桶 `kind` 及 Task 5 前端的 `row.nfo.tvshow` 一致；本行原写 `show` 是笔误，spec §11 已同步）与 `nfo_scope`（`full` / `episode_only` / `unsupported_source` / `disabled`）

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_rename_nfo_route.py`：

```python
import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.main import app
from app.models.file import FileInfo


TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"
OVERRIDES = {"f1": {"show_name": "Test Show", "season": 1, "episode": 2}}


@pytest.fixture
def client(tmp_path):
    video = tmp_path / "Test Show" / "Test.Show.S01E02.mkv"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"")

    cache_files([
        FileInfo(
            id="f1",
            source="local",
            path=str(video),
            filename="Test.Show.S01E02.mkv",
            extension=".mkv",
            parent_dir=str(video.parent),
        )
    ])
    return TestClient(app)


def payload(**extra):
    data = {
        "file_ids": ["f1"],
        "template": TEMPLATE,
        "source": "local",
        "path": "",
        "overrides": OVERRIDES,
        "conflict_strategy": "skip",
    }
    data.update(extra)
    return data


def test_generate_nfo_off_writes_nothing(client, tmp_path):
    res = client.post("/api/rename/execute", json=payload(generate_nfo=False))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["nfo_written"] == []
    assert list(tmp_path.rglob("*.nfo")) == []


def test_dry_run_lists_nfo_plan_without_writing(client, tmp_path):
    # Review Focus：干跑必须列出清单但绝不落盘
    res = client.post("/api/rename/dry-run", json=payload(generate_nfo=True))
    assert res.status_code == 200, res.text
    body = res.json()

    assert list(tmp_path.rglob("*.nfo")) == [], "干跑不得落盘"
    assert body["nfo_written"] == [], "未配 TMDB 时没有可写的 NFO"

    row = body["results"][0]
    assert row["nfo_path"] is not None
    assert row["nfo_path"].endswith("Test Show - S01E02.nfo")


def test_generate_nfo_without_tmdb_key_produces_no_files(client, tmp_path):
    # Review Focus 4：无 TMDB 数据时不写残缺 NFO, 但重命名照常完成
    res = client.post("/api/rename/execute", json=payload(generate_nfo=True))
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["results"][0]["success"] is True
    assert body["nfo_written"] == []
    assert list(tmp_path.rglob("*.nfo")) == []
    assert any("TMDB" in item["reason"] for item in body["nfo_skipped"])


def test_openlist_source_refuses_nfo(client):
    # Review Focus：OpenList 本期不支持写 NFO。预览不依赖连接, 可以直接断言。
    res = client.post("/api/rename/preview", json=payload(source="openlist", generate_nfo=True))
    assert res.status_code == 200, res.text

    row = res.json()["results"][0]
    assert row["nfo_scope"] == "unsupported_source"
    assert row["nfo"] is None


def test_preview_reports_disabled_scope_without_tmdb(client):
    res = client.post("/api/rename/preview", json=payload(generate_nfo=True))
    assert res.status_code == 200, res.text

    row = res.json()["results"][0]
    assert row["nfo_scope"] == "disabled"
    assert row["nfo"] is None
```

创建 `backend/tests/test_preview_nfo_fields.py`：

```python
from app.core.nfo_writer import build_nfo_decisions
from app.models.nfo import NfoEntry, NfoOptions
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow


def test_preview_shows_resolvable_show_level_paths():
    """预览必须能报出剧集级 NFO 的落点, 否则用户看不到 tvshow.nfo 写到哪了 ——
    库根污染的唯一防线就是「让他看见」。"""
    entries = [
        NfoEntry(
            file_id="f1",
            new_path="/media/绝命毒师/Season 02/绝命毒师 - S02E05.mkv",
            show_name="绝命毒师",
            season=2,
            episode=5,
            show=TmdbShow(tv_id=1396, name="绝命毒师", original_name="Breaking Bad", year=2008),
            season_data=TmdbSeason(season_number=2, name="第 2 季", tmdb_id=3575),
            episode_data=TmdbEpisode(episode_number=5, name="Breakage", tmdb_id=62085),
        )
    ]
    decisions = build_nfo_decisions(entries, NfoOptions(enabled=True))

    paths = {d.kind: d.path for d in decisions}
    assert paths["episode"] == "/media/绝命毒师/Season 02/绝命毒师 - S02E05.nfo"
    assert paths["season"] == "/media/绝命毒师/Season 02/season.nfo"
    assert paths["tvshow"] == "/media/绝命毒师/tvshow.nfo"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_rename_nfo_route.py tests/test_preview_nfo_fields.py -v
```

预期：`test_preview_nfo_fields.py` 的 1 个用例 PASS（Task 2 已实现）。`test_rename_nfo_route.py` 全部 FAIL —— 响应里没有 `nfo_written` / `nfo_path` / `nfo_scope`，且 `_with_tmdb_titles` 尚未返回 matches。

- [ ] **Step 3: 让 `_with_tmdb_titles` 暴露 matches**

编辑 `backend/app/api/renamer.py`。

把该函数的签名、docstring 与返回值改为：

```python
async def _with_tmdb_titles(
    req, files: list[FileInfo]
) -> tuple[dict[str, dict], dict[str, dict], dict[str, EpisodeMatch]]:
    """查 TMDB 并把标题并进 overrides。

    返回 (合并后的 overrides, 每文件的 TMDB 摘要, 每文件的 EpisodeMatch)。

    第三项供 NFO 生成消费 —— 它是 NFO 内容的唯一来源, 不重新查 TMDB。
    **手动指定的 title 永远优先于 TMDB** —— 这也是 episode_not_found 的兜底手段。
    """
    merged: dict[str, dict] = {
        f.id: dict(req.overrides.get(f.id) or {}) for f in files
    }
    summaries: dict[str, dict] = {}
    matches_by_file: dict[str, EpisodeMatch] = {}

    client = _tmdb_client_from_request(req)
    if client is None:
        for f in files:
            summaries[f.id] = _tmdb_summary(STATUS_DISABLED)
        return merged, summaries, matches_by_file

    parsed: dict[str, ParsedInfo] = {}
    for f in files:
        raw = req.overrides.get(f.id) or {}
        parsed[f.id] = apply_override(
            parse_filename(f.filename, f.parent_dir),
            OverrideInfo(**raw) if raw else None,
        )

    resolver = TmdbResolver(client, overrides=req.tmdb_overrides)
    try:
        matches = await resolver.resolve_many([
            ResolveRequest(
                show_name=parsed[f.id].show_name,
                season=parsed[f.id].season,
                episode=parsed[f.id].episode,
            )
            for f in files
        ])
    except TmdbAuthError as exc:
        raise HTTPException(status_code=400, detail=f"TMDB API Key 无效: {exc}")

    for f, match in zip(files, matches):
        summaries[f.id] = _tmdb_summary(match.status, match)
        matches_by_file[f.id] = match
        if match.status == STATUS_MATCHED and match.episode and match.episode.name:
            if not merged[f.id].get("title"):
                merged[f.id]["title"] = match.episode.name

    return merged, summaries, matches_by_file
```

- [ ] **Step 4: 加入 NFO 辅助函数**

在 `_with_tmdb_titles` 之后加入：

```python
def _nfo_options_from_request(req) -> NfoOptions:
    return NfoOptions(
        enabled=bool(getattr(req, "generate_nfo", False)),
        overwrite=bool(getattr(req, "nfo_overwrite", False)),
    )


def _nfo_supported(source: str) -> bool:
    """本期只有本地源能写 NFO。

    OpenList 要写文件得先给 OpenListClient 加 /api/fs/put 上传能力,
    那是独立的一块工作与风险, 见 spec §2 与 §14。
    """
    return source == "local"
```

并把 import 区补上：

```python
from ..models.nfo import NfoEntry, NfoOptions
from ..core.nfo_writer import build_nfo_decisions
```

- [ ] **Step 5: 预览路由返回 NFO 落点**

把 `/rename/preview` 路由函数体**整体替换**为下面这版。相比第一期，变化有三处：解包三元组、计划只构建一次（NFO 落点与响应共用）、响应新增两个字段。

```python
@router.post("/rename/preview")
async def preview_rename(req: RenamePreviewRequest):
    files = find_files_by_ids(req.file_ids)
    pad = _pad_from_request(req)
    source = req.source.lower()

    # 两遍解析的原因: {title} 是模板的渲染输入之一, 所以 TMDB 的标题必须在
    # build_rename_plan 渲染之前到手。第一遍只解析拿 (剧名, 季, 集), 批量查完
    # TMDB 后再把标题并进 overrides, 第二遍才渲染。
    merged, summaries, matches_by_file = await _with_tmdb_titles(req, files)

    # 计划只构建一次 —— NFO 落点的推导与响应共用同一批 plan,
    # 重复构建不但浪费, 两份结果一旦分叉就会出现「预览说写这里、实际写那里」。
    plans: list[RenamePlan] = []
    for f in files:
        overrides_for_f = merged.get(f.id) or {}
        override_for_f = OverrideInfo(**overrides_for_f) if overrides_for_f else None

        if source == "local":
            from ..core.local_renamer import build_rename_plan
            plans.append(build_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override_for_f, pad=pad,
            ))
        elif source == "openlist":
            plans.append(build_openlist_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override_for_f, pad=pad,
            ))
        else:
            raise HTTPException(status_code=400, detail=f"未知数据源: {source}")

    # NFO 落点必须在预览里可见 —— 「tvshow.nfo 会写到哪里」是库根污染的
    # 唯一防线（spec §9.4）。这里只算决策, 绝不落盘。
    nfo_options = _nfo_options_from_request(req)
    nfo_paths_by_file: dict[str, dict] = {}
    nfo_scope = "disabled"

    if nfo_options.enabled:
        if not _nfo_supported(source):
            nfo_scope = "unsupported_source"
        elif _tmdb_client_from_request(req) is None:
            # 启用了 NFO 但没有 TMDB —— 没有任何内容可写, 如实报 disabled,
            # 而不是让它落到下面算出 episode_only（那会暗示「只是没写剧集级」）。
            nfo_scope = "disabled"
        else:
            decisions = build_nfo_decisions(
                [
                    NfoEntry(
                        file_id=plan.file_id,
                        new_path=plan.new_path,
                        show_name=plan.parsed.show_name if plan.parsed else "",
                        season=plan.parsed.season if plan.parsed else None,
                        episode=plan.parsed.episode if plan.parsed else None,
                        show=getattr(matches_by_file.get(plan.file_id), "show", None),
                        season_data=getattr(matches_by_file.get(plan.file_id), "season", None),
                        episode_data=getattr(matches_by_file.get(plan.file_id), "episode", None),
                    )
                    for plan in plans
                ],
                nfo_options,
            )
            for decision in decisions:
                if decision.content is None:
                    continue
                nfo_paths_by_file.setdefault(decision.file_id, {})[decision.kind] = decision.path

            nfo_scope = "full" if all(
                "tvshow" in nfo_paths_by_file.get(f.id, {}) for f in files
            ) else "episode_only"

    results: list[dict] = []
    for f, plan in zip(files, plans):
        summary = summaries.get(f.id) or _tmdb_summary(STATUS_DISABLED)
        results.append({
            "original_path": plan.original_path,
            "original_filename": plan.original_filename,
            "new_path": plan.new_path,
            "new_filename": plan.new_filename,
            "has_conflict": plan.original_filename == plan.new_filename,
            "conflicts": plan.conflicts,
            "show_name": plan.parsed.show_name if plan.parsed else None,
            "season": plan.parsed.season if plan.parsed else None,
            "episode": plan.parsed.episode if plan.parsed else None,
            "title": plan.parsed.title if plan.parsed else None,
            "confidence": plan.parsed.parse_confidence if plan.parsed else 0,
            "needs_review": plan.parsed.needs_manual_review if plan.parsed else False,
            "tmdb_status": summary["status"],
            "tmdb_match": {
                "tv_id": summary["tv_id"],
                "name": summary["name"],
                "original_name": summary["original_name"],
                "year": summary["year"],
            } if summary["tv_id"] else None,
            "nfo": nfo_paths_by_file.get(f.id) or None,
            "nfo_scope": nfo_scope,
        })

    return {
        "success": True,
        "source": req.source,
        "total": len(results),
        "results": results,
    }
```

- [ ] **Step 6: 执行与干跑路由传入 NFO 选项**

在 `/rename/execute` 路由中，把 `merged, _summaries = await _with_tmdb_titles(req, files)` 改为：

```python
    merged, _summaries, matches_by_file = await _with_tmdb_titles(req, files)
    effective_overrides = merged
```

把 `local_batch_rename(...)` 调用改为：

```python
        result = local_batch_rename(
            files=files,
            template=req.template,
            folder_template=req.folder_template,
            create_season_folder=req.create_season_folder,
            overrides=effective_overrides,
            dry_run=False,
            conflict_strategy=req.conflict_strategy,
            pad=pad,
            nfo_options=_nfo_options_from_request(req) if _nfo_supported(source) else NfoOptions(),
            nfo_matches=matches_by_file,
        )
```

在 `/rename/dry-run` 路由中做同样的改动，只是 `dry_run=True`。

**`_nfo_supported(source)` 为假时传 `NfoOptions()`**（`enabled=False`）而不是传 `None`：`None` 与「未启用」在 `batch_rename` 里走同一分支，但显式传未启用的 options 让「OpenList 不写 NFO」这条规则在调用点就是可见的，而不是依赖 `batch_rename` 内部的空值判断。

- [ ] **Step 7: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/ -v
```

预期：全部 PASS

- [ ] **Step 8: 端到端确认路由可用**

```bash
cd backend && python -c "from app.main import app; print('路由数:', len(app.routes))"
```

预期：正常输出，无 ImportError

- [ ] **Step 9: 提交**

```bash
git add backend/app/api/renamer.py backend/tests/test_rename_nfo_route.py backend/tests/test_preview_nfo_fields.py
git commit -m "feat(backend): 路由接入 NFO 生成（OpenList 守卫 / 预览暴露落点 / matches 向上暴露）"
```

---

### Task 5: 前端 NFO 勾选与预览表 NFO 列

**Files:**
- Modify: `frontend/src/stores/workspace.js`（`generateNfo` / `nfoOverwrite`、下发、预览行 `nfo`）
- Modify: `frontend/src/components/TemplateConfig.vue`
- Modify: `frontend/src/components/FileTable.vue`

**Interfaces:**
- Consumes: 预览响应的 `nfo` / `nfo_scope`（Task 4）；`batch_rename` 的响应字段 `nfo_written` / `nfo_skipped`（Task 3）
- Produces:
  - `workspaceStore.generateNfo` / `workspaceStore.nfoOverwrite`
  - `previewRows` 每行新增 `nfo`（对象或 null）与 `nfo_scope`（字符串）
  - `TemplateConfig` 新增 `update:generateNfo` / `update:nfoOverwrite` 两个 emit

- [ ] **Step 1: 工作区新增选项与下发**

编辑 `frontend/src/stores/workspace.js`。

在 `const executeDryRun = ref(false)` 之后加：

```javascript
  // NFO 选项是本次会话的工作参数, 不进设置页 —— 它跟「扫哪个目录」一样,
  // 是这一次任务的属性, 不是长期偏好。
  const generateNfo = ref(false)
  const nfoOverwrite = ref(false)
```

在 `buildPreview` 的请求体里，于 `tmdb_overrides: { ...tmdbOverrides },` 之后加：

```javascript
        generate_nfo: generateNfo.value,
        nfo_overwrite: nfoOverwrite.value,
```

在 `previewRows.value = filesStore.files.map(...)` 的返回对象里，于 `tmdb_match: pv.tmdb_match || null,` 之后加：

```javascript
          nfo: pv.nfo || null,
          nfo_scope: pv.nfo_scope || 'disabled',
```

在 `executeAction` 的请求体里，同样于 `tmdb_overrides: { ...tmdbOverrides },` 之后加：

```javascript
        generate_nfo: generateNfo.value,
        nfo_overwrite: nfoOverwrite.value,
```

在返回对象里把 `tmdbOverrides, tmdbDialog, rematchShow, searchShow, pickShow,` 一行替换为：

```javascript
    tmdbOverrides, tmdbDialog, rematchShow, searchShow, pickShow,
    generateNfo, nfoOverwrite,
```

- [ ] **Step 2: 面板新增勾选**

编辑 `frontend/src/components/TemplateConfig.vue`，在季文件夹那个 `<div class="flex flex-col gap-3">` 之后插入：

```html
    <div class="flex flex-col gap-3 border-t border-line pt-3">
      <AppCheckbox
        :model-value="generateNfo"
        :disabled="source === 'openlist'"
        :label="source === 'openlist' ? '同时生成 NFO 文件（OpenList 暂不支持）' : '同时生成 NFO 文件'"
        @update:model-value="$emit('update:generateNfo', $event)"
      />
      <AppCheckbox
        :model-value="nfoOverwrite"
        :disabled="!generateNfo || source === 'openlist'"
        label="覆盖已存在的 NFO"
        @update:model-value="$emit('update:nfoOverwrite', $event)"
      />
      <p v-if="generateNfo && source !== 'openlist'" class="text-[11px] leading-relaxed text-ink-3">
        生成 tvshow.nfo、season.nfo 与每集 .nfo。剧集级文件需要该目录下只有一部剧，否则只写每集 NFO。
      </p>
    </div>
```

在 `defineProps` 中加入两个新 prop：

```javascript
const props = defineProps({
  tplStore: { type: Object, required: true },
  source: { type: String, required: true },
  generateNfo: { type: Boolean, default: false },
  nfoOverwrite: { type: Boolean, default: false },
})
```

在 `defineEmits` 数组里加入两个新 emit：

```javascript
defineEmits([
  'preset-change', 'template-edit',
  'update:createSeasonFolder', 'update:folderTemplate',
  'update:generateNfo', 'update:nfoOverwrite',
])
```

- [ ] **Step 3: 页面接线**

编辑 `frontend/src/views/HomeView.vue`，在 `<TemplateConfig>` 的监听列表里加入：

```html
            :generate-nfo="ws.generateNfo"
            :nfo-overwrite="ws.nfoOverwrite"
            @update:generateNfo="v => ws.generateNfo = v"
            @update:nfoOverwrite="v => ws.nfoOverwrite = v"
```

- [ ] **Step 4: 预览表新增 NFO 列**

编辑 `frontend/src/components/FileTable.vue`。

在表头「新文件名」列之前插入：

```html
            <th class="hidden px-4 py-3 text-left font-semibold lg:table-cell">NFO</th>
```

在数据行的「新文件名」`<td>` 之前插入：

```html
              <td class="hidden px-4 py-2.5 lg:table-cell">
                <div v-if="row.nfo" class="flex flex-col gap-0.5 text-[11px]">
                  <span class="truncate text-ink-2" :title="row.nfo.episode">
                    {{ nfoBaseName(row.nfo.episode) }}
                  </span>
                  <span v-if="row.nfo.tvshow" class="truncate text-ink-3" :title="row.nfo.tvshow">
                    + tvshow.nfo
                  </span>
                  <span v-else class="text-warn" :title="nfoScopeHint(row.nfo_scope)">
                    仅每集 NFO
                  </span>
                </div>
                <span v-else class="text-[11px] text-ink-3">{{ nfoScopeHint(row.nfo_scope) }}</span>
              </td>
```

在骨架行的「新文件名」占位之前插入：

```html
              <td class="hidden px-4 py-2.5 lg:table-cell">
                <div class="h-4 w-[140px] rounded-[4px] bg-sunken" />
              </td>
```

在 `<script setup>` 中加入：

```javascript
const NFO_SCOPE_HINTS = {
  disabled: '未启用',
  unsupported_source: '云盘不支持',
  episode_only: '多剧混放，仅每集 NFO',
  full: '—',
}

function nfoBaseName(path) {
  return path ? path.split('/').pop() : ''
}

function nfoScopeHint(scope) {
  return NFO_SCOPE_HINTS[scope] || '—'
}
```

- [ ] **Step 5: 确认可编译并构建**

```bash
cd frontend && node scripts/check-sfc-compile.mjs && npm run build
```

预期：两者均成功

- [ ] **Step 6: 确认新代码进入构建产物**

```bash
cd frontend && grep -rl "nfo_scope\|nfoOverwrite" dist/assets/ | head -3
```

预期：至少命中一个文件

- [ ] **Step 7: 提交**

```bash
git add frontend/src/stores/workspace.js frontend/src/components/TemplateConfig.vue \
        frontend/src/components/FileTable.vue frontend/src/views/HomeView.vue
git commit -m "feat(frontend): NFO 生成勾选与预览表 NFO 列"
```

---

## 完成后

### 机械等价验证（可自动化）

```bash
cd backend && python -m pytest tests/ -v
cd frontend && node scripts/check-settings-schema.mjs && node scripts/check-sfc-compile.mjs && npm run build
```

### 端到端验证（deferred-to-human）

以下步骤需要真实媒体目录与浏览器，按项目惯例标为 `deferred-to-human`：

1. 选一个已有 `tvshow.nfo` 的剧集目录 → 勾选「同时生成 NFO 文件」、**不勾** 覆盖 → 执行 → 结果对话框应报告既有 NFO 被跳过，且原有文件内容未被改动
2. 同上，改勾「覆盖已存在的 NFO」→ 执行 → 既有 NFO 内容应被替换
3. 找一个**未启用季文件夹**的剧集目录 → 生成 → `tvshow.nfo` 与 `season.nfo` 应与视频同目录，`season.nfo` **存在**（Review Focus 5）
4. 构造一个多剧混放目录（如把两部剧各放一集进同一个新建目录）→ 预览表的 NFO 列应显示「多剧混放，仅每集 NFO」→ 执行 → 该目录下**不得出现** `tvshow.nfo`
5. 找一个剧名含 `&` 的剧（或临时把目录名改成 `Tom & Jerry`）→ 生成 → 用浏览器或 `python -c "import xml.etree.ElementTree as ET; ET.parse('tvshow.nfo')"` 确认文件可解析
6. 选一个 TMDB 匹配失败的文件（手改剧名为不存在的名字）→ 生成 → 不得产生任何 `.nfo`，且重命名照常完成
7. 点「试运行」并勾 NFO → 预览应列出将写入的路径，且执行后 `find <目录> -name "*.nfo"` 为空

## 验收判据

本期交付后，「生成 NFO」这件事必须能被一句话验证：**在一个 TMDB 已匹配的本地剧集目录里执行一次重命名，`tvshow.nfo` / `season.nfo` / 每集 `.nfo` 三者出现在正确位置，且用 `ET.parse` 全部可解析、`<uniqueid type="tmdb">` 非空。**

## Self-Review

**Spec 覆盖**

| Spec 节 | 落位 |
|---|---|
| §4 模块结构（`nfo_writer` 纯函数 + 写盘分离） | Task 1、Task 2（纯）、Task 3（副作用，单独一个函数） |
| §8.1 三种 XML 的字段 | Task 1 Step 4 |
| §8.2 `<uniqueid>` 必写 | Task 1 `test_tvshow_emits_uniqueid_and_tmdbid`、`test_season_core_fields`、`test_episode_core_fields` |
| §8.2 每集 NFO 靠文件名配对 | Task 2 `episode_nfo_path` + `test_episode_nfo_is_sibling_of_video` |
| §8.3 ElementTree + 省略空标签 | Task 1 `test_tvshow_escapes_ampersand_and_angle_brackets`、`test_tvshow_omits_missing_fields_instead_of_empty_tags` |
| §8.4 内容来源（`showtitle` 用剧名） | Task 1 `build_episode_nfo(..., show_title=)`；Task 2 传 `item.show.name` |
| §9.1 三种落点 | Task 2 `test_tvshow_goes_to_show_root_and_season_to_season_folder`、`test_season_nfo_still_written_without_season_folders` |
| §9.3 公共父目录 | Task 2 `common_parent` 三例 + `test_split_season_folders_put_tvshow_at_show_root` |
| §9.3 show_name 一致性校验（同管 tvshow 与 season） | Task 2 `test_mixed_shows_in_one_directory_are_refused` |
| §9.4 可见性（预览列出落点） | Task 4 `test_preview_shows_resolvable_show_level_paths`；Task 5 NFO 列 |
| §9.4 覆盖默认关闭 | Task 3 `test_existing_file_is_skipped_when_overwrite_is_off` |
| §10.2 请求字段 | Task 3 Step 6 |
| §11 响应字段 | Task 3 Step 5（模型）；Task 4 Step 5-6（路由填充） |
| §12.3 工作区状态 | Task 5 Step 1 |
| §12.4 NFO 列 | Task 5 Step 4 |
| §13 `test_nfo_writer` / `test_nfo_plan` / `test_rename_nfo_route` | Task 1 / Task 2（含 `test_nfo_write`）/ Task 4 |
| §2 OpenList 不写 NFO | Task 4 Step 4 `_nfo_supported` + `test_openlist_source_refuses_nfo`；Task 5 Step 2 置灰 |
| spec §11 的响应字段位置（按文件 vs 按批次） | **有意偏差**：spec 原文把 `nfo_written` / `nfo_skipped` 挂在每条 `RenameResult` 上。实际上 `tvshow.nfo` / `season.nfo` 不隶属任何单个文件，挂在每条结果上会把同一路径重复 N 遍。故改为：`RenameResult.nfo_path`（每集落点，确实一一对应）+ `BatchRenameResult.nfo_written` / `nfo_skipped`（汇总）。spec §9.1 的 `season.nfo` 落点笔误已同步修正 |
| §14 OpenList / 番剧限制 | 本期不新增限制；番剧 `episode_not_found` 在第一期已处理，本期只消费其结果 |

**占位符扫描**：无 TBD / TODO / 「类似 Task N」。每个代码步骤含完整可粘贴的代码。

**类型一致性**

- `NfoOptions(enabled, overwrite)` / `NfoEntry(...)` / `NfoDecision(file_id, kind, path, content, reason)` 在 Task 1 定义；Task 2、3、4 的构造与读取字段名一致 ✓
- `build_nfo_decisions(entries, options)` 在 Task 2 定义；Task 3、4 按此调用 ✓
- `write_nfo_files(decisions, overwrite) -> (list[str], list[tuple[str, str]])` 在 Task 3 定义；Task 3 `batch_rename` 按此解包 ✓
- `_with_tmdb_titles` 从第一期的二元组变为**三元组** —— Task 4 Step 3 明确替换签名，Step 5 与 Step 6 的三处调用点同步改为三值解包 ✓
- `batch_rename(..., nfo_options=, nfo_matches=)` 在 Task 3 Step 7 定义；Task 4 Step 6 按此调用 ✓
- `RenameResult.nfo_path` / `BatchRenameResult.nfo_written` / `nfo_skipped` 在 Task 3 Step 5 定义；Task 4 测试断言同名字段 ✓
- 前端 `generateNfo` / `nfoOverwrite` 在 Task 5 Step 1 定义；Step 2-3 的 props 与 emit 名称 `update:generateNfo` / `update:nfoOverwrite` 一致 ✓
- `nfo_scope` 的四个取值 `disabled` / `unsupported_source` / `episode_only` / `full` 在 Task 4 Step 5 产生；Task 5 Step 4 的 `NFO_SCOPE_HINTS` 键逐字一致 ✓

**Review Focus 落位**

| # | 覆盖它的测试 |
|---|---|
| 1 剧名含 `&` / `<` | `test_tvshow_escapes_ampersand_and_angle_brackets`、`test_episode_escapes_titles`（Task 1）；`parse()` 辅助函数让非法 XML 直接抛异常 |
| 2 多剧混放目录 | `test_mixed_shows_in_one_directory_are_refused`、`test_mixed_shows_in_parent_do_not_block_subdirectory_shows`（Task 2） |
| 3 目标 NFO 已存在 | `test_existing_file_is_skipped_when_overwrite_is_off`、`test_existing_file_is_overwritten_when_asked`（Task 3） |
| 4 TMDB 未匹配不写残缺 NFO | `test_episode_nfo_skipped_without_metadata`、`test_show_level_files_skipped_without_show_metadata`（Task 2）；`test_generate_nfo_without_tmdb_key_produces_no_files`（Task 4） |
| 5 未启用季文件夹 | `test_season_nfo_still_written_without_season_folders`（Task 2） |

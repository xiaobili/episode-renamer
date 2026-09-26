import os

import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.core.tmdb_client import TmdbAuthError, TmdbClient
from app.core.tmdb_resolver import (
    STATUS_DISABLED,
    STATUS_EPISODE_NOT_FOUND,
    STATUS_MATCHED,
    STATUS_SEASON_NOT_FOUND,
    STATUS_SHOW_NOT_FOUND,
    STATUS_UNAVAILABLE,
)
from app.main import app
from app.models.file import FileInfo
from app.models.tmdb import TmdbEpisode, TmdbSearchItem, TmdbSeason, TmdbShow

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"

# 用 overrides 钉死解析结果, 让断言不依赖文件名解析器的行为
OVERRIDES = {"f1": {"show_name": "Test Show", "season": 1, "episode": 2}}


@pytest.fixture
def client():
    cache_files([
        FileInfo(
            id="f1",
            source="local",
            path="/media/Test Show/Test.Show.S01E02.mkv",
            filename="Test.Show.S01E02.mkv",
            extension=".mkv",
            parent_dir="/media/Test Show",
        )
    ])
    return TestClient(app)


def preview(client, **extra):
    payload = {
        "file_ids": ["f1"],
        "template": TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "overrides": OVERRIDES,
    }
    payload.update(extra)
    res = client.post("/api/rename/preview", json=payload)
    assert res.status_code == 200, res.text
    return res.json()["results"][0]


def test_omitting_pad_fields_preserves_current_behaviour(client):
    # Review Focus 4: 老客户端不传 pad, 行为必须与改动前逐字节一致
    row = preview(client)
    assert row["new_filename"] == "Test Show - S01E02.mkv"


def test_episode_pad_digits_is_honoured(client):
    row = preview(client, episode_pad_digits=3)
    assert row["new_filename"] == "Test Show - S01E002.mkv"


def test_season_pad_digits_is_honoured(client):
    row = preview(client, season_pad_digits=3)
    assert row["new_filename"] == "Test Show - S001E02.mkv"


def test_episode_only_does_not_disturb_season(client):
    # Review Focus 3: 只传一个字段时, 另一个退回全局默认
    row = preview(client, episode_pad_digits=4)
    assert row["new_filename"] == "Test Show - S01E0002.mkv"


def test_zero_is_clamped_to_one(client):
    # Review Focus 1: 用户清空数字框留下 0
    row = preview(client, episode_pad_digits=0, season_pad_digits=0)
    assert row["new_filename"] == "Test Show - S1E2.mkv"


def test_negative_is_clamped_to_one(client):
    # Review Focus 1: str(-1).zfill(2) == "-1" 会产出损坏文件名
    row = preview(client, episode_pad_digits=-1, season_pad_digits=-1)
    assert row["new_filename"] == "Test Show - S1E2.mkv"


def test_oversized_is_clamped_to_six(client):
    # Review Focus 2: 输入 99 不应生成 99 位补零
    row = preview(client, episode_pad_digits=99, season_pad_digits=99)
    assert row["new_filename"] == "Test Show - S000001E000002.mkv"


def test_folder_template_honours_pad(client):
    row = preview(
        client,
        folder_template="Season {season_padded}",
        create_season_folder=True,
        season_pad_digits=3,
    )
    assert row["new_path"] == "/media/Test Show/Season 001/Test Show - S001E02.mkv"


def _write_payload(**extra):
    payload = {
        "file_ids": ["f1"],
        "template": TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "overrides": OVERRIDES,
        "conflict_strategy": "skip",
    }
    payload.update(extra)
    return payload


def test_dry_run_route_honours_pad_fields(client):
    # 干跑, 不触盘。必须断言真实文件名而不是只断言 200 —— 路由丢掉 `pad=pad`
    # 同样会返回 200 且测试全绿, 那正是计划为前端点名的失败模式
    # （「只加 buildPreview 一处…写出的文件名与预览不一致」），只是搬到了路由层。
    res = client.post("/api/rename/dry-run", json=_write_payload(
        episode_pad_digits=3, season_pad_digits=3))
    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["new_filename"] == "Test Show - S001E002.mkv"


def test_execute_route_honours_pad_fields(client):
    # execute 会真写盘, 但 fixture 的源文件 /media/Test Show/... 并不存在于磁盘,
    # 所以只会得到一个 success=False 的结果 —— 文件名与路径仍按 pad 算好了,
    # 因此可以在不接触文件系统的前提下断言。
    res = client.post("/api/rename/execute", json=_write_payload(
        episode_pad_digits=3, season_pad_digits=3))
    assert res.status_code == 200, res.text
    row = res.json()["results"][0]
    assert row["new_filename"] == "Test Show - S001E002.mkv"
    assert row["new_path"] == "/media/Test Show/Test Show - S001E002.mkv"


TITLE_TEMPLATE = "{show} - S{season_padded}E{episode_padded} - {title}{extension}"


def test_no_tmdb_key_degrades_to_disabled(client):
    # Review Focus 3：完全未配置 Key。功能降级, 重命名与既有字段完全不受影响。
    row = preview(client, template=TITLE_TEMPLATE)
    assert row["tmdb_status"] == "disabled"
    assert row["tmdb_match"] is None
    assert row["new_filename"] == "Test Show - S01E02 - .mkv"


def test_manual_title_override_wins_over_tmdb(client):
    # 手动填的 title 优先 —— 也是 episode_not_found 的兜底手段
    row = preview(client, template=TITLE_TEMPLATE,
                  overrides={"f1": {"show_name": "Test Show", "season": 1,
                                    "episode": 2, "title": "手工标题"}})
    assert row["title"] == "手工标题"
    assert row["new_filename"] == "Test Show - S01E02 - 手工标题.mkv"


def test_invalid_tmdb_key_returns_400_not_silent_disabled(client, monkeypatch):
    # Review Focus 2：Key 无效必须报错, 不得静默降级 ——
    # 静默会让用户以为「功能没做」而不是「我填错了」。
    #
    # 本用例**密闭, 不发起任何网络调用**。链路两端各有归属:
    # 「真实 401 → TmdbAuthError」由 Task 1 的 test_401_raises_auth_error
    # （MockTransport 回 401）覆盖; 这里只证明后半段「TmdbAuthError → 400」。
    # 之前那版直接打真 TMDB, 换台机器或断网就会红/超时, 在单元套件里是
    # 构造性的不稳定, 故改为让客户端在鉴权点抛同名异常。
    async def fake_search_tv(self, query, year=None):
        raise TmdbAuthError("TMDB API Key 无效")

    monkeypatch.setattr(TmdbClient, "search_tv", fake_search_tv)

    res = client.post("/api/rename/preview", json={
        "file_ids": ["f1"],
        "template": TITLE_TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "overrides": OVERRIDES,
        "tmdb_api_key": "definitely-invalid",
    })
    assert res.status_code == 400, res.text
    assert "TMDB" in res.json()["detail"]
    # 文案不再重复前缀（异常自带的这句已含 "TMDB" 与「无效」）
    assert res.json()["detail"] == "TMDB API Key 无效"


def test_tmdb_overrides_are_accepted_by_the_request_model(client):
    # 只验证请求模型接受字段且不 422（未配 Key 时不会真的去查）
    res = client.post("/api/rename/preview", json={
        "file_ids": ["f1"],
        "template": TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "overrides": OVERRIDES,
        "tmdb_overrides": {"Test Show": 1396},
    })
    assert res.status_code == 200, res.text


class _FakeTmdbClient:
    """离线替身: 固定返回「Test Show」第 1 季第 2 集「Breakage」, 不碰网络。"""

    language = "zh-CN"

    def cache_fingerprint(self):
        return "fake-client"

    async def search_tv(self, query, year=None):
        return [TmdbSearchItem(tv_id=1396, name=query, original_name=query, year=2008)]

    async def get_tv_detail(self, tv_id):
        return TmdbShow(tv_id=tv_id, name="Test Show", original_name="Test Show", year=2008)

    async def get_season(self, tv_id, season_number):
        return TmdbSeason(season_number=season_number, episodes={
            2: TmdbEpisode(episode_number=2, name="Breakage"),
        })


@pytest.fixture
def fake_tmdb(monkeypatch):
    from app.api import renamer as renamer_api

    monkeypatch.setattr(
        renamer_api, "_tmdb_client_from_request", lambda req: _FakeTmdbClient()
    )


def test_tmdb_title_reaches_the_rendered_filename(client, fake_tmdb):
    # 这是本任务的核心断言: {title} 是模板输入, 所以标题必须在渲染之前拿到。
    # 单遍解析（先渲染再查 TMDB）会让这一条红 —— 上面那些用例全都不会。
    row = preview(client, template=TITLE_TEMPLATE)
    assert row["tmdb_status"] == "matched"
    assert row["title"] == "Breakage"
    assert row["new_filename"] == "Test Show - S01E02 - Breakage.mkv"
    assert row["tmdb_match"]["tv_id"] == 1396
    assert row["tmdb_match"]["year"] == 2008


def test_tmdb_title_does_not_override_a_manual_title(client, fake_tmdb):
    # 与上一个用例的区别: TMDB 确实查到了 (matched), 手动标题仍然赢。
    row = preview(client, template=TITLE_TEMPLATE,
                  overrides={"f1": {"show_name": "Test Show", "season": 1,
                                    "episode": 2, "title": "手工标题"}})
    assert row["tmdb_status"] == "matched"
    assert row["new_filename"] == "Test Show - S01E02 - 手工标题.mkv"


@pytest.fixture
def disk_client(tmp_path):
    """execute 会真的动盘, 源文件必须真实存在 —— 不能用 client 夹具里那个假路径。"""
    src = tmp_path / "Test.Show.S01E02.mkv"
    src.write_bytes(b"")
    cache_files([
        FileInfo(
            id="f1",
            source="local",
            path=str(src),
            filename=src.name,
            extension=".mkv",
            parent_dir=str(tmp_path),
        )
    ])
    return TestClient(app)


def _tmdb_write_payload(**extra):
    payload = {
        "file_ids": ["f1"],
        "template": TITLE_TEMPLATE,
        "source": "local",
        "path": "",
        "overrides": OVERRIDES,
    }
    payload.update(extra)
    return payload


def test_execute_route_merges_the_tmdb_title(disk_client, fake_tmdb, tmp_path):
    # 本仓库有前科的缺陷形态（见 2026-09-25-backend-pad-digits 的注释:
    # 「只加 buildPreview 一处…写出的文件名与预览不一致」）—— 预览显示一套、
    # 执行写另一套, 且全程无报错。execute 路径的合并若被删掉或漏传
    # overrides=effective_overrides, 预览里仍有标题而写出的文件名没有,
    # 上面所有用例照样全绿。本条钉住它: TMDB 标题必须真的进入被执行的文件名,
    # 而不只是进入预览响应。
    res = disk_client.post("/api/rename/execute", json=_tmdb_write_payload())
    assert res.status_code == 200, res.text
    row = res.json()["results"][0]
    assert row["new_filename"] == "Test Show - S01E02 - Breakage.mkv"
    assert row["new_path"] == str(tmp_path / "Test Show - S01E02 - Breakage.mkv")
    # 真的落到盘上, 不只是算出了一个字符串
    assert row["success"] is True
    assert os.path.isfile(str(tmp_path / "Test Show - S01E02 - Breakage.mkv"))
    assert not os.path.isfile(str(tmp_path / "Test.Show.S01E02.mkv"))


def test_dry_run_route_merges_the_tmdb_title(disk_client, fake_tmdb, tmp_path):
    # 干跑与预览/执行走同一个合并调用点, 也正是「预览与执行不一致」的高发处。
    res = disk_client.post("/api/rename/dry-run", json=_tmdb_write_payload())
    assert res.status_code == 200, res.text
    row = res.json()["results"][0]
    assert row["new_filename"] == "Test Show - S01E02 - Breakage.mkv"
    assert row["new_path"] == str(tmp_path / "Test Show - S01E02 - Breakage.mkv")
    # 干跑绝不落盘
    assert os.path.isfile(str(tmp_path / "Test.Show.S01E02.mkv"))
    assert not os.path.isfile(str(tmp_path / "Test Show - S01E02 - Breakage.mkv"))


def test_tmdb_status_literals_are_the_wire_contract():
    # 这六个字符串是前后端共享的线上契约: 预览响应的 tmdb_status 字段与前端分支
    # 都按字面值判等, 而别处的测试全部引用常量本身 —— 互换任意两个常量的值
    # 一个测试都不会红。所以在这里逐字钉死。
    # "disabled" 尤其重要: 它不由解析器产出, 只由路由在未配置 Key 时产出,
    # 是最容易被顺手改名的一个。
    assert STATUS_MATCHED == "matched"
    assert STATUS_DISABLED == "disabled"
    assert STATUS_SHOW_NOT_FOUND == "show_not_found"
    assert STATUS_SEASON_NOT_FOUND == "season_not_found"
    assert STATUS_EPISODE_NOT_FOUND == "episode_not_found"
    assert STATUS_UNAVAILABLE == "unavailable"

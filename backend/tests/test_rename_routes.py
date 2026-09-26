import os

import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.core.tmdb_client import TmdbAuthError, TmdbClient, TmdbUnavailableError
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
    #
    # 但 200 **证明不了**「模型声明了这个字段」—— Pydantic 默认忽略未知字段,
    # 把 tmdb_overrides 从 RenamePreviewRequest 里删掉, 下面这条 POST 依然 200。
    # 所以真正钉住声明的是 model_fields 那一条; 200 只顺带证明它没被 422 拒绝。
    from app.models.api import RenamePreviewRequest

    assert "tmdb_overrides" in RenamePreviewRequest.model_fields

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
    """离线替身: 固定返回「Test Show」第 1 季第 2 集「Breakage」, 不碰网络。

    `fail=` 的两种取值对应两种**不同深度**的故障, 两者在路由层都必须得到
    「200 + 重命名照做」, 但走的是链条上不同的几段（见
    test_tmdb_outage_does_not_block_the_rename 的说明）:
    - `"search"`: search_tv 抛 TmdbUnavailableError —— 已分类的故障
      （连接被拒 / 超时）。
    - `"value"`: search_tv 抛 ValueError —— **未分类**的故障, 只能在映射层炸出来
      （如 int(number) 拿到 null）。它必须先经过守卫的宽捕获才会变成 unavailable,
      所以它也是唯一能钉住「守卫的宽捕获还在」的那种故障。取值与
      test_tmdb_resolver.FakeClient 的 `fail=` 对齐。
    """

    language = "zh-CN"
    # 类属性而不是只写在 __init__ 里: _recording_client_cls 那个子类重写了
    # __init__ 且不调 super(), 只在 __init__ 里赋值会让它的 self._fail 变成
    # AttributeError —— 而那会**在 search_tv 里**抛出, 被守卫归类成 unavailable,
    # 表现为一条与本次改动毫不相干的用例(str_env_key 那条)莫名其妙地转红。
    _fail = None

    def __init__(self, fail=None):
        self._fail = fail

    def cache_fingerprint(self):
        return "fake-client"

    async def search_tv(self, query, year=None):
        if self._fail == "search":
            raise TmdbUnavailableError("TMDB 请求失败: connection refused")
        if self._fail == "value":
            raise ValueError("invalid literal for int() with base 10: None")
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


@pytest.fixture
def failing_tmdb(monkeypatch):
    """把「客户端**能**构造、但外部调用一定失败」的假客户端装进路由。

    与 disabled 的区别正在这里: disabled 时 TmdbResolver 根本不会被构造, 那条
    路径证明不了解析器故障时的行为。返回的是安装函数而不是装好的客户端, 让同一
    条用例能覆盖 `fail=` 的多个取值。
    """
    from app.api import renamer as renamer_api

    def install(fail):
        monkeypatch.setattr(
            renamer_api,
            "_tmdb_client_from_request",
            lambda req: _FakeTmdbClient(fail=fail),
        )

    return install


class _OverrideOnlyTmdbClient(_FakeTmdbClient):
    """已指定 tv_id 时的替身: 记下 search_tv 的调用次数。

    自动搜索返回 1396, 而用例会用 9999 作为 tmdb_overrides 的值 —— 两条路径
    因此可以区分: 请求体里的 tv_id 若没被传下去, 结果会退回 1396 且
    search_calls 从 0 变成 1。
    """

    def __init__(self):
        self.search_calls = 0

    def cache_fingerprint(self):
        return "override-only-client"

    async def search_tv(self, query, year=None):
        self.search_calls += 1
        return await super().search_tv(query, year)


@pytest.fixture
def override_only_tmdb(monkeypatch):
    from app.api import renamer as renamer_api

    client = _OverrideOnlyTmdbClient()
    monkeypatch.setattr(renamer_api, "_tmdb_client_from_request", lambda req: client)
    return client


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


@pytest.mark.parametrize("fail", ["search", "value"])
def test_tmdb_outage_does_not_block_the_rename(
    disk_client, failing_tmdb, tmp_path, fail
):
    """铁律「TMDB 故障绝不阻断重命名」在**路由层**的钉子。

    此前它只在解析器层被钉住（test_unclassified_error_is_degraded_not_raised
    之类）, 而在路由层唯一能走到 unavailable 的路径是 disabled —— 那条路径上
    TmdbResolver 根本不会被构造, 解析器一次都不会被调用。于是「解析器故障时路由
    与解析器的接口还成立」这件事没有任何用例管: 把 _with_tmdb_titles 换成
    「任何异常都变成 4xx/5xx」或「吞掉后什么都不写」, 全套测试依然全绿, 而每一次
    重命名都被阻断 / 被谎报成 disabled。

    两个 fail= 取值覆盖链条上不同的段（都以「返回 200 且盘上真的换了名字」收尾）:
    - `"value"`（未分类异常）钉住**守卫的宽捕获**: 这是唯一一条必须经过
      _guarded 的宽捕获才能降级的路径。删掉宽捕获, ValueError 会一路冒到路由。
    - `"search"`（TmdbUnavailableError）钉住**调用点的分类**: 它是已分类的降级
      语义, 由 _resolve_show 的 `except TmdbUnavailableError` 接住并翻成
      unavailable。把那处 re-raise 掉, 异常同样一路冒到路由。
    两个 mutate 都实测过: 只有本条用例红（见最终修复报告的变异记录）。

    两段断言各管一头, 缺一不可:
    - preview 是唯一**暴露 tmdb_status 的行**（execute/dry-run 回的是
      BatchRenameResult, 没有这一列）, 所以「故障被分类成 unavailable, 而不是
      静默假装 disabled/matched」只能在预览响应上断。
    - execute 必须用**真的存在**的文件 (disk_client/tmp_path): 只断言 200 的话,
      一个「返回空结果 + 200」的实现照样能骗过它, 盘上什么都没发生。
    """
    failing_tmdb(fail)

    res = disk_client.post("/api/rename/preview", json=_tmdb_write_payload())
    assert res.status_code == 200, res.text
    row = res.json()["results"][0]
    # 故障被分类成 unavailable, 不是静默假装没事(disabled / matched)
    assert row["tmdb_status"] == "unavailable"
    assert row["tmdb_match"] is None
    assert row["new_filename"] == "Test Show - S01E02 - .mkv"

    res = disk_client.post("/api/rename/execute", json=_tmdb_write_payload())
    assert res.status_code == 200, res.text
    row = res.json()["results"][0]
    # 重命名照做, 且真的落到盘上 —— 没有 {title} 的回落文件名
    assert row["success"] is True
    assert row["new_filename"] == "Test Show - S01E02 - .mkv"
    assert row["new_path"] == str(tmp_path / "Test Show - S01E02 - .mkv")
    assert os.path.isfile(str(tmp_path / "Test Show - S01E02 - .mkv"))
    assert not os.path.isfile(str(tmp_path / "Test.Show.S01E02.mkv"))


def test_tmdb_override_selects_that_tv_id_and_skips_search(client, override_only_tmdb):
    # tmdb_overrides 是「预览表里手动重选」这条能力的**唯一承载**: 它若静默失效,
    # 用户点了重选却毫无反应 —— 这正是 spec 对这类失灵点名的措辞。
    # 此前唯一发送该字段的用例跑在 disabled 路径上（TmdbResolver 根本不会被构造）,
    # 所以删掉 renamer.py 里 overrides=req.tmdb_overrides 那一处传递, 全套测试全绿。
    # 这里用 9999（自动搜索会返回 1396）让两条路径可区分。
    row = preview(client, template=TITLE_TEMPLATE,
                  tmdb_overrides={"Test Show": 9999})
    assert row["tmdb_status"] == "matched"
    assert row["tmdb_match"]["tv_id"] == 9999
    # 既然请求体已指定 tv_id, 就不该再去搜索 —— 否则用户的重选会被自动匹配盖掉
    assert override_only_tmdb.search_calls == 0
    assert row["title"] == "Breakage"


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


def _recording_client_cls(sink):
    """能记录构造实参的离线替身。

    monkeypatch 的是 `api/tmdb.py` 里那个 `TmdbClient` —— build_tmdb_client
    在**调用时**按模块全局查找它, 所以钉在这里既能看见「用哪个 Key 构造」,
    也能看见「到底有没有被构造」, 且全程不出网。
    """

    class _RecordingTmdbClient(_FakeTmdbClient):
        def __init__(self, api_key, language, timeout=0):
            sink["api_key"] = api_key
            sink["language"] = language
            sink["constructed"] = True

    return _RecordingTmdbClient


def test_blank_request_key_falls_back_to_env_key(client, monkeypatch):
    # findings 1: 设置页的提示「留空则用服务端 .env 的配置」必须为真。
    # 空串是「未提供」而不是「用户提供了一把空 Key」—— 用 `is not None` 判断会
    # 把空串当成已提供, key 为空 → 返回 None → **静默禁用 TMDB**, 而界面说它会
    # 回退到 .env。Docker 部署(只配 .env、不经界面填 Key)正是这么被破坏的。
    from app.config import settings
    from app.api import tmdb as tmdb_api

    sink = {}
    monkeypatch.setattr(settings, "tmdb_api_key", "from-env")
    monkeypatch.setattr(tmdb_api, "TmdbClient", _recording_client_cls(sink))

    row = preview(client, template=TITLE_TEMPLATE, tmdb_api_key="")
    assert row["tmdb_status"] == "matched"  # 没被短路成 disabled
    assert sink["api_key"] == "from-env"    # 用的是 .env 的那把


def test_request_key_overrides_env_key_on_rename(client, monkeypatch):
    # 优先级的另一半: 设置页填的值必须能盖掉 .env, 否则又是「设置不生效」。
    from app.config import settings
    from app.api import tmdb as tmdb_api

    sink = {}
    monkeypatch.setattr(settings, "tmdb_api_key", "from-env")
    monkeypatch.setattr(tmdb_api, "TmdbClient", _recording_client_cls(sink))

    preview(client, template=TITLE_TEMPLATE, tmdb_api_key="from-request")
    assert sink["api_key"] == "from-request"


def test_blank_request_language_falls_back_to_env_language(client, monkeypatch):
    # 语言与 Key 同一套优先级 —— 前端 store 里 language 被归一化过, 但老客户端
    # 或手改过的 localStorage 仍可能发出空串。
    from app.config import settings
    from app.api import tmdb as tmdb_api

    sink = {}
    monkeypatch.setattr(settings, "tmdb_api_key", "from-env")
    monkeypatch.setattr(settings, "tmdb_language", "zh-CN")
    monkeypatch.setattr(tmdb_api, "TmdbClient", _recording_client_cls(sink))

    preview(client, template=TITLE_TEMPLATE, tmdb_api_key="k", tmdb_language="")
    assert sink["language"] == "zh-CN"


def test_request_disable_wins_over_key(client, monkeypatch):
    # findings 2: 设置页的「启用 TMDB 元数据」勾选框必须真的生效。
    # 取消勾选前它是死设置 —— 写进 localStorage 却没人读, 全程零报错。
    from app.api import tmdb as tmdb_api

    sink = {}
    monkeypatch.setattr(tmdb_api, "TmdbClient", _recording_client_cls(sink))

    row = preview(client, template=TITLE_TEMPLATE,
                  tmdb_api_key="from-request", tmdb_enabled=False)
    assert row["tmdb_status"] == "disabled"
    assert row["tmdb_match"] is None
    # 连客户端都没构造 = 一个网络请求都不会发出去
    assert sink.get("constructed") is None
    # 关闭的是 TMDB, 不是重命名本身(spec §5.4)
    assert row["new_filename"] == "Test Show - S01E02 - .mkv"


def test_server_side_disable_beats_request_enable(client, monkeypatch):
    # 服务端的 tmdb_enabled 为假时压过用户的勾选 —— 与 /api/tmdb/test 报的
    # disabled 是同一语义, 否则那个总开关对 preview/execute 形同虚设。
    from app.config import settings
    from app.api import tmdb as tmdb_api

    sink = {}
    monkeypatch.setattr(settings, "tmdb_enabled", False)
    monkeypatch.setattr(tmdb_api, "TmdbClient", _recording_client_cls(sink))

    row = preview(client, template=TITLE_TEMPLATE,
                  tmdb_api_key="from-request", tmdb_enabled=True)
    assert row["tmdb_status"] == "disabled"
    assert sink.get("constructed") is None

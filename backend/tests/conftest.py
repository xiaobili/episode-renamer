import pytest

from app.config import settings
from app.core import tmdb_resolver


@pytest.fixture(autouse=True)
def _no_ambient_tmdb(monkeypatch):
    """钉死 TMDB 配置，使整套测试与运行环境无关。

    `Settings` 会读 `.env` 与环境变量（config.py 的 env_file=".env"），而 `.env`
    是本设计支持的一个配置来源。若某台机器上配了 key，没显式传 tmdb_api_key 的
    用例就会真的去打 api.themoviedb.org —— 单元套件不得依赖外网，也不得依赖
    运行环境的偶然状态。

    放在 conftest 里 autouse，是为了让**将来新增**的用例自动继承这道约束，
    而不是靠每条用例记得自己传 tmdb_api_key。

    需要「环境里有 key」的用例（Task 4 的 test_header_key_overrides_env_key 之类）
    在用例内部再 monkeypatch 一次即可 —— autouse 夹具先执行，用例内的覆盖生效。
    """
    monkeypatch.setattr(settings, "tmdb_api_key", "")
    monkeypatch.setattr(settings, "tmdb_enabled", True)


@pytest.fixture(autouse=True)
def _isolate_default_cache():
    """逐例清空进程级默认缓存, 否则用例之间会互相污染。

    `_DEFAULT_CACHE` 是刻意的进程级共享（生产里预览接口每次按键都会调 resolve_many,
    缓存不跨 resolver 实例就等于没有）。但测试里它是跨用例的全局状态: 凡是不传
    `cache=` 的用例都写同一批键（FakeClient 的指纹与语言是常量), 于是先跑的用例
    填充的命中会让后跑的用例根本打不到假客户端 —— 断言请求次数的用例会以
    「结果看着合理但其实是旧的」的方式失败, 而不是报错。

    monkeypatch 在这里帮不上忙: 缓存对象在模块导入时就已绑定, 测试要清的是它的内容。

    原先只放在 test_tmdb_resolver.py 里, 但它保护的范围不止那个文件 ——
    test_rename_routes.py 的用例同样共用这个缓存, 所以搬到这里对全套生效。
    """
    tmdb_resolver._DEFAULT_CACHE.clear()
    yield
    tmdb_resolver._DEFAULT_CACHE.clear()

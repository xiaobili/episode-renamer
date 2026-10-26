"""OpenList 流式上传的判据。

异步驱动用标准库 asyncio.run —— 本项目未装 pytest-asyncio（理由见
tests/test_openlist_single.py 的模块注释）。
"""
import asyncio
from urllib.parse import quote

import httpx

import app.core.openlist_client as mod


class _FakeAsyncClient:
    """记录每次请求的假 httpx.AsyncClient。"""

    calls: list = []
    response: dict = {}

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def request(self, method, url, **kwargs):
        _FakeAsyncClient.calls.append((method, url, kwargs))
        return httpx.Response(
            200, json=_FakeAsyncClient.response,
            request=httpx.Request(method, url),
        )


def _client(monkeypatch, response):
    client = mod.OpenListClient("http://x", "u", "p")
    client.token = "token-1"
    # 请求间隔归零: 默认 0.5s 会让这条纯单元用例白等。
    client.apply_limits(request_interval=0.0)
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.response = response
    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeAsyncClient)
    return client


def test_put_file_calls_stream_endpoint_with_encoded_path(monkeypatch):
    client = _client(monkeypatch, {"code": 200, "data": None})

    asyncio.run(client.put_file("/媒体/Show - S01E01.nfo", b"<x/>"))

    method, url, kwargs = _FakeAsyncClient.calls[0]
    assert method == "PUT"
    assert url == "http://x/api/fs/put"
    assert kwargs["headers"]["File-Path"] == quote("/媒体/Show - S01E01.nfo", safe="")
    assert kwargs["headers"]["Authorization"] == "token-1"
    assert kwargs["headers"]["Content-Type"] == "application/xml; charset=utf-8"
    assert kwargs["headers"]["Content-Length"] == str(len(b"<x/>"))
    assert kwargs["content"] == b"<x/>"


def test_put_file_raises_on_non_200_code(monkeypatch):
    client = _client(monkeypatch, {"code": 500, "message": "permission denied"})

    try:
        asyncio.run(client.put_file("/媒体/a.nfo", b"<x/>"))
    except Exception as exc:  # noqa: BLE001 —— 断言的是消息内容
        assert "permission denied" in str(exc)
    else:
        raise AssertionError("非 200 的 code 必须抛错")

"""限流器必须真的限流，且上限可运行时调整。

异步驱动用**标准库 asyncio.run** —— 本项目未装 pytest-asyncio（理由与写法见
tests/test_openlist_single.py 的模块注释）。
"""
import asyncio

import httpx

from app.core.openlist_client import OpenListClient, _AdaptiveLimiter


def test_limiter_never_exceeds_limit():
    async def _run():
        limiter = _AdaptiveLimiter(2)
        peak = 0
        active = 0

        async def worker():
            nonlocal peak, active
            async with limiter:
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(*[worker() for _ in range(10)])
        return peak

    peak = asyncio.run(_run())
    assert peak == 2, f"峰值并发 {peak}，上限 2 未被遵守"


def test_limit_can_be_lowered_at_runtime():
    """调低之后必须**立刻**生效 —— 这是设置页「立即生效」的全部含义。"""
    async def _run():
        limiter = _AdaptiveLimiter(5)
        limiter.set_limit(1)
        peak = 0
        active = 0

        async def worker():
            nonlocal peak, active
            async with limiter:
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(*[worker() for _ in range(6)])
        return peak

    peak = asyncio.run(_run())
    assert peak == 1, f"调低后峰值并发 {peak}，期望 1"


def test_limit_can_be_raised_at_runtime():
    """调高时必须把等待者**全部**唤醒，否则多出来的名额要等下一轮释放才生效。

    判据是 `set_limit` 返回**那一刻**队列里还剩几个等待者 —— 同步可观测, 不依赖
    时序: 调高到 3 而此刻只有 1 个在跑, 队列里的 2 个必须当场被全部摘走。
    `_wake(1)` 会留下 1 个 → 红; 一个都不唤醒 → 留下 2 个 → 红。

    **不用「峰值 == 3」当判据**: 那要求唤醒发生在持有者那 0.05s 睡眠之内, 被 OS
    级调度停顿 50ms 以上就会偶发变成 2（实测 20/20 稳定, 但它依赖时序）。
    峰值只留作附加的健全性检查。
    """
    async def _run():
        limiter = _AdaptiveLimiter(1)
        active = 0
        peak = 0
        started = asyncio.Event()

        async def worker():
            nonlocal active, peak
            async with limiter:
                active += 1
                peak = max(peak, active)
                if active == 1:
                    started.set()
                await asyncio.sleep(0.05)
                active -= 1

        tasks = [asyncio.create_task(worker()) for _ in range(3)]
        await started.wait()
        # 让另外两个确定地排进等待队列（create_task 只是调度, 未必已运行）
        await asyncio.sleep(0.01)
        limiter.set_limit(3)
        # **同步观测**: 此处还没有 await, 被唤醒者尚未运行
        remaining = len(limiter._waiters)
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=1.0)
        return peak, remaining

    peak, remaining = asyncio.run(_run())
    assert remaining == 0, f"调高后仍有 {remaining} 个等待者没被唤醒"
    assert peak >= 2, f"调高后峰值并发仍为 {peak}，等待者未被唤醒"


def test_reconnect_does_not_deadlock_at_limit_one(monkeypatch):
    """401 重连时**不得**持着名额再要名额 —— limit=1 下那会永久挂住。

    这是 `_request` 这条路径的**第一个**判据。把实现改回「持着名额递归调用
    自己」（旧版形状）本用例会挂到 `wait_for` 超时 —— 超时即红, 不是断言失败。

    用假的 `httpx.AsyncClient` 喂**四次**响应, 按 `_request` 的真实调用序列:
    401（token 过期）→ login 成功 → **login 内部的 `_discover_mounts` 列根目录**
    → 带新 token 重试成功。`login` 读取 token 的字段名以 `openlist_client.py`
    为准（`data["data"]["token"]`, 回退 `data["token"]`）。

    （第四次调用是实测出来的: 骨架只列了三次, 漏掉 `login` 结尾那句
    `await self._discover_mounts()` —— 少列会在第四次 `pop` 时 IndexError,
    红的原因就不是死锁了。）
    """
    import app.core.openlist_client as mod

    class _FakeAsyncClient:
        responses: list = []
        calls: list = []

        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def request(self, method, url, **kwargs):
            _FakeAsyncClient.calls.append((method, url))
            status, payload = _FakeAsyncClient.responses.pop(0)
            return httpx.Response(status, json=payload, request=httpx.Request(method, url))

    async def _run():
        client = mod.OpenListClient("http://x", "u", "p")
        client.token = "expired-token"
        client.apply_limits(max_concurrent=1)
        _FakeAsyncClient.calls = []
        _FakeAsyncClient.responses = [
            (401, {}),                                       # 1. 第一次: token 过期
            (200, {"code": 200, "data": {"token": "new"}}),  # 2. login
            (200, {"code": 200, "data": {"content": []}}),   # 3. login 内的 _discover_mounts
            (200, {"code": 200, "data": {"ok": True}}),      # 4. 重试
        ]
        monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeAsyncClient)
        # 超时即红: 死锁时这个 await 永远不会返回
        return await asyncio.wait_for(client._request("POST", "/api/fs/get"), timeout=2.0)

    data = asyncio.run(_run())
    assert data == {"code": 200, "data": {"ok": True}}
    assert len(_FakeAsyncClient.calls) == 4, _FakeAsyncClient.calls


def test_apply_limits_is_a_noop_when_unchanged():
    """值没变就不动 —— 每次请求都替换限流器会摧毁限流本身（spec R13）。

    **两个方向都要钉**:
    · 字段为 None（未提供）→ 不动;
    · 字段**等于当前值** → 也不动。

    只钉前者的判据对「apply_limits 在值非 None 时重建 limiter」这一变异是
    **失明的** —— 而那正是本任务存在的理由（spec R13）。实测: 去掉下面第二段,
    把 `self._limiter.set_limit(...)` 写成 `self._limiter = _AdaptiveLimiter(...)`
    时五条判据全绿。
    """
    client = OpenListClient("http://x", "u", "p")
    before = client._limiter
    client.apply_limits(max_concurrent=None, request_interval=None)
    assert client._limiter is before, "未提供时不该动 limiter"

    # 传**当前值**（而非 None）—— 这一条才拦得住「重建」那种写法
    client.apply_limits(
        max_concurrent=before._limit,
        request_interval=client._request_interval,
    )
    assert client._limiter is before, "值未变时不该重建 limiter"


def test_apply_limits_sets_interval():
    client = OpenListClient("http://x", "u", "p")
    client.apply_limits(request_interval=1.25)
    assert client._request_interval == 1.25

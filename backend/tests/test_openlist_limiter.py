"""限流器必须真的限流，且上限可运行时调整。

异步驱动用**标准库 asyncio.run** —— 本项目未装 pytest-asyncio（理由与写法见
tests/test_openlist_single.py 的模块注释）。
"""
import asyncio

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
    """调高时必须唤醒等待者，否则它们会永远睡着（notify 漏掉的典型形态）。"""
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
        limiter.set_limit(3)
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=1.0)
        return peak

    peak = asyncio.run(_run())
    assert peak >= 2, f"调高后峰值并发仍为 {peak}，等待者未被唤醒"


def test_apply_limits_is_a_noop_when_unchanged():
    """值没变就不动 —— 每次请求都替换限流器会摧毁限流本身（spec R13）。"""
    client = OpenListClient("http://x", "u", "p")
    before = client._limiter
    client.apply_limits(max_concurrent=None, request_interval=None)
    assert client._limiter is before


def test_apply_limits_sets_interval():
    client = OpenListClient("http://x", "u", "p")
    client.apply_limits(request_interval=1.25)
    assert client._request_interval == 1.25

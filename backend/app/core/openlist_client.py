from __future__ import annotations

import asyncio
import time
from typing import Optional
from datetime import datetime

import httpx

from ..config import settings
from ..models.openlist import OpenListConnection, OpenListFile, RenameObject


class _AdaptiveLimiter:
    """上限可变的并发限流器。

    为什么不用 asyncio.Semaphore 再「需要时换一个」: 替换对象会摧毁限流本身 ——
    在途持有者释放到旧对象, 新对象满额放行, 于是瞬时并发翻倍; 而「值没变就不
    替换」的补丁仍在首个请求处留下抖动。计数器 + 等待者队列是十几行代码,
    且上限可以在等待者入睡之后被调高（被唤醒的等待者重新判条件）。

    等待者用 Future 而不是 asyncio.Condition: Condition.notify* 必须在**持有
    锁**时调用, 而 set_limit 是同步方法（apply_limits 也可以从同步上下文调用,
    见 tests 里 `limiter.set_limit(1)` 这种写法）, 同步方法没有办法不阻塞事件
    循环地拿到 asyncio.Lock —— 直接 notify 会抛
    `RuntimeError: cannot notify on un-acquired lock`。Future 由事件循环线程
    直接 set_result, 同步、即时, 且在没有等待者（也就没有运行中的循环）时天然
    是安全的空操作。
    """

    def __init__(self, limit: int):
        self._limit = max(1, int(limit))
        self._active = 0
        self._waiters: list[asyncio.Future] = []

    async def __aenter__(self):
        while self._active >= self._limit:
            waiter = asyncio.get_running_loop().create_future()
            self._waiters.append(waiter)
            try:
                await waiter
            except BaseException:
                # 被取消。若这个等待者已经吃掉了 _wake 发出的唤醒名额（它已被
                # 摘出队列 = 名额已发到它手上），必须把名额转交给下一个等待者,
                # 否则名额空着而后面的人还在睡 —— 这是真实可复现的丢唤醒, 不是
                # 理论担忧。asyncio.Lock 在取消路径上做的也是同一件事。
                if waiter not in self._waiters:
                    self._wake(1)
                raise
            finally:
                # 正常唤醒时已被 _wake 摘掉; 未被唤醒（取消）时还留在队列里, 自己摘。
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
        # 判断与自增之间没有 await ⇒ 与其它任务之间是原子的。
        self._active += 1
        return self

    async def __aexit__(self, *exc_info):
        self._active -= 1
        self._wake(1)

    def set_limit(self, limit: int) -> None:
        limit = max(1, int(limit))
        # 值未变就直接返回。这道早退行为上不可观测: 队列非空时必然
        # _active >= _limit, 故 limit == _limit 时下面的 limit > _active 恒为假,
        # 不会误唤醒任何人。留着是让「值没变」这件事在代码里看得见 ——
        # 别为它写判据（写不出能红的）。
        if limit == self._limit:
            return
        self._limit = limit
        # 调高后必须唤醒等待者: 它们在旧的（更小的）上限下已入睡, 不会再自己醒。
        if limit > self._active:
            self._wake(limit - self._active)

    def _wake(self, count: int) -> None:
        """唤醒至多 count 个等待者。

        被唤醒者会重新判条件, 抢不到名额的会再排队 —— 而每次释放都会再唤醒
        一个, 所以不存在「有人睡着但名额空着」的窗口。
        """
        while count > 0 and self._waiters:
            waiter = self._waiters.pop(0)
            if waiter.done():
                continue  # 已被取消
            waiter.set_result(None)
            count -= 1


class OpenListClient:
    def __init__(self, server_url: str, username: str, password: str):
        self.server_url = server_url.rstrip("/")
        self.username = username
        self.password = password
        self.token: Optional[str] = None
        self.connected = False
        self.mount_points: list[str] = []
        self.write_access: bool = True
        self.last_request_time = 0.0
        self._limiter = _AdaptiveLimiter(settings.openlist_max_concurrent)
        # 间隔值放在**实例**上（原来是每次读全局 settings）, 否则设置页的值无法
        # 在运行时生效 —— 见 spec §7.2。
        self._request_interval = settings.openlist_request_interval
        self._lock = asyncio.Lock()

    async def _wait_interval(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_request_time
        if elapsed < self._request_interval:
            await asyncio.sleep(self._request_interval - elapsed)

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """发一次请求（401 时自动重连后重试一次）。

        **限流器只包住单次 HTTP 尝试, 不包住重连** —— 这是刻意的, 也是本次
        重构的全部理由: `_reconnect` 会走 `login` → `_request`, 也就是**在持着
        名额的情况下再要一个名额**。在途请求数已达上限时（每个都撞上 401）
        外层名额永不释放、内层永远拿不到 —— 死锁。

        这不是新引入的: 旧版 `asyncio.Semaphore(settings.openlist_max_concurrent)`
        持着名额递归调用自己, 同样会死锁（默认 3 时, 3 个在途请求同时 401 即
        触发）。但本函数此前**没有任何测试**, 这条路径至今没有判据 —— 本次
        顺带补上（见 Step 1 的 test_reconnect_does_not_deadlock_at_limit_one）。

        与旧实现唯一的行为差异: 调用方传进来的 `headers` 现在**每次重试都会
        带上**（旧版 `kwargs.pop` 之后递归, 重试时只剩 Authorization）。仓库里
        没有任何调用方传 headers, 且新行为才是对的。
        """
        url = f"{self.server_url}{path}"
        headers = kwargs.pop("headers", {})

        while True:
            async with self._limiter:
                await self._wait_interval()

                req_headers = dict(headers)
                if self.token:
                    req_headers["Authorization"] = self.token

                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0), verify=False) as client:
                        resp = await client.request(method, url, headers=req_headers, **kwargs)
                        self.last_request_time = time.monotonic()
                        resp.raise_for_status()
                        return resp.json()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code != 401 or not self.token:
                        raise
                except httpx.RequestError as e:
                    raise ConnectionError(f"OpenList 请求失败: {e}") from e

            # 走到这里说明撞了 401 且 token 还在 —— **出了 limiter 再重连**。
            # 重连自己会发请求（login）, 在名额内做就会与外层争名额。
            await self._reconnect()

    def apply_limits(
        self,
        max_concurrent: Optional[int] = None,
        request_interval: Optional[float] = None,
    ) -> None:
        """把设置页的值应用到本客户端。None = 该字段未提供, 保持当前值。

        **已知副作用**: 限流参数设在进程级单例客户端上, 所以一次执行设下的值会
        持续生效到下次被覆盖 —— 之后的预览、扫描、列目录同样受它约束。单用户
        场景下可接受（设置页的值本就是用户想要的稳态）, 但它是隐性状态。
        """
        if max_concurrent is not None:
            self._limiter.set_limit(max_concurrent)
        if request_interval is not None:
            self._request_interval = request_interval

    async def login(self, otp_code: Optional[str] = None) -> OpenListConnection:
        body = {
            "username": self.username,
            "password": self.password,
        }
        if otp_code:
            body["otp_code"] = otp_code

        data = await self._request("POST", "/api/auth/login", json=body)

        if data.get("code") != 200:
            raise Exception(f"登录失败: {data.get('message')}")

        self.token = data.get("data", {}).get("token") or data.get("token")
        if not self.token:
            raise Exception("登录响应中无 token")

        self.connected = True
        await self._discover_mounts()

        return OpenListConnection(
            server_url=self.server_url,
            connected=True,
            token=self.token,
            mount_points=self.mount_points,
            username=self.username,
            last_check=datetime.now(),
            write_access=self.write_access,
        )

    async def _discover_mounts(self) -> None:
        data = await self._request("POST", "/api/fs/list", json={"path": "/", "password": "", "refresh": False})

        content = (data.get("data") or {}).get("content", [])
        self.mount_points = [
            f"/{c['name']}" for c in content
            if c.get("is_dir", True) or c.get("type") == 1
        ]

    async def _reconnect(self) -> None:
        # 先清 token: 它正是引起这次重连的那个**已知无效**的值。不清的话,
        # login 自己发出的那个请求还会带着它 —— 若 login 端点也回 401, 嵌套的
        # _request 会再次触发重连, 无限递归到 RecursionError（实测 329 次调用
        # 后崩）。旧实现在这里会**先死锁**, 所以这条路径此前从未被观察到 ——
        # 是 _request 的重构（把重连移出限流器）把它暴露出来的。
        self.token = None
        self.connected = False
        await self.login()

    async def test_connection(self) -> bool:
        try:
            if not self.token:
                await self.login()
            else:
                data = await self._request("POST", "/api/fs/get", json={"path": "/", "password": ""})
                if data.get("code") == 200:
                    self.connected = True
        except Exception:
            self.connected = False
        return self.connected

    async def list_directory(self, path: str, refresh: bool = False) -> tuple[list[OpenListFile], bool]:
        print(f"[DEBUG] list_directory(path={path!r})")
        data = await self._request(
            "POST", "/api/fs/list",
            json={"path": path, "password": "", "refresh": refresh},
        )
        print(f"[DEBUG] list_directory response code={data.get('code')}")
        if data.get("code") != 200:
            print(f"[DEBUG] list_directory error: {data.get('message')}")
            raise Exception(f"列出目录失败: {data.get('message')}")

        payload = data.get("data") or {}
        write_access = payload.get("write", True)
        content = payload.get("content") or []
        print(f"[DEBUG] list_directory path={path!r} content_count={len(content)} write={write_access}")
        for c in content[:3]:
            print(f"[DEBUG]   entry: name={c.get('name')!r} is_dir={c.get('is_dir')} type={c.get('type')} path={c.get('path')!r}")
        if len(content) > 3:
            print(f"[DEBUG]   ... ({len(content)-3} more)")

        files = []
        for c in content:
            raw_path = c.get("path") or ""
            if not raw_path:
                raw_path = f"{path.rstrip('/')}/{c.get('name', '')}"
            files.append(
                OpenListFile(
                    name=c.get("name", ""),
                    size=c.get("size", 0),
                    is_dir=c.get("is_dir", c.get("type") == 1),
                    path=raw_path,
                    type=c.get("type", 0),
                    sign=c.get("sign", ""),
                    thumb=c.get("thumb", ""),
                    raw_url=c.get("raw_url", ""),
                    modified=c.get("modified"),
                    created=c.get("created"),
                    provider=c.get("provider"),
                )
            )

        return files, write_access

    async def get_file_info(self, path: str) -> OpenListFile:
        data = await self._request(
            "POST", "/api/fs/get",
            json={"path": path, "password": ""},
        )

        if data.get("code") != 200:
            raise Exception(f"获取文件信息失败: {data.get('message')}")

        c = data.get("data") or {}
        return OpenListFile(
            name=c.get("name", ""),
            size=c.get("size", 0),
            is_dir=c.get("is_dir", c.get("type") == 1),
            path=c.get("path", path),
            type=c.get("type", 0),
            raw_url=c.get("raw_url", ""),
            provider=c.get("provider"),
        )

    async def batch_rename(self, src_dir: str, rename_objects: list[RenameObject]) -> dict:
        data = await self._request(
            "POST", "/api/fs/batch_rename",
            json={
                "src_dir": src_dir,
                "rename_objects": [r.model_dump() for r in rename_objects],
            },
        )

        if data.get("code") != 200:
            raise Exception(f"批量重命名失败: {data.get('message')}")

        return data

    async def rename(self, path: str, new_name: str) -> dict:
        data = await self._request(
            "POST", "/api/fs/rename",
            json={"path": path, "name": new_name},
        )

        if data.get("code") != 200:
            raise Exception(f"重命名失败: {data.get('message')}")

        return data

    async def move(self, src_dir: str, dst_dir: str, names: list[str]) -> dict:
        data = await self._request(
            "POST", "/api/fs/move",
            json={"src_dir": src_dir, "dst_dir": dst_dir, "names": names},
        )

        if data.get("code") != 200:
            raise Exception(f"移动失败: {data.get('message')}")

        return data

    async def mkdir(self, parent_dir: str, dir_name: str) -> dict:
        data = await self._request(
            "POST", "/api/fs/mkdir",
            json={"path": parent_dir, "name": dir_name},
        )

        if data.get("code") != 200:
            raise Exception(f"创建目录失败: {data.get('message')}")

        return data

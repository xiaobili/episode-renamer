from __future__ import annotations

import asyncio
import time
from typing import Optional
from datetime import datetime

import httpx

from ..config import settings
from ..models.openlist import OpenListConnection, OpenListFile, RenameObject


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
        self._semaphore = asyncio.Semaphore(settings.openlist_max_concurrent)
        self._lock = asyncio.Lock()

    async def _wait_interval(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_request_time
        if elapsed < settings.openlist_request_interval:
            await asyncio.sleep(settings.openlist_request_interval - elapsed)

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with self._semaphore:
            await self._wait_interval()

            url = f"{self.server_url}{path}"
            headers = kwargs.pop("headers", {})
            if self.token:
                headers["Authorization"] = self.token

            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0), verify=False) as client:
                    resp = await client.request(method, url, headers=headers, **kwargs)
                    self.last_request_time = time.monotonic()
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401 and self.token:
                    await self._reconnect()
                    return await self._request(method, path, **kwargs)
                raise
            except httpx.RequestError as e:
                raise ConnectionError(f"OpenList 请求失败: {e}") from e

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

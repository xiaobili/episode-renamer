from fastapi import APIRouter, HTTPException
from datetime import datetime

from ..models.api import OpenListLoginRequest
from ..core.openlist_client import OpenListClient
from .scanner import register_client, get_client, get_default_client

router = APIRouter(prefix="/api/openlist", tags=["openlist"])


@router.post("/login")
async def login(req: OpenListLoginRequest):
    client = OpenListClient(req.server_url, req.username, req.password)
    try:
        conn = await client.login(req.otp_code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 同一服务器 + 账号重新登录时, 旧客户端持有的连接池必须显式关掉: 客户端
    # 现在自带一条复用的 httpx 连接（见 `_http_client`）, 直接覆盖字典会把它
    # 连同 socket 一起丢掉, 只能等 GC。
    previous = get_client(client.server_url, client.username)
    if previous is not None and previous is not client:
        await previous.aclose()
    register_client(client)

    return {
        "success": True,
        "token": conn.token,
        "mount_points": conn.mount_points,
        "username": conn.username,
        "server_url": conn.server_url,
    }


@router.post("/test")
async def test_connection(req: OpenListLoginRequest):
    client = OpenListClient(req.server_url, req.username, req.password)
    try:
        conn = await client.login(req.otp_code)
        return {
            "success": True,
            "connected": conn.connected,
            "mount_points": conn.mount_points,
            "write_access": conn.write_access,
        }
    except Exception as e:
        return {"success": False, "connected": False, "error": str(e)}
    finally:
        # 试连用的是一次性客户端, 用完就关: 它的连接池没有别人会用。
        await client.aclose()


@router.get("/status")
async def connection_status():
    client = get_default_client()
    if not client:
        return {"success": True, "connected": False, "message": "未连接"}

    return {
        "success": True,
        "connected": client.connected,
        "server_url": client.server_url,
        "username": client.username,
        "mount_points": client.mount_points,
        "write_access": client.write_access,
    }


@router.get("/mounts")
async def get_mounts():
    client = get_default_client()
    if not client or not client.connected:
        raise HTTPException(status_code=401, detail="请先连接 OpenList")

    if not client.mount_points:
        try:
            await client.test_connection()
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    return {"success": True, "mount_points": client.mount_points}


@router.post("/logout")
async def logout():
    from .scanner import _openlist_clients
    # 先关连接池再清字典: 断开之后没人会再用这些客户端, 留着 socket 只是泄漏。
    for client in list(_openlist_clients.values()):
        await client.aclose()
    _openlist_clients.clear()
    return {"success": True, "message": "已断开连接"}


@router.post("/browse")
async def browse_directory(req: dict):
    client = get_default_client()
    if not client or not client.connected:
        raise HTTPException(status_code=401, detail="请先连接 OpenList")

    path = req.get("path") or "/"
    try:
        files, write_access = await client.list_directory(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dirs = [
        {"name": f.name, "path": f.path, "type": f.type}
        for f in files if f.is_dir
    ]
    return {
        "success": True,
        "path": path,
        "dirs": dirs,
        "write_access": write_access,
        "parent": str(path).rstrip("/").rsplit("/", 1)[0] if path != "/" and path != "" else "/",
    }

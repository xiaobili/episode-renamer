"""STRM 生成的工作参数与落点模型。

`mode` 用 Literal 而不是普通 str: 非法值要在请求校验阶段就 422, 而不是等到
落点推导里走进一个「未知模式」分支 —— 那种分支在界面上表现为「勾了但什么都没
发生」, 用户查不出原因。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

StrmMode = Literal["local", "remote_custom", "remote_same"]


class StrmOptions(BaseModel):
    enabled: bool = False
    mode: StrmMode = "remote_same"
    # 播放器侧可访问的地址。留空时路由回落 client.server_url —— 容器里的
    # localhost:5244 播放器是访问不到的, 所以它必须是可覆盖的。
    base_url: str = ""
    local_root: str = ""
    remote_root: str = ""


class StrmTarget(BaseModel):
    """一条 strm 的落点与内容来源。"""

    mode: str
    path: str
    url: str

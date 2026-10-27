from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ShowFolderPlan(BaseModel):
    """一部剧的剧集文件夹改名计划。

    `reason` 非空即「不改」—— 与 `NfoDecision`/`StrmTarget` 同构：**拒绝也是结果**，
    必须能报出来（留白等于静默，用户会以为改了或以为没勾）。
    """
    # 解析出来的剧名（分组键）。**不是**目标名 —— 目标名在 new_path 的末段。
    show_name: str = ""
    old_path: str
    new_path: str = ""
    # 目标目录名（末段），OpenList 的 /api/fs/rename 要的是「新名字」而不是新路径。
    target_name: str = ""
    reason: Optional[str] = None
    file_ids: list[str] = Field(default_factory=list)

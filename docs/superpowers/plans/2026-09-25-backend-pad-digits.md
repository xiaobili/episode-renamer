# 补零位数请求级生效 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让前端的「集数补零位数 / 季数补零位数」设置真正生效 —— 当前后端从 `config.py` 读全局常量，请求里无处可传，前端改动永远无效。

**Architecture:** 引入一个不可变的 `PadConfig` 值对象，沿 `apply_template` → `build_rename_plan` → 路由 的调用链向下透传。所有新参数默认 `None`，`None` 表示回退到 `config.py` 的全局默认值，因此对现有调用方完全向后兼容。

**Tech Stack:** Python 3.9+ / FastAPI / Pydantic 2 / pytest

**Spec:** `docs/superpowers/specs/2026-09-25-frontend-refactor-design.md`（§13 后端改动、§17 风险与遗留）

## Global Constraints

- 补零位数合法区间 `[1, 6]`，越界值钳制而非报错（spec §13.2）
- 所有新参数默认 `None`；`None` = 回退 `settings.episode_pad_digits` / `settings.season_pad_digits`（spec §13.2）
- 不修改 `app/config.py` 的默认值（保持 `2`）
- 不修改 `app/models/api.py` 中除两个 Request 模型以外的任何模型
- 不得改动 API 路径、方法、响应结构
- 仅新增 `pytest` 为开发依赖，`requirements.txt` 运行时依赖不变

## Review Focus

以下是 spec 隐含但未被任何测试点名、且最可能咬到真实用户的输入，各自的测试已挂在拥有该代码的任务里：

1. **补零位数传 0 或负数** —— 用户在前端数字框里清空后留下 `0`，或输入 `-1`。`str(-1).zfill(2)` 得到 `"-1"`，会产出 `Show - S01E-1.mkv` 这类损坏文件名。期望：钳制到 `1`，产出 `E1`。
2. **补零位数传超大值** —— 用户输入 `99`。期望：钳制到 `6`，而不是生成 99 位补零的文件名。
3. **只传其中一个字段** —— 用户只改集数补零位数、不动季数。期望：集数用请求值，季数退回全局默认，两者互不影响。
4. **老客户端不传任何 pad 字段** —— 现有 API 调用方（无 pad 字段）。期望：行为与改动前逐字节一致。
5. **`{episode}`（未补零）与 `{episode_padded}` 同模板共存** —— 补零位数只应影响 `_padded` 变量。期望：`{episode}` 仍输出 `2`，`{episode_padded}` 输出 `002`。

## File Structure

| 文件 | 职责 | 本次改动 |
|---|---|---|
| `backend/app/core/template.py` | 模板变量解析与渲染 | 新增 `PadConfig`；`_resolve_variable` / `apply_template` / `apply_folder_template` 接受 `pad`；删除死函数 `generate_full_path` |
| `backend/app/models/api.py` | 请求/响应模型 | 两个 Request 模型各加两个可选字段 |
| `backend/app/core/local_renamer.py` | 本地重命名计划与执行 | `build_rename_plan` / `batch_rename` 接受并透传 `pad`；删除未使用的 import |
| `backend/app/core/openlist_renamer.py` | OpenList 重命名计划 | `build_openlist_rename_plan` 接受并透传 `pad` |
| `backend/app/api/renamer.py` | 三个重命名路由 | 从请求构造 `PadConfig` 并透传 |
| `backend/tests/` | 测试 | 新建 |

---

### Task 1: 测试设施 + `PadConfig` 值对象

建立 pytest 设施，并实现带钳制的 `PadConfig`。这是唯一一处纯函数式的边界校验逻辑，先测后写。

**Files:**
- Create: `backend/requirements-dev.txt`
- Create: `backend/pytest.ini`
- Create: `backend/tests/test_pad_config.py`
- Modify: `backend/app/core/template.py`（在文件顶部 import 区之后新增 `PadConfig`）

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: `app.core.template.PadConfig` —— 不可变 dataclass，字段 `episode: int`、`season: int`，构造时各自钳制到 `[1, 6]`

- [ ] **Step 1: 建测试设施**

创建 `backend/requirements-dev.txt`：

```
pytest>=8.0.0
```

创建 `backend/pytest.ini`：

```ini
[pytest]
testpaths = tests
pythonpath = .
```

创建空文件 `backend/tests/__init__.py`。

安装：

```bash
cd backend && pip install -r requirements-dev.txt
```

- [ ] **Step 2: 写失败的测试**

创建 `backend/tests/test_pad_config.py`：

```python
import pytest

from app.core.template import PadConfig


def test_pad_config_stores_in_range_values():
    pad = PadConfig(episode=3, season=1)
    assert pad.episode == 3
    assert pad.season == 1


def test_pad_config_is_frozen():
    pad = PadConfig(episode=2, season=2)
    with pytest.raises(Exception):
        pad.episode = 5


def test_episode_zero_is_clamped_to_one():
    # 用户清空数字框后留下 0：str(0).zfill(2) == "00" 尚可,
    # 但 0 作为补零位数无意义，统一钳到 1
    assert PadConfig(episode=0, season=2).episode == 1


def test_episode_negative_is_clamped_to_one():
    # str(-1).zfill(2) == "-1" -> 会产出 Show - S01E-1.mkv 这类损坏文件名
    assert PadConfig(episode=-1, season=2).episode == 1


def test_episode_oversized_is_clamped_to_six():
    assert PadConfig(episode=99, season=2).episode == 6


def test_season_zero_is_clamped_to_one():
    assert PadConfig(episode=2, season=0).season == 1


def test_season_negative_is_clamped_to_one():
    assert PadConfig(episode=2, season=-3).season == 1


def test_season_oversized_is_clamped_to_six():
    assert PadConfig(episode=2, season=99).season == 6


def test_both_fields_clamped_independently():
    pad = PadConfig(episode=99, season=0)
    assert pad.episode == 6
    assert pad.season == 1
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_pad_config.py -v
```

预期：全部 FAIL，报 `ImportError: cannot import name 'PadConfig' from 'app.core.template'`

- [ ] **Step 4: 写最小实现**

编辑 `backend/app/core/template.py`。把第 1-7 行改为：

```python
from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import settings
from ..models.file import ParsedInfo
from .utils import safe_filename, pad_number, get_extension


PAD_MIN = 1
PAD_MAX = 6


@dataclass(frozen=True)
class PadConfig:
    """请求级补零位数。构造时钳制到 [PAD_MIN, PAD_MAX]。"""

    episode: int
    season: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "episode", max(PAD_MIN, min(PAD_MAX, self.episode)))
        object.__setattr__(self, "season", max(PAD_MIN, min(PAD_MAX, self.season)))
```

注意 `frozen=True` 下必须用 `object.__setattr__` 绕过冻结。`VARIABLE_PATTERN` 定义在下方，保持不动。

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_pad_config.py -v
```

预期：9 passed

- [ ] **Step 6: 提交**

```bash
git add backend/requirements-dev.txt backend/pytest.ini backend/tests/ backend/app/core/template.py
git commit -m "feat(backend): 引入 PadConfig 值对象与 pytest 设施"
```

---

### Task 2: 模板渲染接受 pad

让 `_resolve_variable` / `apply_template` / `apply_folder_template` 接受并透传 `pad`，同时删除死函数 `generate_full_path`。

**Files:**
- Modify: `backend/app/core/template.py:12-30`（`_resolve_variable`）
- Modify: `backend/app/core/template.py:48-68`（`apply_template`、`apply_folder_template`）
- Modify: `backend/app/core/template.py:71-85`（删除 `generate_full_path`）
- Modify: `backend/app/core/local_renamer.py:14`（删除未使用的 import）
- Create: `backend/tests/test_template_pad.py`

**Interfaces:**
- Consumes: `app.core.template.PadConfig`（Task 1）
- Produces:
  - `apply_template(template: str, info: ParsedInfo, include_extension: bool = True, pad: PadConfig | None = None) -> str`
  - `apply_folder_template(template: str, info: ParsedInfo, pad: PadConfig | None = None) -> str`
  - `generate_full_path` **被删除**，后续任务不得引用

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_template_pad.py`：

```python
from app.core.template import PadConfig, apply_template, apply_folder_template
from app.config import settings
from app.models.file import ParsedInfo

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"


def make_info():
    return ParsedInfo(
        show_name="Test Show",
        season=1,
        episode=2,
        extension=".mkv",
        original_filename="Test.Show.S01E02.mkv",
    )


def test_no_pad_falls_back_to_global_settings():
    # 向后兼容：pad=None 必须与改动前逐字节一致
    result = apply_template(TEMPLATE, make_info())
    assert result == "Test Show - S01E02.mkv"
    assert settings.episode_pad_digits == 2
    assert settings.season_pad_digits == 2


def test_explicit_pad_overrides_global_settings():
    pad = PadConfig(episode=3, season=1)
    result = apply_template(TEMPLATE, make_info(), pad=pad)
    assert result == "Test Show - S1E002.mkv"


def test_pad_does_not_affect_unpadded_variables():
    # {episode} 与 {episode_padded} 同模板共存时，只有后者受 pad 影响
    info = make_info()
    result = apply_template("{episode}|{episode_padded}", info, pad=PadConfig(episode=3, season=2))
    assert result == "2|002"


def test_folder_template_honours_pad():
    result = apply_folder_template(
        "Season {season_padded}", make_info(), pad=PadConfig(episode=2, season=3)
    )
    assert result == "Season 001"


def test_folder_template_without_pad_uses_globals():
    result = apply_folder_template("Season {season_padded}", make_info())
    assert result == "Season 02"


def test_pad_of_one_disables_padding():
    result = apply_template(TEMPLATE, make_info(), pad=PadConfig(episode=1, season=1))
    assert result == "Test Show - S1E2.mkv"


def test_generate_full_path_is_removed():
    import app.core.template as tpl

    assert not hasattr(tpl, "generate_full_path")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_template_pad.py -v
```

预期：`test_explicit_pad_overrides_global_settings`、`test_pad_does_not_affect_unpadded_variables`、`test_folder_template_honours_pad`、`test_pad_of_one_disables_padding` FAIL，报 `TypeError: apply_template() got an unexpected keyword argument 'pad'`；`test_generate_full_path_is_removed` FAIL。

- [ ] **Step 3: 实现 pad 透传**

编辑 `backend/app/core/template.py`，把 `_resolve_variable` 整体替换为：

```python
def _resolve_variable(var: str, info: ParsedInfo, pad: PadConfig | None = None) -> str:
    var_lower = var.lower()

    if var_lower == "show":
        return info.show_name or ""
    if var_lower == "show_clean":
        return safe_filename(info.show_name or "")
    if var_lower == "season":
        return str(info.season) if info.season is not None else str(settings.default_season)
    if var_lower == "season_padded":
        s = info.season if info.season is not None else settings.default_season
        digits = pad.season if pad else settings.season_pad_digits
        return pad_number(s, digits)
    if var_lower == "episode":
        return str(info.episode) if info.episode is not None else "1"
    if var_lower == "episode_padded":
        e = info.episode if info.episode is not None else 1
        digits = pad.episode if pad else settings.episode_pad_digits
        return pad_number(e, digits)
    if var_lower == "title":
        return info.title or ""
    if var_lower == "quality":
        return " ".join(info.qualities) if info.qualities else ""
    if var_lower == "source":
        return " ".join(info.source_tags) if info.source_tags else ""
    if var_lower == "extension":
        return info.extension or ".mkv"
    if var_lower == "sub_lang":
        return info.sub_lang or ""

    return ""
```

把 `apply_template` 与 `apply_folder_template` 替换为：

```python
def apply_template(
    template: str,
    info: ParsedInfo,
    include_extension: bool = True,
    pad: PadConfig | None = None,
) -> str:
    def replacer(match: re.Match) -> str:
        return _resolve_variable(match.group(1), info, pad)

    result = VARIABLE_PATTERN.sub(replacer, template)

    result = re.sub(r'\s+', ' ', result).strip()

    has_ext_var = _template_has_extension(template)
    if not has_ext_var and include_extension and info.extension:
        result = result + info.extension

    result = safe_filename(result)

    return result


def apply_folder_template(
    template: str,
    info: ParsedInfo,
    pad: PadConfig | None = None,
) -> str:
    if not template:
        return ""
    return apply_template(template, info, include_extension=False, pad=pad)
```

- [ ] **Step 4: 删除死函数**

删除 `generate_full_path` 整个函数（原 `template.py:71-85`）。

已验证：全项目仅 `local_renamer.py:14` 导入它，且从未调用。
`apply_template` / `apply_folder_template` 在 `local_renamer.py:51,58` 与 `openlist_renamer.py:33,37` 有直接调用，不受影响。

同时删除 `backend/app/core/local_renamer.py:14` 中未使用的导入：

```python
# 改前
from .template import apply_template, apply_folder_template, generate_full_path
# 改后
from .template import apply_template, apply_folder_template
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/ -v
```

预期：16 passed（Task 1 的 9 个 + 本任务的 7 个）

- [ ] **Step 6: 确认服务仍可导入**

```bash
cd backend && python -c "from app.main import app; print('导入成功')"
```

预期：输出 `导入成功`。这一步专门捕获删除 `generate_full_path` 可能遗漏的其他引用。

- [ ] **Step 7: 提交**

```bash
git add backend/app/core/template.py backend/app/core/local_renamer.py backend/tests/test_template_pad.py
git commit -m "feat(backend): 模板渲染接受请求级补零位数, 删除死函数 generate_full_path"
```

---

### Task 3: 调用链与路由接上 pad

打通 `plan builder` → `batch_rename` → 三个路由，并给两个 Request 模型加字段。

**Files:**
- Modify: `backend/app/models/api.py`（`RenamePreviewRequest`、`RenameExecuteRequest`）
- Modify: `backend/app/core/local_renamer.py:32-38`（`build_rename_plan` 签名）
- Modify: `backend/app/core/local_renamer.py:51,58`（渲染调用点透传 pad）
- Modify: `backend/app/core/local_renamer.py:171-179`（`batch_rename` 签名）
- Modify: `backend/app/core/local_renamer.py:188`（`build_rename_plan` 调用点）
- Modify: `backend/app/core/openlist_renamer.py:16-22`（签名）
- Modify: `backend/app/core/openlist_renamer.py:33,37`（渲染调用点透传 pad）
- Modify: `backend/app/api/renamer.py`（preview / execute / dry-run 三个路由）
- Create: `backend/tests/test_rename_routes.py`

**Interfaces:**
- Consumes: `PadConfig`（Task 1）；`apply_template(..., pad=)` / `apply_folder_template(..., pad=)`（Task 2）
- Produces:
  - `build_rename_plan(file, template, folder_template="", create_season_folder=False, override=None, pad=None) -> RenamePlan`
  - `build_openlist_rename_plan(file, template, folder_template="", create_season_folder=False, override=None, pad=None) -> RenamePlan`
  - `batch_rename(files, template, folder_template="", create_season_folder=False, overrides=None, dry_run=False, conflict_strategy="skip", pad=None) -> BatchRenameResult`

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_rename_routes.py`：

```python
import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.main import app
from app.models.file import FileInfo

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


def test_execute_route_accepts_pad_fields(client):
    # 干跑, 不触盘; 只验证请求模型接受字段且不报 422
    payload = {
        "file_ids": ["f1"],
        "template": TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "overrides": OVERRIDES,
        "conflict_strategy": "skip",
        "episode_pad_digits": 3,
        "season_pad_digits": 3,
    }
    res = client.post("/api/rename/dry-run", json=payload)
    assert res.status_code == 200, res.text
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_rename_routes.py -v
```

预期：`test_episode_pad_digits_is_honoured` 等 5 个断言补零的测试 FAIL（返回 `S01E02` 而非期望值）；`test_execute_route_accepts_pad_fields` FAIL，报 422 Unprocessable Entity（模型不接受未知字段不会 422，但 Pydantic 默认忽略未知字段 —— 若它 PASS 属正常，因为字段被静默丢弃；重点看前 5 个必然 FAIL）。`test_omitting_pad_fields_preserves_current_behaviour` 应 PASS（当前行为本就是这个）。

若 `test_omitting_pad_fields_preserves_current_behaviour` 也 FAIL，说明解析器行为与预期不符，先修 OVERRIDES 而不是改实现。

- [ ] **Step 3: 给请求模型加字段**

编辑 `backend/app/models/api.py`，把 `RenamePreviewRequest` 与 `RenameExecuteRequest` 替换为：

```python
class RenamePreviewRequest(BaseModel):
    file_ids: list[str]
    template: str
    folder_template: str = ""
    create_season_folder: bool = False
    overrides: dict[str, dict] = Field(default_factory=dict)
    source: str = "local"
    path: str = ""
    episode_pad_digits: Optional[int] = None
    season_pad_digits: Optional[int] = None


class RenameExecuteRequest(BaseModel):
    file_ids: list[str]
    template: str
    folder_template: str = ""
    create_season_folder: bool = False
    overrides: dict[str, dict] = Field(default_factory=dict)
    source: str = "local"
    path: str = ""
    conflict_strategy: str = "skip"
    episode_pad_digits: Optional[int] = None
    season_pad_digits: Optional[int] = None
```

- [ ] **Step 4: 给 plan builder 加 pad 参数**

编辑 `backend/app/core/local_renamer.py`。

把 `build_rename_plan` 签名（第 32-38 行）改为：

```python
def build_rename_plan(
    file: FileInfo,
    template: str,
    folder_template: str = "",
    create_season_folder: bool = False,
    override: Optional[OverrideInfo] = None,
    pad: PadConfig | None = None,
) -> RenamePlan:
```

把第 51 行的渲染调用改为：

```python
    new_filename = apply_template(template, parsed, pad=pad)
```

把第 58 行的渲染调用改为：

```python
        folder_name = apply_folder_template(folder_template, parsed, pad=pad)
```

把第 14 行的导入改为：

```python
from .template import PadConfig, apply_template, apply_folder_template
```

把 `batch_rename` 签名（第 171-179 行）改为：

```python
def batch_rename(
    files: list[FileInfo],
    template: str,
    folder_template: str = "",
    create_season_folder: bool = False,
    overrides: dict[str, dict] | None = None,
    dry_run: bool = False,
    conflict_strategy: str = "skip",
    pad: PadConfig | None = None,
) -> BatchRenameResult:
```

把第 188 行的调用改为：

```python
        plan = build_rename_plan(
            f, template, folder_template, create_season_folder, override, pad=pad
        )
```

编辑 `backend/app/core/openlist_renamer.py`。

把第 11 行的导入改为：

```python
from .template import PadConfig, apply_template, apply_folder_template
```

把 `build_openlist_rename_plan` 签名（第 16-22 行）改为：

```python
def build_openlist_rename_plan(
    file: FileInfo,
    template: str,
    folder_template: str = "",
    create_season_folder: bool = False,
    override: Optional[OverrideInfo] = None,
    pad: PadConfig | None = None,
) -> RenamePlan:
```

把第 33 行改为：

```python
    new_filename = apply_template(template, parsed, pad=pad)
```

把第 37 行改为：

```python
        folder_name = apply_folder_template(folder_template, parsed, pad=pad)
```

- [ ] **Step 5: 三个路由构造并透传 PadConfig**

编辑 `backend/app/api/renamer.py`，在 import 区加上：

```python
from ..config import settings
from ..core.template import PadConfig
```

在文件顶部（`router` 定义之后）加一个共用辅助函数：

```python
def _pad_from_request(req) -> PadConfig | None:
    """两个字段都没传时返回 None, 保持与改动前完全一致的行为。"""
    if req.episode_pad_digits is None and req.season_pad_digits is None:
        return None
    # 必须显式判 None, 不能用 `x or default` —— 0 是合法输入,
    # 用 or 会让 0 短路成全局默认值, 钳制逻辑永远不触发。
    episode = (
        req.episode_pad_digits
        if req.episode_pad_digits is not None
        else settings.episode_pad_digits
    )
    season = (
        req.season_pad_digits
        if req.season_pad_digits is not None
        else settings.season_pad_digits
    )
    return PadConfig(episode=episode, season=season)
```

在 `/rename/preview` 路由中，把循环前的 `results: list[dict] = []` 之后加一行：

```python
    pad = _pad_from_request(req)
```

并把该路由内两处 `build_rename_plan(...)` / `build_openlist_rename_plan(...)` 调用改为传入 `pad=pad`：

```python
            plan = build_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override, pad=pad,
            )
```

```python
            plan = build_openlist_rename_plan(
                f, req.template, req.folder_template,
                req.create_season_folder, override, pad=pad,
            )
```

在 `/rename/execute` 路由中，`if source == "local":` 之前加：

```python
    pad = _pad_from_request(req)
```

`local_batch_rename(...)` 调用加 `pad=pad`：

```python
        result = local_batch_rename(
            files=files,
            template=req.template,
            folder_template=req.folder_template,
            create_season_folder=req.create_season_folder,
            overrides=req.overrides,
            dry_run=False,
            conflict_strategy=req.conflict_strategy,
            pad=pad,
        )
```

该路由内的 `build_openlist_rename_plan(...)` 调用加 `pad=pad`。

在 `/rename/dry-run` 路由中同样处理：加 `pad = _pad_from_request(req)`，`local_batch_rename(...)` 加 `pad=pad`，`build_openlist_rename_plan(...)` 加 `pad=pad`。

- [ ] **Step 6: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/ -v
```

预期：25 passed（Task 1 的 9 个 + Task 2 的 7 个 + 本任务的 9 个）

- [ ] **Step 7: 确认服务启动无回归**

```bash
cd backend && python -c "from app.main import app; print('路由数:', len(app.routes))"
```

预期：正常输出路由数，无 ImportError

- [ ] **Step 8: 提交**

```bash
git add backend/app/models/api.py backend/app/core/local_renamer.py backend/app/core/openlist_renamer.py backend/app/api/renamer.py backend/tests/test_rename_routes.py
git commit -m "feat(backend): 三个重命名路由支持请求级补零位数"
```

---

## 完成后

后端改完即可独立验证：`curl` 或前端调用 `/api/rename/preview` 时传 `episode_pad_digits`，返回的 `new_filename` 随之变化。

前端接线在 `docs/superpowers/plans/2026-09-25-frontend-3-features.md` 的 **Task 8** 中完成（`buildPreview()` 与 `executeAction()` 两处请求体各加 `episode_pad_digits` / `season_pad_digits`，值取自 `settings` store）。该任务的第一步就是核对本计划的两个请求模型字段是否已就位 —— 若本计划尚未实施，Task 8 必须跳过。

## Self-Review

**Spec 覆盖**
- §13.1 请求模型加字段 → Task 3 Step 3 ✓
- §13.2 `PadConfig` + 钳制 + pad 透传 + 删 `generate_full_path` → Task 1、Task 2 ✓
- §13.3 两个 plan builder + `batch_rename` → Task 3 Step 4 ✓
- §13.4 三个路由构造 `PadConfig` → Task 3 Step 5 ✓
- §13.5 前端发送字段 → 属前端计划范围 ✓
- §15.3 补零位数闭环验证 → Task 3 的 9 个路由测试即后端侧的闭环证明 ✓
- §17 风险「后端签名变更波及」→ 全参数默认 `None`，Task 2 Step 6 与 Task 3 Step 7 各设一道导入/启动检查 ✓

**占位符扫描**：无 TBD / TODO / 「类似 Task N」；所有代码步骤含完整代码 ✓

**类型一致性**：`PadConfig(episode=, season=)` 在 Task 1 定义，Task 2、3 均按此名调用；`apply_template(..., pad=)` / `apply_folder_template(..., pad=)` 签名在 Task 2 定义，Task 3 按此调用；`_pad_from_request` 在 Task 3 内定义并使用 ✓

**Review Focus 落位**：5 条各自有测试 —— ①0/负数 → `test_zero_is_clamped_to_one` / `test_negative_is_clamped_to_one`（Task 3）；②超大值 → `test_oversized_is_clamped_to_six`（Task 3）；③只传一个字段 → `test_episode_only_does_not_disturb_season`（Task 3）；④老客户端 → `test_omitting_pad_fields_preserves_current_behaviour`（Task 3）；⑤`_padded` 与未补零共存 → `test_pad_does_not_affect_unpadded_variables`（Task 2）✓

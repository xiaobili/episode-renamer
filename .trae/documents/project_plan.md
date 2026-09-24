# 电视剧/番剧自动化重命名工具 - 实现计划

## 一、项目概述

### 目标
开发一个自动化重命名工具，用于处理电视剧和番剧资源文件，输出符合 Emby/Jellyfin 刮削规范的命名格式。支持两种模式：
1. **本地文件模式**: 直接操作本地磁盘文件
2. **OpenList 云盘模式**: 通过 OpenList API 操作云盘中的文件（支持 115、阿里云盘、百度云盘等数十种云存储）

### 技术栈
- **前端**: Vue 3 + Vite + Element Plus + Pinia
- **后端**: Python 3 + FastAPI + Pydantic + httpx (异步 HTTP 客户端)
- **数据库**: SQLite (轻量存储配置和历史记录)
- **通信**: RESTful API + JSON

### 项目结构
```
episode-renamer/
├── backend/                          # Python 后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI 应用入口
│   │   ├── config.py                 # 配置管理
│   │   ├── api/                      # API 路由层
│   │   │   ├── __init__.py
│   │   │   ├── scanner.py            # 文件扫描接口（本地+OpenList）
│   │   │   ├── parser.py             # 文件名解析接口
│   │   │   ├── renamer.py            # 重命名接口
│   │   │   ├── template.py           # 模板管理接口
│   │   │   └── openlist.py           # OpenList 连接管理接口
│   │   ├── core/                     # 核心业务逻辑
│   │   │   ├── __init__.py
│   │   │   ├── local_scanner.py      # 本地目录扫描器
│   │   │   ├── openlist_client.py    # OpenList API 客户端
│   │   │   ├── openlist_scanner.py   # OpenList 云盘扫描器
│   │   │   ├── parser.py             # 文件名解析引擎
│   │   │   ├── template.py           # 模板引擎
│   │   │   ├── local_renamer.py      # 本地文件重命名器
│   │   │   ├── openlist_renamer.py   # OpenList 云盘重命名器
│   │   │   └── utils.py              # 工具函数
│   │   ├── models/                   # Pydantic 数据模型
│   │   │   ├── __init__.py
│   │   │   ├── file.py               # 文件相关模型
│   │   │   ├── template.py           # 模板模型
│   │   │   ├── openlist.py           # OpenList 连接模型
│   │   │   └── api.py                # API 请求/响应模型
│   │   └── database.py               # SQLite 连接
│   ├── requirements.txt
│   └── run.py                        # 启动脚本
├── frontend/                         # Vue 3 前端
│   ├── src/
│   │   ├── App.vue
│   │   ├── main.js
│   │   ├── router/
│   │   ├── stores/
│   │   │   ├── files.js              # 文件列表状态
│   │   │   ├── template.js           # 模板状态
│   │   │   ├── settings.js           # 设置状态
│   │   │   └── openlist.js           # OpenList 连接状态
│   │   ├── api/
│   │   │   ├── request.js            # axios 实例
│   │   │   ├── scanner.js
│   │   │   ├── parser.js
│   │   │   ├── renamer.js
│   │   │   ├── template.js
│   │   │   └── openlist.js
│   │   ├── views/
│   │   │   ├── HomeView.vue          # 主工作区（本地/云盘切换）
│   │   │   ├── SettingsView.vue      # 设置页（含 OpenList 配置）
│   │   │   └── HistoryView.vue       # 历史记录
│   │   ├── components/
│   │   │   ├── SourceSelector.vue    # 数据源选择器（本地/OpenList）
│   │   │   ├── OpenListConnect.vue   # OpenList 连接配置组件
│   │   │   ├── PathSelector.vue      # 目录选择器（本地或云盘路径）
│   │   │   ├── FileTable.vue         # 文件列表表格
│   │   │   ├── TemplateEditor.vue    # 模板编辑器
│   │   │   └── ConflictDialog.vue    # 冲突处理对话框
│   │   └── assets/
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
└── README.md
```

---

## 二、数据源抽象设计

### 2.1 统一数据源接口
```python
class DataSource(ABC):
    @abstractmethod
    def scan(self, path: str, recursive: bool = True) -> List[FileInfo]: ...
    
    @abstractmethod
    def rename(self, file: FileInfo, new_name: str) -> RenameResult: ...
    
    @abstractmethod
    def batch_rename(self, plans: List[RenamePlan]) -> List[RenameResult]: ...
    
    @abstractmethod
    def test_connection(self) -> bool: ...
```

### 2.2 双数据源架构
```
┌─────────────────────────────────────────────┐
│              前端 Vue 3                     │
│     (SourceSelector 切换本地/OpenList)      │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│          FastAPI 后端 API 层                │
│  /api/scan  /api/rename  /api/parse  ...   │
└────────────────────┬────────────────────────┘
                     │
          ┌───────────┴───────────┐
          ▼                       ▼
┌──────────────────┐    ┌──────────────────────┐
│ LocalScanner     │    │ OpenListScanner      │
│ LocalRenamer     │    │ OpenListRenamer      │
└────────┬─────────┘    └──────────┬───────────┘
         │                         │
         ▼                         ▼
    本地文件系统            OpenList HTTP API
                         (支持 115/阿里云盘/百度云/...)
```

---

## 三、OpenList 集成设计

### 3.1 OpenList API 客户端 (`backend/app/core/openlist_client.py`)

**OpenList API 基础信息**:
- OpenList 是 AList 的活跃分支，API 完全兼容
- 基础 URL: 用户配置的 OpenList 服务地址（如 `http://localhost:5244`）
- 认证方式: JWT Token (放在 `Authorization` Header 中)
- 关键 API 端点:

#### 认证接口
```
POST /api/auth/login
Body:   { "username": "admin", "password": "xxx", "otp_code": "123456"(可选) }
Header: Content-Type: application/json
Response: { "code": 200, "message": "success", "data": { "token": "eyJ..." } }
```

#### 文件列表
```
POST /api/fs/list
Header: Authorization: <token>
Body:   { "path": "/115/电视剧", "password": "", "refresh": false }
Response: { 
  "code": 200, 
  "data": {
    "content": [
      { "name": "Show.S01E01.mkv", "size": 12345, "is_dir": false, 
        "type": 2, "path": "/115/电视剧/Show.S01E01.mkv", ... }
    ],
    "total": 42,
    "write": true
  }
}
```

#### 文件详情
```
POST /api/fs/get
Header: Authorization: <token>
Body:   { "path": "/115/电视剧/Show.S01E01.mkv", "password": "" }
```

#### 批量重命名 ⭐ 关键接口
```
POST /api/fs/batch_rename
Header: Authorization: <token>, Content-Type: application/json
Body:   { 
  "src_dir": "/115/电视剧", 
  "rename_objects": [
    { "src_name": "Show.S01E01.mkv", "new_name": "Show Name - S01E01.mkv" },
    { "src_name": "Show.S01E02.mkv", "new_name": "Show Name - S01E02.mkv" }
  ]
}
Response: { "code": 200, "message": "success", "data": null }
```

#### 单个重命名
```
POST /api/fs/rename  (或内部使用 POST /api/fs/batch_rename 的单条形式)
Header: Authorization: <token>
Body:   { "path": "/115/电视剧/Show.S01E01.mkv", "name": "Show Name - S01E01.mkv" }
```

#### 移动文件
```
POST /api/fs/move
Header: Authorization: <token>
Body:   { 
  "src_dir": "/115/电视剧", 
  "dst_dir": "/115/电视剧/Show Name/Season 01",
  "names": ["Show Name - S01E01.mkv"]
}
```

### 3.2 OpenList 连接配置模型
```python
class OpenListConfig(BaseModel):
    enabled: bool = False
    server_url: str = Field(..., example="http://localhost:5244")
    username: str
    password: str
    otp_code: Optional[str] = None  # 2FA 验证码（动态获取）
    token: Optional[str] = None     # 登录后缓存的 token
    
class OpenListConnection(BaseModel):
    config: OpenListConfig
    connected: bool = False
    last_check: Optional[datetime] = None
    mount_points: List[str] = []    # OpenList 挂载点列表
```

### 3.3 OpenList 扫描器
```python
class OpenListScanner:
    async def list_directory(self, path: str) -> List[OpenListFile]:
        """调用 /api/fs/list 列出目录内容"""
        
    async def recursive_scan(self, path: str) -> List[FileInfo]:
        """递归扫描（可能需要分页处理大量文件）"""
        
    async def get_file_info(self, path: str) -> OpenListFile:
        """调用 /api/fs/get 获取单个文件信息"""

class OpenListFile(BaseModel):
    name: str
    size: int
    is_dir: bool
    path: str
    type: int           # 0: unknown, 1: folder, 2: video, 4: subtitle...
    sign: str           # 签名
    thumb: str          # 缩略图
    raw_url: str        # 直链地址
    modified: datetime
    provider: str       # 云盘提供商 (115 Cloud, 阿里云盘 等)
```

### 3.4 OpenList 重命名器
```python
class OpenListRenamer:
    async def batch_rename(self, src_dir: str, 
                          rename_objects: List[RenameObject]) -> BatchRenameResult:
        """调用 /api/fs/batch_rename 批量重命名"""
        
    async def single_rename(self, path: str, new_name: str) -> RenameResult:
        """单个文件重命名"""
        
    async def move_to_season_folder(self, file: OpenListFile, 
                                    season_folder: str) -> MoveResult:
        """移动到季文件夹"""

class RenameObject(BaseModel):
    src_name: str
    new_name: str
```

### 3.5 OpenList 特性与限制处理

| 特性 | 处理方式 |
|------|---------|
| **多挂载点** | OpenList 支持同时挂载多个云盘，扫描时需指定挂载路径前缀（如 `/115/`, `/阿里云盘/`） |
| **云盘文件类型** | OpenList 内部 type 字段标识：1=文件夹, 2=视频, 4=字幕 等，利用此快速过滤 |
| **批量 API** | 使用 `batch_rename` 接口高效处理，避免逐文件调用 |
| **写权限检测** | 调用 `list` 接口时检查响应中的 `write` 字段，无写权限时提示用户 |
| **并发限制** | 不同云盘有不同 QPS 限制，实现请求队列控制并发 |
| **重试机制** | 网络抖动/Token 过期自动重试 + 重新登录 |
| **操作不可撤销** | 云盘 API 无原生撤销，需本地记录反向映射，支持手动生成重命名脚本 |

---

## 四、后端模块详细设计

### 4.1 文件名解析引擎 (`backend/app/core/parser.py`)

**支持的命名格式（与数据源无关）**:

| 格式类型 | 示例 | 解析结果 |
|---------|------|---------|
| SxxExx 标准 | `Show.Name.S01E01.1080p.mkv` | show=Show Name, season=1, episode=1 |
| SxEx 简写 | `Show.Name.S1E01.mkv` | show=Show Name, season=1, episode=1 |
| 仅 E 格式 | `Show.Name.E01.mkv` | show=Show Name, season=?, episode=1 |
| 中文季/集 | `剧名 第1季 第01集.mp4` | show=剧名, season=1, episode=1 |
| 中文 话 | `剧名 - 01话.mp4` | show=剧名, episode=1 |
| 番剧格式 | `[字幕组] 番剧名 - 01 [1080p].mkv` | show=番剧名, episode=1 |
| 数字序号 | `剧名-01.mkv` 或 `剧名 01.mkv` | show=剧名, episode=1 |
| BDrip 来源 | `Show.S01E01.BDRip.1080p.mkv` | show=Show, season=1, episode=1 |

**核心方法**:
- `parse_filename(filename: str) -> ParsedInfo`
- `extract_show_name(name: str) -> str`
- `extract_season(name: str, parent_dir_hint: Optional[str] = None) -> Optional[int]`
- `extract_episode(name: str) -> Optional[int]`
- `extract_quality(name: str) -> List[str]`
- `extract_source_tags(name: str) -> List[str]`

**智能推断**:
- 当文件名中没有季数信息时，从父目录名推断（如父目录为 "Season 1" 或 "第1季"）
- 利用 `type` 字段区分视频/字幕/其他文件

**正则表达式模式库**:
```python
SEASON_PATTERNS = [
    r'[Ss](\d{1,2})[Ee]',                # S01E
    r'第\s*(\d{1,2})\s*季',               # 第1季
    r'[Ss]eason\s*(\d{1,2})',             # Season 1
    r'(\d{1,2})[Tt][Rr]',                 # 01T (泰剧常见)
]

EPISODE_PATTERNS = [
    r'[Ss]\d{1,2}[Ee](\d{1,3})',          # S01E01
    r'(?<![0-9])[Ee](\d{1,3})(?!\d)',      # E01
    r'第\s*\d{1,2}\s*季.*?第\s*(\d{1,3})\s*集',  # 第1季...第01集
    r'第\s*(\d{1,3})\s*集',                # 第01集
    r'(?<![0-9A-Za-z])-\s*(\d{1,3})\s*[.\s\[话集话]',  # - 01 或 01话
    r'\[(\d{1,3})\]',                      # [01]
    r'(?<![0-9])(\d{2,3})(?=[.\s\-]|$)',  # 末尾数字 01
]

CLEAN_PATTERNS = [
    r'\[.*?\]',          # 字幕组/信息括号
    r'\(.*?\)',          # 注释括号
    r'【.*?】',          # 中文括号
    r'[._]+',            # 分隔符
    r'\b(1080p|720p|4K|2160p|8K)\b',
    r'\b(HDR|SDR|DV|HDR10\+?|HLG)\b',
    r'\b(x264|x265|H\.?264|H\.?265|HEVC|AVC|AV1)\b',
    r'\b(BDRip|BRRip|BluRay|WEB[-_ ]?DL|WEBRip|HDTV|DVDRip)\b',
    r'\b(AAC|AC3|DTS|FLAC|TrueHD|DDP5\.1)\b',
    r'\b(CHS|CHT|GB|BIG5|JPN|KOR|ENG|简中|繁中|国语|粤语|日语)\b',
    r'\b(SSA|ASS|SRT|SUB)\b',
]
```

**输出数据结构**:
```json
{
  "show_name": "Show Name",
  "season": 1,
  "episode": 1,
  "title": null,
  "qualities": ["1080p", "HDR"],
  "source_tags": ["WEB-DL"],
  "audio_tags": ["AAC"],
  "sub_lang": null,
  "original_filename": "Show.Name.S01E01.1080p.mkv",
  "extension": ".mkv",
  "parse_confidence": 0.95,
  "needs_manual_review": false,
  "warnings": ["无法确定季数，使用默认值 1"]
}
```

### 4.2 模板系统 (`backend/app/core/template.py`)

**支持的模板变量**:
- `{show}` - 剧名
- `{show_clean}` - 剧名（清理特殊字符）
- `{season}` - 季数 (数字)
- `{season_padded}` - 季数 (补零, e.g., 01)
- `{episode}` - 集数 (数字)
- `{episode_padded}` - 集数 (补零, e.g., 01)
- `{title}` - 标题
- `{quality}` - 画质
- `{source}` - 来源
- `{extension}` - 扩展名
- `{sub_lang}` - 字幕语言后缀 (仅字幕文件)

**预设模板**:
1. **Emby 标准**: `{show} - S{season_padded}E{episode_padded}{extension}`
2. **Jellyfin 中文**: `{show} - 第{season}季第{episode}集{extension}`
3. **带标题**: `{show} - S{season_padded}E{episode_padded} - {title}{extension}`
4. **番剧简化**: `{show} - {episode_padded}{extension}`
5. **完整信息**: `{show} S{season_padded}E{episode_padded} [{quality}][{source}]{extension}`
6. **字幕专用**: `{show} - S{season_padded}E{episode_padded}{sub_lang}{extension}`

**额外功能**:
- **目录模板**: 自动创建季文件夹 `Season {season_padded}/`
- **路径冲突处理**: 当目标路径已存在时，自动追加序号 `_1`, `_2`

### 4.3 本地重命名器 (`backend/app/core/local_renamer.py`)

**核心方法**:
- `generate_plan(file: FileInfo, template: str) -> RenamePlan`
- `batch_generate_plans(files: List[FileInfo], template: str) -> List[RenamePlan]`
- `execute_plan(plan: RenamePlan, dry_run: bool = False) -> RenameResult`
- `batch_execute(plans: List[RenamePlan], dry_run: bool = False) -> List[RenameResult]`
- `create_season_folder_if_needed(path: str) -> bool`

**冲突处理策略**:
- `abort` - 立即停止，报告冲突
- `skip` - 跳过冲突文件，继续处理
- `overwrite` - 覆盖已有文件
- `rename_dup` - 自动追加序号

### 4.4 OpenList 重命名器 (`backend/app/core/openlist_renamer.py`)

**核心方法**:
- `batch_prepare(src_dir: str, plans: List[RenamePlan]) -> BatchRenameRequest`
- `batch_execute(src_dir: str, plans: List[RenamePlan]) -> BatchRenameResult`
- `execute_with_move(file: OpenListFile, new_name: str, target_dir: str) -> RenameResult`

**OpenList 特性处理**:
- 批量 API 一次性处理同一目录下的多个文件
- 如果需要跨目录移动（如同时创建 Season 文件夹），先创建文件夹再移动
- 记录原始路径映射，支持后续手动生成反向重命名脚本

**OpenList 限制**:
- `batch_rename` 只支持同一 `src_dir` 下的文件批量改名
- 跨目录操作需要单独使用 `move` API
- 部分云盘驱动可能不支持文件移动

---

## 五、API 接口设计

### 5.1 OpenList 连接管理

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/openlist/login` | 登录 OpenList 并获取 Token |
| POST | `/api/openlist/test` | 测试连接是否有效 |
| GET  | `/api/openlist/status` | 获取当前连接状态 |
| GET  | `/api/openlist/mounts` | 获取 OpenList 挂载点列表 |
| POST | `/api/openlist/logout` | 断开连接（清除本地 Token） |

**POST /api/openlist/login 请求体**:
```json
{
  "server_url": "http://localhost:5244",
  "username": "admin",
  "password": "mypassword",
  "otp_code": "123456"
}
```

**POST /api/openlist/login 响应**:
```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "mount_points": ["/115", "/阿里云盘", "/百度云"],
  "user_info": { "username": "admin", "avatar": "" }
}
```

### 5.2 文件扫描（本地 & OpenList 统一接口）

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/scan` | 扫描目录（自动根据 source 区分） |
| POST | `/api/scan/openlist` | 扫描 OpenList 云盘 |
| GET  | `/api/files` | 获取已扫描的文件列表 |
| DELETE | `/api/files` | 清空文件列表 |

**POST /api/scan 请求体**:
```json
{
  "source": "local",            // "local" | "openlist"
  "path": "/home/user/Movies",
  "recursive": true,
  "include_subtitles": true,
  "video_extensions": [".mkv", ".mp4"]
}
```

**POST /api/scan/openlist 请求体**:
```json
{
  "path": "/115/电视剧/半泽直树",
  "recursive": true,
  "openlist_config": null       // 若已登录可传 null 复用
}
```

**POST /api/scan 响应**:
```json
{
  "success": true,
  "source": "local",
  "total_files": 42,
  "videos": 35,
  "subtitles": 7,
  "duration_ms": 1234,
  "files": [
    {
      "id": "f-001",
      "source": "local",
      "path": "/home/user/Movies/Show.S01E01.mkv",
      "filename": "Show.S01E01.mkv",
      "extension": ".mkv",
      "size": 1234567890,
      "is_dir": false,
      "provider": null
    }
  ]
}
```

### 5.3 解析相关

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/parse` | 解析单个文件名 |
| POST | `/api/parse/batch` | 批量解析文件名 |

### 5.4 重命名相关（统一接口，自动分发）

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/rename/preview` | 预览重命名结果（不执行） |
| POST | `/api/rename/dry-run` | 试运行（本地模式） |
| POST | `/api/rename/execute` | 执行重命名 |
| GET  | `/api/rename/history` | 获取历史记录 |
| POST | `/api/rename/undo` | 撤销（仅本地模式） |

**POST /api/rename/execute 请求体**:
```json
{
  "file_ids": ["f-001", "f-002", "f-003"],
  "template": "{show} - S{season_padded}E{episode_padded}{extension}",
  "create_season_folder": true,
  "folder_template": "Season {season_padded}",
  "conflict_strategy": "skip",     // abort | skip | overwrite | rename_dup
  "overrides": {
    "f-001": { "show_name": "半泽直树", "season": 2 }
  }
}
```

**POST /api/rename/execute 响应**:
```json
{
  "success": true,
  "source": "openlist",
  "executed": 42,
  "skipped": 3,
  "failed": 0,
  "conflicts": [],
  "results": [
    { "src": "Show.S01E01.mkv", "dst": "Show Name - S01E01.mkv", "status": "success" }
  ]
}
```

### 5.5 模板相关

| 方法 | 路径 | 描述 |
|------|------|------|
| GET  | `/api/templates/presets` | 获取预设模板 |
| GET  | `/api/templates/custom` | 获取自定义模板列表 |
| POST | `/api/templates/custom` | 新建自定义模板 |
| PUT  | `/api/templates/custom/{id}` | 更新自定义模板 |
| DELETE | `/api/templates/custom/{id}` | 删除自定义模板 |

---

## 六、前端界面设计

### 6.1 主工作区 (HomeView)
```
┌─────────────────────────────────────────────────────────────┐
│  🎬 Episode Renamer                                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 数据源: [本地磁盘 ▼]                                    │ │
│  │   → 本地: 路径选择器 + 扫描按钮                         │ │
│  │   → OpenList: 连接状态 + 挂载点选择 + 云盘路径          │ │
│  │                                                          │ │
│  │ 模板: [Emby标准 ▼]  [自定义模板编辑器]  [预览实时更新]  │ │
│  └────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ ☑ 全选 │  已选 42 个文件  │  总大小 84GB   │  [刷新] [筛选] │
├─────────────────────────────────────────────────────────────┤
│ 原文件名               │ 新文件名                    │ 状态 │
│ ──────────────────────┼─────────────────────────────┼────── │
│ Show.Name.S01E01.mkv │ Show Name - S01E01.mkv     │ ✅  │
│ Show.Name.S01E02.mkv │ Show Name - S01E02.mkv     │ ✅  │
│ 葬送的芙莉莲 - 01.mkv │ 葬送的芙莉莲 - S01E01.mkv  │ ⚠️  │
│半泽直树2.第2季.05集.mp4│ 半泽直树2 - S02E05.mp4     │ ✅  │
│                        │  (⚠️ 置信度低请检查)      │      │
├─────────────────────────────────────────────────────────────┤
│ 批量: [应用模板] [覆盖解析] [执行重命名]  冲突: [跳过 ▼]    │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 数据源切换组件 (SourceSelector)
- 选项卡形式：`[本地磁盘]  [OpenList 云盘]`
- 切换时自动重置扫描状态
- OpenList 模式下显示连接状态指示器

### 6.3 OpenList 连接组件 (OpenListConnect)
```
┌────────────────────────────────────────────┐
│ OpenList 云盘连接                          │
│                                            │
│ 服务器地址: [http://localhost:5244]         │
│ 用户名:     [admin]                        │
│ 密码:       [••••••]                       │
│ 2FA 验证码: [123456] (可选)                │
│                                            │
│ [测试连接]  [登录]   状态: 🟢 已连接       │
│                                            │
│ 挂载点: [/115 ▼ /阿里云盘 /百度云]         │
└────────────────────────────────────────────┘
```

### 6.4 设置页 (SettingsView)
- **通用设置**: 默认模板、自动补零位数、视频/字幕扩展名
- **OpenList 设置**: 服务器地址、自动重连、请求间隔（避免触发云盘限速）
- **高级选项**: 创建季文件夹策略、字幕同步重命名、冲突默认处理方式
- **撤销保留**: 保留本地/云盘操作历史的时间范围

### 6.5 关键交互
- 切换数据源时自动重置上下文
- 模板修改 → 新文件名实时预览更新
- 点击文件名展开解析详情并可手动编辑（剧名/季/集）
- OpenList 连接状态异常时提示重连
- 执行重命名前二次确认对话框（显示变更数量和目标路径）
- OpenList 模式下无"撤销"按钮，改为"生成反向脚本"

---

## 七、实现步骤

### Phase 1: 项目初始化与基础框架
1. 创建项目目录结构
2. 后端 FastAPI 基础搭建 + Pydantic 模型定义
3. 前端 Vue3 + Vite + Element Plus 脚手架
4. 前后端通信联调
5. SQLite 配置管理

### Phase 2: 文件名解析引擎（最核心）
1. 实现正则匹配引擎
2. 实现剧名清理和提取逻辑
3. 实现置信度评估
4. 实现父目录智能推断
5. 准备测试数据集

### Phase 3: 模板系统
1. 模板变量引擎
2. 预设模板库
3. 自定义模板存储
4. 实时预览功能

### Phase 4: 本地文件功能
1. 本地扫描器
2. 本地重命名执行器
3. 字幕关联处理
4. 冲突检测和处理策略
5. dry-run 模式
6. 撤销功能

### Phase 5: OpenList 云盘功能
1. OpenList API 客户端封装（httpx 异步）
2. 认证 + Token 管理 + 自动重试
3. OpenList 扫描器（挂载点发现 + 目录列表）
4. OpenList 重命名器（batch_rename 高效调用）
5. 跨目录移动处理
6. 请求并发控制（尊重云盘 QPS 限制）

### Phase 6: 前端界面完善
1. 数据源切换组件
2. OpenList 连接配置
3. 文件列表表格 + 内联编辑
4. 批量操作栏
5. 模板编辑器
6. 冲突处理对话框
7. 执行确认和进度反馈

### Phase 7: 测试与打磨
1. 解析引擎单元测试（覆盖各种命名格式）
2. 本地 vs OpenList 双端测试
3. 错误处理和边界情况
4. 性能优化（大量文件场景）
5. README 和使用说明

---

## 八、关键技术考量

### 8.1 OpenList 异步调用
- 使用 `httpx` 的 `AsyncClient` 实现非阻塞 API 调用
- 后端 FastAPI 天然支持 async/await
- 并发控制使用 `asyncio.Semaphore` 防止触发云盘限流

### 8.2 云盘驱动差异
- OpenList 内部不同云盘驱动（115/阿里云盘/百度云）的可操作性不同
- 部分驱动可能不支持 `batch_rename` 或 `move`
- 运行时检测响应中的错误码，自动降级为单文件操作

### 8.3 撤销策略
- **本地模式**: 记录操作日志到 SQLite，支持原路径恢复
- **OpenList 模式**: 生成反向重命名脚本（因为云盘 API 原生不支持 undo），用户执行脚本可恢复

### 8.4 跨平台兼容
- Python 3 `pathlib` 统一处理本地路径
- OpenList 路径始终使用正斜杠 `/` 开头的绝对路径
- Windows 本地路径 → OpenList 路径转换工具

### 8.5 安全性
- OpenList 密码存储时使用 SQLite 本地加密（或仅存储 Token）
- 重命名操作前始终支持 dry-run/preview
- 严格限制重命名范围（防止误操作系统路径或 OpenList 根目录）

---

## 九、依赖清单

### 后端 (`requirements.txt`)
```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
httpx>=0.27.0
python-multipart>=0.0.9
aiofiles>=23.2.0
```

### 前端 (`package.json`)
```json
{
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.2.0",
    "pinia": "^2.1.0",
    "element-plus": "^2.5.0",
    "@element-plus/icons-vue": "^2.3.0",
    "axios": "^1.6.0",
    "dayjs": "^1.11.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-vue": "^5.0.0",
    "unplugin-auto-import": "^0.17.0",
    "unplugin-vue-components": "^0.26.0"
  }
}
```

---

## 十、预期效果

### 10.1 本地文件处理示例
```
原: [ANi] 葬送的芙莉莲 - 01 [1080P][Baha][WEB-DL][AAC AVC][CHT].mkv
新: 葬送的芙莉莲 - S01E01.mkv
```

### 10.2 OpenList 云盘处理示例 (115 云盘)
```
OpenList 挂载点: /115
原路径: /115/电视剧/半泽直树2/半泽直树2.第2季.05话.mp4
新路径: /115/电视剧/半泽直树2/Season 02/半泽直树2 - S02E05.mp4
```

### 10.3 Emby/Jellyfin 规范目录结构
```
TV Shows/
└── Show Name/
    ├── Season 01/
    │   ├── Show Name - S01E01.mkv
    │   ├── Show Name - S01E01.chs.srt
    │   └── Show Name - S01E02.mkv
    └── Season 02/
        └── ...
```

---

## 十一、风险与处理

| 风险 | 影响 | 处理方式 |
|------|------|---------|
| 解析失败率高 | 用户频繁手动修正 | 低置信度标红 + 父目录提示 + 手动覆盖 |
| OpenList 云盘限流 | API 调用失败 | 请求间隔 + 重试退避 + 批量 API 减少调用次数 |
| 云盘重命名不可撤销 | 误操作无法恢复 | 执行前强制 dry-run + 生成反向脚本 |
| OpenList 驱动能力差异 | 部分操作失败 | 运行时检测 + 降级为单文件操作 |
| 大量云盘文件扫描 | 内存/网络开销 | 分页处理 + 流式 API + 懒加载子目录 |
| 中文/日文编码问题 | 解析失败 | Unicode 模式 + 多编码尝试 + 常见别名映射 |
| OpenList Token 过期 | 操作中断 | 自动检测 + 后台静默重登 + 失败重试 |
| 跨磁盘移动 (本地) | 性能问题 | 同盘 rename，跨盘 copy+delete |
| 重复文件名冲突 | 覆盖重要文件 | 冲突检测 + 4 种策略选项 |

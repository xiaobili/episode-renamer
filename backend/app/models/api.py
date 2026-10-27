from typing import Optional
from pydantic import BaseModel, Field

from .strm import StrmMode


class ScanRequest(BaseModel):
    source: str = "local"
    path: str
    recursive: bool = True
    include_subtitles: bool = True
    video_extensions: Optional[list[str]] = None


class ScanResponse(BaseModel):
    success: bool = True
    source: str = "local"
    total_files: int = 0
    videos: int = 0
    subtitles: int = 0
    dirs: int = 0
    duration_ms: int = 0
    files: list[dict] = Field(default_factory=list)


class ParseRequest(BaseModel):
    filename: str
    parent_dir: Optional[str] = None


class BatchParseRequest(BaseModel):
    filenames: list[str]
    parent_dirs: Optional[list[str]] = None


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
    tmdb_api_key: Optional[str] = None
    tmdb_language: Optional[str] = None
    # 前端设置页的「启用 TMDB 元数据」勾选框。None = 老客户端没传, 视为未表态;
    # False = 用户显式关闭, 优先级最高(见 api/tmdb.py 的 resolve_tmdb_client)。
    tmdb_enabled: Optional[bool] = None
    tmdb_overrides: dict[str, int] = Field(default_factory=dict)
    generate_nfo: bool = False
    nfo_overwrite: bool = False
    generate_strm: bool = False
    strm_mode: StrmMode = "remote_same"
    strm_base_url: str = ""
    strm_local_root: str = ""
    strm_remote_root: str = ""
    # 用户实际扫描的目录。STRM 的镜像结构以它为根 —— 不能用 `path`:
    # 那是前端从首行文件路径推出来的**文件所在目录**, 递归扫描时它不是扫描根,
    # 拿它做 relpath 会让所有剧都退化成扁平落点。
    strm_scan_root: str = ""
    # 是否把剧集目录改名为 `剧名 (年份) [tmdbid-x]`。它是**批次级**动作
    # （改的是目录, 不是文件）, 故只在预览/干跑里读它来决定报不报计划;
    # 真正的动作在 /rename/folders（见 core/show_folder.py 的模块注释）。
    rename_folders: bool = False


class RenameBatchRequest(BaseModel):
    """批量请求的字段集合。dry-run 与 finalize 共用它。

    抽出来是因为这两个接口的字段**必须**与批量执行完全一致 —— 它们描述的是
    同一批文件、同一套模板与同一份 TMDB 配置。各写一份必然漂移。
    """
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
    tmdb_api_key: Optional[str] = None
    tmdb_language: Optional[str] = None
    tmdb_enabled: Optional[bool] = None
    tmdb_overrides: dict[str, int] = Field(default_factory=dict)
    generate_nfo: bool = False
    nfo_overwrite: bool = False
    generate_strm: bool = False
    strm_mode: StrmMode = "remote_same"
    strm_base_url: str = ""
    strm_local_root: str = ""
    strm_remote_root: str = ""
    strm_scan_root: str = ""
    # 设置页的 OpenList 限流。None = 未提供, 后端保持当前值（回落 .env）。
    openlist_max_concurrent: Optional[int] = None
    openlist_request_interval: Optional[float] = None
    # 见 RenamePreviewRequest 里同名字段的注释。
    rename_folders: bool = False


class RenameDryRunRequest(RenameBatchRequest):
    """干跑仍是批量 —— 它是纯计划操作, 不写盘, 没有进度可言。"""


class RenameFoldersRequest(RenameBatchRequest):
    """剧集文件夹改名（批次级, **真动盘**）。

    `conflict_strategy` / `generate_nfo` / strm 相关字段都是继承带来的, 路由**不读**:
    目录改名不覆盖、不自动编号, 也不写任何元数据 —— 这是 `/rename/folders` 与
    `/rename/finalize` 的分工（后者只写 NFO, 前者只改目录）。
    """


class RenameDryRunRequest(RenameBatchRequest):
    """干跑仍是批量 —— 它是纯计划操作, 不写盘, 没有进度可言。"""


class RenameFinalizeRequest(RenameBatchRequest):
    """批次收尾。landed 是**真实落点**, 由前端从单文件响应回传。

    不含 conflict_strategy 的用法: finalize 不做任何文件操作, 该字段被继承下来
    只为复用模型, 路由不读它。
    """
    landed: dict[str, str] = Field(default_factory=dict)


class RenameExecuteRequest(BaseModel):
    """**单个文件**的执行请求。

    `override` 用单数而非「只有一个键的字典」: 单文件接口收字典-of-1 是无意义的
    形状。路由内适配成 {file_id: override} 喂给既有的 _with_tmdb_titles。
    """
    file_id: str
    template: str
    folder_template: str = ""
    create_season_folder: bool = False
    override: Optional[dict] = None
    source: str = "local"
    path: str = ""
    conflict_strategy: str = "skip"
    episode_pad_digits: Optional[int] = None
    season_pad_digits: Optional[int] = None
    tmdb_api_key: Optional[str] = None
    tmdb_language: Optional[str] = None
    tmdb_enabled: Optional[bool] = None
    tmdb_overrides: dict[str, int] = Field(default_factory=dict)
    generate_nfo: bool = False
    nfo_overwrite: bool = False
    generate_strm: bool = False
    strm_mode: StrmMode = "remote_same"
    strm_base_url: str = ""
    strm_local_root: str = ""
    strm_remote_root: str = ""
    strm_scan_root: str = ""
    openlist_max_concurrent: Optional[int] = None
    openlist_request_interval: Optional[float] = None
    # 逐文件执行**不看**它: 文件夹改名是批次级动作, 由 /rename/folders 承担。
    # 字段保留是为了让前端的载荷构造函数只有一份（renamePayload.js 的 common）,
    # 少一处「某个形态要带、某个形态不带」的分叉。
    rename_folders: bool = False


class OpenListLoginRequest(BaseModel):
    server_url: str = Field(..., example="http://localhost:5244")
    username: str
    password: str
    otp_code: Optional[str] = None


class ApiResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[dict | list] = None

from typing import Optional
from pydantic import BaseModel, Field


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
    # False = 用户显式关闭, 优先级最高(见 api/tmdb.py 的 build_tmdb_client)。
    tmdb_enabled: Optional[bool] = None
    tmdb_overrides: dict[str, int] = Field(default_factory=dict)


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
    tmdb_api_key: Optional[str] = None
    tmdb_language: Optional[str] = None
    # 前端设置页的「启用 TMDB 元数据」勾选框。None = 老客户端没传, 视为未表态;
    # False = 用户显式关闭, 优先级最高(见 api/tmdb.py 的 build_tmdb_client)。
    tmdb_enabled: Optional[bool] = None
    tmdb_overrides: dict[str, int] = Field(default_factory=dict)


class OpenListLoginRequest(BaseModel):
    server_url: str = Field(..., example="http://localhost:5244")
    username: str
    password: str
    otp_code: Optional[str] = None


class ApiResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[dict | list] = None

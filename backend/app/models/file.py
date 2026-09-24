from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    id: str = ""
    source: str = "local"
    path: str
    filename: str
    extension: str = ""
    size: int = 0
    is_dir: bool = False
    is_subtitle: bool = False
    subtitle_of: Optional[str] = None
    parent_dir: str = ""
    provider: Optional[str] = None
    raw_path: Optional[str] = None


class ParsedInfo(BaseModel):
    show_name: str = ""
    season: Optional[int] = None
    episode: Optional[int] = None
    title: Optional[str] = None
    qualities: list[str] = Field(default_factory=list)
    source_tags: list[str] = Field(default_factory=list)
    audio_tags: list[str] = Field(default_factory=list)
    sub_lang: Optional[str] = None
    original_filename: str = ""
    extension: str = ""
    parse_confidence: float = 0.0
    needs_manual_review: bool = False
    warnings: list[str] = Field(default_factory=list)
    is_subtitle: bool = False


class OverrideInfo(BaseModel):
    show_name: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    title: Optional[str] = None


class RenamePlan(BaseModel):
    id: str = ""
    file_id: str = ""
    original_path: str
    new_path: str
    original_filename: str
    new_filename: str
    original_dir: str = ""
    new_dir: str = ""
    conflicts: list[str] = Field(default_factory=list)
    status: str = "pending"
    parsed: Optional[ParsedInfo] = None
    file_info: Optional[FileInfo] = None


class RenameResult(BaseModel):
    id: str = ""
    original_path: str
    new_path: str
    original_filename: str = ""
    new_filename: str = ""
    success: bool = False
    error: Optional[str] = None
    status: str = "pending"


class BatchRenameResult(BaseModel):
    success: bool = False
    source: str = "local"
    executed: int = 0
    skipped: int = 0
    failed: int = 0
    total: int = 0
    conflicts: list[dict] = Field(default_factory=list)
    results: list[RenameResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

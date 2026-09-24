from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class OpenListConfig(BaseModel):
    enabled: bool = False
    server_url: str = Field(..., example="http://localhost:5244")
    username: str
    password: str
    otp_code: Optional[str] = None
    token: Optional[str] = None


class OpenListConnection(BaseModel):
    server_url: str = ""
    connected: bool = False
    token: Optional[str] = None
    mount_points: list[str] = Field(default_factory=list)
    username: str = ""
    last_check: Optional[datetime] = None
    write_access: bool = True


class OpenListFile(BaseModel):
    name: str
    size: int = 0
    is_dir: bool = False
    path: str = ""
    type: int = 0
    sign: str = ""
    thumb: str = ""
    raw_url: str = ""
    modified: Optional[str] = None
    created: Optional[str] = None
    provider: Optional[str] = None


class RenameObject(BaseModel):
    src_name: str
    new_name: str

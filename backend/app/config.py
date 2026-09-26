from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Episode Renamer"
    version: str = "1.0.0"
    debug: bool = True

    host: str = "0.0.0.0"
    port: int = 8000

    db_path: str = str(DATA_DIR / "app.db")

    video_extensions: set[str] = {
        ".mkv", ".mp4", ".avi", ".ts", ".rmvb", ".mov",
        ".wmv", ".flv", ".m4v", ".webm", ".mpg", ".mpeg", ".m2ts",
    }
    subtitle_extensions: set[str] = {".srt", ".ass", ".ssa", ".vtt", ".sub"}

    default_season: int = 1
    episode_pad_digits: int = 2
    season_pad_digits: int = 2

    openlist_max_concurrent: int = 3
    openlist_request_interval: float = 0.5

    # TMDB 集成。api_key 为空 = 未配置 = 功能整体降级为 disabled,
    # 不发任何网络请求, 重命名行为与改动前完全一致。
    tmdb_api_key: str = ""
    tmdb_language: str = "zh-CN"
    tmdb_enabled: bool = True
    tmdb_timeout: float = 10.0
    tmdb_cache_ttl: int = 3600


settings = Settings()
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

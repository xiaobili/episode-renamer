from pydantic import BaseModel, Field


class TemplatePreset(BaseModel):
    id: str
    name: str
    description: str = ""
    template: str
    is_dir_template: bool = False
    folder_template: str = ""


class CustomTemplate(BaseModel):
    id: str = ""
    name: str
    template: str
    folder_template: str = ""
    is_default: bool = False


TEMPLATE_PRESETS: list[TemplatePreset] = [
    TemplatePreset(
        id="emby_standard",
        name="Emby 标准",
        description="Emby/Jellyfin 通用规范",
        template="{show} - S{season_padded}E{episode_padded}{extension}",
        folder_template="Season {season_padded}",
    ),
    TemplatePreset(
        id="chinese",
        name="中文友好",
        description="中文命名风格",
        template="{show} - 第{season}季第{episode}集{extension}",
        folder_template="第{season}季",
    ),
    TemplatePreset(
        id="with_title",
        name="带标题",
        description="包含集标题（如果有）",
        template="{show} - S{season_padded}E{episode_padded} - {title}{extension}",
        folder_template="Season {season_padded}",
    ),
    TemplatePreset(
        id="anime_simple",
        name="番剧简化",
        description="适合无季数的番剧",
        template="{show} - {episode_padded}{extension}",
        folder_template="",
    ),
    TemplatePreset(
        id="full_info",
        name="完整信息",
        description="包含画质来源",
        template="{show} S{season_padded}E{episode_padded} [{quality}]{extension}",
        folder_template="Season {season_padded}",
    ),
]

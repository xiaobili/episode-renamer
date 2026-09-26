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


VARIABLE_PATTERN = re.compile(r'\{(\w+)\}')


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


def _template_has_extension(template: str) -> bool:
    vars_in_template = VARIABLE_PATTERN.findall(template)
    return any(v.lower() == "extension" for v in vars_in_template)


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


def validate_template(template: str) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not template.strip():
        return False, ["模板不能为空"]

    required_vars = VARIABLE_PATTERN.findall(template)
    if "show" not in [v.lower() for v in required_vars]:
        errors.append("建议包含 {show} 变量")

    unknown = set(required_vars) - {
        "show", "show_clean", "season", "season_padded",
        "episode", "episode_padded", "title", "quality",
        "source", "extension", "sub_lang",
    }
    for v in unknown:
        errors.append(f"未知变量: {{{v}}}")

    return len(errors) == 0, errors


def get_presets() -> list[dict]:
    from ..models.template import TEMPLATE_PRESETS
    return [p.model_dump() for p in TEMPLATE_PRESETS]

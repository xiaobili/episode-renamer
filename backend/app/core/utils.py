import re
import uuid
import hashlib
from pathlib import Path


ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')


def generate_id() -> str:
    return uuid.uuid4().hex[:12]


def safe_filename(name: str, replacement: str = " ") -> str:
    cleaned = ILLEGAL_FILENAME_CHARS.sub(replacement, name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def pad_number(num: int, digits: int = 2) -> str:
    return str(num).zfill(digits)


def remove_extension(filename: str) -> str:
    p = Path(filename)
    return p.stem


def get_extension(filename: str) -> str:
    p = Path(filename)
    return p.suffix.lower()


def split_name_ext(filename: str) -> tuple[str, str]:
    name = remove_extension(filename)
    ext = get_extension(filename)
    return name, ext


def is_video_extension(ext: str, video_extensions: set[str] | None = None) -> bool:
    if video_extensions is None:
        from ..config import settings
        video_extensions = settings.video_extensions
    return ext.lower() in video_extensions


def is_subtitle_extension(ext: str, sub_extensions: set[str] | None = None) -> bool:
    if sub_extensions is None:
        from ..config import settings
        sub_extensions = settings.subtitle_extensions
    return ext.lower() in sub_extensions


def detect_sub_lang(filename: str) -> str | None:
    name, ext = split_name_ext(filename)
    if not is_subtitle_extension(ext):
        return None

    lang_patterns = [
        (r'\.chs$|\.sc$|\.zh-cn$|简体|简中|国语', '.chs'),
        (r'\.cht$|\.tc$|\.zh-tw$|繁体|繁中|粤语|粤', '.cht'),
        (r'\.jpn$|\.ja$|日语', '.jpn'),
        (r'\.kor$|\.ko$|韩语|韩文', '.kor'),
        (r'\.eng$|\.en$|英语|英文', '.eng'),
        (r'\.spa$|\.es$|西班牙语', '.spa'),
        (r'\.fre$|\.fr$|法语', '.fre'),
    ]

    name_lower = name.lower()
    for pattern, suffix in lang_patterns:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return suffix
    return None


def parent_dir_hint(parent_dir: str) -> int | None:
    if not parent_dir:
        return None

    name = Path(parent_dir).name
    match = re.search(r'[Ss]eason\s*(\d{1,2})', name, re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r'第\s*(\d{1,2})\s*季', name)
    if match:
        return int(match.group(1))

    match = re.search(r'[Ss](\d{1,2})', name)
    if match:
        return int(match.group(1))

    return None

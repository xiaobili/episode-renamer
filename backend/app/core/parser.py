from __future__ import annotations

import re
from typing import Optional

from ..models.file import ParsedInfo
from .utils import (
    split_name_ext,
    get_extension,
    is_video_extension,
    is_subtitle_extension,
    detect_sub_lang,
    parent_dir_hint,
)


QUALITY_PATTERNS = re.compile(
    r'\b('
    r'1080p|720p|2160p|4K|8K|4320p|'
    r'HDR|SDR|DV|HDR10\+?|HLG|Dolby Vision|DoVi|'
    r'HDR10|HDR10\+|PQ10'
    r')\b', re.IGNORECASE
)

SOURCE_PATTERNS = re.compile(
    r'\b('
    r'BDRip|BRRip|BluRay|BD-?Rip|BD|'
    r'WEB[-_ ]?DL|WEBRip|WEB-?DL|WEB|WEBDL|'
    r'HDTV|DVDRip|DVDScr|CAM|TS|TC|TELECINE|TELESYNC|'
    r'ReMUX|Remux|'
    r'BDMV|BDISO|FullBD|FullBluRay|'
    r'R5|R6|Line-?TV|PPVRip'
    r')\b', re.IGNORECASE
)

ENCODE_PATTERNS = re.compile(
    r'\b('
    r'x264|x265|X264|X265|h264|h265|H\.?264|H\.?265|HEVC|AVC|AV1|VP9|'
    r'AAC|AC3|DTS|DTS[-_ ]HD|DTS[-_ ]HDMA|TrueHD|FLAC|'
    r'Opus|MP3|PCM|DDP5\.1|DD5\.1|DDP|DDP5\.1\.ATMOS|'
    r'Dolby Digital|Atmos|TrueHD Atmos'
    r')\b', re.IGNORECASE
)

LANG_PATTERNS = re.compile(
    r'\b('
    r'CHS|CHT|GB|BIG5|ZHS|ZHT|'
    r'JPN|JAP|JP|KOR|KR|ENG|EN|US|'
    r'SPA|SP|FRE|FR|GER|DE|ITA|IT|'
    r'RUS|RU|TUR|TR|POR|PT|NL|PL|'
    r'SUBBED|DUBBED|SUB|DUB'
    r')\b', re.IGNORECASE
)

CHINESE_LANG_DESC = re.compile(
    r'(简体|繁體|繁体|双语|国语|普通话|粤语|日语|韩语|英语|西语|法语|德语|俄语|原声|无字幕|内封|外挂|中字|英字|日字)',
    re.IGNORECASE,
)

BROADCASTER_PATTERNS = re.compile(
    r'\b('
    r'ANi|GM-Team|DBD|RARBG|SPARKS|NTb|DEMAND|FLUX|ION265|HOMELAND|'
    r'TAG|CHT|CHS|ANiA|AniPanda|AnimeKaizoku|HorribleSubs|Commie|'
    r'Underwater|Hatsuyuki|Ryuujin|Otakutw|Tenshi|Doki'
    r')\b', re.IGNORECASE
)

BRACKET_OPEN = re.compile(r'[\[【\(（]')
BRACKET_CLOSE = re.compile(r'[\]】\)）]')

SEASON_PATTERNS = [
    re.compile(r'[Ss](\d{1,2})[Ee]'),
    re.compile(r'第\s*(\d{1,2})\s*季'),
    re.compile(r'[Ss]eason\s*(\d{1,2})', re.IGNORECASE),
    re.compile(r'(\d{1,2})[Tt][Rr]'),
    re.compile(r'(?<![A-Za-z])[Ss](\d{1,2})(?=\s*[-\s~])'),
]

EPISODE_PATTERNS = [
    (re.compile(r'[Ss]\d{1,2}[Ee](\d{1,3})'), 1.0),
    (re.compile(r'第\s*\d{1,2}\s*季.*?第\s*(\d{1,3})\s*集'), 0.95),
    (re.compile(r'(?<![0-9])[Ee][Pp]?\s*(\d{1,3})(?!\d)'), 0.9),
    (re.compile(r'第\s*(\d{1,3})\s*集'), 0.9),
    (re.compile(r'第\s*(\d{1,3})\s*话'), 0.85),
    (re.compile(r'\[(\d{1,3})\]'), 0.8),
    (re.compile(r'\((\d{1,3})\)'), 0.75),
    (re.compile(r'^(\d{1,3})(?=[~\.\s\-]|$)'), 0.8),
    (re.compile(r'(?<=[-\s_\.])(\d{2,3})(?=[.\s\[话集~\-]|$)'), 0.7),
    (re.compile(r'^(\d{1,3})$'), 0.65),
    (re.compile(r'[A-Za-z\u4e00-\u9fff](\d{1,3})$'), 0.55),
    (re.compile(r'^(\d{1,3})(?=[A-Za-z\u4e00-\u9fff])'), 0.55),
]


def _remove_bracketed(text: str) -> str:
    open_map = {'[': ']', '(': ')', '【': '】', '（': '）'}
    close_set = set(open_map.values())

    stack = []
    bracket_ranges: list[tuple[int, int, str]] = []

    i = 0
    while i < len(text):
        ch = text[i]
        if ch in open_map:
            stack.append((ch, i))
        elif ch in close_set and stack:
            open_ch, start = stack.pop()
            if open_map[open_ch] == ch:
                bracket_ranges.append((start, i + 1, text[start + 1:i]))
        i += 1

    if not bracket_ranges:
        return text

    merged_all = []
    for start, end, _ in bracket_ranges:
        if merged_all and start <= merged_all[-1][1]:
            merged_all[-1] = (merged_all[-1][0], max(merged_all[-1][1], end))
        else:
            merged_all.append((start, end))

    def _apply_ranges(ranges: list[tuple[int, int]]) -> str:
        result = []
        last = 0
        for start, end in ranges:
            result.append(text[last:start])
            last = end
        result.append(text[last:])
        return "".join(result).strip()

    all_removed = _apply_ranges(merged_all)
    if all_removed:
        all_removed = re.sub(r'[\[\]【】\(\)（）]', '', all_removed).strip()
        all_removed = re.sub(r'\s{2,}', ' ', all_removed).strip()
        if all_removed:
            return all_removed

    import re as _re
    label_keywords = (
        r'\d{3,4}[pP]?|HDR|SDR|DV|10bit|8bit|12bit|HEVC|AVC|AV1|'
        r'BDRip|BRRip|BluRay|WEB|WEBDL|WebRip|WEB-?DL|HDTV|'
        r'AAC|AC3|DTS|DTS-HD|FLAC|TrueHD|Opus|MP3|x26[45]|h26[45]|'
        r'CHS|CHT|GB|BIG5|JPN|JAP|KOR|ENG|简|繁|双|国语|粤语|'
        r'SUB|DUB|字幕|双语|简繁|原声|内封|外挂|'
        r'第\d+季|第\d+集|第\d+话|S\d+E?\d*|E\d+|'
        r'\b\d+\b|\b[0-9A-Fa-f]{8,}\b'
    )

    to_remove = []
    for start, end, content in bracket_ranges:
        if _re.search(label_keywords, content, _re.IGNORECASE):
            to_remove.append((start, end))

    merged_labeled = []
    for start, end in to_remove:
        if merged_labeled and start <= merged_labeled[-1][1]:
            merged_labeled[-1] = (merged_labeled[-1][0], max(merged_labeled[-1][1], end))
        else:
            merged_labeled.append((start, end))

    if merged_labeled:
        text_no_labels = _apply_ranges(merged_labeled)
        return text_no_labels

    return all_removed


def _extract_season(name: str, parent_hint: Optional[int] = None) -> tuple[Optional[int], float]:
    for pattern in SEASON_PATTERNS:
        m = pattern.search(name)
        if m:
            val = int(m.group(1))
            if 0 < val <= 30:
                return val, 0.95

    if parent_hint is not None:
        return parent_hint, 0.7

    return None, 0.0


def _extract_episode(name: str, season_found: bool) -> tuple[Optional[int], float]:
    best_match: tuple[Optional[int], float] = (None, 0.0)

    for pattern, weight in EPISODE_PATTERNS:
        for m in pattern.finditer(name):
            val = int(m.group(1))
            if 0 < val <= 999:
                conf = weight
                if season_found and weight < 0.9:
                    conf += 0.05
                if conf > best_match[1]:
                    best_match = (val, conf)

    return best_match


def _clean_show_name(raw: str, ext: str, season_val: Optional[int], episode_val: Optional[int]) -> str:
    name = raw

    name = _remove_bracketed(name)

    if season_val is not None:
        season_variants = '|'.join(re.escape(v) for v in [f'{season_val:02d}', str(season_val)])
        name = re.sub(
            rf'[Ss](?:{season_variants})[Ee]\d{{1,3}}', '', name, flags=re.IGNORECASE,
        )
        name = re.sub(rf'第\s*{season_val}\s*季', '', name)
        name = re.sub(rf'[Ss]eason\s*{season_val}', '', name, flags=re.IGNORECASE)
        name = re.sub(rf'(?<![A-Za-z])[Ss](?:{season_variants})(?=\s*[-\s~])', '', name, flags=re.IGNORECASE)

    if episode_val is not None:
        ep_str = str(episode_val)
        ep_padded = f'{episode_val:02d}'
        ep_padded3 = f'{episode_val:03d}'
        ep_variants = '|'.join(re.escape(v) for v in [ep_padded3, ep_padded, ep_str])
        name = re.sub(rf'第\s*(?:{ep_variants})\s*集', '', name)
        name = re.sub(rf'第\s*(?:{ep_variants})\s*话', '', name)
        name = re.sub(rf'(?<=[-\s_\.])(?:{ep_variants})(?=[.\s\[话集话]|$)', '', name)
        name = re.sub(rf'\b[Ee][Pp]?\s*(?:{ep_variants})\b', '', name, flags=re.IGNORECASE)
        name = re.sub(rf'^(?:{ep_variants})[\s~.\-_]+', '', name)
        name = re.sub(rf'^(?:{ep_variants})$', '', name)

    if season_val is not None:
        se_str = str(season_val)
        se_padded = f'{season_val:02d}'
        se_padded3 = f'{season_val:03d}'
        se_variants = '|'.join(re.escape(v) for v in [se_padded3, se_padded, se_str])
        name = re.sub(rf'第\s*(?:{se_variants})\s*季', '', name)

    name = BROADCASTER_PATTERNS.sub(' ', name)
    name = QUALITY_PATTERNS.sub(' ', name)
    name = SOURCE_PATTERNS.sub(' ', name)
    name = ENCODE_PATTERNS.sub(' ', name)
    name = LANG_PATTERNS.sub(' ', name)
    name = CHINESE_LANG_DESC.sub(' ', name)

    name = re.sub(r'[话集话]', ' ', name)
    name = re.sub(r'(?<=\s)第(?=\s)', ' ', name)

    name = re.sub(r'[_\.]+', ' ', name)
    name = re.sub(r'[-]+', ' ', name)

    name = re.sub(r'\s{2,}', ' ', name).strip()
    name = re.sub(r'^[\s\-_\.]+|[\s\-_\.]+$', '', name).strip()
    name = re.sub(r'^\d+\s*[话集话]?\s*$', '', name).strip()
    name = re.sub(r'^[话集话第]+$', '', name).strip()

    return name


def _extract_tags(name: str, pattern: re.Pattern) -> list[str]:
    found = []
    for m in pattern.finditer(name):
        val = m.group(1).upper()
        if val not in found:
            found.append(val)
    return found


_SEASON_DIR_PATTERNS = [
    re.compile(r'^[Ss]eason\s*\d{1,2}$', re.IGNORECASE),
    re.compile(r'^[Ss]\d{1,2}$'),
    re.compile(r'^第\s*\d{1,2}\s*季$'),
]


def _inherit_show_from_parent(parent_dir: Optional[str]) -> Optional[str]:
    if not parent_dir:
        return None
    parts = [p for p in parent_dir.split('/') if p]
    for part in reversed(parts):
        if any(p.match(part) for p in _SEASON_DIR_PATTERNS):
            continue
        candidate = _clean_parent_show_name(part)
        if candidate:
            return candidate
    return None


def _clean_parent_show_name(raw: str) -> str:
    name = re.sub(r'[_\.]+', ' ', raw)
    name = re.sub(r'S\d{1,2}E?\d*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Season\s*\d{1,2}', '', name, flags=re.IGNORECASE)
    name = re.sub(r'第\s*\d{1,2}\s*季', '', name)
    name = QUALITY_PATTERNS.sub(' ', name)
    name = SOURCE_PATTERNS.sub(' ', name)
    name = re.sub(r'\s{2,}', ' ', name).strip()
    return name


def parse_filename(filename: str, parent_dir: Optional[str] = None) -> ParsedInfo:
    info = ParsedInfo(original_filename=filename)

    name, ext = split_name_ext(filename)
    info.extension = ext

    confidences: list[float] = []
    warnings: list[str] = []

    season_from_dir = parent_dir_hint(parent_dir)
    season, season_conf = _extract_season(name, season_from_dir)
    season_found_in_name = season is not None and season_conf >= 0.9

    if season is not None:
        info.season = season
        confidences.append(season_conf)
    elif season_from_dir is not None:
        info.season = season_from_dir
        confidences.append(0.7)
        warnings.append(f"季数从父目录推断: {season_from_dir}")
    else:
        info.season = None

    episode, ep_conf = _extract_episode(name, season_found_in_name or season_from_dir is not None)
    if episode is not None:
        info.episode = episode
        confidences.append(ep_conf)
    else:
        info.episode = None
        warnings.append("无法确定集数")

    if info.season is None and info.episode is not None:
        info.season = 1
        confidences.append(0.5)
        warnings.append("季数未找到，默认为第1季")

    info.qualities = _extract_tags(name, QUALITY_PATTERNS)
    info.source_tags = _extract_tags(name, SOURCE_PATTERNS)
    info.audio_tags = _extract_tags(name, ENCODE_PATTERNS)

    name_show = _clean_show_name(name, ext, info.season, info.episode)
    parent_show = _inherit_show_from_parent(parent_dir) if parent_dir else None

    if parent_show:
        info.show_name = parent_show
        confidences.append(0.85)
        if name_show and name_show != parent_show:
            warnings.append(f"剧名优先使用父目录: {parent_show} (文件名: {name_show})")
    elif name_show:
        info.show_name = name_show
    else:
        info.show_name = ""

    info.sub_lang = detect_sub_lang(filename)
    info.is_subtitle = is_subtitle_extension(ext)

    if confidences:
        info.parse_confidence = round(sum(confidences) / len(confidences), 2)
    else:
        info.parse_confidence = 0.3

    info.needs_manual_review = (
        info.parse_confidence < 0.5
        or info.episode is None
        or not info.show_name
    )
    info.warnings = warnings

    return info


def batch_parse_filenames(
    filenames: list[str],
    parent_dirs: Optional[list[str]] = None,
) -> list[ParsedInfo]:
    results = []
    for i, fn in enumerate(filenames):
        parent = parent_dirs[i] if parent_dirs and i < len(parent_dirs) else None
        results.append(parse_filename(fn, parent))
    return results

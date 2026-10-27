"""STRM 生成：URL 拼装、落点推导与三种写盘方式。

**为什么单独一个模块**: 落点规则（剧集名目录 + 相对扫描根镜像 / 扁平回落）与
URL 拼装都是纯逻辑, 与「谁触发它」无关。放进路由会让「预览显示这里、执行写到
那里」的两份推导成为可能 —— 本仓库已经为那类分叉付过一次代价（见
api/renamer.py 里「计划只构建一次」的注释）。

**路径契约**: 远端与解析出来的落点一律 POSIX（`posixpath`）; 只有本地模式的
最后一步才转成 `os.path`, 否则 Windows 宿主机会把远端路径写成 `\\` 分隔。
"""
from __future__ import annotations

import os
import posixpath
from typing import TYPE_CHECKING, Optional

from ..models.file import RenamePlan, RenameResult
from ..models.strm import StrmOptions, StrmTarget
from .local_renamer import landed_path_of
from .utils import safe_filename

if TYPE_CHECKING:  # 只为类型标注, 运行期不导入 —— 避免 strm 与客户端互相牵连
    from .openlist_client import OpenListClient

STRM_EXT = ".strm"

NOT_LANDED_STRM_REASON = "该文件未改名, 不生成 STRM"
MISSING_LOCAL_ROOT = "未配置 STRM 输出目录"
MISSING_REMOTE_ROOT = "未配置 STRM 远端目录"
MISSING_BASE_URL = "未配置 STRM 地址"
OUT_OF_ROOT_REASON = "输出目录越界"


def strm_filename(new_filename: str) -> str:
    """视频文件名 → strm 文件名（只换扩展名）。

    用**重命名后**的名字: 这个功能叫「跟随重命名」, 写出的 strm 必须与旁边的
    视频同名, 否则播放器按文件名配对会失败。
    """
    stem, _extension = posixpath.splitext(new_filename)
    return f"{stem}{STRM_EXT}"


def build_strm_url(base_url: str, remote_path: str) -> str:
    """拼 `/d/` 直链, **原样写入**远端路径, 不做百分号编码。

    刻意不编码（用户明确要求「内容不要有转义」）: 写出来的是人能读懂的
    `http://h:5244/d/115/我的剧/第 1 集.mkv`, 而不是
    `.../%E6%88%91%E7%9A%84%E5%89%A7/...`。Emby / VLC 这类播放器取到 strm 后
    自己会把非法字符编码后再发请求, 所以中文与空格仍能播放。

    **代价（写在这里, 别让后来人踩）**: `#` 与 `?` 在 URL 里有语法含义 ——
    文件名带这两个字符时, 播放器会把后面当成 fragment / query, 链接必然 404。
    这是「不转义」这条规则自身的边界, 不是本函数能两全的事。
    """
    base = (base_url or "").strip().rstrip("/")
    path = (remote_path or "").strip().lstrip("/")
    if not base or not path:
        return ""
    return f"{base}/d/{path}"


def rel_dir_of(landing_dir: str, scan_root: str) -> str:
    """落点目录相对扫描根的子路径。

    三种情况都回落成「扁平」（空串）: 扫描根为空、落点就是扫描根本身、落点跑
    到扫描根外面。**绝不返回以 `..` 开头的路径** —— 本地模式下那会让文件写到
    输出根之外, 远端模式下会拼出 `..` 这种 OpenList 不认的路径。
    """
    root = (scan_root or "").strip()
    if not root:
        return ""
    rel = posixpath.relpath(landing_dir, root.rstrip("/") or "/")
    if rel in (".", "") or rel.startswith(".."):
        return ""
    return rel


def _safe_dir_name(raw: str) -> str:
    """目录名清洗: 去掉 `\\ / : * ? " < > |` 之类的非法字符并压掉空白。

    `.` / `..` 必须同时挡掉 —— 它们是**路径语义**而不是名字, 放行会让
    `{root}/../x.strm` 写到输出根之外（本地模式是真实的目录穿越, 远端模式会拼出
    OpenList 不认的路径）。
    """
    name = safe_filename(raw or "")
    if name in ("", ".", ".."):
        return ""
    return name


def show_dir_of(plan: RenamePlan, landing_dir: str, scan_root: str = "") -> str:
    """该文件所属**剧集目录名**。

    优先用解析结果（含用户手动改过的剧名）—— 它才是「这部剧叫什么」的权威答案;
    解析不出来的文件退回目录名。三层回落保证只要输入里还有一点信息就有一个
    确定的目录名, 全空时才返回空串（此时落点退回旧行为: 只按相对扫描根镜像）。

    **为什么必须单独成目录**: 扫描根常常就是剧目录本身（用户一次扫一部剧）,
    相对扫描根的镜像在那种情况下退化成扁平 —— 所有剧的 strm 全堆在输出根里。
    先建剧集名目录, 落点就与「扫的是整库还是单剧」无关。
    """
    parsed = plan.parsed
    candidates = [
        getattr(parsed, "show_name", "") if parsed is not None else "",
        posixpath.basename(landing_dir or ""),
        posixpath.basename((scan_root or "").rstrip("/")),
    ]
    for candidate in candidates:
        name = _safe_dir_name(candidate or "")
        if name:
            return name
    return ""


def rooted_rel_dir(rel_dir: str, show_dir: str) -> str:
    """把「剧集名目录」冠到相对目录上, 并去掉重复的那一层。

    扫描根在剧目录**之上**时, `rel_dir` 的首段已经是剧名（`Show/Season 01`）;
    再冠一次会得到 `Show/Show/Season 01`。首段与剧名同形（忽略大小写）时只保留
    一层 —— 两种扫描起点（整库 / 单剧）于是落到同一个位置。
    """
    parts = [part for part in (rel_dir or "").split("/") if part and part != "."]
    if show_dir and parts and parts[0].casefold() == show_dir.casefold():
        parts = parts[1:]
    if show_dir:
        parts = [show_dir, *parts]
    return "/".join(parts)


def safe_local_target(root: str, rel_dir: str, name: str) -> Optional[str]:
    """把 (根, 相对目录, 文件名) 拼成本地绝对路径; 越界返回 None。

    `rel_dir_of` 已经不产生 `..`, 这里是**独立**的第二道防线: 输入可能来自
    任何调用方（含将来的手工 API 调用）, 而「写到输出根外面」是不可逆的破坏。
    """
    root_abs = os.path.realpath(os.path.expanduser(root))
    parts = [part for part in (rel_dir or "").split("/") if part and part != "."]
    candidate = os.path.join(root_abs, *parts, name)
    resolved = os.path.realpath(candidate)
    if resolved != root_abs and not resolved.startswith(root_abs + os.sep):
        return None
    return candidate


def _rel_parts(landing_dir: str, scan_root: str, plan: RenamePlan) -> list[str]:
    """根目录模式（远端自定义 / 本地镜像）下的子目录链。

    形状: `{剧集名}/{相对扫描根}`。「剧集名」由 `show_dir_of` 兜底,
    所以哪怕扫描根就是剧目录、相对路径为空, 也仍然会建出一层剧名目录。
    """
    rel = rooted_rel_dir(
        rel_dir_of(landing_dir, scan_root),
        show_dir_of(plan, landing_dir, scan_root),
    )
    return [part for part in rel.split("/") if part]


def strm_target_for_plan(
    plan: RenamePlan,
    result: RenameResult,
    options: StrmOptions,
    scan_root: str = "",
) -> tuple[Optional[StrmTarget], Optional[str]]:
    """(落点, 不写的原因)。

    - `(None, None)`: 本行与 strm 无关（未启用 / 字幕）。
    - `(None, 原因)`: 应该写但写不成（未落地 / 缺配置 / 越界）。
    - `(target, None)`: 写到 target.path, 内容是 target.url。
    """
    if not options.enabled:
        return None, None
    # 字幕与视频的解析结果一字不差, 不挡住的话每集字幕旁都会多一个无意义的
    # .strm —— 与 NFO 管线同一条判据（看扫描器给的事实, 不嗅扩展名）。
    if plan.file_info is not None and plan.file_info.is_subtitle:
        return None, None

    landed = landed_path_of(result) is not None
    if not landed:
        return None, NOT_LANDED_STRM_REASON

    landing_path = result.new_path
    landing_dir = posixpath.dirname(landing_path)
    name = strm_filename(posixpath.basename(landing_path))

    url = build_strm_url(options.base_url, landing_path)
    if not url:
        return None, MISSING_BASE_URL

    if options.mode == "remote_same":
        path = posixpath.join(landing_dir, name)
    elif options.mode == "remote_custom":
        root = (options.remote_root or "").strip()
        if not root:
            return None, MISSING_REMOTE_ROOT
        path = posixpath.join(
            root.rstrip("/") or "/", *_rel_parts(landing_dir, scan_root, plan), name,
        )
    elif options.mode == "local":
        root = (options.local_root or "").strip()
        if not root:
            return None, MISSING_LOCAL_ROOT
        path = safe_local_target(
            root, "/".join(_rel_parts(landing_dir, scan_root, plan)), name,
        )
        if path is None:
            return None, OUT_OF_ROOT_REASON
    else:
        # Literal 已经在请求校验时挡掉非法模式; 留这支是为了 api/renamer 之外的
        # 调用方（脚本、将来的批量工具）不会静默地什么都不写。
        return None, f"未知 STRM 输出模式: {options.mode}"

    return StrmTarget(mode=options.mode, path=path, url=url), None


def strm_target_for_preview(
    plan: RenamePlan, options: StrmOptions, scan_root: str = "",
) -> tuple[Optional[StrmTarget], Optional[str]]:
    """预览用：假设该文件会落到 `plan.new_path`。

    预览没有真实结果可读（还没执行）, 但它必须显示**执行时会写到哪里** ——
    落点规则只有一份, 所以这里用一条 `pending` 结果走同一条推导, 而不是另写
    一套「预览版」规则。
    """
    assumed = RenameResult(
        id=plan.id,
        original_path=plan.original_path,
        new_path=plan.new_path,
        original_filename=plan.original_filename,
        new_filename=plan.new_filename,
        success=True,
        status="pending",
    )
    return strm_target_for_plan(plan, assumed, options, scan_root)


def strm_content(url: str) -> bytes:
    """strm 文件内容: 一行 URL（带结尾换行）。

    结尾换行不是装饰: 不少播放器与编辑器按行读取, 没有它时最后一行在某些
    实现里会被截断（Windows 工具尤其如此）。
    """
    return f"{url}\n".encode("utf-8")


def write_strm_local(target_path: str, content: bytes) -> None:
    """写本地 strm。目录按需创建, 已存在则覆盖。

    覆盖是刻意的: strm 是派生文件, 内容只由本次落点与 base URL 决定 ——
    跳过只会让旧链接留在原地, 而旧链接指向的是**旧文件名**。
    """
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    with open(target_path, "wb") as handle:
        handle.write(content)


async def ensure_remote_dir(
    client: "OpenListClient", dir_path: str, cache: dict[str, bool],
) -> None:
    """逐级创建远端目录, 成功后按路径缓存。

    失败一律忽略: `mkdir` 在「目录已存在」时也会抛错, 而这不是错误。真正的
    失败会在随后的 `put_file` 上暴露, 那里的原因串才是有意义的。
    逐级建而不是只建最后一层: OpenList 的 mkdir 不递归, 父目录不存在时子目录
    建不出来。
    """
    current = "/"
    for part in [p for p in (dir_path or "").split("/") if p]:
        current = posixpath.join(current, part)
        if current in cache:
            continue
        try:
            await client.mkdir(posixpath.dirname(current) or "/", part)
        except Exception:  # noqa: BLE001 —— 已存在是常态, 见 docstring
            pass
        cache[current] = True


async def write_strm_remote(
    client: "OpenListClient",
    target_path: str,
    content: bytes,
    cache: dict[str, bool],
) -> None:
    directory, _name = posixpath.split(target_path)
    await ensure_remote_dir(client, directory, cache)
    # PUT /api/fs/put 本身是覆盖语义, 不需要先查存在性。
    await client.put_file(target_path, content)


async def write_strm_for_plan(
    client: Optional["OpenListClient"],
    plan: RenamePlan,
    result: RenameResult,
    options: StrmOptions,
    scan_root: str = "",
) -> tuple[list[str], list[tuple[str, str]]]:
    """单文件执行后的 strm 副作用。返回 (写入的路径, [(未写的原因, 路径)])。

    **绝不抛异常** —— strm 是重命名的附属品, 它失败不能让一次已经成功的改名
    变成「操作失败」（与 NFO 同一条纪律）。
    """
    target, reason = strm_target_for_plan(plan, result, options, scan_root)
    if target is None:
        if reason is None:
            return [], []
        return [], [(result.new_path or plan.new_path, reason)]

    content = strm_content(target.url)
    try:
        if target.mode == "local":
            write_strm_local(target.path, content)
        elif target.mode == "remote_same":
            # 同目录模式不建目录: 视频就在那里, 它的父目录必然存在。省一次
            # mkdir 请求在大批量下就是省掉几千次无意义的远端调用。
            if client is None:
                raise RuntimeError("OpenList 客户端未连接")
            await client.put_file(target.path, content)
        else:
            # 客户端缺失只可能来自调用方的编程错误（远端模式必然已连接）;
            # 仍按「写入失败」降级, 不让它冒到路由层变成 500。
            if client is None:
                raise RuntimeError("OpenList 客户端未连接")
            await write_strm_remote(client, target.path, content, {})
    except Exception as exc:  # noqa: BLE001
        return [], [(target.path, f"写入失败: {exc}")]
    return [target.path], []

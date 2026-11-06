#!/usr/bin/env bash
# =============================================================================
# Episode Renamer —— 构建镜像并推送到 GitHub Container Registry (ghcr.io)
#
#   默认行为（不带任何参数）：
#     1. 从 git remote 推断镜像名   → ghcr.io/<owner>/<repo>
#     2. 从 HEAD 上的 git tag 或 frontend/package.json 推断版本号
#     3. docker build 出本机架构镜像，打上 <版本> 与 latest 两个标签
#     4. 登录 ghcr.io 并推送全部标签，最后打印远端 digest
#
#   常用示例：
#     ./docker/build-and-push.sh                     # 构建 + 推送（版本自动推断）
#     ./docker/build-and-push.sh -t 1.1.0            # 指定版本号
#     ./docker/build-and-push.sh --no-push           # 只构建到本地，验证用
#     ./docker/build-and-push.sh -p linux/amd64,linux/arm64
#                                                    # 多架构 manifest（自动走 buildx）
#     ./docker/build-and-push.sh --sha --pull        # 额外打 sha-<短哈希>，并刷新基础镜像
#
#   认证（按顺序尝试，命中即用）：
#     $GHCR_TOKEN / $GITHUB_TOKEN  ── 带 write:packages 的 PAT 或 Actions 令牌
#     gh auth token                ── 本机装了 GitHub CLI 且已登录
#     ~/.docker/config.json 已有 ghcr.io 凭据 ── 直接复用，不再重复登录
#     都没有           ── 交互式提示输入用户名 + PAT（密码不回显）
#
#   注意：GHCR 的包默认是 private，首次推送后可在
#   https://github.com/users/<owner>/packages/container/<repo>/settings 改为 public。
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# 输出
# -----------------------------------------------------------------------------
if [ -t 1 ]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
else
    C_RESET=''; C_BOLD=''; C_DIM=''; C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''
fi

log()  { printf '%s==>%s %s\n' "$C_BLUE$C_BOLD" "$C_RESET" "$*"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '%s  ✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s  !%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
die()  { printf '%s  ✗%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }

# -----------------------------------------------------------------------------
# 默认值
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

IMAGE=""                 # 空 = 从 git remote 推断
VERSION=""               # 空 = 从 git tag / package.json 推断
PLATFORMS=""             # 空 = 本机原生架构（经典 docker build）
UID_ARG="1000"           # 容器内 app 用户 uid，对应 Dockerfile 的 APP_UID
GID_ARG="1000"           # 同理，APP_GID
BUILDER=""               # 空 = buildx 默认 builder
REGISTRY="ghcr.io"

DO_PUSH=1
DO_LATEST=1
DO_SHA=0
DO_PULL=0
DRY_RUN=0

# -----------------------------------------------------------------------------
# 参数解析
# -----------------------------------------------------------------------------
usage() {
    # 只取文件头部的注释块：跳过 shebang，遇到第一个非注释行（set -euo）就停
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"
    cat <<'EOF'

选项：
  -t, --tag VER         版本号，如 1.1.0（默认：HEAD 上的 git tag，否则 frontend/package.json）
  -i, --image NAME      完整镜像名（默认：ghcr.io/<git remote 的 owner>/<repo>）
  -p, --platform LIST   目标平台，逗号分隔，如 linux/amd64,linux/arm64
                        指定后自动改用 buildx 并直接推 manifest（多架构无法 --load 到本地）
      --uid N           构建参数 APP_UID（默认 1000）
      --gid N           构建参数 APP_GID（默认 1000）
      --sha             额外打一个 sha-<短哈希> 标签，方便回滚到具体提交
      --pull            构建前强制拉取最新基础镜像
      --no-push         只构建不推送（多架构模式下退化为构建到缓存，不落本地）
      --no-latest       不额外打 latest 标签
      --builder NAME    指定 buildx builder 名称
      --dry-run         只打印将要执行的命令，不做任何实际动作
  -h, --help            显示本帮助
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        -t|--tag)       VERSION="${2:-}";   [ -n "$VERSION" ] || die "$1 需要一个版本号";   shift 2 ;;
        -i|--image)     IMAGE="${2:-}";     [ -n "$IMAGE" ]   || die "$1 需要一个镜像名";   shift 2 ;;
        -p|--platform)  PLATFORMS="${2:-}"; [ -n "$PLATFORMS" ] || die "$1 需要平台列表";   shift 2 ;;
        --uid)          UID_ARG="${2:-}";   shift 2 ;;
        --gid)          GID_ARG="${2:-}";   shift 2 ;;
        --builder)      BUILDER="${2:-}";   shift 2 ;;
        --sha)          DO_SHA=1;   shift ;;
        --pull)         DO_PULL=1;  shift ;;
        --no-push)      DO_PUSH=0;  shift ;;
        --no-latest)    DO_LATEST=0; shift ;;
        --dry-run)      DRY_RUN=1;  shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              die "未知参数：$1（用 --help 查看用法）" ;;
    esac
done

# -----------------------------------------------------------------------------
# 执行包装：dry-run 时只回显
# -----------------------------------------------------------------------------
run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '%s$%s ' "$C_DIM" "$C_RESET"
        printf '%q ' "$@"
        printf '\n'
        return 0
    fi
    "$@"
}

# -----------------------------------------------------------------------------
# 推断镜像名与版本
# -----------------------------------------------------------------------------
infer_image() {
    local url owner repo
    url="$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || true)"
    [ -n "$url" ] || die "当前仓库没有 origin 远端，请用 -i/--image 显式指定镜像名"

    # 兼容四种写法：https://host/owner/repo(.git) / git@host:owner/repo(.git)
    url="${url%.git}"
    case "$url" in
        *://*)  owner="$(printf '%s' "$url" | sed -E 's#^[a-z+]+://[^/]+/##' | cut -d/ -f1)"
                repo="$(printf '%s' "$url" | sed -E 's#^[a-z+]+://[^/]+/##' | cut -d/ -f2)" ;;
        *:*)    owner="$(printf '%s' "$url" | sed -E 's#^[^:]+:##' | cut -d/ -f1)"
                repo="$(printf '%s' "$url" | sed -E 's#^[^:]+:##' | cut -d/ -f2)" ;;
        *)      die "无法解析 origin 远端地址：$url" ;;
    esac
    [ -n "$owner" ] && [ -n "$repo" ] || die "无法从 $url 解析出 owner/repo"

    # GHCR 要求镜像路径全小写
    printf '%s/%s' "$REGISTRY" "$(printf '%s/%s' "$owner" "$repo" | tr '[:upper:]' '[:lower:]')"
}

infer_version() {
    local tag pkg
    # 1) HEAD 正好打在某个 tag 上（v1.2.3 或 1.2.3 都认）
    tag="$(git -C "$REPO_ROOT" describe --tags --exact-match 2>/dev/null || true)"
    if [ -n "$tag" ]; then
        printf '%s' "${tag#v}"
        return 0
    fi
    # 2) 前端 package.json 的 version（与 Dockerfile 的 APP_VERSION 默认值同源）
    pkg="$REPO_ROOT/frontend/package.json"
    if [ -f "$pkg" ]; then
        tag="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$pkg" | head -n1)"
        if [ -n "$tag" ]; then
            printf '%s' "$tag"
            return 0
        fi
    fi
    printf '0.0.0'
}

[ -n "$IMAGE" ]   || IMAGE="$(infer_image)"
[ -n "$VERSION" ] || VERSION="$(infer_version)"

# 登录目标跟着镜像名走：镜像名首段带据点/端口（ghcr.io、docker.io、localhost:5000）
# 就认它是 registry 主机，否则按 Docker Hub 处理
case "${IMAGE%%/*}" in
    *.*|*:*|localhost) PUSH_REGISTRY="${IMAGE%%/*}" ;;
    *)                 PUSH_REGISTRY="docker.io" ;;
esac

# 版本号再兜一层：去掉可能残留的 v 前缀与空格
VERSION="$(printf '%s' "$VERSION" | tr -d '[:space:]')"
VERSION="${VERSION#v}"
[ -n "$VERSION" ] || die "版本号为空，请用 -t/--tag 指定"

SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short=7 HEAD 2>/dev/null || printf 'unknown')"

TAGS=("$IMAGE:$VERSION")
[ "$DO_LATEST" -eq 1 ] && TAGS+=("$IMAGE:latest")
[ "$DO_SHA" -eq 1 ]    && TAGS+=("$IMAGE:sha-$SHORT_SHA")

# -----------------------------------------------------------------------------
# 前置检查
# -----------------------------------------------------------------------------
log "检查构建环境"

command -v docker >/dev/null 2>&1 || die "找不到 docker 命令"
if [ "$DRY_RUN" -eq 1 ]; then
    # dry-run 也要能在没有守护进程的机器上预览命令
    docker info >/dev/null 2>&1 || warn "Docker 守护进程当前不可用（dry-run 不校验）"
else
    docker info >/dev/null 2>&1 || die "无法连接 Docker 守护进程（未启动，或当前用户不在 docker 组）"
fi

# 多平台 → 必须 buildx；单平台 → 用经典 build，兼容性最好
USE_BUILDX=0
if [ -n "$PLATFORMS" ]; then
    command -v docker >/dev/null 2>&1 && docker buildx version >/dev/null 2>&1 \
        || die "多平台构建需要 docker buildx 插件"
    USE_BUILDX=1
fi

DOCKER_VERSION="$(docker version --format '{{.Server.Version}}' 2>/dev/null | tr -d '[:space:]' || true)"
DOCKER_ARCH="$(docker version --format '{{.Server.Arch}}' 2>/dev/null | tr -d '[:space:]' || true)"
ok "docker ${DOCKER_VERSION:-未知版本}"
info "仓库      $REPO_ROOT"
info "镜像      $IMAGE"
info "版本      $VERSION  (提交 $SHORT_SHA)"
info "标签      ${TAGS[*]}"
if [ "$USE_BUILDX" -eq 1 ]; then
    info "平台      $PLATFORMS  (buildx)"
else
    info "平台      本机原生 ${DOCKER_ARCH:-$(uname -m)}  (经典构建)"
fi
[ "$DRY_RUN" -eq 1 ] && warn "dry-run 模式：以下命令仅回显，不执行"

# -----------------------------------------------------------------------------
# 登录 registry（默认 ghcr.io，随镜像名变化）
# -----------------------------------------------------------------------------
login_registry() {
    local user token

    # 已有凭据就直接复用，避免重复写 config.json
    if [ -f "$HOME/.docker/config.json" ] && grep -q "\"$PUSH_REGISTRY\"" "$HOME/.docker/config.json" 2>/dev/null; then
        ok "已存在 $PUSH_REGISTRY 登录凭据，跳过登录"
        return 0
    fi

    token="${GHCR_TOKEN:-${GITHUB_TOKEN:-}}"
    user="${GHCR_USER:-${GITHUB_ACTOR:-}}"

    if [ -z "$token" ] && command -v gh >/dev/null 2>&1; then
        token="$(gh auth token 2>/dev/null || true)"
    fi

    if [ -z "$user" ]; then
        # 从镜像名反推 owner，GHCR 的用户名就是 GitHub 用户名/组织名
        user="$(printf '%s' "$IMAGE" | cut -d/ -f2)"
    fi

    # dry-run：不碰凭据，只回显命令
    if [ "$DRY_RUN" -eq 1 ]; then
        log "登录 $PUSH_REGISTRY（用户 ${user:-<owner>}）"
        info "（dry-run）echo '***' | docker login $PUSH_REGISTRY -u ${user:-<owner>} --password-stdin"
        return 0
    fi

    if [ -n "$token" ]; then
        log "登录 $PUSH_REGISTRY（用户 $user）"
        printf '%s' "$token" | docker login "$PUSH_REGISTRY" -u "$user" --password-stdin >/dev/null \
            || die "登录 $PUSH_REGISTRY 失败：凭据无效或缺少推送权限"
        ok "登录成功"
        return 0
    fi

    # 兜底：交互式输入
    [ -t 0 ] || die "非交互环境且没有可用令牌；请设置 GHCR_TOKEN 或 GITHUB_TOKEN"
    log "登录 $PUSH_REGISTRY（需要带 write:packages 权限的 Personal Access Token）"
    printf '    用户名 [%s]: ' "$user"
    read -r input_user
    [ -n "$input_user" ] && user="$input_user"
    printf '    PAT（输入不回显）: '
    read -r -s input_token; printf '\n'
    [ -n "$input_token" ] || die "令牌为空"
    printf '%s' "$input_token" | docker login "$PUSH_REGISTRY" -u "$user" --password-stdin >/dev/null \
        || die "登录 $PUSH_REGISTRY 失败：凭据无效或缺少推送权限"
    ok "登录成功"
}

if [ "$DO_PUSH" -eq 1 ]; then
    login_registry
fi

# -----------------------------------------------------------------------------
# 构建
# -----------------------------------------------------------------------------
BUILD_ARGS=(
    --build-arg "APP_VERSION=$VERSION"
    --build-arg "APP_UID=$UID_ARG"
    --build-arg "APP_GID=$GID_ARG"
)
[ "$DO_PULL" -eq 1 ] && BUILD_ARGS+=(--pull)

if [ "$USE_BUILDX" -eq 1 ]; then
    # ---- 多架构：直接产出 manifest 列表，无法 --load 到本地守护进程 ----
    BX_ARGS=(buildx build
        --platform "$PLATFORMS"
        --file "$REPO_ROOT/Dockerfile"
    )
    [ -n "$BUILDER" ] && BX_ARGS+=(--builder "$BUILDER")
    for t in "${TAGS[@]}"; do BX_ARGS+=(-t "$t"); done
    BX_ARGS+=("${BUILD_ARGS[@]}")
    if [ "$DO_PUSH" -eq 1 ]; then
        BX_ARGS+=(--push)
    else
        BX_ARGS+=(--output type=cacheonly)
    fi
    BX_ARGS+=("$REPO_ROOT")

    log "构建（buildx，$PLATFORMS）"
    run docker "${BX_ARGS[@]}"
else
    # ---- 单架构：经典 docker build，产物留在本地，再逐个 tag 推送 ----
    B_ARGS=(build
        --file "$REPO_ROOT/Dockerfile"
    )
    for t in "${TAGS[@]}"; do B_ARGS+=(-t "$t"); done
    B_ARGS+=("${BUILD_ARGS[@]}")
    B_ARGS+=("$REPO_ROOT")

    log "构建镜像"
    run docker "${B_ARGS[@]}"

    if [ "$DO_PUSH" -eq 1 ]; then
        log "推送标签"
        for t in "${TAGS[@]}"; do
            run docker push "$t"
            if [ "$DRY_RUN" -eq 1 ]; then
                info "（dry-run）将推送 $t"
            else
                ok "已推送 $t"
            fi
        done
    else
        warn "已跳过推送（--no-push）"
    fi
fi

# -----------------------------------------------------------------------------
# 收尾
# -----------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
    printf '\n'; ok "dry-run 结束，未产生任何镜像"; exit 0
fi

if [ "$DO_PUSH" -eq 1 ]; then
    printf '\n'
    log "完成"
    for t in "${TAGS[@]}"; do
        digest="$(docker buildx imagetools inspect "$t" --format '{{json .Manifest.Digest}}' 2>/dev/null | tr -d '"' || true)"
        info "$t${digest:+  @ $digest}"
    done
    printf '\n'
    info "拉取：docker pull $IMAGE:$VERSION"
    info "运行：docker run -d -p 6969:6969 -v /你的媒体目录:/media:ro $IMAGE:$VERSION"
    if [ "$PUSH_REGISTRY" = "ghcr.io" ]; then
        owner="$(printf '%s' "$IMAGE" | cut -d/ -f2)"
        name="$(printf '%s' "$IMAGE" | cut -d/ -f3)"
        info "改可见性：https://github.com/users/$owner/packages/container/$name/settings"
    fi
else
    printf '\n'; ok "构建完成（未推送）：${TAGS[0]}"
    info "本地试跑：docker run --rm -p 6969:6969 -v /你的媒体目录:/media:ro ${TAGS[0]}"
fi

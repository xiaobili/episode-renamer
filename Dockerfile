# =============================================================================
# Episode Renamer —— 单镜像构建（self-contained）
#
#   构建期完成三件事，产物只留下一个运行镜像：
#     1. 前端（Vue 3 + Vite）编译成静态产物；
#     2. Python 依赖装进独立 venv；
#     3. 两者与人一起装进最终镜像。
#
#   运行期不需要 Node、不需要源码树、不需要 pip、不需要联网安装任何东西，
#   可以 `docker save` 后拷到无网络机器上 `docker load` 直接跑。
#
#   构建：docker build -t episode-renamer:latest .
#   运行：docker run -d -p 6969:6969 -v /你的媒体目录:/media:ro episode-renamer:latest
# =============================================================================

ARG NODE_IMAGE=node:20-bookworm-slim
ARG PYTHON_IMAGE=python:3.12-slim-bookworm


# -----------------------------------------------------------------------------
# Stage 1 / 3 —— 前端构建
# -----------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS frontend

WORKDIR /build/frontend

# 先只拷清单，让 npm 层在源码变动时仍可命中缓存
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# -----------------------------------------------------------------------------
# Stage 2 / 3 —— Python 运行时依赖（装进 venv，连解释器环境一起搬走）
# -----------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS python-deps

# 注意：这里**不设** PIP_NO_CACHE_DIR —— 否则下面的 pip 缓存挂载形同虚设。
# 缓存只存在于挂载点，不会进入镜像层。
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential 只在这一层出现：万一时没有预编译 wheel，也能当场编译；
# 它不会进入最终镜像，最终镜像里没有编译器。
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY backend/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt


# -----------------------------------------------------------------------------
# Stage 3 / 3 —— 运行镜像（最终镜像，也是默认构建目标）
# -----------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ARG APP_VERSION=1.0.0
ARG APP_UID=1000
ARG APP_GID=1000

LABEL org.opencontainers.image.title="Episode Renamer" \
      org.opencontainers.image.description="电视剧/番剧自动化重命名工具：本地磁盘 + OpenList 双源，FastAPI + Vue 3 单镜像" \
      org.opencontainers.image.source="https://github.com/xiaobili/episode-renamer" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH \
    HOME=/app \
    HOST=0.0.0.0 \
    PORT=6969 \
    DEBUG=false

# tzdata 是唯一的系统级运行依赖；ca-certificates 由 python:slim 基础镜像自带，
# TMDB / OpenList 的 HTTPS 请求靠它。
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 非 root 运行。APP_UID / APP_GID 可在构建时改成宿主机媒体目录的属主，
# 这样容器写 NFO / STRM 不会在宿主机上留下 root 属主的文件：
#   docker build --build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g) .
RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home --shell /usr/sbin/nologin app

# venv 整体搬过来：最终镜像里没有任何 pip 安装动作残留
COPY --from=python-deps /opt/venv /opt/venv

WORKDIR /app

# 后端只拷运行期需要的部分（tests / pytest.ini / requirements-dev 不进入镜像）
COPY --chown=app:app backend/app ./backend/app
COPY --chown=app:app backend/run.py ./backend/run.py
COPY --chown=app:app docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# 前端静态产物：main.py 按 <repo>/frontend/dist 定位，容器内即 /app/frontend/dist
COPY --from=frontend --chown=app:app /build/frontend/dist ./frontend/dist

# config.py 导入时会 mkdir(data/, logs/)，必须提前建好且可写；
# /media 作为媒体目录的默认挂载点。其余文件已由 COPY --chown 归 app 所有，
# 这里只处理新建的空目录，避免整棵树重写元数据。
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/data /app/logs /media \
    && chown app:app /app/data /app/logs /media

USER app

WORKDIR /app/backend

EXPOSE 6969

# 健康检查跟随 PORT 环境变量，避免改端口后检查打到空处
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '6969'), timeout=3)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

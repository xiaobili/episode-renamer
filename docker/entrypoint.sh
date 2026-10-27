#!/bin/sh
# Episode Renamer 容器入口
#   - HOST / PORT 走环境变量，镜像可独立部署到任意端口
#   - worker 数固定为 1：execute 与 finalize 依赖进程内的文件缓存，多 worker 会读到空缓存
#   - 传了参数就按参数执行，方便 `docker run <image> python -m pytest` 这类覆盖
set -eu

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-6969}"

exec python -m uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers 1

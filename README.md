# Episode Renamer

电视剧 / 番剧自动化重命名工具，支持本地文件和 OpenList 云盘，输出符合 Emby / Jellyfin 刮削规范的文件结构。

!\[badge]\(https\://img.shields.io/badge/python-3.9+-blue.svg null) !\[badge]\(https\://img.shields.io/badge/vue-3-42b883.svg null) !\[badge]\(https\://img.shields.io/badge/FastAPI-0.110-009688.svg null) !\[badge]\(https\://img.shields.io/badge/TailwindCSS-4-38bdf8.svg null)

## ✨ 功能特性

- **双数据源** — 本地磁盘 + OpenList 云盘统一处理
- **智能解析** — 支持父文件夹剧名，识别 `S01E01`、`01~4k`、`第2季第3话`、`sbtj03` 等多种命名
- **模板系统** — 预设模板 + 自定义模板，支持 `{show}` `{season}` `{episode}` `{year}` 等变量
- **自动季文件夹** — 本地模式可自动创建 `Season 01/` 目录并移动文件
- **试运行 (Dry Run)** — 先预览再执行，零风险
- **批量重命名** — 并发 BFS 扫描 + 分组批量 move，大目录高效处理
- **Docker 一键部署** — 支持健康检查，挂载媒体目录即可运行

## 🖥️ 界面预览

> 主工作区

!\[home]\(./screenshot/home.png null)

> OpenList 目录浏览

!\[browse]\(./screenshot/browse.png null)

> 设置页

!\[settings]\(./screenshot/settings.png null)

## 🛠️ 技术栈

| 层  | 技术                                                         |
| -- | ---------------------------------------------------------- |
| 前端 | Vue 3 + Pinia + Vue Router + Tailwind CSS 4 + Lucide Icons |
| 后端 | Python 3.9+ + FastAPI + Pydantic 2 + httpx + uvicorn       |
| 部署 | Docker + docker-compose + Nginx (静态托管)                     |

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 克隆项目
git clone https://github.com/yourname/episode-renamer.git
cd episode-renamer

# 编辑 docker-compose.yml，把 volumes 里的路径改成你的媒体目录
# volumes:
#   - /your/media/path:/media:ro

# 一键构建并启动
docker compose up -d --build
```

浏览器访问 `http://localhost:6969` 即可使用。

### 方式二：本地开发

**前置条件**: Python 3.9+、Node.js 18+

```bash
# 克隆项目
git clone https://github.com/yourname/episode-renamer.git
cd episode-renamer

# --- 后端 ---
cd backend
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                 # http://localhost:8000

# --- 前端（新终端）---
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

后端启动后前端自动代理到 `localhost:8000`。

## ⚙️ 配置

### 后端环境变量

| 变量                | 默认        | 说明               |
| ----------------- | --------- | ---------------- |
| `HOST`            | `0.0.0.0` | 监听地址             |
| `PORT`            | `6969`    | 监听端口             |
| `DEBUG`           | `false`   | 开启热重载和详细日志       |
| `UVICORN_WORKERS` | `1`       | uvicorn worker 数 |

创建 `.env` 文件放在 `backend/` 下或通过环境变量传入：

```bash
PORT=6969
DEBUG=false
```

### OpenList 集成

在应用内依次：

1. **设置页** — 填入 OpenList 服务器地址（如 `http://your-openlist:5244`）和管理员凭证
2. **工作区 OpenList Tab** — 登录成功后选择 mount 点 → 浏览选择子目录 → 扫描 → 重命名

> 🔒 OpenList 扫描强制要求选择**子目录**，禁止全盘扫描。

## 📦 模板与变量

内置预设模板：

| 名称      | 模板                                      | 输出示例                          |
| ------- | --------------------------------------- | ----------------------------- |
| Emby 标准 | `{show} - S{season}E{episode}`          | `绝命毒师 - S02E05.mp4`           |
| 含年份     | `{show} ({year}) - S{season}E{episode}` | `绝命毒师 (2008) - S02E05.mp4`    |
| 季文件夹    | 模板 `Season {season_padded}` + 文件名模板     | `Season 02/绝命毒师 - S02E05.mp4` |

可用变量：

```
{show}              剧名
{year}              年份
{season}            季号 (1-99)
{season_padded}     季号补零 (01-99)
{episode}           集号 (1-999)
{episode_padded}    集号补零 (001-999)
{title}             副标题 (部分解析时可用)
{ext}               原扩展名
```

## 📂 项目结构

```
episode-renamer/
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── core/                 # 核心引擎
│   │   │   ├── parser.py         # 文件名解析（正则 + 父文件夹剧名）
│   │   │   ├── template.py       # 模板变量渲染
│   │   │   ├── local_scanner.py  # 本地目录扫描
│   │   │   ├── local_renamer.py  # 本地批量重命名
│   │   │   ├── openlist_client.py
│   │   │   ├── openlist_scanner.py  # 云盘并发 BFS 扫描
│   │   │   └── openlist_renamer.py  # 云盘分组批量 move
│   │   ├── api/                  # REST 路由
│   │   ├── models/               # Pydantic 模型
│   │   ├── config.py
│   │   └── main.py
│   ├── run.py
│   └── requirements.txt
├── frontend/                     # Vue 3 前端
│   ├── src/
│   │   ├── api/                  # axios 封装
│   │   ├── stores/               # Pinia stores
│   │   ├── views/                # 页面（HomeView / SettingsView）
│   │   ├── App.vue
│   │   ├── main.js
│   │   └── style.css             # Tailwind + 设计 token
│   ├── vite.config.js
│   └── package.json
├── Dockerfile                    # 多阶段构建
├── docker-compose.yml
└── README.md
```

## 🔌 API 速览

所有接口前缀 `/api`。

| 方法   | 路径                     | 说明                 |
| ---- | ---------------------- | ------------------ |
| POST | `/api/scan`            | 扫描本地目录返回文件列表       |
| POST | `/api/preview`         | 根据模板生成预览重命名结果      |
| POST | `/api/execute`         | 执行重命名（支持 dry\_run） |
| POST | `/api/openlist/login`  | OpenList 登录        |
| GET  | `/api/openlist/mounts` | 获取 mount 点列表       |
| POST | `/api/openlist/browse` | 浏览云盘子目录            |
| POST | `/api/openlist/scan`   | 扫描云盘子目录            |
| GET  | `/api/presets`         | 获取预设模板列表           |
| GET  | `/health`              | 健康检查               |

OpenAPI 文档：`http://localhost:6969/docs`

## 📄 License

MIT

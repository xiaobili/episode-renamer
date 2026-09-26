from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .config import settings


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    description="Episode Renamer - 电视剧/番剧自动化重命名工具",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api import scanner, parser, renamer, template, openlist, tmdb

app.include_router(scanner.router)
app.include_router(parser.router)
app.include_router(renamer.router)
app.include_router(template.router)
app.include_router(openlist.router)
app.include_router(tmdb.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/info")
async def api_info():
    return {
        "name": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "status": "running",
    }


@app.get("/api/files")
async def get_cached_files():
    from .api.renamer import get_cached_files
    files = get_cached_files()
    return {
        "success": True,
        "total": len(files),
        "files": [f.model_dump() for f in files],
    }


frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(frontend_dist / "index.html")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")

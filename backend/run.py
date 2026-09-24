import uvicorn
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings


def main():
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()

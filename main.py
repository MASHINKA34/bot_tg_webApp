from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from contextlib import asynccontextmanager
from backend.database import init_db, close_db
from backend.config import settings
from backend.routers import clicker, farms, daily, leaderboard, referral, link
import logging
import time
import os
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Запуск приложения")
    await init_db(settings.DATABASE_URL)
    logger.info(
        f"✅ PostgreSQL подключён: "
        f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
    yield
    await close_db()
    logger.info("🛑 Остановка приложения")


app = FastAPI(title="Clicker Web App", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s"
    )
    # Отключить кеширование для JS и HTML (чтобы Telegram всегда грузил свежую версию)
    path = request.url.path
    if path.endswith(".js") or path.endswith(".html") or path == "/" or path == "":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clicker.router, prefix="/api")
app.include_router(farms.router, prefix="/api")
app.include_router(daily.router, prefix="/api")
app.include_router(leaderboard.router, prefix="/api")
app.include_router(referral.router, prefix="/api")
app.include_router(link.router, prefix="/api")

NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


@app.get("/app.js")
async def serve_app_js():
    """Служит app.js с гарантированными no-cache заголовками."""
    resp = FileResponse(
        os.path.join(FRONTEND_DIR, "app.js"),
        media_type="application/javascript",
        headers=NO_CACHE_HEADERS,
    )
    return resp


@app.get("/")
@app.get("/index.html")
async def serve_index():
    """Служит index.html с динамическим timestamp в URL app.js — предотвращает кеш навсегда."""
    with open(os.path.join(FRONTEND_DIR, "index.html"), "r", encoding="utf-8") as f:
        html = f.read()
    # Каждый раз новый timestamp → Telegram никогда не найдёт app.js в кеше
    ts = int(time.time())
    html = re.sub(r'src="app\.js\?v=[^"]*"', f'src="app.js?v={ts}"', html)
    return HTMLResponse(content=html, headers=NO_CACHE_HEADERS)


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    logger.info("🎮 Clicker Web App запускается на http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

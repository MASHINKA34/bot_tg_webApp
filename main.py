from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from backend.database import init_db
from backend.routers import clicker, farms, daily, leaderboard
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Запуск приложения")
    await init_db()
    logger.info("✅ База данных инициализирована")
    yield
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

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    logger.info("🎮 Clicker Web App запускается на http://0.0.0.0:8000")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_level="info"
    )

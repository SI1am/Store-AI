import os
import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
from pydantic_settings import BaseSettings

from api.db import Database
from api.cache import CacheManager

# Configure Pydantic settings to load configurations
class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/retail_db"
    redis_url: str = "redis://localhost:6379"
    log_level: str = "info"
    model_path: str = "models/yolov8n.pt"
    api_port: int = 8000

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

# Configure structlog JSON structured logs
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()

# Custom Exceptions
class StoreLensException(Exception):
    """Base exception for StoreLens."""
    pass

class StoreNotFoundException(StoreLensException):
    def __init__(self, store_id: str):
        self.store_id = store_id
        super().__init__(f"Store with ID '{store_id}' does not exist.")

class DatabaseException(StoreLensException):
    pass

# Lifespan Context Manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Database and Caching connections if not already present (e.g., in unit tests)
    if not hasattr(app.state, "db") or app.state.db is None:
        app.state.db = Database(settings.database_url)
    if not hasattr(app.state, "cache") or app.state.cache is None:
        app.state.cache = CacheManager(settings.redis_url)
    
    try:
        await app.state.db.connect()
    except Exception as e:
        logger.warning("db_connection_failed_at_startup", error=str(e))
        
    try:
        await app.state.cache.connect()
    except Exception as e:
        logger.warning("cache_connection_failed_at_startup", error=str(e))
    
    logger.info("Application startup complete", port=settings.api_port)
    
    yield
    
    # Clean shutdown
    try:
        await app.state.db.disconnect()
    except Exception:
        pass
        
    try:
        await app.state.cache.disconnect()
    except Exception:
        pass
    
    logger.info("Application shutdown completed")

# Create FastAPI instance
app = FastAPI(
    title="StoreLens",
    description="Real-time retail video analytics and conversion metrics correlating store cameras with POS data.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Logging Middleware
@app.middleware("http")
async def add_trace_id_and_log(request: Request, call_next):
    # Retrieve trace_id from headers or generate new UUID
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    request.scope["trace_id"] = trace_id
    
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 2)
    
    # Log request and metrics
    logger.info(
        "request_processed",
        trace_id=trace_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=duration_ms
    )
    
    # Propagate trace ID back in response headers
    response.headers["X-Trace-ID"] = trace_id
    return response

# Exception handlers
@app.exception_handler(StoreLensException)
async def storelens_exception_handler(request: Request, exc: StoreLensException):
    trace_id = request.scope.get("trace_id", "N/A")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": {
                "code": "SERVER_ERROR",
                "message": str(exc),
                "trace_id": trace_id
            }
        }
    )

@app.exception_handler(StoreNotFoundException)
async def store_not_found_handler(request: Request, exc: StoreNotFoundException):
    trace_id = request.scope.get("trace_id", "N/A")
    return JSONResponse(
        status_code=404,
        content={
            "status": "error",
            "error": {
                "code": "STORE_NOT_FOUND",
                "message": str(exc),
                "trace_id": trace_id,
                "details": {"store_id": exc.store_id}
            }
        }
    )

# Include Routers (Dynamically loaded in routes package)
from api.routes.events import router as events_router
from api.routes.metrics import router as metrics_router
from api.routes.funnel import router as funnel_router
from api.routes.heatmap import router as heatmap_router
from api.routes.anomalies import router as anomalies_router
from api.routes.health import router as health_router

app.include_router(events_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(funnel_router, prefix="/api/v1")
app.include_router(heatmap_router, prefix="/api/v1")
app.include_router(anomalies_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")

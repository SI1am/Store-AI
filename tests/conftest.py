import os
import sys
import pytest
import asyncio
import fakeredis
from typing import Generator, AsyncGenerator
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Add workspace root to system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app
from api.db import Database
from api.cache import CacheManager
from detection.pipeline import DetectionPipeline

# Set event loop policy for Windows if needed
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Creates a session-scoped event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_redis():
    """Provides an in-memory async-compatible FakeRedis client."""
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis(decode_responses=True)

@pytest.fixture
async def cache(mock_redis) -> CacheManager:
    """Provides a mocked CacheManager using FakeRedis."""
    manager = CacheManager("redis://localhost:6379")
    manager.client = mock_redis
    return manager

@pytest.fixture
async def db() -> Database:
    """Provides a Database mock or connection wrapper."""
    # We load DSN from environment
    dsn = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/retail_db")
    db_conn = Database(dsn)
    # We don't call actual connect() in unit tests unless testing integration
    return db_conn

@pytest.fixture
def sample_zones_config() -> dict:
    """Mock store configurations for testing."""
    return {
        "S001": {
            "frame_width": 640,
            "frame_height": 480,
            "entry_line": [[0.0, 0.8], [1.0, 0.8]],
            "zones": {
                "BILLING": {
                    "type": "polygon",
                    "points": [[0.7, 0.7], [1.0, 0.7], [1.0, 1.0], [0.7, 1.0]]
                },
                "PRODUCT_A": {
                    "type": "polygon",
                    "points": [[0.0, 0.0], [0.4, 0.0], [0.4, 0.5], [0.0, 0.5]]
                }
            }
        }
    }

@pytest.fixture
def pipeline(sample_zones_config) -> DetectionPipeline:
    """Provides a test instance of the DetectionPipeline."""
    return DetectionPipeline(
        model_path="models/yolov8n.pt",
        store_id="S001",
        camera_id="CAM_A",
        zones_config=sample_zones_config,
        output_path="test_output.jsonl"
    )

@pytest.fixture
def client(mock_redis) -> Generator[TestClient, None, None]:
    """Provides a standard TestClient for synchronous API testing with mocked Database/Redis."""
    # Inject FakeRedis client directly into app state
    app.state.cache = CacheManager("redis://localhost:6379")
    app.state.cache.client = mock_redis
    
    # Inject a mocked DB into app state to prevent real queries
    from unittest.mock import MagicMock, AsyncMock
    db_mock = MagicMock()
    db_mock.fetch_val = AsyncMock(return_value=0)
    db_mock.fetch_one = AsyncMock(return_value=None)
    db_mock.fetch_all = AsyncMock(return_value=[])
    db_mock.execute = AsyncMock(return_value="INSERT 0 1")
    db_mock.executemany = AsyncMock(return_value=None)
    
    app.state.db = db_mock
    
    with TestClient(app) as tc:
        yield tc

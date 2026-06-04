import logging
import asyncpg
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Initializes the PostgreSQL connection pool asynchronously."""
        if self.pool is not None:
            return
            
        logger.info("Initializing asyncpg PostgreSQL connection pool...")
        try:
            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=5,
                max_size=20,
                max_inactive_connection_lifetime=300.0
            )
            logger.info("PostgreSQL connection pool initialized successfully.")
        except Exception as e:
            error_msg = f"Failed to connect to PostgreSQL: {e}"
            logger.error(error_msg)
            raise ConnectionError(error_msg) from e

    async def disconnect(self) -> None:
        """Closes the connection pool and releases all resources."""
        if self.pool is None:
            return
            
        logger.info("Closing PostgreSQL connection pool...")
        try:
            await self.pool.close()
            self.pool = None
            logger.info("PostgreSQL connection pool closed cleanly.")
        except Exception as e:
            logger.warning(f"Failed to close PostgreSQL pool cleanly: {e}")

    async def execute(self, query: str, *args: Any) -> str:
        """Executes a query (INSERT, UPDATE, DELETE) and returns the status string."""
        if self.pool is None:
            raise RuntimeError("Database pool is not connected. Call connect() first.")
            
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch_one(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        """Queries the database and returns a single record, or None if empty."""
        if self.pool is None:
            raise RuntimeError("Database pool is not connected. Call connect() first.")
            
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch_all(self, query: str, *args: Any) -> List[asyncpg.Record]:
        """Queries the database and returns multiple records in a list."""
        if self.pool is None:
            raise RuntimeError("Database pool is not connected. Call connect() first.")
            
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetch_val(self, query: str, *args: Any) -> Any:
        """Queries the database and returns a single value from the first row and column."""
        if self.pool is None:
            raise RuntimeError("Database pool is not connected. Call connect() first.")
            
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def executemany(self, query: str, params: List[Any]) -> None:
        """Executes a batch of queries in a single database round-trip (highly optimized for ingestion)."""
        if self.pool is None:
            raise RuntimeError("Database pool is not connected. Call connect() first.")
            
        async with self.pool.acquire() as conn:
            await conn.executemany(query, params)

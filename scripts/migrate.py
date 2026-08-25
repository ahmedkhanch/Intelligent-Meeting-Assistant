#!/usr/bin/env python
"""Run database migrations — creates all tables.

Usage:
    python scripts/migrate.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Base
from app.db.session import engine


async def migrate() -> None:
    print("Running migrations...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ All tables created.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())

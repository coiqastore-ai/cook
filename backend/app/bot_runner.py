"""Entry point: uv run python -m app.bot_runner"""
import asyncio
from app.bot import main

asyncio.run(main())

"""python -m app.scheduler entrypoint."""

import asyncio

from app.scheduler.main import main

if __name__ == "__main__":
    asyncio.run(main())

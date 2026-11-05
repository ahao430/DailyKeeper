"""python -m app.browser_worker entrypoint."""

import asyncio

from app.browser_worker.main import main

if __name__ == "__main__":
    asyncio.run(main())

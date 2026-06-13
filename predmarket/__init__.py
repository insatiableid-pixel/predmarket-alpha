import asyncio
import sys

# Ensure an active event loop is available in the current thread for async
# venue clients imported during application startup.
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

__version__ = "1.0.0"

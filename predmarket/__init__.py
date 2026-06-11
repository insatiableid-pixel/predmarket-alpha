import asyncio
import sys

# Ensure an active event loop is available in the current thread to prevent 
# eventkit/ib_insync from throwing RuntimeError on import in Python 3.12+
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

__version__ = "1.0.0"

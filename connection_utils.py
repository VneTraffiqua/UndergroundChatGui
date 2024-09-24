from contextlib import asynccontextmanager
import asyncio


@asynccontextmanager
async def manage_connection(host, port):
    reader, writer = await asyncio.open_connection(host=host, port=port)
    try:
        yield reader, writer
    finally:
        writer.close()
        await writer.wait_closed()

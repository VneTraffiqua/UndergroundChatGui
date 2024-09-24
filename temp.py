import asyncio
import  aiofiles
import gui
import datetime
from environs import Env
from connection_utils import manage_connection

SEC=1

loop = asyncio.get_event_loop()

messages_queue = asyncio.Queue()
sending_queue = asyncio.Queue()
status_updates_queue = asyncio.Queue()
saved_massages_queue = asyncio.Queue()

async def read_history(filepath, queue):
    async with aiofiles.open(filepath, 'r') as file:
        messages = await file.readlines()
        for message in messages:
            queue.put_nowait(message.strip())

async def save_messages(file_path, queue):
    while True:
        message = await queue.get()
        async with aiofiles.open(file=file_path, mode='a') as file:
            await file.write(message.strip())

async def read_msgs(host, port, queue):
    async with manage_connection(host, port) as (reader, writer):
        while True:
            line = await reader.readline()
            chat_with_time = datetime.datetime.now().strftime('%Y-%m-%d | %H.%M.%S || ') + line.decode("utf-8").rstrip()
            queue.put_nowait(chat_with_time)


async def generate_msgs(queue):
    while True:
        formatted_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        queue.put_nowait(formatted_date)
        await asyncio.sleep(SEC)


async def main():
    env = Env()
    env.read_env()

    connection_host = env.str('HOST')
    connection_port = env.str('CHAT_PORT')
    connection_token = env.str('TOKEN')
    output_file = env.str('FILE_PATH')

    await read_history(output_file, messages_queue)

    await asyncio.gather(
        read_msgs(connection_host, connection_port, messages_queue),
        save_messages(output_file, saved_massages_queue),
        gui.draw(messages_queue, sending_queue, status_updates_queue)
    )

if __name__ == '__main__':
    loop.run_until_complete(main())

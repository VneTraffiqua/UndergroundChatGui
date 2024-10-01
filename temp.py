import asyncio
import  aiofiles
import gui
import datetime
import logging
import json
import async_timeout
from environs import Env
from connection_utils import manage_connection, InvalidToken


logging.basicConfig(
    format=u'# %(levelname)-4s [%(asctime)s]  %(message)s',
    level=logging.INFO,
    filename='watchdog_logger.log'
)

SEC=1
SLEEP_SEC=0

loop = asyncio.get_event_loop()

messages_queue = asyncio.Queue()
sending_queue = asyncio.Queue()
status_updates_queue = asyncio.Queue()
saved_massages_queue = asyncio.Queue()
error_queue = asyncio.Queue()
watchdog_queue = asyncio.Queue()


async def is_authentic_token(reader, writer, token):
    writer.write(f'{token}\n\n'.encode())
    watchdog_queue.put_nowait('Connection is alive. Prompt before auth')
    await writer.drain()
    for _ in range(2):
        results = await reader.readline()
    if json.loads(results):
        nickname = gui.NicknameReceived(json.loads(results)['nickname'])
        status_updates_queue.put_nowait(nickname)
    return json.loads(results)

async def send_msgs(host, port, queue, token):
    async with manage_connection(host, port) as (reader, writer):
        status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.INITIATED)
        if not await is_authentic_token(reader, writer, token):
            error_queue.put_nowait('Invalid token')
            watchdog_queue.put_nowait('Connection lost. Invalid token')
            status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.CLOSED)
            raise InvalidToken('Invalid token')
        watchdog_queue.put_nowait('Connection is alive. Authorization done')
        while True:
            status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.ESTABLISHED)
            print(await reader.readline())
            msg = await queue.get()
            if msg:
                watchdog_queue.put_nowait('Connection is alive. Message sent')
                writer.write(f'{msg}\n\n'.encode())
            await writer.drain()

async def read_history(filepath, queue):
    async with aiofiles.open(filepath, 'r') as file:
        messages = await file.readlines()
        for message in messages:
            queue.put_nowait(message.strip())

async def save_messages(file_path, queue):
    while True:
        message = await queue.get()
        async with aiofiles.open(file=file_path, mode='a') as file:
            await file.write(f'{message.strip()}\n')

async def read_msgs(host, port, queue):
    status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.INITIATED)
    async with manage_connection(host, port) as (reader, writer):
        while True:
            status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.ESTABLISHED)
            line = await reader.readline()
            chat_with_time = datetime.datetime.now().strftime('%Y-%m-%d | %H.%M.%S || ') + line.decode("utf-8").rstrip()
            queue.put_nowait(chat_with_time)
            watchdog_queue.put_nowait('Connection is alive. New message in chat')
            saved_massages_queue.put_nowait(chat_with_time)

async def generate_msgs(queue):
    while True:
        formatted_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        queue.put_nowait(formatted_date)
        await asyncio.sleep(SEC)

async def watch_for_connection(queue):
    time_out = 0
    while True:
        try:
            async with async_timeout.timeout(1) as cm:
                msg = await queue.get()
                logging.info(msg=msg)
                await asyncio.sleep(SLEEP_SEC)
        except asyncio.TimeoutError:
            time_out +=1
            print(f'Операция прервана по тайм-ауту. {time_out} сек.')
        if cm.expired:
            logging.info(msg='Тайм-аут истек')


async def main():
    env = Env()
    env.read_env()

    connection_host = env.str('HOST')
    connection_port = env.str('CHAT_PORT')
    writer_port = env.str('WRITER_PORT')
    connection_token = env.str('TOKEN')
    output_file = env.str('FILE_PATH')

    await read_history(output_file, messages_queue)

    await asyncio.gather(
        send_msgs(connection_host, writer_port, sending_queue, connection_token),
        save_messages(output_file, saved_massages_queue),
        read_msgs(connection_host, connection_port, messages_queue),
        gui.draw(messages_queue, sending_queue, status_updates_queue, error_queue),
        watch_for_connection(watchdog_queue)
    )

if __name__ == '__main__':
    loop.run_until_complete(main())

import asyncio
import aiofiles
import gui
import datetime
import logging
import json
import anyio
import async_timeout
import socket
from environs import Env
from connection_utils import manage_connection, InvalidToken
from gui import TkAppClosed
import sys

logging.basicConfig(
    format=u'%(filename)s[LINE:%(lineno)d]# %(levelname)-4s [%(asctime)s]  %(message)s',
    level=logging.INFO,
    filename='watchdog_logger.log'
)

CHECK_CONN_TIMEOUT=3

loop = asyncio.get_event_loop()


async def is_authentic_token(reader, writer, token, queues):
    writer.write(f'{token}\n\n'.encode())
    queues['watchdog_queue'].put_nowait('Connection is alive. Prompt before auth')
    await writer.drain()
    for _ in range(2):
        results = await reader.readline()
    if json.loads(results):
        nickname = gui.NicknameReceived(json.loads(results)['nickname'])
        queues['status_updates_queue'].put_nowait(nickname)
    return json.loads(results)

async def watch_for_connection(queue):
    while True:
        msg = await queue.get()
        logging.info(msg=msg)

async def ping_pong(host, port, queues):
    async with manage_connection(host, port) as (reader, writer):
        while True:
            async with async_timeout.timeout(CHECK_CONN_TIMEOUT) as time_out:
                try:
                    writer.write('\n\n'.encode())
                    writer.drain()
                    await reader.readline()
                    await asyncio.sleep(1)
                finally:
                    if time_out.expired:
                        queues['status_updates_queue'].put_nowait(gui.ReadConnectionStateChanged.CLOSED)
                        queues['status_updates_queue'].put_nowait(gui.SendingConnectionStateChanged.CLOSED)
                        raise ConnectionError

async def send_msgs(host, port, queues, token):
    queues['status_updates_queue'].put_nowait(gui.SendingConnectionStateChanged.INITIATED)
    async with manage_connection(host, port) as (reader, writer):
        if not await is_authentic_token(reader, writer, token, queues):
            queues['error_queue'].put_nowait('Invalid token')
            queues['watchdog_queue'].put_nowait('Connection lost. Invalid token')
            queues['status_updates_queue'].put_nowait(gui.SendingConnectionStateChanged.CLOSED)
            raise InvalidToken('Invalid token')
        queues['watchdog_queue'].put_nowait('Connection is alive. Authorization done')
        while True:
            queues['status_updates_queue'].put_nowait(gui.SendingConnectionStateChanged.ESTABLISHED)
            msg = await queues['sending_queue'].get()
            if msg:
                queues['watchdog_queue'].put_nowait('Connection is alive. Message sent')
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

async def read_msgs(host, port, queues):
    queues['status_updates_queue'].put_nowait(gui.ReadConnectionStateChanged.INITIATED)
    async with manage_connection(host, port) as (reader, writer):
        while True:
            queues['status_updates_queue'].put_nowait(gui.ReadConnectionStateChanged.ESTABLISHED)
            line = await reader.readline()
            chat_with_time = datetime.datetime.now().strftime('%Y-%m-%d | %H.%M.%S || ') + line.decode("utf-8").rstrip()
            queues['messages_queue'].put_nowait(chat_with_time)
            queues['watchdog_queue'].put_nowait('Connection is alive. New message in chat')
            queues['saved_massages_queue'].put_nowait(chat_with_time)



async def handle_connection(host, reader_port, writer_port, token, queues):
    while True:
        try:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(ping_pong, host, writer_port, queues)
                task_group.start_soon(send_msgs, host, writer_port, queues, token)
                task_group.start_soon(read_msgs, host, reader_port, queues)
                task_group.start_soon(watch_for_connection, queues['watchdog_queue'])
        except ConnectionError as e:
            queues['watchdog_queue'].put_nowait(f'{e}...Reconnecting to server')
            await asyncio.sleep(5)
        except ExceptionGroup as eg:
            print(f"Raise any exceptions:")
            for exc in eg.exceptions:
                print(f'- {type(exc).__name__}: {exc}')
                if isinstance(exc, (TkAppClosed, KeyboardInterrupt)):
                    sys.exit(0)
            await asyncio.sleep(5)
        except socket.gaierror as e:
            queues['watchdog_queue'].put_nowait(f'{e}...Reconnecting to server')


async def main():
    env = Env()
    env.read_env()

    connection_host = env.str('HOST')
    connection_port = env.str('CHAT_PORT')
    writer_port = env.str('WRITER_PORT')
    connection_token = env.str('TOKEN')
    output_file = env.str('FILE_PATH')

    queues = {
        'messages_queue': asyncio.Queue(),
        'sending_queue': asyncio.Queue(),
        'status_updates_queue': asyncio.Queue(),
        'saved_massages_queue': asyncio.Queue(),
        'error_queue': asyncio.Queue(),
        'watchdog_queue': asyncio.Queue()
    }

    await read_history(output_file, queues['messages_queue'])

    try:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(
                handle_connection, connection_host, connection_port, writer_port, connection_token, queues
            )
            task_group.start_soon(save_messages, output_file, queues['saved_massages_queue'])
            task_group.start_soon(
                gui.draw,
                queues['messages_queue'],
                queues['sending_queue'],
                queues['status_updates_queue'],
                queues['error_queue']
            )
    except ExceptionGroup as eg:
        for exc in eg.exceptions:
            if isinstance(exc, (TkAppClosed, KeyboardInterrupt)):
                sys.exit(0)
        raise eg
    except (TkAppClosed, KeyboardInterrupt):
        sys.exit(0)
    except (TkAppClosed, KeyboardInterrupt):
        raise SystemExit(0)

if __name__ == '__main__':
    try:
        loop.run_until_complete(main())
    except (TkAppClosed, KeyboardInterrupt):
        sys.exit(0)

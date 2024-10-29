import tkinter as tk
from tkinter import messagebox
import asyncio
import sys
from connection_utils import manage_connection
from environs import Env
import json
import aiofiles
from gui import TkAppClosed


async def register(host, port, nickname):
    async with manage_connection(host, port) as (reader, writer):
        await reader.readline()
        writer.write('\n'.encode())
        await reader.readline()
        nickname = nickname.replace('\n', '').strip()
        writer.write(f'{nickname}\n'.encode())
        await  writer.drain()
        data = await reader.readline()
        response = json.loads(data.decode())
        async with aiofiles.open(file='token.txt', mode='a') as file:
            await file.write(f'\nTOKEN={response["account_hash"]}')
            print(f'create account hash - {response["account_hash"]} in txt file')
        writer.close()
        await writer.wait_closed()

def send_nickname(host, port, entry):
    nickname = entry.get()
    if nickname:
        asyncio.run(register(host, port, nickname))
        messagebox.showwarning('Регистрация прошла', f'Пользователь {nickname} успешно зарегестрирован.')
    else:
        messagebox.showwarning('Предупреждение', 'Пожалуйста, введите никнейм')


def draw(host, port):
    root = tk.Tk()
    root.title('Регистрация в Чате')
    root.geometry("300x150")

    label = tk.Label(root, text="Введите ваш никнейм:")
    label.pack(pady=10)

    entry = tk.Entry(root, width=30)
    entry.pack(pady=5)

    button = tk.Button(
        root, text="Зарегестрироваться", command= lambda: send_nickname(host, port, entry)
    )
    button.pack(pady=10)

    root.mainloop()



def main():
    env = Env()
    env.read_env()
    connection_host = env.str('HOST')
    writer_port = env.str('WRITER_PORT')
    draw(connection_host, writer_port)


if __name__ == '__main__':
    try:
      main()
    except (TkAppClosed, KeyboardInterrupt):
        sys.exit(0)
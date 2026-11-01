"""Log in once with the QVAC session and print your channels with their ids.

Use the id of the output channel as TARGET_CHANNEL in .env.
"""

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()


async def main():
    tg = TelegramClient(os.getenv("TG_SESSION", "qvac_session"),
                        int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    await tg.start()
    async for d in tg.iter_dialogs():
        if d.is_channel:
            print(f"{d.id:>16}  {d.name}")
    await tg.disconnect()


asyncio.run(main())

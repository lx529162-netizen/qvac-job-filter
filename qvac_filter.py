"""
Local-AI job filter for Telegram, powered by QVAC.

Listens to a list of Telegram channels, asks a local LLM (running on this
machine through the QVAC SDK) whether each new post is a vacancy for a
Project / Delivery Manager, Scrum Master or Agile Coach, and forwards the
matches to a private channel. No message text leaves the server.
"""

import asyncio
import csv
import logging
import os
import re
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.utils import get_peer_id
from tetherto.qvac_sdk import Client, load_model, unload_model
import tetherto.qvac_sdk.models as qvac_models

from classifier import PROMPT_VERSION, LocalClassifier

load_dotenv()

# ---------- configuration (all secrets live in .env, never in code) ----------
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_NAME = os.getenv("TG_SESSION", "qvac_session")   # must differ from the cloud script's session
TARGET_CHANNEL = os.environ["TARGET_CHANNEL"].strip()
if TARGET_CHANNEL.lstrip("-").isdigit():
    TARGET_CHANNEL = int(TARGET_CHANNEL)  # numeric id of a private channel, not a username
CHANNELS_FILE = os.getenv("CHANNELS_FILE", "channels.txt")
MODEL_NAME = os.getenv("QVAC_MODEL", "QWEN3_4B_INST_Q4_K_M")
CTX_SIZE = int(os.getenv("QVAC_CTX_SIZE", "4096"))
LOG_FILE = os.getenv("LOG_FILE", "decisions.csv")

PRE_FILTER = re.compile(
    r"(project|проджект|менеджер|manager|pm|пм|delivery|scrum|master|agile|coach|"
    r"вакансия|vacancy|job|role|ищем)",
    re.IGNORECASE,
)

def load_channels() -> list:
    if not os.path.exists(CHANNELS_FILE):
        return []
    channels = []
    with open(CHANNELS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                channels.append(int(line))
            except ValueError:
                channels.append(line)
    return channels


def log_decision(chat_id, channel, msg_id, verdict, latency_ms, chars):
    """One CSV row per checked post. Stores no message text."""
    new_file = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["utc_time", "chat_id", "channel", "msg_id", "verdict", "latency_ms", "chars", "model"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    chat_id, channel, msg_id, verdict, latency_ms, chars, f"{MODEL_NAME}/{PROMPT_VERSION}"])


async def main():
    model_src = getattr(qvac_models, MODEL_NAME)
    tg = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    async with Client(config={"loggerLevel": "warn"}) as qvac:
        t = qvac.transport
        print(f"Loading {MODEL_NAME} (first run downloads it)...")
        started = time.perf_counter()
        model_id = await load_model(t, model_src=model_src, model_config={"ctx_size": CTX_SIZE})
        print(f"Model ready in {time.perf_counter() - started:.1f}s")
        clf = LocalClassifier(t, model_id)

        await tg.start()
        await tg.get_dialogs()  # caches private channels so numeric ids like -100... resolve

        async def notify(text):
            try:
                await tg.send_message(TARGET_CHANNEL, f"⚠️ #Ошибки\n\n{text}")
            except Exception as e:
                print(f"Could not send notice: {e}")

        watched: set[int] = set()  # marked ids (-100...) of channels from channels.txt

        async def reload_channels() -> int:
            ids = set()
            for chat in load_channels():
                try:
                    ids.add(get_peer_id(await tg.get_entity(chat)))
                except Exception:
                    pass
            watched.clear()
            watched.update(ids)
            return len(ids)

        async def watch_channels_file():
            """Picks up edits to channels.txt without a restart (checks once a minute)."""
            last = os.path.getmtime(CHANNELS_FILE) if os.path.exists(CHANNELS_FILE) else 0
            while True:
                await asyncio.sleep(60)
                mtime = os.path.getmtime(CHANNELS_FILE) if os.path.exists(CHANNELS_FILE) else 0
                if mtime != last:
                    last = mtime
                    await tg.get_dialogs()
                    count = await reload_channels()
                    await notify(f"🔄 Список каналов обновлён. Слушаю каналов: {count}.")

        if not await reload_channels():
            await notify("Нет доступных каналов. Проверь channels.txt.")
            return

        await notify(f"🚀 QVAC-агент запущен. Модель: {MODEL_NAME}, промт: {PROMPT_VERSION}. Слушаю каналов: {len(watched)}.")
        asyncio.create_task(watch_channels_file())

        @tg.on(events.NewMessage())
        async def handler(event):
            if event.chat_id not in watched:
                return
            message = event.message
            text = message.raw_text
            if not text or not PRE_FILTER.search(text):
                return
            chat = await event.get_chat()
            channel = getattr(chat, "title", None) or str(event.chat_id)
            print(f"Checking msg {message.id} from «{channel}»...", flush=True)
            try:
                verdict, latency_ms, raw = await clf.classify(text)
            except Exception as e:
                log_decision(event.chat_id, channel, message.id, "ERROR", 0, len(text))
                print(f"  ERROR: {e!r}", flush=True)
                await notify(f"Ошибка локальной модели: {e}")
                return
            print(f"  {verdict} in {latency_ms} ms, model said: {raw[:80]!r}", flush=True)
            log_decision(event.chat_id, channel, message.id, verdict, latency_ms, len(text))
            if verdict != "YES":
                return
            try:
                await tg.forward_messages(TARGET_CHANNEL, message)
            except Exception as e:
                if "protected chat" in str(e).lower():
                    await tg.send_message(
                        TARGET_CHANNEL,
                        f"🛡 **Вакансия из защищенного канала «{channel}»:**\n\n{text}",
                    )
                else:
                    await notify(f"Не удалось переслать из «{channel}»:\n{e}")

        try:
            await tg.run_until_disconnected()
        finally:
            # On Ctrl+C / systemctl stop the QVAC worker gets the signal too and may already be gone.
            try:
                await unload_model(t, model_id)
            except Exception:
                pass


if __name__ == "__main__":
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)  # hide worker disconnect noise on shutdown
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")

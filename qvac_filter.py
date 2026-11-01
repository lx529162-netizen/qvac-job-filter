"""
Local-AI job filter for Telegram, powered by QVAC.

Listens to a list of Telegram channels, asks a local LLM (running on this
machine through the QVAC SDK) whether each new post is a vacancy for a
Project / Delivery Manager, Scrum Master or Agile Coach, and forwards the
matches to a private channel. No message text leaves the server.
"""

import asyncio
import csv
import os
import re
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from telethon import TelegramClient, events
from tetherto.qvac_sdk import Client, completion, load_model, unload_model
import tetherto.qvac_sdk.models as qvac_models

load_dotenv()

# ---------- configuration (all secrets live in .env, never in code) ----------
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_NAME = os.getenv("TG_SESSION", "qvac_session")   # must differ from the cloud script's session
TARGET_CHANNEL = os.environ["TARGET_CHANNEL"]
CHANNELS_FILE = os.getenv("CHANNELS_FILE", "channels.txt")
MODEL_NAME = os.getenv("QVAC_MODEL", "QWEN3_4B_INST_Q4_K_M")
CTX_SIZE = int(os.getenv("QVAC_CTX_SIZE", "4096"))
MAX_CHARS = int(os.getenv("MAX_CHARS", "6000"))           # long posts are cut to fit the context window
LOG_FILE = os.getenv("LOG_FILE", "decisions.csv")

PRE_FILTER = re.compile(
    r"(project|проджект|менеджер|manager|pm|пм|delivery|scrum|master|agile|coach|"
    r"вакансия|vacancy|job|role|ищем)",
    re.IGNORECASE,
)

PROMPT = """Проанализируй текст сообщения.
Определи, является ли это актуальной вакансией на позицию Project Manager, Delivery Manager, Scrum Master или Agile Coach.

1. Возможны опечатки или сленг.
2. Это должна быть именно вакансия.
3. Отклоняй вакансии, где роль просто упоминается.
4. ВАЖНО: "Product Manager", "Продукт менеджер", "Продакт", "Data Manager", "Account Manager" — это ДРУГИЕ профессии. Отвечай NO.

Ответь строго одним словом: YES или NO.
Текст: {text}"""


class LocalClassifier:
    """Holds one loaded model and answers YES/NO, one request at a time."""

    def __init__(self, transport, model_id: str):
        self.t = transport
        self.model_id = model_id
        self.lock = asyncio.Lock()  # CPU inference: run requests one by one

    async def classify(self, text: str) -> tuple[str, int]:
        history = [{"role": "user", "content": PROMPT.format(text=text[:MAX_CHARS])}]
        async with self.lock:
            started = time.perf_counter()
            run = completion(
                self.t,
                model_id=self.model_id,
                history=history,
                stream=False,
                generation_params={"temp": 0.1, "predict": 8, "reasoning_budget": 0},
            )
            answer = (await run.text()).strip().upper()
            latency_ms = int((time.perf_counter() - started) * 1000)
        match = re.search(r"\b(YES|NO)\b", answer)
        return (match.group(1) if match else "UNCLEAR"), latency_ms


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
                    chat_id, channel, msg_id, verdict, latency_ms, chars, MODEL_NAME])


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

        async def notify(text):
            try:
                await tg.send_message(TARGET_CHANNEL, f"⚠️ #Ошибки\n\n{text}")
            except Exception as e:
                print(f"Could not send notice: {e}")

        valid = []
        for chat in load_channels():
            try:
                valid.append(await tg.get_entity(chat))
            except Exception:
                pass
        if not valid:
            await notify("Нет доступных каналов. Проверь channels.txt.")
            return

        await notify(f"🚀 QVAC-агент запущен. Модель: {MODEL_NAME}. Слушаю каналов: {len(valid)}.")

        @tg.on(events.NewMessage(chats=valid))
        async def handler(event):
            message = event.message
            text = message.raw_text
            if not text or not PRE_FILTER.search(text):
                return
            chat = await event.get_chat()
            channel = getattr(chat, "title", None) or str(event.chat_id)
            try:
                verdict, latency_ms = await clf.classify(text)
            except Exception as e:
                log_decision(event.chat_id, channel, message.id, "ERROR", 0, len(text))
                await notify(f"Ошибка локальной модели: {e}")
                return
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
            await unload_model(t, model_id)


if __name__ == "__main__":
    asyncio.run(main())

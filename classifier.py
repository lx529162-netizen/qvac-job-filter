"""YES/NO vacancy classifier on a local QVAC model.

Two prompt versions:
- "cloud": the exact prompt the cloud (Claude Haiku) script uses, kept for comparison.
- "local": rewritten for a small local model: English instructions in a system
  message, explicit YES/NO rules, and a few worked examples.
"""

import asyncio
import os
import re
import time

from tetherto.qvac_sdk import completion

MAX_CHARS = int(os.getenv("MAX_CHARS", "6000"))  # long posts are cut to fit the context window

CLOUD_PROMPT = """Проанализируй текст сообщения.
Определи, является ли это актуальной вакансией на позицию Project Manager, Delivery Manager, Scrum Master или Agile Coach.

1. Возможны опечатки или сленг.
2. Это должна быть именно вакансия.
3. Отклоняй вакансии, где роль просто упоминается.
4. ВАЖНО: "Product Manager", "Продукт менеджер", "Продакт", "Data Manager", "Account Manager" — это ДРУГИЕ профессии. Отвечай NO.

Ответь строго одним словом: YES или NO.
Текст: {text}"""

LOCAL_SYSTEM = """You sort Telegram posts for a job seeker. Posts may be in Russian or English, with typos and slang ("проджект", "PM", "пм").

Answer YES if the post is a job vacancy, meaning a company or recruiter is hiring, and the role being hired is one of:
Project Manager, Delivery Manager, Scrum Master, Agile Coach. Any seniority counts, including Junior and Senior.

Answer NO if any of these is true:
- The role being hired is a different profession, for example Product Manager, Продакт, Data Manager, Account Manager, developer, QA, designer.
- A project manager is only mentioned, but the vacancy is for another role.
- The post is not a vacancy: an article, news, a course, an ad, or a person looking for a job.

Reply with exactly one word: YES or NO."""

# Worked examples. Kept different from the posts in eval_prompt.py, so the test is fair.
LOCAL_EXAMPLES = [
    ("Ищем Project Manager в e-commerce, гибрид Варшава, от 2 лет опыта. Резюме в ЛС", "YES"),
    ("Hiring a Senior Product Manager for our payments team, remote EU", "NO"),
    ("Наша команда ищет Scrum Master на проект в банке, удалёнка", "YES"),
    ("Senior Backend Developer (Go). Работа в тесной связке с project manager и дизайнером", "NO"),
    ("Project Manager с 7 годами опыта ищет работу, открыт к предложениям", "NO"),
    ("We're hiring: Delivery Manager (IT outsourcing), full remote", "YES"),
]

PROMPT_VERSION = os.getenv("PROMPT_VERSION", "local")


def build_history(text: str, version: str = PROMPT_VERSION) -> list[dict]:
    text = text[:MAX_CHARS]
    if version == "cloud":
        return [{"role": "user", "content": CLOUD_PROMPT.format(text=text)}]
    history = [{"role": "system", "content": LOCAL_SYSTEM}]
    for post, label in LOCAL_EXAMPLES:
        history += [{"role": "user", "content": post}, {"role": "assistant", "content": label}]
    history.append({"role": "user", "content": text})
    return history


def parse_answer(raw: str) -> str:
    # Qwen3 may emit an (empty) <think>...</think> block before the answer
    answer = re.sub(r"<think>.*?(</think>|$)", "", raw, flags=re.S).strip().upper()
    match = re.search(r"\b(YES|NO)\b", answer)
    return match.group(1) if match else "UNCLEAR"


class LocalClassifier:
    """Holds one loaded model and answers YES/NO, one request at a time."""

    def __init__(self, transport, model_id: str, version: str = PROMPT_VERSION):
        self.t = transport
        self.model_id = model_id
        self.version = version
        self.lock = asyncio.Lock()  # CPU inference: run requests one by one

    async def classify(self, text: str) -> tuple[str, int, str]:
        async with self.lock:
            started = time.perf_counter()
            run = completion(
                self.t,
                model_id=self.model_id,
                history=build_history(text, self.version),
                stream=False,
                generation_params={"temp": 0.1, "predict": 32, "reasoning_budget": 0},
            )
            raw = await run.text()
            latency_ms = int((time.perf_counter() - started) * 1000)
        return parse_answer(raw), latency_ms, raw

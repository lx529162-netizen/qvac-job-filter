"""Acceptance test for the classifier: runs labelled posts through the local model.

Usage:
  .venv/bin/python eval_prompt.py              # both prompt versions
  .venv/bin/python eval_prompt.py local        # one version
  QVAC_MODEL=QWEN3_8B_INST_Q4_K_M .venv/bin/python eval_prompt.py

The posts below are written for testing; none is copied from real channels.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from tetherto.qvac_sdk import Client, load_model, unload_model
import tetherto.qvac_sdk.models as qvac_models

from classifier import LocalClassifier

load_dotenv()

CASES = [
    ("Ищем Project Manager в финтех-команду, remote, опыт от 3 лет. Пишите", "YES"),
    ("Looking for a Project Manager to join our gaming studio. Remote, EU hours. DM me", "YES"),
    ("Вакансия: Agile Coach для трансформации 10 команд, удалённо", "YES"),
    ("Требуется проджект менеджер в веб-студию, зп 2500$", "YES"),
    ("Junior PM в мобильную разработку, обучаем с нуля, офис в Минске", "YES"),
    ("Technical Delivery Manager, EU timezone, B2B contract", "YES"),
    ("Ищем Product Manager в крутую команду, remote, опыт от 5 лет", "NO"),
    ("Ищем Data Manager в аналитический отдел", "NO"),
    ("Account Manager B2B SaaS, Kyiv or remote", "NO"),
    ("Статья: 5 ошибок, которые совершает каждый project manager", "NO"),
    ("QA Engineer на проект. Будете работать с PM и аналитиками", "NO"),
    ("Курс «Project Manager с нуля» — скидка 50% до пятницы", "NO"),
]


async def run(versions: list[str]):
    model_name = os.getenv("QVAC_MODEL", "QWEN3_4B_INST_Q4_K_M")
    async with Client(config={"loggerLevel": "error"}) as qvac:
        t = qvac.transport
        model_id = await load_model(t, model_src=getattr(qvac_models, model_name),
                                    model_config={"ctx_size": int(os.getenv("QVAC_CTX_SIZE", "4096"))})
        for version in versions:
            clf = LocalClassifier(t, model_id, version)
            correct, latencies = 0, []
            print(f"\n=== {model_name}, prompt: {version} ===")
            for text, expected in CASES:
                verdict, ms, _ = await clf.classify(text)
                latencies.append(ms)
                ok = verdict == expected
                correct += ok
                print(f"{'✅' if ok else '❌'} want {expected:3} got {verdict:7} {ms:5} ms  {text[:60]}")
            latencies.sort()
            print(f"Accuracy: {correct}/{len(CASES)}, median {latencies[len(latencies) // 2]} ms")
        await unload_model(t, model_id)


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1:] or ["cloud", "local"]))

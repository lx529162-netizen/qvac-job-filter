"""Acceptance test for the classifier: runs labelled posts through the local model.

Usage:
  .venv/bin/python eval_prompt.py                      # all prompt versions on the synthetic set
  .venv/bin/python eval_prompt.py extract              # one version
  .venv/bin/python eval_prompt.py extract --real eval_real.jsonl
  QVAC_MODEL=QWEN3_8B_INST_Q4_K_M .venv/bin/python eval_prompt.py extract

The synthetic posts below are written for testing; none is copied from real channels.
eval_real.jsonl holds real posts with labels. It is private and git-ignored.
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from tetherto.qvac_sdk import Client, load_model, unload_model
import tetherto.qvac_sdk.models as qvac_models

from classifier import LocalClassifier

load_dotenv()

CASES = [
    # target vacancies
    ("Ищем Project Manager в финтех-команду, remote, опыт от 3 лет. Пишите", "YES"),
    ("Looking for a Project Manager to join our gaming studio. Remote, EU hours. DM me", "YES"),
    ("Вакансия: Agile Coach для трансформации 10 команд, удалённо", "YES"),
    ("Требуется проджект менеджер в веб-студию, зп 2500$", "YES"),
    ("Junior PM в мобильную разработку, обучаем с нуля, офис в Минске", "YES"),
    ("Technical Delivery Manager, EU timezone, B2B contract", "YES"),
    ("#vacancy Project Manager / Business Analyst в студию мобильных игр. Ведение нескольких "
     "проектов от идеи до релиза, работа с требованиями. Удалённо, полная занятость", "YES"),
    ("Свежие вакансии недели:\nFrontend Developer — Lumen\nSenior Project Manager — PayFlow\n"
     "Data Analyst — Orbit", "YES"),
    # found in the one-week comparison: the pre-filter missed these two forms
    ("Руководитель ML-проектов в IT-компанию: портфель AI-проектов, сроки, риски, команда. "
     "Опыт управления IT-проектами от 3 лет", "YES"),
    ("Вакансия Проджект‑менеджер в студию мобильной разработки. Удалённо, полная занятость", "YES"),
    # leadership levels and program, engagement and implementation roles
    ("Hiring: Head of Delivery for a fintech software company. You will run 6 delivery teams "
     "and own client releases. Remote, EU", "YES"),
    ("Ищем PMO Director в IT-компанию: портфель проектов, стандарты управления, отчётность "
     "для правления. Варшава, гибрид", "YES"),
    ("Technical Program Manager for our cloud platform. Coordinate 8 engineering teams "
     "across one roadmap. Remote", "YES"),
    ("Engagement Manager, AI implementations: lead client deployments of our AI platform "
     "from scoping to production. Remote", "YES"),
    ("Szukamy: Kierownik Projektu IT w software house. Wdrożenia systemów dla klientów "
     "z sektora finansowego. Praca hybrydowa, Kraków", "YES"),
    ("Project Marketing Manager in a SaaS company: run product launch campaigns with the "
     "product and sales teams. Remote", "YES"),
    # traps: leadership words without a target role
    ("Head of Product for a fintech app. Own the product vision and roadmap. Remote", "NO"),
    ("Lead Java Developer, Spring and Kafka, 6+ years. Remote, B2B", "NO"),
    ("Head of Sales B2B SaaS, quota-carrying, Warsaw", "NO"),
    ("Kierownik sklepu, sieć handlowa, Warszawa, pełny etat", "NO"),
    ("Affiliate Program Manager (iGaming): grow the partner network, negotiate deals. Remote", "NO"),
    ("Customer Engagement Manager: CRM campaigns, retention and push notifications", "NO"),
    # other professions
    ("Ищем Product Manager в крутую команду, remote, опыт от 5 лет", "NO"),
    ("Ищем Data Manager в аналитический отдел", "NO"),
    ("Account Manager B2B SaaS, Kyiv or remote", "NO"),
    ("QA Engineer на проект. Будете работать с PM и аналитиками", "NO"),
    ("🔥 Ищем менеджера по продажам! Доход от 1500$, процент со сделок, обучение. "
     "Опыт в продажах от полугода. Пиши в ЛС", "NO"),
    ("Senior Backend Engineer (Python, Django). Remote. TLDR: build and scale backend "
     "services of an AI platform. 5+ years of experience, REST, SQL", "NO"),
    ("Affiliate Manager (iGaming), офис или удалёнка, $2000 + KPI. Привлечение партнёров, "
     "переговоры, ведение пула аффилиатов", "NO"),
    # not IT
    ("Требуется руководитель проекта на строительство коттеджного посёлка. Опыт в девелопменте "
     "от 5 лет, полный день", "NO"),
    # not a vacancy
    ("Статья: 5 ошибок, которые совершает каждый project manager", "NO"),
    ("Курс «Project Manager с нуля» — скидка 50% до пятницы", "NO"),
    ("#cv #opentowork Senior Project Manager, 8 лет в IT, Scrum, Kanban, Jira. "
     "Ищу удалённую работу, рассмотрю предложения. TG @example", "NO"),
    ("Вакансия удалена модератором: требования к гражданству не соответствуют правилам чата", "NO"),
]


def load_real(path: str) -> list[tuple[str, str]]:
    with open(path, encoding="utf-8") as f:
        return [(row["text"], row["label"]) for row in map(json.loads, f) if row.get("text")]


async def run(versions: list[str], cases: list[tuple[str, str]], verbose: bool):
    model_name = os.getenv("QVAC_MODEL", "QWEN3_4B_INST_Q4_K_M")
    async with Client(config={"loggerLevel": "error"}) as qvac:
        t = qvac.transport
        model_id = await load_model(t, model_src=getattr(qvac_models, model_name),
                                    model_config={"ctx_size": int(os.getenv("QVAC_CTX_SIZE", "4096"))})
        for version in versions:
            clf = LocalClassifier(t, model_id, version)
            latencies = []
            tp = fp = fn = tn = other = 0
            print(f"\n=== {model_name}, prompt: {version}, {len(cases)} posts ===", flush=True)
            for text, expected in cases:
                verdict, ms, raw = await clf.classify(text)
                latencies.append(ms)
                if verdict == "YES":
                    tp, fp = (tp + 1, fp) if expected == "YES" else (tp, fp + 1)
                elif verdict == "NO":
                    fn, tn = (fn + 1, tn) if expected == "YES" else (fn, tn + 1)
                else:
                    other += 1
                mark = "✅" if verdict == expected else "❌"
                line = f"{mark} want {expected:3} got {verdict:7} {ms:6} ms  {text[:55].replace(chr(10), ' ')}"
                if verbose or verdict != expected:
                    line += f"\n      model: {raw.strip()[:160].replace(chr(10), ' ')}"
                print(line, flush=True)
            latencies.sort()
            print(f"Correct: {tp + tn}/{len(cases)} | vacancies caught: {tp}/{tp + fn} | "
                  f"wrong forwards: {fp} | unclear: {other} | median {latencies[len(latencies) // 2]} ms")
        await unload_model(t, model_id)


if __name__ == "__main__":
    args = sys.argv[1:]
    cases = CASES
    if "--real" in args:
        i = args.index("--real")
        cases = load_real(args[i + 1])
        args = args[:i] + args[i + 2:]
    verbose = "-v" in args
    args = [a for a in args if a != "-v"]
    asyncio.run(run(args or ["cloud", "local", "extract"], cases, verbose))

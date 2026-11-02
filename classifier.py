"""Vacancy classifier on a local QVAC model.

Prompt versions:
- "cloud":   the exact YES/NO prompt the cloud (Claude Haiku) script uses, kept for comparison.
- "local":   a YES/NO prompt rewritten for a small model. Passed a short synthetic test,
             but on real posts it answered YES to almost any job-related post.
- "extract": the model only extracts facts into JSON (post type, roles being hired,
             IT or not), constrained by a JSON schema. Plain code makes the decision.
             This is the default.
"""

import asyncio
import json
import os
import re
import time

from tetherto.qvac_sdk import completion

MAX_CHARS = int(os.getenv("MAX_CHARS", "4000"))  # job titles sit near the top; this keeps prompts small
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "extract")
INCLUDE_DIGESTS = os.getenv("INCLUDE_DIGESTS", "true").lower() == "true"  # lists of several vacancies
REQUIRE_IT = os.getenv("REQUIRE_IT", "true").lower() == "true"            # skip construction PM and similar

# ---------------------------------------------------------------- YES/NO prompts
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

LOCAL_EXAMPLES = [
    ("Ищем Project Manager в e-commerce, гибрид Варшава, от 2 лет опыта. Резюме в ЛС", "YES"),
    ("Hiring a Senior Product Manager for our payments team, remote EU", "NO"),
    ("Наша команда ищет Scrum Master на проект в банке, удалёнка", "YES"),
    ("Senior Backend Developer (Go). Работа в тесной связке с project manager и дизайнером", "NO"),
    ("Project Manager с 7 годами опыта ищет работу, открыт к предложениям", "NO"),
    ("We're hiring: Delivery Manager (IT outsourcing), full remote", "YES"),
]

# ---------------------------------------------------------------- extraction prompt
EXTRACT_SYSTEM = """You read job-board posts from Telegram, in Russian or English, and describe them as JSON. Do not judge whether a post is interesting. Only describe it.

post_type:
- "vacancy": an employer or recruiter is hiring for one role, or a few roles at one company.
- "digest": a list of many vacancies, usually from different companies.
- "resume": a person describes their own experience and is looking for a job (CV, #resume, #cv, #opentowork, "ищу работу", "рассматриваю предложения").
- "other": anything else, for example news, an article, a course, an ad, a moderation notice.

hired_roles: the job titles the employer is hiring for, copied as written in the post. For a digest, list the titles, at most 12. For "resume" and "other", use an empty list.

it_company: true if the job is in IT, software, games, fintech, iGaming, crypto or another tech product. false for construction, real estate, retail, logistics, manufacturing and similar."""

EXTRACT_EXAMPLES = [
    ("#resume Должность: Project Manager. Опыт 6 лет в финтехе, ищу удалённую работу. TG @someone",
     {"post_type": "resume", "hired_roles": [], "it_company": True}),
    ("Ищем Sales Manager в iGaming-проект. ЗП от 2000$, выплаты еженедельно. Пиши @hr_contact",
     {"post_type": "vacancy", "hired_roles": ["Sales Manager"], "it_company": True}),
    ("Вакансия: менеджер проектов на строительство складского комплекса, Варшава, полная занятость",
     {"post_type": "vacancy", "hired_roles": ["менеджер проектов"], "it_company": False}),
    ("Подборка недели:\nSenior Python Developer — Acme\nProject Manager — Beta Soft\nUX Designer — Gamma Labs",
     {"post_type": "digest", "hired_roles": ["Senior Python Developer", "Project Manager", "UX Designer"],
      "it_company": True}),
]

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "post_type": {"type": "string", "enum": ["vacancy", "digest", "resume", "other"]},
        "hired_roles": {"type": "array", "items": {"type": "string", "maxLength": 80}, "maxItems": 12},
        "it_company": {"type": "boolean"},
    },
    "required": ["post_type", "hired_roles", "it_company"],
    "additionalProperties": False,
}

# Target roles, decided in code. Same list as the cloud prompt, plus Russian and slang spellings.
TARGET_ROLE = re.compile(
    r"(project|проджект|проектн\w*|delivery|деливери)[\s/\-\w]{0,20}?(manager|менеджер|lead|лид)"
    r"|менеджер\w*\s+проект\w*"
    r"|руководител\w*\s+проект\w*"
    r"|scrum[\s\-]*master|скрам[\s\-]*мастер"
    r"|agile[\s\-]*coach|аджайл[\s\-]*коуч"
    r"|\bt?pm\b|\bпм\b",
    re.IGNORECASE,
)


def build_history(text: str, version: str = PROMPT_VERSION) -> list[dict]:
    text = text[:MAX_CHARS]
    if version == "cloud":
        return [{"role": "user", "content": CLOUD_PROMPT.format(text=text)}]
    if version == "local":
        history = [{"role": "system", "content": LOCAL_SYSTEM}]
        for post, label in LOCAL_EXAMPLES:
            history += [{"role": "user", "content": post}, {"role": "assistant", "content": label}]
    else:
        history = [{"role": "system", "content": EXTRACT_SYSTEM}]
        for post, facts in EXTRACT_EXAMPLES:
            history += [{"role": "user", "content": post},
                        {"role": "assistant", "content": json.dumps(facts, ensure_ascii=False)}]
    history.append({"role": "user", "content": text})
    return history


def strip_think(raw: str) -> str:
    # Qwen3 may emit an (empty) <think>...</think> block before the answer
    return re.sub(r"<think>.*?(</think>|$)", "", raw, flags=re.S).strip()


def parse_yes_no(raw: str) -> str:
    match = re.search(r"\b(YES|NO)\b", strip_think(raw).upper())
    return match.group(1) if match else "UNCLEAR"


def parse_facts(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", strip_think(raw), flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def decide(facts: dict) -> str:
    """The business rule, in plain code: a vacancy for a target role, in IT."""
    allowed_types = {"vacancy", "digest"} if INCLUDE_DIGESTS else {"vacancy"}
    if facts.get("post_type") not in allowed_types:
        return "NO"
    if REQUIRE_IT and facts.get("it_company") is False:
        return "NO"
    roles = facts.get("hired_roles") or []
    return "YES" if any(TARGET_ROLE.search(str(r)) for r in roles) else "NO"


class LocalClassifier:
    """Holds one loaded model and classifies posts, one request at a time."""

    def __init__(self, transport, model_id: str, version: str = PROMPT_VERSION):
        self.t = transport
        self.model_id = model_id
        self.version = version
        self.lock = asyncio.Lock()  # CPU inference: run requests one by one

    async def classify(self, text: str) -> tuple[str, int, str]:
        """Returns (YES | NO | UNCLEAR, latency in ms, raw model output)."""
        extract = self.version == "extract"
        kwargs = {}
        if extract:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "post_facts", "schema": EXTRACT_SCHEMA},
            }
        async with self.lock:
            started = time.perf_counter()
            run = completion(
                self.t,
                model_id=self.model_id,
                history=build_history(text, self.version),
                stream=False,
                generation_params={"temp": 0.1, "predict": 200 if extract else 32, "reasoning_budget": 0},
                **kwargs,
            )
            raw = await run.text()
            latency_ms = int((time.perf_counter() - started) * 1000)
        if not extract:
            return parse_yes_no(raw), latency_ms, raw
        facts = parse_facts(raw)
        return (decide(facts) if facts else "UNCLEAR"), latency_ms, raw

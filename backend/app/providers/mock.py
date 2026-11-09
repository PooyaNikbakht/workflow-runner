"""Deterministic offline provider. Same inputs, same outputs, no network and no key.

It builds answers from the step context with simple rules, then validates them through the same
pydantic models the Claude adapter uses, so the rest of the app can't tell the difference.
"""

import asyncio
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.models import EmailDraft, PainPoints, ReplyDraft, TicketClassification
from app.providers.base import ProviderError, Task

IMPACT_WORDS = {
    "high": ("hiring", "slipped", "hold times", "400 tickets", "incidents", "different prices"),
    "medium": ("manual", "by hand", "data entry", "shared inbox", "conflict", "sync"),
}


def _impact(text: str) -> str:
    lowered = text.lower()
    for level, words in IMPACT_WORDS.items():
        if any(w in lowered for w in words):
            return level
    return "low"


TITLES: list[tuple[tuple[str, ...], str]] = [
    (("slipped", "turnaround"), "Slow quote turnaround"),
    (("hold times",), "Phone booking bottleneck"),
    (("data entry", "by hand"), "Manual data entry"),
    (("tickets",), "High support volume"),
    (("incident",), "Unreliable integrations"),
    (("prices", "listings"), "Catalog drift across channels"),
    (("conflict", "onboarding"), "Slow client onboarding"),
    (("emails", "inbox"), "Manual email handling"),
    (("hiring",), "Team stretched by repetitive work"),
]


def _title(text: str) -> str:
    lowered = text.lower()
    for words, title in TITLES:
        if any(w in lowered for w in words):
            return title
    return "Growth adding operational load"


def pain_points(ctx: dict[str, Any]) -> dict[str, Any]:
    company = ctx["company"]
    seen: set[str] = set()
    points = []
    for signal in company["signals"]:
        title = _title(signal["text"])
        if title in seen:
            continue
        seen.add(title)
        points.append(
            {
                "title": title,
                "evidence": f"{signal['text']} ({signal['source']})",
                "impact": _impact(signal["text"]),
            }
        )
    order = {"high": 0, "medium": 1, "low": 2}
    points.sort(key=lambda p: order[p["impact"]])
    return {
        "summary": (
            f"{company['name']} is growing, and {points[0]['title'].lower()} is taking up "
            "a lot of the team's time."
        ),
        "pain_points": points[:3],
    }


def email_draft(ctx: dict[str, Any]) -> dict[str, Any]:
    lead, company, pains = ctx["lead"], ctx["company"], ctx["pain_points"]["pain_points"]
    first = lead["name"].split()[0]
    top = pains[0]
    text, _, source = top["evidence"].rpartition(" (")
    source = source.rstrip(")")
    lines = [
        f"Hi {first},",
        "",
        f"Thanks for reaching out. I had a look at {company['name']}, and this line on your "
        f'{source} stood out: "{text}"',
        "",
        "I build small, reliable automations for teams in this spot. A typical first project "
        "takes the repetitive part of the work, drafts the response with AI, and keeps a person "
        "in the loop to approve it before anything goes out.",
    ]
    if len(pains) > 1:
        lines += [
            "",
            f"It could also help with {pains[1]['title'].lower()}, if that's on your list.",
        ]
    cta = "Would a 20 minute call next week work to see if this fits?"
    lines += ["", cta, "", "Best,", "Pooya"]
    return {
        "subject": f"{top['title']} at {company['name']}",
        "body": "\n".join(lines),
        "call_to_action": cta,
    }


CATEGORY_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("billing", ("charge", "charged", "refund", "invoice", "billing", "payment")),
    ("bug", ("error", "not working", "failed", "broken", "hasn't", "crash", "sync")),
    ("account", ("password", "login", "log in", "account", "sso")),
    ("feature_request", ("would be great", "feature", "wish", "could you add")),
    ("how_to", ("how do", "is there a way", "how can", "export")),
]


def classify(ctx: dict[str, Any]) -> dict[str, Any]:
    ticket = ctx["ticket"]
    text = f"{ticket['subject']} {ticket['message']}".lower()
    category, hits = "how_to", 0
    for name, words in CATEGORY_WORDS:
        count = sum(w in text for w in words)
        if count > hits:
            category, hits = name, count
    negative = any(w in text for w in ("frustrat", "second time", "angry", "unacceptable"))
    positive = any(w in text for w in ("thanks for the great", "love", "great product"))
    sentiment = "negative" if negative else "positive" if positive else "neutral"
    urgent = any(w in text for w in ("month end", "asap", "urgent", "down"))
    if urgent or (category in ("billing", "bug") and negative):
        priority = "high"
    elif category in ("billing", "bug") or ticket["plan"] == "business":
        priority = "normal"
    else:
        priority = "low"
    return {
        "category": category,
        "priority": priority,
        "sentiment": sentiment,
        "summary": f"{ticket['customer_name']} wrote about: {ticket['subject'].lower()}.",
        "confidence": min(0.95, 0.6 + 0.12 * hits),
    }


REPLIES = {
    "billing": (
        "I'm sorry about the duplicate charge. I've checked your account and asked our billing "
        "team to refund the extra payment. You'll see it back on your card within 5 to 10 "
        "business days. I've also flagged your account so we can find out why it happened twice."
    ),
    "bug": (
        "Thanks for the details, and sorry for the trouble. I've passed this to our engineering "
        "team with your account info so they can look at the sync logs. In the meantime, you can "
        "import transactions with a CSV file from Settings > Import. I'll update you as soon as "
        "we know more."
    ),
    "account": (
        "Thanks for reaching out. I can help with your account. For security, please confirm the "
        "email address you sign in with and I'll take it from there."
    ),
    "feature_request": (
        "Thanks for the suggestion. I've shared it with our product team and added your vote. "
        "I can't promise a date, but requests like this shape what we build next."
    ),
    "how_to": (
        "Good question. Open Reports, choose the report you need, then use Export > Spreadsheet "
        "in the top right. The file opens in Excel or Google Sheets and is ready to share with "
        "your accountant."
    ),
}


def reply(ctx: dict[str, Any]) -> dict[str, Any]:
    ticket, cls = ctx["ticket"], ctx["classification"]
    first = ticket["customer_name"].split()[0]
    body = f"Hi {first},\n\n{REPLIES[cls['category']]}\n\nBest,\nThe support team"
    return {
        "subject": f"Re: {ticket['subject']}",
        "body": body,
        "internal_note": (
            f"{cls['priority'].capitalize()} priority {cls['category'].replace('_', ' ')} "
            f"ticket from a {ticket['plan']} customer."
        ),
    }


HANDLERS: dict[type[BaseModel], Callable[[dict[str, Any]], dict[str, Any]]] = {
    PainPoints: pain_points,
    EmailDraft: email_draft,
    TicketClassification: classify,
    ReplyDraft: reply,
}


class MockProvider:
    name = "offline"
    model = "offline-mock"

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds

    async def generate[T: BaseModel](self, task: Task[T]) -> T:
        handler = HANDLERS.get(task.output)
        if handler is None:
            raise ProviderError(
                "unsupported", f"No offline answer for {task.output.__name__}.", retryable=False
            )
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return task.output.model_validate(handler(task.context))

"""Workflow definitions. A workflow is an input model plus an ordered list of steps.

The engine knows nothing about leads or tickets: it runs whatever handlers a definition lists.
Adding a workflow means adding a definition here, nothing else.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from app.errors import PermanentError, TransientError
from app.models import (
    CompanyProfile,
    EmailDraft,
    LeadInput,
    PainPoints,
    ReplyDraft,
    TicketClassification,
    TicketInput,
)
from app.providers.base import LLM, Task
from app.webhook import WebhookSender

FIXTURES = Path(__file__).parent / "fixtures"

StepKind = Literal["action", "llm", "review", "webhook"]
Level = Literal["debug", "info", "warn", "error"]


@dataclass
class StepContext:
    run_id: str
    input: dict[str, Any]
    outputs: dict[str, Any]
    attempt: int
    provider: LLM
    webhook: WebhookSender
    log: Callable[..., None]
    delay: float = 0.0

    async def pause(self, factor: float = 1.0) -> None:
        """Demo pacing so a run is watchable. Zero in tests."""
        if self.delay:
            await asyncio.sleep(self.delay * factor)


Handler = Callable[[StepContext], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class StepDef:
    key: str
    title: str
    kind: StepKind
    description: str
    handler: Handler | None = None
    max_attempts: int = 3
    # Review steps: which earlier step's output (a subject and a body) the reviewer works on.
    review_source: str | None = None


@dataclass(frozen=True)
class WorkflowDef:
    key: str
    name: str
    description: str
    input_model: type[BaseModel]
    steps: tuple[StepDef, ...]
    title: Callable[[Any], str]

    def step(self, key: str) -> StepDef:
        for s in self.steps:
            if s.key == key:
                return s
        raise KeyError(key)

    def next_step(self, key: str) -> StepDef | None:
        keys = [s.key for s in self.steps]
        i = keys.index(key)
        return self.steps[i + 1] if i + 1 < len(self.steps) else None


# Shared step builders -----------------------------------------------------------------------


async def run_llm[T: BaseModel](ctx: StepContext, task: Task[T]) -> T:
    ctx.log(f"Calling {ctx.provider.name} ({ctx.provider.model}) for {task.name}", level="debug")
    result = await ctx.provider.generate(task)
    ctx.log(f"Validated output against {task.output.__name__}", level="debug")
    return result


def review_step(source: str, description: str) -> StepDef:
    return StepDef(
        key="review",
        title="Human review",
        kind="review",
        description=description,
        review_source=source,
        max_attempts=1,
    )


def webhook_step(
    event: str, build: Callable[[StepContext], dict[str, Any]], description: str
) -> StepDef:
    async def handler(ctx: StepContext) -> dict[str, Any]:
        await ctx.pause(0.5)
        data = build(ctx)
        key = f"{ctx.run_id}:send"
        ctx.log(f"POST {ctx.webhook.url}", data={"event": event, "idempotency_key": key})
        result = await ctx.webhook.send(event, data, key=key)
        status = result["receiver"].get("status", "ok")
        ctx.log(f"Receiver answered {result['status_code']} ({status})")
        return {"event": event, "idempotency_key": key, **result}

    return StepDef(
        key="send",
        title="Send via webhook",
        kind="webhook",
        description=description,
        handler=handler,
        max_attempts=4,
    )


def approved(ctx: StepContext) -> dict[str, Any]:
    return ctx.outputs["review"]["final"]


@cache
def companies() -> dict[str, CompanyProfile]:
    raw = json.loads((FIXTURES / "companies.json").read_text())
    return {c["domain"]: CompanyProfile.model_validate(c) for c in raw}


@cache
def samples() -> dict[str, list[dict[str, Any]]]:
    return json.loads((FIXTURES / "samples.json").read_text())


# Lead outreach ------------------------------------------------------------------------------

OUTREACH_SYSTEM = (
    "You help a freelance software engineer qualify inbound leads and write first replies. "
    "Use only facts from the input. Write in plain, friendly English with no hype, no "
    "buzzwords and no em dashes."
)


async def lead_intake(ctx: StepContext) -> dict[str, Any]:
    await ctx.pause(0.5)
    lead = LeadInput.model_validate(ctx.input)
    ctx.log(f"Lead {lead.name} <{lead.email}>, company domain {lead.company_domain}")
    return {"lead": lead.model_dump(exclude={"simulate_transient_failure"})}


async def fetch_company(ctx: StepContext) -> dict[str, Any]:
    domain = ctx.outputs["intake"]["lead"]["company_domain"]
    ctx.log(f"Looking up {domain} in the company dataset")
    await ctx.pause()
    if ctx.input.get("simulate_transient_failure") and ctx.attempt == 1:
        raise TransientError("Company info source timed out (simulated transient failure).")
    company = companies().get(domain)
    if company is None:
        raise PermanentError(f"No company info found for {domain}.")
    ctx.log(f"Found {company.name}: {company.industry}, {len(company.signals)} signals")
    return {"company": company.model_dump()}


async def extract_pain_points(ctx: StepContext) -> dict[str, Any]:
    task = Task(
        name="pain point extraction",
        system=OUTREACH_SYSTEM,
        instructions=(
            "List the business problems this company most likely has that software automation "
            "could help with. Ground every point in a specific signal or fact from the input and "
            "quote that fact as evidence. Return at most three points, most important first."
        ),
        output=PainPoints,
        context={
            "lead": ctx.outputs["intake"]["lead"],
            "company": ctx.outputs["fetch_company"]["company"],
        },
    )
    result = await run_llm(ctx, task)
    for p in result.pain_points:
        ctx.log(f"Pain point: {p.title} ({p.impact} impact)")
    return result.model_dump()


async def draft_email(ctx: StepContext) -> dict[str, Any]:
    task = Task(
        name="outreach email",
        system=OUTREACH_SYSTEM,
        instructions=(
            "Write a short first reply to this lead from Pooya, a freelance senior full-stack "
            "engineer. Mention one pain point with its evidence, explain in one or two sentences "
            "how a small automation project could help, and end with a single clear ask. Keep "
            "the body under 150 words. Sign off as Pooya."
        ),
        output=EmailDraft,
        context={
            "lead": ctx.outputs["intake"]["lead"],
            "company": ctx.outputs["fetch_company"]["company"],
            "pain_points": ctx.outputs["pain_points"],
        },
    )
    result = await run_llm(ctx, task)
    ctx.log(f'Drafted "{result.subject}" ({len(result.body.split())} words)')
    return result.model_dump()


def outreach_payload(ctx: StepContext) -> dict[str, Any]:
    lead = ctx.outputs["intake"]["lead"]
    final = approved(ctx)
    return {
        "to": {"name": lead["name"], "email": lead["email"]},
        "subject": final["subject"],
        "body": final["body"],
        "company": ctx.outputs["fetch_company"]["company"]["name"],
    }


LEAD_OUTREACH = WorkflowDef(
    key="lead_outreach",
    name="Lead outreach",
    description=(
        "Qualify an inbound lead, find what the company is struggling with and draft a "
        "personal first reply for a person to approve."
    ),
    input_model=LeadInput,
    title=lambda i: f"{i.name} at {i.company_domain}",
    steps=(
        StepDef("intake", "Lead intake", "action", "Validate and normalize the lead.", lead_intake),
        StepDef(
            "fetch_company",
            "Fetch company info",
            "action",
            "Look the company up in the local dataset. Fails once on purpose to show a retry.",
            fetch_company,
            max_attempts=3,
        ),
        StepDef(
            "pain_points",
            "Extract pain points",
            "llm",
            "LLM call with a structured output schema.",
            extract_pain_points,
        ),
        StepDef("draft_email", "Draft outreach email", "llm", "LLM writes the email.", draft_email),
        review_step("draft_email", "Approve, edit or reject the email before it goes out."),
        webhook_step(
            "lead_outreach.email_approved",
            outreach_payload,
            "Deliver the approved email to the outgoing webhook.",
        ),
    ),
)


# Ticket triage ------------------------------------------------------------------------------

SUPPORT_SYSTEM = (
    "You triage support tickets for a small bookkeeping software company. Be accurate, calm "
    "and kind. Use only facts from the ticket. Never promise refunds or dates you can't "
    "confirm from the input, and don't use em dashes."
)


async def ticket_intake(ctx: StepContext) -> dict[str, Any]:
    await ctx.pause(0.5)
    ticket = TicketInput.model_validate(ctx.input)
    ctx.log(f'Ticket from {ticket.customer_name} ({ticket.plan} plan): "{ticket.subject}"')
    return {"ticket": ticket.model_dump()}


async def classify_ticket(ctx: StepContext) -> dict[str, Any]:
    task = Task(
        name="ticket classification",
        system=SUPPORT_SYSTEM,
        instructions=(
            "Classify this ticket: category, priority, customer sentiment, a one sentence "
            "summary and your confidence from 0 to 1."
        ),
        output=TicketClassification,
        context={"ticket": ctx.outputs["intake"]["ticket"]},
    )
    result = await run_llm(ctx, task)
    ctx.log(
        f"Category {result.category}, priority {result.priority}, sentiment {result.sentiment} "
        f"({result.confidence:.0%} confident)"
    )
    return result.model_dump()


async def suggest_reply(ctx: StepContext) -> dict[str, Any]:
    task = Task(
        name="reply suggestion",
        system=SUPPORT_SYSTEM,
        instructions=(
            "Write a reply to the customer that answers the ticket or explains the next step. "
            "Keep it under 120 words and sign off as The support team. Add a one line internal "
            "note for the team."
        ),
        output=ReplyDraft,
        context={
            "ticket": ctx.outputs["intake"]["ticket"],
            "classification": ctx.outputs["classify"],
        },
    )
    result = await run_llm(ctx, task)
    ctx.log(f'Suggested reply "{result.subject}"')
    return result.model_dump()


def ticket_payload(ctx: StepContext) -> dict[str, Any]:
    ticket = ctx.outputs["intake"]["ticket"]
    final = approved(ctx)
    return {
        "to": {"name": ticket["customer_name"], "email": ticket["email"]},
        "subject": final["subject"],
        "body": final["body"],
        "category": ctx.outputs["classify"]["category"],
        "priority": ctx.outputs["classify"]["priority"],
    }


TICKET_TRIAGE = WorkflowDef(
    key="ticket_triage",
    name="Support ticket triage",
    description="Classify a support ticket, suggest a reply and send it once a person approves.",
    input_model=TicketInput,
    title=lambda i: f"{i.customer_name}: {i.subject}",
    steps=(
        StepDef("intake", "Ticket intake", "action", "Validate the ticket.", ticket_intake),
        StepDef(
            "classify", "Classify", "llm", "Category, priority and sentiment.", classify_ticket
        ),
        StepDef("suggest_reply", "Suggest reply", "llm", "LLM drafts a reply.", suggest_reply),
        review_step("suggest_reply", "Check the reply before it goes to the customer."),
        webhook_step(
            "ticket_triage.reply_approved",
            ticket_payload,
            "Post the approved reply to the outgoing webhook.",
        ),
    ),
)


WORKFLOWS: dict[str, WorkflowDef] = {w.key: w for w in (LEAD_OUTREACH, TICKET_TRIAGE)}

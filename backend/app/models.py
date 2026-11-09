"""Pydantic models: workflow inputs, fixture data and the structured outputs the LLM must return."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address.")
    return value


# Inputs ------------------------------------------------------------------------------------


class LeadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=80)
    email: str
    role: str = Field(default="", max_length=80)
    company_domain: str = Field(min_length=3, max_length=120)
    note: str = Field(default="", max_length=600)
    simulate_transient_failure: bool = True

    _check_email = field_validator("email")(_email)

    @field_validator("company_domain")
    @classmethod
    def _domain(cls, value: str) -> str:
        value = value.lower().removeprefix("https://").removeprefix("http://")
        return value.removeprefix("www.").strip("/")


class TicketInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_name: str = Field(min_length=2, max_length=80)
    email: str
    plan: Literal["free", "team", "business"] = "team"
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=10, max_length=4000)

    _check_email = field_validator("email")(_email)


# Fixture data -----------------------------------------------------------------------------


class Signal(BaseModel):
    source: str
    text: str


class CompanyProfile(BaseModel):
    domain: str
    name: str
    industry: str
    size: str
    location: str
    about: str
    signals: list[Signal]


# LLM outputs ------------------------------------------------------------------------------


class PainPoint(BaseModel):
    title: str = Field(description="Short name for the problem, under 8 words.")
    evidence: str = Field(description="The fact from the company info that points to it.")
    impact: Literal["low", "medium", "high"]


class PainPoints(BaseModel):
    summary: str = Field(description="One sentence on what the company is dealing with.")
    pain_points: list[PainPoint] = Field(min_length=1, max_length=4)


class EmailDraft(BaseModel):
    subject: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=40, max_length=2500)
    call_to_action: str = Field(description="The single ask at the end of the email.")


class TicketClassification(BaseModel):
    category: Literal["billing", "bug", "how_to", "account", "feature_request"]
    priority: Literal["low", "normal", "high", "urgent"]
    sentiment: Literal["negative", "neutral", "positive"]
    summary: str = Field(description="One sentence summary of the customer's issue.")
    confidence: float = Field(ge=0, le=1)


class ReplyDraft(BaseModel):
    subject: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=40, max_length=3000)
    internal_note: str = Field(description="A short note for the support team, not sent.")


# Review -----------------------------------------------------------------------------------


class ReviewEdits(BaseModel):
    subject: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=10, max_length=4000)


class ReviewDecision(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    edits: ReviewEdits | None = None
    note: str = Field(default="", max_length=600)

from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class Payload(BaseModel):
    model_config = ConfigDict(extra="allow")


class SearchRequest(Payload):
    source: Literal["maps", "google", "exhibitions", "websites", "import", "demo"] = "maps"
    country: str
    keywords: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    max_results: int = Field(default=20, ge=1, le=200)
    interval_seconds: float | None = Field(default=None, ge=5, le=3600)
    urls: list[str] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)


class CustomerRequest(Payload):
    customer_id: str


class MarketRequest(Payload):
    source: Literal["imported", "comtrade", "demo"] = "imported"
    hs_codes: list[str] = Field(default_factory=list)


class SelectRequest(Payload):
    country: str


class DraftRequest(Payload):
    customer_id: str
    to: str
    subject: str
    body: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    personalization_notes: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    draft_id: str | None = None
    thread_id: str | None = None
    reply_to: str | None = None
    in_reply_to: str | None = None
    references: str | None = None


class ApprovalRequest(Payload):
    drafts: list[dict[str, Any]]
    confirmed: bool = False


class SyncRequest(Payload):
    max_messages: int = Field(default=100, ge=1, le=500)
    query: str = ""
    page_token: str | None = None
    download_attachments: bool = True


class WhatsAppRequest(Payload):
    customer_id: str
    phone: str
    text: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    personalization_notes: str = ""


class ProfitRequest(Payload):
    business: Literal["bags", "tea"]
    product_id: str | None = None
    proposed_min_margin: str
    suggested_margin: str
    rationale: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class QuoteRequest(Payload):
    product_id: str
    quantity: str
    currency: str
    terms: str
    profit_rule_id: str
    cost_items: list[dict[str, Any]] = Field(default_factory=list)
    fx_rates: dict[str, str] = Field(default_factory=dict)
    required_cost_categories: list[str] = Field(default_factory=list)
    market_comparables: list[dict[str, Any]] = Field(default_factory=list)


class OrderRequest(Payload):
    customer_id: str
    currency: str
    terms: str
    lines: list[dict[str, Any]]
    seller: dict[str, Any] = Field(default_factory=dict)
    buyer: dict[str, Any] = Field(default_factory=dict)


class UpdateRequest(Payload):
    order_id: str
    stage: Literal["contract", "production", "documents", "logistics", "receipts", "aftersales", "reorder"]
    patch: dict[str, Any]
    source: Literal["manual", "email", "external"] = "manual"


class CompleteOAuth(Payload):
    code: str
    state: str | None = None


class RecordsRequest(Payload):
    records: list[dict[str, Any]]


class FollowupRequest(Payload):
    days: int = Field(default=7, ge=1, le=365)

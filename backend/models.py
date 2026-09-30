"""models.py — every structured type that crosses a boundary in the Campus Customs shop.

Three groups:
  * tool results   what a tool hands back to the agent (ProductMatch, ProductDetail, StockCheck, ...)
  * agent I/O      the agent's deps (ShopDeps) and its structured output (ShopReply)
  * HTTP API       what FastAPI sends to / receives from the React front end

The front end only ever renders ProductCard objects that the *backend* builds from SQLite, so
the model can pick which products to show but can never change a price, image or stock number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Catalogue shapes (shared by the REST API and the agent tools)
# ---------------------------------------------------------------------------


class SizeStock(BaseModel):
    """One row of `inventory` for a product."""

    size: str
    quantity: int
    in_stock: bool


class ProductCard(BaseModel):
    """What a product card on the website needs — built from the DB, never by the model."""

    product_id: str
    name: str
    garment_type: str
    category: str = Field(description="Normalised shop category, e.g. 'Hoodies', 'T-Shirts'")
    price: float
    image_url: str
    short_description: str
    colors: list[str]
    total_stock: int
    in_stock: bool


class ProductDetail(ProductCard):
    """Single-item page: the card plus the full description, tags and per-size stock."""

    description: str
    search_tags: list[str]
    sizes: list[SizeStock]


# ---------------------------------------------------------------------------
# Tool results (kept small: the model reads these, so every field costs tokens)
# ---------------------------------------------------------------------------


class ProductMatch(BaseModel):
    """One search hit. Enough to answer 'what do you have?' without a second lookup."""

    product_id: str
    name: str
    category: str
    price: float
    colors: list[str]
    in_stock: bool
    total_stock: int
    short_description: str


class SearchResult(BaseModel):
    query: str
    filters: dict[str, Any]
    total_matches: int = Field(description="Matches before the result cap was applied")
    products: list[ProductMatch]


class ProductInfo(BaseModel):
    """get_product_details result: the full, authoritative record for one product."""

    product_id: str
    name: str
    garment_type: str
    category: str
    price: float
    description: str
    colors: list[str]
    sizes: list[SizeStock]
    total_stock: int


class StockCheck(BaseModel):
    """check_stock result. `requested_*` fields are None when no size was asked for."""

    product_id: str
    name: str
    price: float
    requested_size: Optional[str] = None
    requested_size_quantity: Optional[int] = None
    requested_size_in_stock: Optional[bool] = None
    in_stock_sizes: list[str]
    sold_out_sizes: list[str]
    sizes: list[SizeStock]


class Alternatives(BaseModel):
    """find_alternatives result: what to offer when a product/size is sold out."""

    product_id: str
    name: str
    size: Optional[str]
    other_sizes_in_stock: list[str]
    similar_products_in_stock: list[ProductMatch]


class CustomerInfo(BaseModel):
    """Who is chatting. Only these fields reach the model — never the password hash."""

    user_id: int
    first_name: str
    last_name: str
    email: str


class NotFound(BaseModel):
    """Returned instead of raising so the model can recover (e.g. search by name instead)."""

    error: str
    hint: str


# ---------------------------------------------------------------------------
# Page context + agent deps / output
# ---------------------------------------------------------------------------


class PageContext(BaseModel):
    """What the shopper is looking at when they type — lets 'this' resolve to a product."""

    path: str = "/"
    page: Literal["home", "products", "product", "about", "login", "register", "other"] = "other"
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    selected_size: Optional[str] = None
    visible_product_ids: list[str] = Field(default_factory=list, max_length=24)


@dataclass
class ShopDeps:
    """Per-request dependencies handed to every tool through RunContext."""

    run_id: str
    customer: Optional[CustomerInfo]
    page: PageContext
    # filled in by tools during the run — used by the output validator and the audit trail
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    seen_prices: dict[str, float] = field(default_factory=dict)


class ShopReply(BaseModel):
    """The agent's structured answer. The backend turns product_ids into real cards."""

    message: str = Field(description="What to say to the shopper. Markdown allowed. Keep it short.")
    product_ids: list[str] = Field(
        default_factory=list,
        max_length=12,
        description="Catalogue product_ids to show as cards, best first. Only ids returned by a tool.",
    )
    show_on_page: bool = Field(
        default=False,
        description="True when these products answer a browse/search request and should replace the "
        "results grid on the website. False for a single-item answer shown only in the chat.",
    )
    search_label: Optional[str] = Field(
        default=None, description="Short title for the on-page results, e.g. 'Hoodies' or 'Navy crewnecks under $60'."
    )
    suggestions: list[str] = Field(
        default_factory=list, max_length=3, description="Up to 3 short follow-up questions the shopper might tap."
    )


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)
    product_ids: list[str] = Field(default_factory=list, max_length=12)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    page: PageContext = Field(default_factory=PageContext)
    # guests have no DB history, so the browser sends its recent turns (capped server-side)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


class ChatResponse(BaseModel):
    run_id: str
    reply: str
    products: list[ProductCard]
    show_on_page: bool
    search_label: Optional[str]
    suggestions: list[str]
    stop_reason: str


class ChatMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    products: list[ProductCard]
    created_at: str


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str


class AuthResponse(BaseModel):
    token: str
    user: UserOut

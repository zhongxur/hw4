"""agent.py — the Campus Customs chat agent (PydanticAI) and the one function main.py calls.

    run_chat(message, customer, page, history) -> ChatResponse

Flow for one chat message:
  1. guard_input      redact card numbers / passwords, cap length (before anything reaches the model)
  2. agent.run        system prompt (prompts/prompt.md) + dynamic customer/page context + history,
                      tools from tools.py, structured output ShopReply, UsageLimits loop cap
  3. check_reply      output validator: product ids must be real and every $ amount in the text
                      must be a price a tool actually returned (else ModelRetry)
  4. cards_for        backend turns product_ids into ProductCards from SQLite
  5. audit            every step appended to output/audit_trail.json (append-only)

The model is the course model through the Portkey gateway (PORTKEY_API_KEY in .env).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

import tools
from models import (
    Alternatives,
    ChatResponse,
    ChatTurn,
    CustomerInfo,
    NotFound,
    PageContext,
    ProductInfo,
    SearchResult,
    ShopDeps,
    ShopReply,
    StockCheck,
)

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
PROMPT_PATH = BACKEND_DIR / "prompts" / "prompt.md"
AUDIT_PATH = PROJECT_DIR / "output" / "audit_trail.json"

DEFAULT_MODEL_NAME = "gpt-5.6-luna"
DEFAULT_PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# --- specs / limits ----------------------------------------------------------
REQUEST_LIMIT = 6           # model round-trips per chat message (tool loop cap)
TOOL_CALLS_LIMIT = 8        # tool executions per chat message
OUTPUT_RETRIES = 2          # validator retries before we give up
HISTORY_MESSAGES = 12       # past messages (user+assistant) fed back to the model
HISTORY_CHARS = 1200        # each past message is truncated to this
MAX_INPUT_CHARS = 1000      # longer shopper messages are cut (cost + prompt-injection surface)
REQUEST_TIMEOUT_S = 60      # one HTTP call to the gateway
AUDIT_TEXT_CHARS = 240      # how much of each tool arg/result the audit trail keeps


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def load_env() -> None:
    """.env in hw4/ wins; otherwise walk up (e.g. the course-wide ~/MBA/.env)."""
    for folder in (PROJECT_DIR, *PROJECT_DIR.parents):
        env = folder / ".env"
        if env.is_file():
            load_dotenv(env)
            return
    load_dotenv()


def model_name() -> str:
    return os.environ.get("CAMPUS_MODEL", DEFAULT_MODEL_NAME)


def build_model() -> OpenAIResponsesModel:
    load_env()
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set — copy .env.example to .env and fill it in.")
    client = AsyncOpenAI(
        base_url=os.environ.get("PORTKEY_BASE_URL", DEFAULT_PORTKEY_BASE_URL),
        api_key=key, timeout=REQUEST_TIMEOUT_S, max_retries=1,
        default_headers={"x-portkey-api-key": key, "User-Agent": "hw4-campus-customs/1.0"},
    )
    return OpenAIResponsesModel(model_name(), provider=OpenAIProvider(openai_client=client))


# ---------------------------------------------------------------------------
# Input guardrail (runs before the model sees anything)
# ---------------------------------------------------------------------------
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SECRET_RE = re.compile(r"(?i)\b(password|passcode|pwd|cvv|cvc|security code|pin)\b(\s*(?:is|:|=)\s*)(\S+)")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def guard_input(text: str) -> tuple[str, list[str]]:
    """Returns (cleaned text, list of guardrail notes for the audit trail)."""
    notes: list[str] = []
    text = text.strip()
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]
        notes.append(f"truncated to {MAX_INPUT_CHARS} chars")

    def _card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            notes.append("redacted card number")
            return "[REDACTED CARD NUMBER]"
        return m.group(0)

    text = CARD_RE.sub(_card, text)
    if SECRET_RE.search(text):
        notes.append("redacted secret")
        text = SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    return text, notes


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
def _short(value: Any, n: int = AUDIT_TEXT_CHARS) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    s = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 1] + "…"


def _remember_prices(deps: ShopDeps, result: Any) -> None:
    """Every price a tool shows the model is recorded so the validator can check quoted $ amounts."""
    if isinstance(result, (ProductInfo, StockCheck)):
        deps.seen_prices[result.product_id] = result.price
    elif isinstance(result, SearchResult):
        for p in result.products:
            deps.seen_prices[p.product_id] = p.price
    elif isinstance(result, Alternatives):
        for p in result.similar_products_in_stock:
            deps.seen_prices[p.product_id] = p.price


def _logged(deps: ShopDeps, name: str, args: dict[str, Any], result: Any) -> Any:
    _remember_prices(deps, result)
    deps.tool_log.append({"tool": name, "args": args, "result": _short(result)})
    return result


def build_agent() -> Agent[ShopDeps, ShopReply]:
    agent: Agent[ShopDeps, ShopReply] = Agent(
        build_model(),
        deps_type=ShopDeps,
        output_type=ShopReply,
        instructions=PROMPT_PATH.read_text(encoding="utf-8"),
        retries=OUTPUT_RETRIES,
        name="campus_customs_shop",
    )

    @agent.instructions
    def shopper_context(ctx: RunContext[ShopDeps]) -> str:
        """Dynamic part of the prompt: who is chatting and what page they are on."""
        d = ctx.deps
        if d.customer:
            who = (f"Logged-in customer: {d.customer.first_name} {d.customer.last_name} "
                   f"<{d.customer.email}> (user_id {d.customer.user_id}).")
        else:
            who = "Guest shopper (not logged in) — no account details are available."
        p = d.page
        lines = [f"## Customer\n{who}", "## Page context", f"- path: {p.path} (page type: {p.page})"]
        if p.product_id:
            lines.append(f"- The shopper is viewing product_id `{p.product_id}`"
                         + (f" ({p.product_name})" if p.product_name else "")
                         + ". 'this' / 'it' means this product.")
        if p.selected_size:
            lines.append(f"- Size currently selected on the page: {p.selected_size}")
        if p.visible_product_ids:
            lines.append(f"- Product cards visible on the page (in order): {', '.join(p.visible_product_ids[:12])}")
        lines.append(f"- Today: {datetime.now().strftime('%A %B %d, %Y')}")
        return "\n".join(lines)

    @agent.tool
    def search_products(
        ctx: RunContext[ShopDeps],
        query: str,
        category: Optional[str] = None,
        color: Optional[str] = None,
        max_price: Optional[float] = None,
        size: Optional[str] = None,
        in_stock_only: bool = False,
        limit: int = tools.DEFAULT_SEARCH_RESULTS,
    ) -> SearchResult:
        """Search the Campus Customs catalogue.

        Args:
            query: what the shopper wants in a few words, e.g. "hoodies", "bulldog crewneck", "Morse".
            category: optional exact shop category: Hoodies, Crewnecks, T-Shirts, Quarter-Zips,
                Jackets & Fleece, Long Sleeve.
            color: optional colour filter, e.g. "navy", "gray".
            max_price: optional upper price limit in USD.
            size: optional size (XS, S, M, L, XL, XXL) — only items in stock in that size are returned.
            in_stock_only: drop items with zero stock in every size.
            limit: how many products to return (max 12).
        """
        args = {k: v for k, v in dict(query=query, category=category, color=color, max_price=max_price,
                                      size=size, in_stock_only=in_stock_only, limit=limit).items() if v}
        return _logged(ctx.deps, "search_products", args,
                       tools.search_products(query, category, color, max_price, size, in_stock_only, limit))

    @agent.tool
    def get_product_details(ctx: RunContext[ShopDeps], product: str) -> ProductInfo | NotFound:
        """Full record for one product: price, description, colours and stock for every size.

        Args:
            product: the product_id (preferred) or the product's name.
        """
        return _logged(ctx.deps, "get_product_details", {"product": product}, tools.get_product_info(product))

    @agent.tool
    def check_stock(ctx: RunContext[ShopDeps], product: str, size: Optional[str] = None) -> StockCheck | NotFound:
        """Live stock for one product, per size. quantity 0 = sold out.

        Args:
            product: the product_id (preferred) or the product's name.
            size: optional size the shopper asked about (XS, S, M, L, XL, XXL).
        """
        return _logged(ctx.deps, "check_stock", {"product": product, "size": size}, tools.check_stock(product, size))

    @agent.tool
    def find_alternatives(ctx: RunContext[ShopDeps], product: str, size: Optional[str] = None) -> Alternatives | NotFound:
        """Use when an item (or a size of it) is sold out: returns other in-stock sizes of the same
        item and up to 4 similar in-stock products (in the requested size if one is given).

        Args:
            product: the product_id (preferred) or the product's name.
            size: the size the shopper wants.
        """
        return _logged(ctx.deps, "find_alternatives", {"product": product, "size": size},
                       tools.find_alternatives(product, size))

    @agent.tool
    def get_customer_profile(ctx: RunContext[ShopDeps]) -> CustomerInfo | NotFound:
        """The logged-in shopper's own name and email. Guests get a NotFound."""
        result: CustomerInfo | NotFound = ctx.deps.customer or NotFound(
            error="The shopper is a guest (not logged in).",
            hint="Suggest logging in or creating an account to save chat history.")
        return _logged(ctx.deps, "get_customer_profile", {}, result)

    @agent.tool
    def list_categories(ctx: RunContext[ShopDeps]) -> list[dict[str, Any]]:
        """Shop categories with product counts."""
        return _logged(ctx.deps, "list_categories", {}, tools.categories())

    @agent.output_validator
    def check_reply(ctx: RunContext[ShopDeps], reply: ShopReply) -> ShopReply:
        """Grounding check: no made-up product ids, no $ amounts that no tool returned."""
        known = tools._catalogue_by_id()
        bad = [pid for pid in reply.product_ids if pid not in known]
        if bad:
            raise ModelRetry(f"These product_ids do not exist: {bad}. Only use ids returned by a tool.")
        reply.product_ids = list(dict.fromkeys(reply.product_ids))[:tools.MAX_SEARCH_RESULTS]
        allowed = set(ctx.deps.seen_prices.values()) | {known[pid]["price"] for pid in reply.product_ids}
        quoted = {float(m.replace(",", "")) for m in re.findall(r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)", reply.message)}
        wrong = sorted(q for q in quoted if q not in allowed)
        if wrong:
            # a price limit the shopper asked for ("under $60") is fine if it came from them
            wrong = [q for q in wrong if not re.search(rf"\$\s?{int(q)}\b", ctx.prompt or "")]
        if wrong:
            raise ModelRetry(f"You quoted ${wrong} but no tool returned that price. Quote only prices "
                             f"from tool results (call get_product_details if needed).")
        if reply.show_on_page and not reply.product_ids:
            reply.show_on_page = False
        return reply

    return agent


_AGENT: Optional[Agent[ShopDeps, ShopReply]] = None


def get_agent() -> Agent[ShopDeps, ShopReply]:
    global _AGENT
    if _AGENT is None:
        _AGENT = build_agent()
    return _AGENT


# ---------------------------------------------------------------------------
# History -> PydanticAI messages
# ---------------------------------------------------------------------------
def to_message_history(turns: list[ChatTurn]) -> list[ModelMessage]:
    """Plain text history (DB or browser) becomes alternating request/response messages.
    Shown cards are appended as `[cards shown: ...]` so 'the second one' can be resolved."""
    msgs: list[ModelMessage] = []
    for t in turns[-HISTORY_MESSAGES:]:
        text = t.content[:HISTORY_CHARS]
        if t.role == "user":
            msgs.append(ModelRequest(parts=[UserPromptPart(content=text)]))
        else:
            if t.product_ids:
                text += f"\n[cards shown: {', '.join(t.product_ids)}]"
            msgs.append(ModelResponse(parts=[TextPart(content=text)]))
    # history must start with a request
    while msgs and isinstance(msgs[0], ModelResponse):
        msgs.pop(0)
    return msgs


# ---------------------------------------------------------------------------
# Audit trail (append-only JSON array)
# ---------------------------------------------------------------------------
_AUDIT_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_audit(entries: list[dict[str, Any]]) -> None:
    """Append entries to output/audit_trail.json without rewriting earlier entries.
    The file stays one valid JSON array: we seek to the closing ']' and write before it."""
    if not entries:
        return
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    chunk = ",\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in entries)
    with _AUDIT_LOCK:
        if not AUDIT_PATH.exists() or AUDIT_PATH.stat().st_size < 2:
            AUDIT_PATH.write_text("[\n" + chunk + "\n]\n", encoding="utf-8")
            return
        with open(AUDIT_PATH, "rb+") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            while pos > 0:                      # find the final ']'
                pos -= 1
                f.seek(pos)
                if f.read(1) == b"]":
                    break
            f.seek(pos)
            empty = pos <= 2  # file is "[\n]"
            f.write(((("" if empty else ",\n") + chunk) + "\n]\n").encode("utf-8"))
            f.truncate()


def _events_from_messages(run_id: str, messages: list[ModelMessage]) -> list[dict[str, Any]]:
    """Tool calls / returns / retries of this run, in order, from PydanticAI's message log."""
    events: list[dict[str, Any]] = []
    step = 0
    for m in messages:
        if isinstance(m, ModelResponse):
            step += 1
            for part in m.parts:
                if isinstance(part, ToolCallPart):
                    events.append({"run_id": run_id, "time": m.timestamp.isoformat(timespec="seconds"),
                                   "event": "tool_call", "step": step, "tool": part.tool_name,
                                   "args": _short(part.args_as_dict())})
        elif isinstance(m, ModelRequest):
            for part in m.parts:
                if isinstance(part, ToolReturnPart):
                    events.append({"run_id": run_id, "time": part.timestamp.isoformat(timespec="seconds"),
                                   "event": "tool_result", "step": step, "tool": part.tool_name,
                                   "result": _short(part.content)})
                elif isinstance(part, RetryPromptPart):
                    events.append({"run_id": run_id, "time": part.timestamp.isoformat(timespec="seconds"),
                                   "event": "retry", "step": step, "tool": part.tool_name,
                                   "reason": _short(part.content if isinstance(part.content, str)
                                                    else [e.get("msg") for e in part.content])})
    return events


# ---------------------------------------------------------------------------
# Entry point used by main.py
# ---------------------------------------------------------------------------
BLOCKED_TEXT = ("I can't help with that one — but I'm happy to help you find Campus Customs gear, "
                "check sizes and stock, or answer questions about an item.")
FALLBACK_TEXT = ("Sorry — I got stuck looking that up. Could you try asking again a bit more "
                 "specifically (for example the item name and size)?")


async def run_chat(message: str, customer: Optional[CustomerInfo], page: PageContext,
                   history: list[ChatTurn]) -> ChatResponse:
    run_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    clean, notes = guard_input(message)
    deps = ShopDeps(run_id=run_id, customer=customer, page=page)
    audit: list[dict[str, Any]] = [{
        "run_id": run_id, "time": now_iso(), "event": "user_message", "model": model_name(),
        "user": customer.email if customer else "guest", "page": page.path,
        "product_in_view": page.product_id, "message": _short(clean), "guardrails": notes or None,
        "history_messages": min(len(history), HISTORY_MESSAGES),
    }]
    reply: Optional[ShopReply] = None
    stop_reason = "final_result"
    usage: dict[str, Any] = {}
    new_messages: list[ModelMessage] = []
    try:
        result = await get_agent().run(
            clean, deps=deps, message_history=to_message_history(history),
            usage_limits=UsageLimits(request_limit=REQUEST_LIMIT, tool_calls_limit=TOOL_CALLS_LIMIT),
        )
        reply = result.output
        new_messages = result.new_messages()
        u = result.usage
        usage = {"requests": u.requests, "tool_calls": u.tool_calls,
                 "input_tokens": u.input_tokens, "output_tokens": u.output_tokens}
    except UsageLimitExceeded as exc:
        stop_reason = f"usage_limit: {exc}"
    except Exception as exc:  # gateway down, validator retries exhausted, ...
        if "content_filter" in str(exc) or "content management policy" in str(exc) or "filtered" in str(exc):
            # the gateway's own safety filter (e.g. jailbreak detection) blocked the prompt
            stop_reason = "blocked: gateway content filter"
            reply = ShopReply(message=BLOCKED_TEXT, suggestions=["What hoodies do you have?"])
        else:
            stop_reason = f"error: {type(exc).__name__}: {_short(str(exc), 160)}"

    if new_messages:
        audit.extend(_events_from_messages(run_id, new_messages))
    else:  # failed run: still record what the tools did
        audit.extend({"run_id": run_id, "time": now_iso(), "event": "tool_call+result", **t}
                     for t in deps.tool_log)

    if reply is None:
        reply = ShopReply(message=FALLBACK_TEXT)
    cards = tools.cards_for(reply.product_ids)
    audit.append({
        "run_id": run_id, "time": now_iso(), "event": "final", "stop_reason": stop_reason,
        "reply": _short(reply.message), "product_ids": reply.product_ids,
        "show_on_page": reply.show_on_page, "usage": usage or None,
        "duration_s": round(time.perf_counter() - started, 2),
    })
    append_audit(audit)
    return ChatResponse(run_id=run_id, reply=reply.message, products=cards,
                        show_on_page=reply.show_on_page, search_label=reply.search_label,
                        suggestions=reply.suggestions, stop_reason=stop_reason)

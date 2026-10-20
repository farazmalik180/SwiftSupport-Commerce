"""Custom agentic tools backed by the mock CSV datasets.

All tools are plain Python functions that take and return strings, never raise,
and return helpful messages so the LLM can recover (e.g. ask the user again).
"""
from __future__ import annotations

import csv
import math
import re
from datetime import date
from typing import Dict, List, Tuple

from app import config

Row = Dict[str, str]

_STOP_WORDS = {
    "a", "an", "the", "i", "me", "my", "for", "to", "of", "and", "or", "with",
    "do", "you", "have", "any", "is", "are", "want", "need", "looking", "show",
    "some", "please", "in", "on", "get", "buy", "find", "that", "this", "it",
    "under", "below", "less", "than", "cheap", "budget", "max", "up",
}
_SYNONYMS = {
    "headphone": ["earbud"], "earbud": ["headphone"], "earphone": ["earbud", "headphone"],
    "shoe": ["sneaker", "boot"], "sneaker": ["shoe"], "sofa": ["chair"],
    "watch": ["smartwatch", "wearable"], "tracker": ["watch"],
}
_FIELD_WEIGHTS = {"name": 3.0, "category": 2.0, "description": 1.0}
_TERMINAL_STATUSES = {"Cancelled", "Returned"}


# --------------------------------------------------------------------------- #
# Data helpers
# --------------------------------------------------------------------------- #
def _read_csv(path) -> List[Row]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith(("ses", "xes", "ches", "shes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _tokenize(text: str) -> List[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower())]


def _normalize_order_id(raw: str) -> str:
    """Accept 'ORD-10001', 'ord10001', '10001', ' #10001 ' -> 'ORD-10001'."""
    digits = re.findall(r"\d+", raw or "")
    return f"ORD-{digits[0]}" if digits else (raw or "").strip().upper()


def _format_product(p: Row) -> str:
    stock = int(p["stock"]) if p["stock"].isdigit() else 0
    if stock == 0:
        availability = "OUT OF STOCK"
    elif stock <= 10:
        availability = f"Low stock ({stock} left)"
    else:
        availability = f"In stock ({stock})"
    return (
        f"- [{p['id']}] {p['name']} | {p['category']} | ${float(p['price']):.2f} | "
        f"{availability}\n  {p['description']}"
    )


# --------------------------------------------------------------------------- #
# Tool 1: catalog search
# --------------------------------------------------------------------------- #
def search_catalog(query: str) -> str:
    """Keyword (TF-IDF style) search across products.csv.

    Supports price hints such as "headphones under 100". Returns up to 5 matches.
    """
    try:
        if not query or not query.strip():
            return "Error: empty search query. Ask the customer what they are looking for."
        products = _read_csv(config.PRODUCTS_CSV)

        max_price = None
        m = re.search(r"(?:under|below|less than|max|up to|<)\s*\$?(\d+(?:\.\d+)?)", query.lower())
        if m:
            max_price = float(m.group(1))

        q_tokens = [t for t in _tokenize(query) if t not in _STOP_WORDS and not t.isdigit()]
        if not q_tokens and max_price is None:
            return "No usable keywords in the query. Ask the customer for a product type or category."

        q_tokens = q_tokens + [s for t in q_tokens for s in _SYNONYMS.get(t, []) if s not in q_tokens]

        # Pre-tokenize fields and compute IDF.
        docs: List[Dict[str, set]] = []
        for p in products:
            docs.append({f: set(_tokenize(p[f])) for f in _FIELD_WEIGHTS})
        n = len(products)
        idf = {}
        for tok in set(q_tokens):
            df = sum(1 for d in docs if any(tok in d[f] for f in _FIELD_WEIGHTS))
            idf[tok] = math.log((n + 1) / (df + 1)) + 1.0

        scored: List[Tuple[float, Row]] = []
        for p, d in zip(products, docs):
            if max_price is not None and float(p["price"]) > max_price:
                continue
            score = 0.0
            for tok in q_tokens:
                for field, weight in _FIELD_WEIGHTS.items():
                    if tok in d[field]:
                        score += weight * idf[tok]
                    elif len(tok) >= 4 and any(w.startswith(tok) for w in d[field]):
                        score += 0.5 * weight * idf[tok]
            if score > 0 or (not q_tokens and max_price is not None):
                scored.append((score, p))

        if not scored:
            cats = sorted({p["category"] for p in products})
            hint = f" within ${max_price:.0f}" if max_price is not None else ""
            return (
                f"No products matched '{query}'{hint}. Available categories: "
                f"{', '.join(cats)}. Suggest a related category or ask to rephrase."
            )

        scored.sort(key=lambda s: (-s[0], -int(s[1]["stock"] or 0)))
        top = [p for _, p in scored[:5]]
        return f"Found {len(scored)} match(es); showing top {len(top)}:\n" + "\n".join(
            _format_product(p) for p in top
        )
    except FileNotFoundError:
        return "Error: product catalog is unavailable right now. Apologise and try again later."
    except Exception as exc:  # noqa: BLE001 - tools must never crash the agent
        return f"Error: catalog search failed ({type(exc).__name__}). Try rephrasing the query."


# --------------------------------------------------------------------------- #
# Tool 2: order status
# --------------------------------------------------------------------------- #
def _find_order(order_id: str) -> Row | None:
    oid = _normalize_order_id(order_id)
    for row in _read_csv(config.ORDERS_CSV):
        if row["order_id"].upper() == oid:
            return row
    return None


def _product_name(product_id: str) -> str:
    for p in _read_csv(config.PRODUCTS_CSV):
        if p["id"] == product_id:
            return p["name"]
    return product_id


def check_order_status(order_id: str) -> str:
    """Look up an order in orders.csv and describe its status."""
    try:
        if not order_id or not order_id.strip():
            return "Error: no order ID provided. Ask the customer for their order ID (format ORD-12345)."
        order = _find_order(order_id)
        if order is None:
            return (
                f"Order '{order_id}' was not found. Ask the customer to double-check the order ID "
                "(format ORD-12345, found in their confirmation email)."
            )
        tracking = order["tracking_number"] or "not assigned yet"
        return (
            f"Order {order['order_id']}: {_product_name(order['product_id'])} "
            f"(product {order['product_id']}) | customer {order['customer_id']} | "
            f"purchased {order['purchase_date']} | status: {order['status']} | tracking: {tracking}"
        )
    except FileNotFoundError:
        return "Error: order database is unavailable right now. Apologise and try again later."
    except Exception as exc:  # noqa: BLE001
        return f"Error: order lookup failed ({type(exc).__name__}). Ask the customer to retry."


# --------------------------------------------------------------------------- #
# Tool 3: refund eligibility (+ mock refund processing)
# --------------------------------------------------------------------------- #
def _evaluate_refund(order: Row) -> Tuple[str, str]:
    """Return (decision, reason). decision in {'Approved', 'Denied', 'Not Yet Eligible'}."""
    status = order["status"]
    window = config.RETURN_WINDOW_DAYS
    try:
        purchased = date.fromisoformat(order["purchase_date"])
    except ValueError:
        return "Denied", "The purchase date on record is invalid; escalate to a human agent."
    age = (config.today() - purchased).days

    if status == "Delivered":
        if age <= window:
            return "Approved", f"Delivered order is {age} day(s) old, within the {window}-day return window."
        return "Denied", (
            f"Delivered order is {age} days old, beyond the {window}-day return window. "
            "Policy: items outside the window can only be refunded if defective (escalate to a human agent)."
        )
    if status in ("Processing", "Shipped"):
        return "Not Yet Eligible", (
            f"Order is still '{status}'. Policy: refunds apply after delivery. "
            + ("It can still be cancelled before shipping." if status == "Processing"
               else "Once delivered, the customer may return it within the window, or refuse delivery.")
        )
    if status == "Cancelled":
        return "Denied", "Order was cancelled, so the customer was not charged. No refund is needed."
    if status == "Returned":
        return "Denied", "This order was already returned and refunded; it cannot be refunded again."
    return "Denied", f"Unknown order status '{status}'; escalate to a human agent."


def calculate_refund_eligibility(order_id: str) -> str:
    """Decide refund eligibility from order status and purchase date (30-day policy)."""
    try:
        if not order_id or not order_id.strip():
            return "Error: no order ID provided. Ask the customer for their order ID (format ORD-12345)."
        order = _find_order(order_id)
        if order is None:
            return (
                f"Order '{order_id}' was not found, so eligibility cannot be determined. "
                "Ask the customer to confirm the order ID."
            )
        decision, reason = _evaluate_refund(order)
        return f"{decision}: {reason} (order {order['order_id']}, status {order['status']}, purchased {order['purchase_date']})"
    except FileNotFoundError:
        return "Error: order database is unavailable right now. Apologise and try again later."
    except Exception as exc:  # noqa: BLE001
        return f"Error: eligibility check failed ({type(exc).__name__}). Ask the customer to retry."


def process_refund(order_id: str) -> str:
    """Process a MOCK refund. Only succeeds when eligibility is 'Approved'."""
    try:
        if not order_id or not order_id.strip():
            return "Error: no order ID provided. Ask the customer for their order ID."
        order = _find_order(order_id)
        if order is None:
            return f"Order '{order_id}' was not found. Ask the customer to confirm the order ID."
        decision, reason = _evaluate_refund(order)
        if decision != "Approved":
            return f"Refund NOT processed. {decision}: {reason}"
        price = next((p["price"] for p in _read_csv(config.PRODUCTS_CSV) if p["id"] == order["product_id"]), "0")
        ref = f"RF-{order['order_id'].split('-')[-1]}"
        return (
            f"Refund processed (mock). Reference {ref}: ${float(price):.2f} will return to the original "
            "payment method in 5-7 business days. Next step: customer ships item back using the prepaid label."
        )
    except Exception as exc:  # noqa: BLE001
        return f"Error: refund processing failed ({type(exc).__name__}). Escalate to a human agent."

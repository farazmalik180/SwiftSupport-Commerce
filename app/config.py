"""Centralised configuration and environment loading."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PRODUCTS_CSV = DATA_DIR / "products.csv"
ORDERS_CSV = DATA_DIR / "orders.csv"

load_dotenv(ROOT_DIR / ".env")

RETURN_WINDOW_DAYS = 30
DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_FALLBACK_MODEL = "openai/gpt-oss-20b"


def get_api_key() -> str | None:
    """Return GROQ_API_KEY from the environment (.env or host secrets)."""
    key = os.getenv("GROQ_API_KEY", "").strip()
    if key and key != "your_groq_api_key_here":
        return key
    return None


def get_model() -> str:
    return os.getenv("GROQ_MODEL", DEFAULT_MODEL)


def get_fallback_model() -> str:
    return os.getenv("GROQ_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)


def today() -> date:
    """Current date, optionally pinned via REFERENCE_DATE (YYYY-MM-DD)."""
    pinned = os.getenv("REFERENCE_DATE", "").strip()
    if pinned:
        try:
            return date.fromisoformat(pinned)
        except ValueError:
            pass
    return date.today()

"""Customer authentication (mock): customer ID + PIN, PBKDF2-hashed, with brute-force lockout.

Demo credentials are documented in the README. Replace this module with a real identity
provider (OAuth/SSO, session tokens) before using real customer data.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app import config

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300
_PBKDF2_ROUNDS = 120_000

# customer_id -> (failed_count, first_failure_monotonic_time)
_failures: Dict[str, Tuple[int, float]] = {}


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str


def normalize_customer_id(raw: str) -> str:
    """Accept 'CUST-001', 'cust001', '1' -> 'CUST-001'."""
    digits = re.findall(r"\d+", raw or "")
    return f"CUST-{int(digits[0]):03d}" if digits else (raw or "").strip().upper()


def hash_pin(customer_id: str, pin: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), customer_id.encode(), _PBKDF2_ROUNDS).hex()


def _load() -> Dict[str, dict]:
    with open(config.CUSTOMERS_CSV, newline="", encoding="utf-8") as fh:
        return {r["customer_id"]: r for r in csv.DictReader(fh)}


def is_locked(customer_id: str) -> bool:
    count, first = _failures.get(customer_id, (0, 0.0))
    if count >= MAX_FAILED_ATTEMPTS:
        if time.monotonic() - first < LOCKOUT_SECONDS:
            return True
        _failures.pop(customer_id, None)
    return False


def authenticate(customer_id: str, pin: str) -> Optional[Customer]:
    """Return the Customer on success, else None. Never reveals which part was wrong."""
    cid = normalize_customer_id(customer_id)
    if not cid or is_locked(cid):
        return None
    try:
        record = _load().get(cid)
    except FileNotFoundError:
        return None
    # Always hash, so unknown IDs and wrong PINs take the same time.
    candidate = hash_pin(cid, (pin or "").strip())
    expected = record["pin_hash"] if record else "0" * 64
    if record and hmac.compare_digest(candidate, expected):
        _failures.pop(cid, None)
        return Customer(cid, record["name"])
    count, first = _failures.get(cid, (0, time.monotonic()))
    _failures[cid] = (count + 1, first)
    return None


def get_name(customer_id: str) -> str:
    try:
        record = _load().get(customer_id)
        return record["name"] if record else "Customer"
    except FileNotFoundError:
        return "Customer"

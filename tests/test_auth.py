"""Offline tests for authentication and customer-scoped access. Run: pytest"""
import pytest

from app import auth


@pytest.fixture(autouse=True)
def clear_failures():
    auth._failures.clear()
    yield
    auth._failures.clear()


def test_login_success():
    c = auth.authenticate("CUST-001", "1001")
    assert c and c.customer_id == "CUST-001" and c.name


def test_id_normalisation():
    assert auth.authenticate("cust001", "1001").customer_id == "CUST-001"
    assert auth.authenticate("2", "1002").customer_id == "CUST-002"


def test_wrong_pin_and_unknown_user_rejected():
    assert auth.authenticate("CUST-001", "9999") is None
    assert auth.authenticate("CUST-999", "1001") is None
    assert auth.authenticate("", "") is None


def test_pin_of_another_customer_rejected():
    assert auth.authenticate("CUST-001", "1002") is None


def test_lockout_after_repeated_failures():
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        assert auth.authenticate("CUST-003", "0000") is None
    assert auth.is_locked("CUST-003")
    # Even the correct PIN is refused while locked.
    assert auth.authenticate("CUST-003", "1003") is None


def test_pins_are_not_stored_in_plain_text():
    from app import config

    raw = config.CUSTOMERS_CSV.read_text(encoding="utf-8")
    assert "1001" not in raw.replace(auth.hash_pin("CUST-001", "1001"), "")

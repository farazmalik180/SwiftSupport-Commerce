"""Offline unit tests for the tools (no API key needed). Run: pytest"""
import pytest

from app import config, tools


@pytest.fixture(autouse=True)
def pin_date(monkeypatch):
    monkeypatch.setenv("REFERENCE_DATE", "2026-10-21")


def test_search_keyword():
    assert "AuraBeat" in tools.search_catalog("wireless headphones")


def test_search_price_filter():
    out = tools.search_catalog("headphones under 100")
    assert "AuraBeat" not in out and "PulseBuds" in out


def test_search_out_of_stock_flagged():
    assert "OUT OF STOCK" in tools.search_catalog("office chair")


def test_search_no_match_and_empty():
    assert "No products matched" in tools.search_catalog("submarine")
    assert tools.search_catalog("   ").startswith("Error")


def test_order_found_and_normalised():
    assert "Delivered" in tools.check_order_status("ORD-10001")
    assert "ORD-10001" in tools.check_order_status("10001")


def test_order_not_found():
    assert "not found" in tools.check_order_status("ORD-99999")


@pytest.mark.parametrize(
    "order_id,expected",
    [
        ("ORD-10001", "Approved"),        # delivered, 9 days
        ("ORD-10014", "Approved"),        # delivered, exactly 30 days
        ("ORD-10005", "Denied"),          # delivered, 52 days
        ("ORD-10002", "Not Yet Eligible"),  # shipped
        ("ORD-10010", "Denied"),          # cancelled
        ("ORD-10016", "Denied"),          # already returned
    ],
)
def test_refund_eligibility(order_id, expected):
    assert tools.calculate_refund_eligibility(order_id).startswith(expected)


def test_refund_unknown_order():
    assert "not found" in tools.calculate_refund_eligibility("ORD-00000")


def test_process_refund():
    assert "Refund processed" in tools.process_refund("ORD-10001")
    assert "NOT processed" in tools.process_refund("ORD-10005")


def test_data_files_exist():
    assert config.PRODUCTS_CSV.exists() and config.ORDERS_CSV.exists()

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
    assert "Delivered" in tools.check_order_status("ORD-10001", "CUST-001")
    assert "ORD-10001" in tools.check_order_status("10001", "CUST-001")


def test_order_not_found():
    assert "not found" in tools.check_order_status("ORD-99999", "CUST-001")


def test_other_customers_order_is_hidden():
    # ORD-10002 belongs to CUST-002; CUST-001 must get the same reply as for a missing order.
    foreign = tools.check_order_status("ORD-10002", "CUST-001")
    assert "not found" in foreign and "TRK564738291US" not in foreign
    assert "not found" in tools.calculate_refund_eligibility("ORD-10002", "CUST-001")
    assert "not found" in tools.process_refund("ORD-10001", "CUST-002")


def test_unauthenticated_access_denied():
    for fn in (tools.check_order_status, tools.calculate_refund_eligibility, tools.process_refund):
        assert "not authenticated" in fn("ORD-10001")
        assert "not authenticated" in fn("ORD-10001", "")


@pytest.mark.parametrize(
    "order_id,customer,expected",
    [
        ("ORD-10001", "CUST-001", "Approved"),          # delivered, 9 days
        ("ORD-10014", "CUST-005", "Approved"),          # delivered, exactly 30 days
        ("ORD-10005", "CUST-004", "Denied"),            # delivered, 52 days
        ("ORD-10002", "CUST-002", "Not Yet Eligible"),  # shipped
        ("ORD-10010", "CUST-007", "Denied"),            # cancelled
        ("ORD-10016", "CUST-006", "Denied"),            # already returned
    ],
)
def test_refund_eligibility(order_id, customer, expected):
    assert tools.calculate_refund_eligibility(order_id, customer).startswith(expected)


def test_refund_unknown_order():
    assert "not found" in tools.calculate_refund_eligibility("ORD-00000", "CUST-001")


def test_process_refund():
    assert "Refund processed" in tools.process_refund("ORD-10001", "CUST-001")
    assert "NOT processed" in tools.process_refund("ORD-10005", "CUST-004")


def test_data_files_exist():
    assert config.PRODUCTS_CSV.exists() and config.ORDERS_CSV.exists()

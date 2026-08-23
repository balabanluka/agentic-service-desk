from service_desk.data.repository import BusinessRepository
from service_desk.tools.business import BusinessTools


def test_get_customer_returns_synthetic_customer() -> None:
    tools = BusinessTools(BusinessRepository.from_default_seed())

    customer = tools.get_customer("cus_orbit_001")

    assert customer is not None
    assert customer.company == "Orbit & Pine"


def test_get_customer_returns_none_when_missing() -> None:
    tools = BusinessTools(BusinessRepository.from_default_seed())

    assert tools.get_customer("cus_unknown_999") is None


def test_subscription_and_invoice_have_consistent_synthetic_data() -> None:
    tools = BusinessTools(BusinessRepository.from_default_seed())

    subscription = tools.get_subscription("cus_orbit_001")
    invoice = tools.get_invoice("inv_orbit_1002")

    assert subscription is not None
    assert invoice is not None
    assert invoice.id in subscription.invoice_ids
    assert invoice.customer_id == subscription.customer_id


def test_list_tickets_returns_empty_tuple_for_unknown_customer() -> None:
    tools = BusinessTools(BusinessRepository.from_default_seed())

    assert tools.list_tickets("cus_unknown_999") == ()

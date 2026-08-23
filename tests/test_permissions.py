from service_desk.ai.gateway import ToolCall
from service_desk.data.repository import BusinessRepository
from service_desk.graph.workflows.permissions import ScopedToolExecutor
from service_desk.tools.business import BusinessTools


def test_billing_exposes_only_its_allowlisted_read_only_tools() -> None:
    executor = ScopedToolExecutor(
        BusinessTools(BusinessRepository.from_default_seed()), "cus_orbit_001", "billing"
    )

    assert set(executor.allowed_names) == {"get_customer", "get_subscription", "get_invoice"}
    assert {definition["name"] for definition in executor.definitions} == set(executor.allowed_names)


def test_workflow_cannot_read_an_invoice_owned_by_another_customer() -> None:
    executor = ScopedToolExecutor(
        BusinessTools(BusinessRepository.from_default_seed()), "cus_orbit_001", "billing"
    )

    result, record = executor.execute(
        ToolCall(name="get_invoice", arguments={"invoice_id": "inv_willow_2001"})
    )

    assert result.status == "denied"
    assert result.content["reason"] == "invoice_not_owned_by_customer"
    assert record == {"name": "get_invoice", "status": "denied"}


def test_no_argument_tools_reject_model_supplied_extra_arguments() -> None:
    executor = ScopedToolExecutor(
        BusinessTools(BusinessRepository.from_default_seed()), "cus_orbit_001", "support"
    )

    result, record = executor.execute(ToolCall(name="list_tickets", arguments={"limit": 100}))

    assert result.status == "invalid_arguments"
    assert record == {"name": "list_tickets", "status": "invalid_arguments"}

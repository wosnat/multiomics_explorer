import pytest
from tests.integration.test_mcp_tools import tool_fns, _ctx_with_conn  # noqa: F401
from tests.unit.test_tool_wrappers import EXPECTED_TOOLS
from tests.integration.edge_cases import invariants as inv
from tests.integration.edge_cases.scenarios import SCENARIO_BUILDERS

# Tools with no meaningful degenerate entity input (pure schema / static
# echo / raw escape hatch). Each exemption is justified inline.
_EXEMPT = {
    "kg_schema",           # static schema dump, no entity input
    "kg_release_info",     # release identity, no entity input
    "run_cypher",          # raw escape hatch, arbitrary query
    "list_filter_values",  # static categorical lists, no entity input
}


def test_every_tool_has_edge_scenarios():
    """Coverage gate: every registered tool must have edge-case scenarios
    (or be explicitly exempted). Mirrors the EXPECTED_TOOLS registration gate
    so corner-case coverage cannot silently lapse when a tool is added."""
    covered = set(SCENARIO_BUILDERS) | _EXEMPT
    missing = set(EXPECTED_TOOLS) - covered
    assert not missing, f"tools missing edge-case scenarios: {sorted(missing)}"

_CASES = [
    (tool, sc)
    for tool, builder in SCENARIO_BUILDERS.items()
    for sc in builder()
]


@pytest.mark.kg
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,scenario",
    _CASES,
    ids=[f"{t}-{sc.label}" for t, sc in _CASES],
)
async def test_tool_edge_case_contract(tool_name, scenario, tool_fns, conn):
    ctx = _ctx_with_conn(conn)
    fn = tool_fns[tool_name]

    if scenario.expects_error is not None:
        with pytest.raises(scenario.expects_error):
            await fn(ctx, **scenario.kwargs)
        return

    # No documented error => must not raise (crash-freedom invariant).
    resp = await fn(ctx, **scenario.kwargs)

    label = f"{tool_name}:{scenario.label}"
    inv.assert_envelope_invariants(label, resp)
    inv.assert_empty_layer_shape(
        label, resp, offset=scenario.kwargs.get("offset", 0))
    if scenario.input_ids:
        inv.assert_batch_diagnostics(label, resp, scenario.input_ids)

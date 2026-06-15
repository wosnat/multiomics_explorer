import types
import pytest
from tests.integration.edge_cases import invariants as inv


def _resp(**kw):
    return types.SimpleNamespace(**kw)


class TestEnvelopeInvariants:
    def test_passes_on_consistent_empty(self):
        inv.assert_envelope_invariants(
            "t", _resp(results=[], total_matching=0, returned=0, truncated=False))

    def test_flags_returned_mismatch(self):
        with pytest.raises(AssertionError):
            inv.assert_envelope_invariants(
                "t", _resp(results=[1, 2], returned=3, truncated=False,
                           total_matching=3))

    def test_flags_negative_count(self):
        with pytest.raises(AssertionError):
            inv.assert_envelope_invariants("t", _resp(total_matching=-1))


class TestBatchDiagnostics:
    def test_not_found_subset_ok(self):
        inv.assert_batch_diagnostics(
            "t", _resp(not_found=["x"], not_matched=[]), input_ids=["x", "y"])

    def test_not_found_not_in_inputs_fails(self):
        with pytest.raises(AssertionError):
            inv.assert_batch_diagnostics(
                "t", _resp(not_found=["z"], not_matched=[]), input_ids=["x"])

    def test_structured_not_found_skipped(self):
        # Non-list not_found (structured submodel) is skipped, not crashed on.
        inv.assert_batch_diagnostics(
            "t", _resp(not_found=_resp(metabolite_ids=["z"]), not_matched=[]),
            input_ids=["x"])

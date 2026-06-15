"""Structural invariants every tool response must satisfy on any input,
including degenerate ones. Operates on Pydantic wrapper responses."""


def _get(resp, name):
    return getattr(resp, name, None)


def assert_envelope_invariants(label, resp):
    """Assert universal envelope invariants. Skips checks for fields a given
    response model does not declare."""
    results = _get(resp, "results")
    total_matching = _get(resp, "total_matching")
    returned = _get(resp, "returned")
    truncated = _get(resp, "truncated")

    if results is not None:
        assert isinstance(results, list), f"{label}: results not a list"

    # returned == len(results)
    if returned is not None and results is not None:
        assert returned == len(results), (
            f"{label}: returned={returned} != len(results)={len(results)}"
        )

    # counts non-negative
    for cname in ("total_matching", "returned", "total_entries"):
        cval = _get(resp, cname)
        if cval is not None:
            assert cval >= 0, f"{label}: {cname}={cval} < 0"

    # not-truncated => everything matching is on this page
    if truncated is False and total_matching is not None and returned is not None:
        assert returned <= total_matching, (
            f"{label}: not truncated but returned={returned} "
            f"> total_matching={total_matching}"
        )


def assert_batch_diagnostics(label, resp, input_ids):
    """not_found / not_matched (when flat lists) subset of inputs and disjoint."""
    nf = _get(resp, "not_found")
    nm = _get(resp, "not_matched")
    input_set = {str(x).lower() for x in input_ids}

    if isinstance(nf, list):
        for x in nf:
            assert str(x).lower() in input_set, (
                f"{label}: not_found id {x!r} not in inputs"
            )
    if isinstance(nm, list):
        for x in nm:
            assert str(x).lower() in input_set, (
                f"{label}: not_matched id {x!r} not in inputs"
            )
    if isinstance(nf, list) and isinstance(nm, list):
        assert set(map(str, nf)).isdisjoint(map(str, nm)), (
            f"{label}: not_found and not_matched overlap"
        )


def assert_empty_layer_shape(label, resp, offset=0):
    """An empty data layer yields an empty, well-formed envelope — not a crash
    and not a malformed shape. (Crash-freedom is asserted by the call site;
    here we assert the shape is the canonical empty one.)

    Skipped when ``offset`` is non-zero: an empty *page* past the end of a
    populated layer is not an empty *layer* (total_matching is legitimately
    > 0 there).
    """
    if offset:
        return
    results = _get(resp, "results")
    total_matching = _get(resp, "total_matching")
    if results == [] and total_matching is not None:
        assert total_matching == 0, (
            f"{label}: empty results but total_matching={total_matching}"
        )

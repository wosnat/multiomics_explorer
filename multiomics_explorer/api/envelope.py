"""Envelope post-processing shared by the api layer and analysis utilities.

Lives outside `api/functions.py` so `analysis/enrichment.py` can import it
at module top without creating an import cycle (functions.py lazily imports
enrichment inside pathway_enrichment / cluster_enrichment).
"""

BREAKDOWN_CAP = 10


def cap_breakdowns(envelope: dict, keys: tuple[str, ...], *, summary: bool) -> dict:
    """Detail calls carry the first BREAKDOWN_CAP entries of each breakdown list;
    summary=True keeps the full list. Lists are already sorted by count DESC.
    When a list is trimmed, a sibling `<key>_truncated: True` is added."""
    if summary:
        return envelope
    for k in keys:
        v = envelope.get(k)
        if isinstance(v, list) and len(v) > BREAKDOWN_CAP:
            envelope[k] = v[:BREAKDOWN_CAP]
            envelope[f"{k}_truncated"] = True
    return envelope
